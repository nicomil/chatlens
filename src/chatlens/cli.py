"""
Chat text analysis — single entry point.

    chatlens all         merge the data and analyse it
    chatlens merge       merge choices and chat only
    chatlens analyze     text analysis only
    chatlens keys        configure the API keys
    chatlens status      what is in input, in output and among the keys

Commands act on a **workspace**: the folder holding `input/` and `output/`. It
is the current directory unless `--workspace` says otherwise, so the usual way
to work is to change into the experiment's folder and run the command there.

The files to analyse go in `input/`: they are recognised by name, not passed on
the command line. Everything produced lands in `output/`.

Examples:

    chatlens all                                  automatic measures
    chatlens all --llm --llm-replicates 2         + validation rubric
    chatlens --workspace ~/studies/ultimatum all  another experiment
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from chatlens.core import config, experiment, library, optional
from chatlens.core import outcome as outcome_module
from chatlens.core import tomlwrite


def _expected_errors():
    """The failures that are the user's to fix, gathered in one place."""
    from chatlens.adapters import generic_chat

    return (
        config.InputError,
        experiment.ConfigError,
        library.LibraryError,
        outcome_module.OutcomeError,
        tomlwrite.TomlWriteError,
        # Only `generic_chat` declares one; the oTree adapter raises
        # `SystemExit` directly, which already carries its own message.
        generic_chat.AdapterError,
        FileNotFoundError,
    )

def _at_least(minimum: int):
    """An argparse type for a count that has to be a real count.

    `--llm-replicates 0` used to be accepted and produced a run that rated every
    unit zero times, reported no errors, and wrote empty columns — a success
    that never happened. Rejecting it at the command line is where the message
    is legible.
    """
    def parse(value: str) -> int:
        try:
            number = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f'{value!r} is not a number') from None
        if number < minimum:
            raise argparse.ArgumentTypeError(
                f'must be at least {minimum}, not {number}')
        return number

    parse.__name__ = f'int >= {minimum}'
    return parse


def spend_defaults():
    """Imported late: the help text needs the figures, nothing else does."""
    from chatlens.core import spend
    return spend.CONFIRM_ABOVE, spend.REFUSE_ABOVE


# Package data: the starting topic list, and the prompt folder it lives in.
PROMPTS_DIR = Path(__file__).resolve().parent / 'prompts'
DEFAULT_SEED = PROMPTS_DIR / 'seed_coalition_formation.md'


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-w', '--workspace', type=Path, default=None,
                        help='folder holding input/ and output/ '
                             '(default: the current directory)')
    parser.add_argument('-e', '--experiment', default=None, metavar='NAME',
                        help='an experiment from the library, by name '
                             '(chatlens experiments lists them)')
    parser.add_argument('--library', type=Path, default=None,
                        help='where the managed experiments live '
                             '(default: this machine\'s application data)')

    # Repeated on every subcommand so that both `chatlens -w DIR all` and
    # `chatlens all -w DIR` work: a researcher should not have to remember on
    # which side of the verb the option goes.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('-w', '--workspace', type=Path,
                        default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    common.add_argument('-e', '--experiment', default=argparse.SUPPRESS,
                        help=argparse.SUPPRESS)
    common.add_argument('--library', type=Path, default=argparse.SUPPRESS,
                        help=argparse.SUPPRESS)

    sub = parser.add_subparsers(dest='command', required=True)

    def add_input_options(sp):
        sp.add_argument('--input', action='append', default=[],
                        metavar='ROLE=PATH',
                        help='point a role at a file instead of looking for it '
                             'in input/; repeatable. The roles are the ones '
                             'the adapter declares (chatlens status lists '
                             'them)')
        # The two the oTree adapter uses, kept as shorthand because they are
        # what every existing instruction says.
        sp.add_argument('--wide', type=Path, default=None,
                        help='shorthand for --input wide=<path>')
        sp.add_argument('--chat', type=Path, default=None,
                        help='shorthand for --input chat=<path>')
        sp.add_argument('--keep-all', action='store_true',
                        help='do not filter: keep the test sessions and anyone '
                             'who was never part of a group')
        sp.add_argument('--pseudonymise', '--pseudonymize',
                        action='store_true', dest='pseudonymise',
                        help='replace participant identifiers with stable '
                             'keyed hashes in the files produced')

    def add_analysis_options(sp):
        sp.add_argument('--verbose', action='store_true')

        # The paid stages charge per call and the count is a product of four
        # choices, so a typo is expensive in a way the command line does not
        # show. See core/spend.py for where the numbers come from.
        sp.add_argument('--max-calls', type=_at_least(1), default=None,
                        metavar='N',
                        help=f'refuse a run needing more than N paid calls '
                             f'(default {spend_defaults()[1]})')
        sp.add_argument('--yes', action='store_true',
                        help='do not ask for confirmation before paid calls '
                             '(--max-calls still applies)')

        sp.add_argument('--llm', action='store_true',
                        help='run the validation rubric')
        sp.add_argument('--llm-provider', default=None,
                        choices=['openai', 'anthropic', 'ollama'],
                        help='rubric provider; if omitted, chosen from the keys '
                             'available')
        sp.add_argument('--llm-models', default=None,
                        help='judge models, comma separated')
        sp.add_argument('--llm-replicates', type=_at_least(1), default=1,
                        help='independent ratings per unit (reliability)')
        sp.add_argument('--llm-levels', nargs='+',
                        default=['dyad_directed', 'group'],
                        choices=['dyad_directed', 'dyad', 'sender_group', 'group'])
        sp.add_argument('--llm-batch', action='store_true',
                        help='Batches API at half price (anthropic provider only)')
        sp.add_argument('--llm-dry-run', action='store_true',
                        help='show the request without contacting the service')

        sp.add_argument('--topics', action='store_true',
                        help='run TopicGPT')
        sp.add_argument('--topicgpt-repo', default=None,
                        help='cloned TopicGPT repository (holds the prompts); '
                             'by default the one installed by '
                             '"chatlens install-topicgpt"')
        sp.add_argument('--topicgpt-api', default='openai',
                        choices=['openai', 'azure', 'vertex', 'gemini',
                                 'ollama', 'vllm'])
        sp.add_argument('--topicgpt-model', default='gpt-4o')
        # Topics are induced on the triad's whole conversation, which has
        # enough text, and assigned to the directed pairs, which are the unit of
        # persuasion.
        sp.add_argument('--topicgpt-unit', default='group',
                        choices=['dyad_directed', 'dyad', 'sender_group', 'group'],
                        help='unit on which to induce the topics')
        sp.add_argument('--topicgpt-assign-unit', default='dyad_directed',
                        choices=['dyad_directed', 'dyad', 'sender_group', 'group'],
                        help='unit to which the induced topics are assigned')
        # A path relative to the current directory would only work from
        # inside the source tree; the seed ships with the package.
        sp.add_argument('--topicgpt-seed', default=str(DEFAULT_SEED),
                        help='starting topic list; the seed shipped by '
                             'TopicGPT itself belongs to another domain')
        sp.add_argument('--topicgpt-induce-only', action='store_true',
                        help='stop after discovering and refining the topics, '
                             'without attributing them: the taxonomy costs a '
                             'fifth of the full run and is what there is to '
                             'judge')
        sp.add_argument('--topicgpt-unsupervised', action='store_true',
                        help='induce the topics with no starting list at all: '
                             'every topic comes from the documents')
        # Induction is order-dependent and stops early, so whatever comes first
        # decides the taxonomy. See core/topicgpt.py.
        sp.add_argument('--topicgpt-shuffle-seed', type=int, default=1,
                        metavar='N',
                        help='seed for shuffling the documents before '
                             'induction (default 1); 0 keeps the file order')
        sp.add_argument('--topicgpt-no-refine', action='store_true',
                        help='skip topic refinement')
        sp.add_argument('--topicgpt-dry-run', action='store_true',
                        help='write the input file only, with no calls')

    sp_all = sub.add_parser('all', parents=[common], help='merge + analysis')
    add_input_options(sp_all)
    add_analysis_options(sp_all)

    sp_merge = sub.add_parser('merge', parents=[common],
                              help='merge choices and chat only')
    add_input_options(sp_merge)

    sp_analyze = sub.add_parser('analyze', parents=[common], help='text analysis only')
    add_input_options(sp_analyze)
    add_analysis_options(sp_analyze)

    sp_report = sub.add_parser(
        'report', parents=[common],
        help='regenerate the readable summary from existing files')
    add_input_options(sp_report)

    sp_runs = sub.add_parser('runs', parents=[common], help='list the archived runs')
    sp_runs.add_argument('--prune', type=int, metavar='N',
                         help='keep the N most recent and delete the rest')
    sp_dash = sub.add_parser('dashboard', parents=[common],
                             help='open the dashboard in a browser')
    sp_dash.add_argument('--port', type=int, default=8765)
    sp_dash.add_argument('--no-browser', action='store_true')
    sp_exp = sub.add_parser(
        'experiments', parents=[common],
        help='list the managed experiments, or make one')
    sp_exp.add_argument('--new', metavar='NAME', default=None,
                        help='create an experiment with this name')
    sp_exp.add_argument('--adapter', default='generic_chat',
                        help='adapter for the new experiment '
                             '(default generic_chat)')
    sp_exp.add_argument('--all', action='store_true',
                        help='include the archived ones')

    sp_export = sub.add_parser(
        'export', parents=[common],
        help='pack an experiment into one file, to send to somebody')
    sp_export.add_argument('name', nargs='?', default=None,
                           help='which experiment (default: the one -e names, '
                                'or the current workspace)')
    sp_export.add_argument('-o', '--output', type=Path, default=None,
                           help='where to write it (default: here, named '
                                'after the experiment)')
    sp_export.add_argument('--with-runs', action='store_true',
                           help='include the archived previous runs '
                                '(much larger, rarely wanted)')
    sp_export.add_argument('--pseudonymise', action='store_true',
                           help='replace participant identifiers on the way '
                                'out, irreversibly')

    sp_import = sub.add_parser(
        'import', parents=[common],
        help='add an experiment somebody exported')
    sp_import.add_argument('file', type=Path,
                           help='the .chatlens.tar.gz to open')
    sp_import.add_argument('--name', default=None,
                           help='import it under a different name')
    sp_import.add_argument('--describe', action='store_true',
                           help='say what is inside and stop')

    sp_demo = sub.add_parser(
        'demo', parents=[common],
        help='write a synthetic workspace and analyse it, to try the tool')
    sp_demo.add_argument('directory', type=Path, nargs='?', default=None,
                         help='where to put it (default: ./chatlens-demo)')
    sp_demo.add_argument('--no-run', action='store_true',
                         help='write the files without running the analysis')
    # The same options as a real run, so `chatlens demo --llm` shows what the
    # paid stages produce on data nobody has to worry about.
    add_input_options(sp_demo)
    add_analysis_options(sp_demo)

    sp_tgpt = sub.add_parser(
        'install-topicgpt', parents=[common],
        help='clone and install TopicGPT (needed only for the topics)')
    sp_tgpt.add_argument('--repo', type=Path, default=None,
                         help='where to clone it (default: this machine\'s '
                              'application data directory)')

    sp_sub = sub.add_parser(
        'subtopics', parents=[common],
        help='second-level topics under the ones already found')
    sp_sub.add_argument('--run', type=Path, default=None,
                        help='the completed topic run to subdivide '
                             '(default: output/topicgpt)')
    sp_sub.add_argument('--prompt', type=Path, default=None,
                        help="a prompt with your own example subtopics; the "
                             "examples control the granularity of the result, "
                             "so running two and comparing says more than one")
    sp_sub.add_argument('--repo', type=Path, default=None)
    sp_sub.add_argument('--api', default='openai')
    sp_sub.add_argument('--model', default='gpt-4o')

    sp_rel = sub.add_parser(
        'install-relatio', parents=[common],
        help='clone and install RELATIO (optional: the narratives page works '
             'without it)')
    sp_rel.add_argument('--repo', type=Path, default=None,
                        help="where to clone it (default: this machine's "
                             'application data directory)')

    sp_model = sub.add_parser(
        'install-model', parents=[common],
        help='download a spaCy language model into this environment')
    sp_model.add_argument('name', nargs='?', default='en_core_web_md',
                          help='the model (default: en_core_web_md, ~40 MB)')

    sub.add_parser('keys', parents=[common], help='configure the API keys')
    sub.add_parser('status', parents=[common],
                   help='what is in input, output and among the keys')

    return parser


def resolve_inputs(args) -> dict:
    """Locate every file the active adapter asks for.

    A role whose pattern is None is optional: absent, it is simply not there,
    and the adapter is told so rather than being handed a path that does not
    exist.
    """
    overrides = {}
    for item in getattr(args, 'input', None) or []:
        role, _, path = item.partition('=')
        if not path:
            raise SystemExit(
                f'\n--input wants ROLE=PATH, not "{item}".\n'
                f'  Roles for this adapter: '
                f'{", ".join(config.INPUT_PATTERNS)}\n'
            )
        overrides[role.strip()] = Path(path).expanduser()
    for role in ('wide', 'chat'):
        given = getattr(args, role, None)
        if given is not None:
            overrides[role] = given

    unknown = set(overrides) - set(config.INPUT_PATTERNS)
    if unknown:
        raise SystemExit(
            f'\nThis adapter has no input called '
            f'{", ".join(sorted(unknown))}.\n'
            f'  Roles: {", ".join(config.INPUT_PATTERNS)}\n'
        )

    paths = {}
    for role, pattern in config.INPUT_PATTERNS.items():
        try:
            paths[role] = config.find_input(role, overrides.get(role))
        except config.InputError:
            if pattern is None and role not in overrides:
                paths[role] = None      # optional and not there: fine
                continue
            raise
    return paths


def dataset_stem(paths: dict) -> str:
    """The prefix of everything produced: the first required input's name."""
    for role, pattern in config.INPUT_PATTERNS.items():
        if pattern is not None and paths.get(role):
            return config.dataset_stem(paths[role])
    first = next((p for p in paths.values() if p), None)
    return config.dataset_stem(first) if first else 'dataset'


def resolve_dataset(args) -> tuple[dict, str]:
    """The adapter's input files, and the stem derived from them."""
    paths = resolve_inputs(args)
    return paths, dataset_stem(paths)


def stem_from_outputs() -> str | None:
    """The stem of what has already been produced, read off the merged files.

    `analyze` and `report` needed nothing from `input/` except the name to
    build their filenames from, and they were getting it by resolving the input
    files — so regenerating a report from results already on disk failed once
    the export had been cleaned away, with a message about a missing export
    that the command did not need.
    """
    suffix = '_messages_long.csv'
    found = sorted(config.MERGED_DIR.glob(f'*{suffix}'))
    if not found:
        return None
    return found[0].name[:-len(suffix)]


def resolve_stem(args) -> str:
    """The stem, from the outputs if they are there and the inputs if not."""
    from_outputs = stem_from_outputs()
    if from_outputs:
        return from_outputs
    return resolve_dataset(args)[1]


def cmd_merge(args) -> int:
    from chatlens import adapters

    experiment = config.EXPERIMENT
    adapter = adapters.load(experiment.adapter)
    paths, stem = resolve_dataset(args)

    print(f'Experiment: {experiment.describe()}')
    print('Input:')
    for role, path in paths.items():
        print(f'  {role:<14} {path.name if path else "(absent)"}')
    print()

    # Only what this adapter understands: an option it never declared would be
    # a silent no-op, which is the kind of thing that wastes an afternoon.
    options = {name: getattr(args, name)
               for name in getattr(adapter, 'OPTIONS', ())
               if hasattr(args, name)}
    if 'columns' in getattr(adapter, 'OPTIONS', ()):
        options['columns'] = experiment.columns

    summary = adapter.run(
        **{role: path for role, path in paths.items()},
        outdir=config.MERGED_DIR, stem=stem,
        pseudonymise=getattr(args, 'pseudonymise', False),
        **options,
    )
    adapter.print_summary(summary)
    return 0


def cmd_analyze(args) -> int:
    from chatlens.core import pipeline

    if getattr(args, 'topics', False) and not args.topicgpt_repo:
        args.topicgpt_repo = str(config.topicgpt_repo())

    stem = resolve_stem(args)
    args.merged_dir = config.MERGED_DIR
    args.outdir = config.OUTPUT_DIR
    args.stem = stem

    summary = pipeline.run(args)
    return pipeline.print_summary(summary)


def cmd_all(args) -> int:
    result = cmd_merge(args)
    if result:
        return result
    print()
    return cmd_analyze(args)


def cmd_report(args) -> int:
    from chatlens.core import report

    stem = resolve_stem(args)
    paths = report.write(config.OUTPUT_DIR, stem)
    print('Readable summary:')
    for path in paths:
        print(f'  {path}')
    return 0


def cmd_runs(args) -> int:
    from chatlens.core import archive

    if args.prune is not None:
        removed = archive.prune(config.OUTPUT_DIR, args.prune)
        if not removed:
            print(f'Nothing to remove: the archived runs are already at most '
                  f'{args.prune}.')
        else:
            print(f'Removed {len(removed)} runs, kept the {args.prune} most '
                  f'recent:')
            for path in removed:
                print(f'  {path.name}')
        print()

    runs = archive.list_runs(config.OUTPUT_DIR)
    print(f'Runs archived in {config.OUTPUT_DIR / "runs"}:')
    print()
    print(archive.render_list(runs))
    if runs:
        print()
        print('The latest run is also in output/, at fixed paths.')
    return 0


def cmd_dashboard(args) -> int:
    from chatlens.web.server import serve

    # Pointed at one folder, the dashboard is that folder's and there is no
    # library page — which is how it behaved before the library existed, and
    # what anyone with workspaces of their own already relies on.
    single = bool(getattr(args, 'workspace', None)
                  or getattr(args, 'experiment', None))
    serve(port=args.port, open_browser=not args.no_browser,
          library_mode=not single)
    return 0


def cmd_experiments(args) -> int:
    """List the managed experiments, or make one."""
    if args.new:
        try:
            path = library.create(args.new, adapter=args.adapter)
        except library.LibraryError as exc:
            raise SystemExit(f'\n{exc}\n') from None
        print(f'Created "{args.new}" in {path}')
        print()
        print('Next:')
        print(f'  put the exported CSVs in {path / "input"}')
        print(f'  chatlens -e "{args.new}" status')
        return 0

    entries = library.entries(include_archived=args.all)
    print(f'Library: {library.ROOT}')
    print()
    if not entries:
        print('  (empty)')
        print()
        print('  chatlens experiments --new "My study"')
        return 0

    for entry in entries:
        state = ' [archived]' if entry['archived'] else ''
        size = f"{entry['size'] // 1024} KB" if entry['size'] else 'no files'
        print(f"  {entry['name']}{state}")
        print(f"      {entry['adapter']} · {entry['n_files']} files, {size}"
              + (f" · last run {entry['last_run']}" if entry['last_run'] else ''))
        if entry['problem']:
            print(f"      PROBLEM: {entry['problem'].splitlines()[0]}")
    print()
    print(f'  chatlens -e "{entries[0]["name"]}" dashboard')
    return 0


def _mb(n) -> str:
    return f'{n / 1048576:.1f} MB'


def _computed(manifest: dict) -> str:
    """What the recipient will not have to produce again.

    The two paid stages, and the relations — which cost no money but a hundred
    seconds, and are the slowest thing the dashboard does.
    """
    inside = [label for label, key in (('the rubric', 'has_rubric'),
                                       ('the topics', 'has_topics'),
                                       ('the relations', 'has_relations'))
              if manifest.get(key)]
    return ', '.join(inside) if inside else 'the measures only'



def cmd_export(args) -> int:
    """Pack an experiment so that somebody else can open the results.

    Everything the analysis produced travels, the paid stages included, so the
    person receiving it re-runs nothing. What does not travel is in
    `core/bundle.py`, which is also where the reasons are.
    """
    from chatlens.core import bundle

    if args.name:
        folder = library.path_for(library.slug(args.name))
        if not folder.is_dir():
            raise SystemExit(f'\nNo experiment called "{args.name}" in '
                             f'{library.ROOT}.\n')
    else:
        folder = config.WORKSPACE

    try:
        manifest = bundle.describe(folder, args.with_runs, args.pseudonymise)
        if args.pseudonymise:
            print('Rewriting the identifier columns. The key is made for this '
                  'bundle and\nthrown away: nobody can undo it afterwards, '
                  'this machine included.', flush=True)
        written = bundle.pack(folder, args.output,
                              with_runs=args.with_runs,
                              pseudonymise=args.pseudonymise)
    except bundle.BundleError as exc:
        raise SystemExit(f'\n{exc}\n') from None

    print(f'\n{manifest["name"]} -> {written}')
    print(f'  {manifest["n_files"]} files, {_mb(written.stat().st_size)} '
          f'compressed (from {_mb(manifest["bytes"])})')
    print(f'  already computed inside: {_computed(manifest)}')
    if manifest['pseudonymised']:
        print('  participant identifiers: replaced')
    else:
        print('  participant identifiers: as they are in the export')
    print()
    print('They open it with:')
    print(f'  chatlens import {written.name}')
    return 0


def cmd_import(args) -> int:
    """Add an experiment somebody exported, without trusting the archive."""
    from chatlens.core import bundle

    try:
        manifest = bundle.inspect(args.file)
    except bundle.BundleError as exc:
        raise SystemExit(f'\n{exc}\n') from None

    print(f'{manifest["name"]}  ({manifest["slug"]})')
    print(f'  packed {manifest["packed"]}, adapter {manifest["adapter"]}')
    print(f'  {manifest["n_files"]} files, {_mb(manifest["bytes"])} unpacked')
    print(f'  already computed inside: {_computed(manifest)}')
    if manifest['pseudonymised']:
        print('  participant identifiers: replaced before it was sent')
    if args.describe:
        return 0

    try:
        path = bundle.unpack(args.file, library.ROOT, args.name)
    except bundle.BundleError as exc:
        raise SystemExit(f'\n{exc}\n') from None

    print(f'\nImported into {path}')
    print()
    print('Next:')
    # The folder, not the name in the manifest: --name may have renamed it,
    # and the command printed has to be the one that opens what just arrived.
    print(f'  chatlens -e "{path.name}" dashboard')
    return 0


def cmd_demo(args) -> int:
    """Write a synthetic study and run the pipeline over it.

    A first step that costs nothing and exposes nobody: the people best placed
    to judge a research tool are the ones who should not be handed somebody
    else's participant data in order to do it.
    """
    from chatlens.core import demo

    target = Path(args.directory) if args.directory else Path.cwd() / 'chatlens-demo'
    if target.exists() and any(target.iterdir()):
        raise SystemExit(
            f'\n{target} already exists and is not empty.\n'
            f'  Give another folder, or delete that one: the demo writes its '
            f'own workspace and will not overwrite yours.\n'
        )

    made = demo.create(target)
    print(f'Synthetic workspace in {made["workspace"]}')
    print(f'  {made["n_groups"]} groups of four, '
          f'{made["n_participants"]} participants, '
          f'{made["n_messages"]} messages, 2 treatments')
    print('  none of it real: generated from a fixed seed')
    print()

    if args.no_run:
        print('To analyse it:')
        print(f'    cd {made["workspace"]}')
        print('    chatlens all')
        return 0

    # From here on it is an ordinary run, in the workspace just written.
    config.use_workspace(made['workspace'])
    config.use_experiment(experiment.load(config.WORKSPACE))
    config.ensure_dirs()

    result = cmd_all(args)
    if result == 0:
        print()
        print('That is the whole procedure. On your own data it is the same,')
        print('with your files in input/ and your columns in experiment.toml.')
        print(f'    chatlens --workspace {made["workspace"]} dashboard')
    return result


def cmd_install_topicgpt(args) -> int:
    """Clone TopicGPT and install it into the running interpreter.

    TopicGPT is installed from its repository rather than from PyPI because the
    prompt files are part of the method and are not inside the published
    package; release 0.2.7 also imports vLLM at the top level, which does not
    install on a machine without a GPU.
    """
    import subprocess

    repo = Path(args.repo).expanduser() if args.repo else config.topicgpt_repo()
    if not repo.exists():
        repo.parent.mkdir(parents=True, exist_ok=True)
        print(f'Cloning TopicGPT into {repo}')
        cloned = subprocess.run(
            ['git', 'clone', '--depth', '1',
             'https://github.com/chtmp223/topicGPT.git', str(repo)]
        )
        if cloned.returncode:
            raise SystemExit('\nClone failed: check the network and that git '
                             'is installed.\n')
    else:
        print(f'Already present: {repo}')

    print('Installing it (heavy dependencies, this may take minutes).')
    print('The warning about google-cloud-aiplatform and the "all" extra is '
          'harmless.')
    installed = subprocess.run(optional.pip_argv(str(repo)))
    if installed.returncode:
        raise SystemExit('\nInstallation failed: see the messages above.\n')

    prompts = repo / 'prompt' / 'generation_1.txt'
    if not prompts.is_file():
        raise SystemExit(f'\nInstalled, but the prompt files are missing in '
                         f'{repo / "prompt"}.\nWithout them the method cannot '
                         f'run: try removing the folder and cloning again.\n')

    print(f'\nTopicGPT installed and verified ({repo}).')
    if not args.repo:
        print('The topics commands will find it on their own.')
    else:
        print(f'Point the commands at it with:  '
              f'--topicgpt-repo {repo}\n'
              f'or set CHATLENS_TOPICGPT_REPO={repo}')
    return 0


def cmd_keys(_args) -> int:
    from chatlens.core import setup_keys

    return setup_keys.main([])


def cmd_status(_args) -> int:
    print(f'Workspace : {config.WORKSPACE}')
    print(f'Experiment: {config.EXPERIMENT.describe()}')
    print()
    print('Input (the roles this adapter asks for):')
    for role, pattern in config.INPUT_PATTERNS.items():
        if pattern is None:
            print(f'  optional {role}')
            continue
        matches = sorted(config.INPUT_DIR.glob(pattern))
        if not matches:
            print(f'  missing  {role:<14} {pattern}')
        for match in matches:
            size = match.stat().st_size // 1024
            print(f'  present  {role:<14} {match.name} ({size} KB)')

    print()
    print('Output:')
    produced = sorted(config.OUTPUT_DIR.rglob('*.csv')) if config.OUTPUT_DIR.is_dir() else []
    if not produced:
        print('  (empty)')
    for path in produced:
        print(f'  {path.relative_to(config.OUTPUT_DIR)}')

    print()
    print(f'API keys (file {config.ENV_FILE}):')
    if config.ENV_FILE == config.user_env_file():
        print('  outside any repository: it cannot be committed by mistake')
    else:
        ignored = config.is_git_ignored(config.ENV_FILE)
        label = {True: 'yes', False: 'NO — needs fixing before any commit',
                 None: 'not verifiable'}[ignored]
        print(f'  git ignores it: {label}')
    for name, purpose, present in config.key_status():
        print(f'  {"present" if present else "absent ":8s} {name:20s} {purpose}')
    return 0


def cmd_install_relatio(args) -> int:
    """Clone RELATIO and install it into the running interpreter.

    From the repository rather than from PyPI: the published release fails to
    build, because its pinned gensim cannot generate metadata under a modern
    setuptools. The master branch installs cleanly.

    This is optional. The narratives page works without it, using spaCy
    dependency parsing, and on the corpus this tool was built for the two agree
    on the finding that matters. What the package adds is its own clustering of
    the phrases that are *not* declared entities, and the automatic choice of
    how many clusters to use — worth having when a corpus has many entities and
    you do not yet know what they are.

    It is also large: torch and transformers come with it, about 1.6 GB against
    the four megabytes chatlens itself takes. Hence a command rather than a
    dependency, so that nobody downloads it by opening a page.
    """
    import subprocess

    repo = Path(args.repo).expanduser() if args.repo else config.relatio_repo()
    if not repo.exists():
        repo.parent.mkdir(parents=True, exist_ok=True)
        print(f'Cloning RELATIO into {repo}')
        cloned = subprocess.run(
            ['git', 'clone', '--depth', '1',
             'https://github.com/relatio-nlp/relatio.git', str(repo)])
        if cloned.returncode:
            raise SystemExit('\nClone failed: check the network and that git '
                             'is installed.\n')
    else:
        print(f'Already present: {repo}')

    print('Installing it. This pulls torch and transformers — about 1.6 GB —')
    print('and will take some minutes.')
    installed = subprocess.run(optional.pip_argv(str(repo)))
    if installed.returncode:
        raise SystemExit('\nInstall failed: the output above says why.\n')

    print('\nInstalled. The narratives page will use it from now on, and says')
    print('which route it took.')
    return 0


def cmd_install_model(args) -> int:
    """Put a spaCy language model in the environment chatlens is installed in.

    A wrapper around `spacy download`, which is worth keeping rather than
    replacing with a wheel URL: it reads spaCy's compatibility table and picks
    the build matching the spaCy that is actually here, and a URL written down
    a year ago does not.

    What it adds is the part that goes wrong. `spacy download` fetches through
    pip, and chatlens normally lives in a uv tool environment, which has no
    pip in it — the download stops at *No module named pip*. So pip is put
    there first if it is missing. Doing that here, once, is better than
    printing two commands on a page that exists to be copied without thinking.
    """
    import subprocess

    from chatlens.core.optional import have, have_spacy_model

    name = args.name
    if have_spacy_model(name):
        print(f'Already present: {name}')
        return 0
    if not have('spacy'):
        raise SystemExit(
            '\nspaCy is not installed, and the model is a package it loads.\n'
            'The narratives screen prints the command for this environment.\n')

    if not have('pip'):
        # Flushed: the installer below writes straight to the terminal, and
        # unflushed prints arrive after it, describing what already happened.
        print('Giving this environment a pip, which spacy download needs.',
              flush=True)
        if subprocess.run(optional.pip_argv('pip')).returncode:
            raise SystemExit('\nCould not install pip: see above.\n')

    print(f'Downloading {name}.', flush=True)
    if subprocess.run([sys.executable, '-m', 'spacy', 'download',
                       name]).returncode:
        raise SystemExit('\nDownload failed: the output above says why.\n')

    print(f'\n{name} installed. The narratives screen will find it.')
    return 0


def cmd_subtopics(args) -> int:
    """Subdivide the topics a completed run already found.

    Cheap: the documents are batched into the prompt, so each parent costs one
    call. What it produces has to be read with care, and the grounding table
    printed afterwards is how to read it.
    """
    from chatlens.core import config, topicgpt

    config.load_env()
    run_dir = args.run or config.TOPICS_DIR
    repo = args.repo or config.topicgpt_repo()
    try:
        topic_file = topicgpt.subtopics(
            run_dir, repo, api=args.api, model=args.model,
            prompt_file=args.prompt)
    except (topicgpt.TopicGPTUnavailable, topicgpt.TopicGPTIncomplete) as exc:
        print(f'\n{exc}')
        return 1

    print()
    print(topic_file.read_text(encoding='utf-8').rstrip())

    grounding = topicgpt.subtopic_grounding(run_dir)
    if grounding:
        print()
        print('  How much of what it was shown each subtopic actually cited:')
        print(f'  {"subtopic":30s} {"cited":>7s} {"shown":>7s} {"share":>7s}')
        for row in grounding:
            print(f'  {row["name"][:30]:30s} {row["cited"]:7d} '
                  f'{row["shown"]:7d} {100 * row["share"]:6.0f}%')
        extreme = [r for r in grounding
                   if r['shown'] > 50 and (r['share'] > 0.99 or r['share'] < 0.1)]
        if extreme:
            print()
            print('  The method asks each subtopic to name the documents that')
            print('  support it, so that it is grounded rather than invented.')
            print('  The shares above say that did not happen: a subtopic')
            print('  citing everything, or only the first handful of a large')
            print('  batch, is not grounded in what it was shown. Treat these')
            print('  labels as suggestions and not as a taxonomy, and do not')
            print('  read prevalence from them.')
    return 0


COMMANDS = {
    'all': cmd_all,
    'merge': cmd_merge,
    'analyze': cmd_analyze,
    'report': cmd_report,
    'runs': cmd_runs,
    'dashboard': cmd_dashboard,
    'experiments': cmd_experiments,
    'demo': cmd_demo,
    'install-topicgpt': cmd_install_topicgpt,
    'subtopics': cmd_subtopics,
    'install-relatio': cmd_install_relatio,
    'install-model': cmd_install_model,
    'keys': cmd_keys,
    'status': cmd_status,
    'export': cmd_export,
    'import': cmd_import,
}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    # First of all, because every path below is read from the workspace.
    library.use_library(library.resolve_root(getattr(args, 'library', None)))

    # An experiment named on the command line is a workspace like any other:
    # the library only decides where to look for it.
    chosen = getattr(args, 'experiment', None)
    if chosen:
        try:
            path = library.path_for(library.slug(chosen))
        except library.LibraryError as exc:
            raise SystemExit(f'\n{exc}\n') from None
        if not path.is_dir():
            raise SystemExit(
                f'\nNo experiment called "{chosen}" in {library.ROOT}.\n'
                f'  chatlens experiments            lists them\n'
                f'  chatlens experiments --new "{chosen}"   makes it\n'
            )
        config.use_workspace(path)
    else:
        config.use_workspace(
            config.resolve_workspace(getattr(args, 'workspace', None)))

    try:
        config.use_experiment(experiment.load(config.WORKSPACE))
    except experiment.ConfigError as exc:
        raise SystemExit(f'\n{exc}\n') from None
    # `import` is the one command normally run from wherever the file was
    # downloaded to, and it writes into the library rather than the workspace.
    # Making input/ and output/ in somebody's Downloads folder is litter.
    if args.command != 'import':
        config.ensure_dirs()
    config.load_env()
    EXPECTED = _expected_errors()
    try:
        return COMMANDS[args.command](args)
    except EXPECTED as exc:
        # Something to fix in the workspace, not a program error. Each of these
        # classes already carries a message written for the person reading it;
        # the traceback above it says nothing they can act on.
        #
        # AdapterError was missing from this list, which made the single most
        # likely mistake — a column mapped to a name the file does not have —
        # the one that printed a stack trace.
        raise SystemExit(f'\n{exc}\n') from None


if __name__ == '__main__':
    sys.exit(main())
