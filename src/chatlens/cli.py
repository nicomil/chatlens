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

from chatlens.core import config, experiment

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

    # Repeated on every subcommand so that both `chatlens -w DIR all` and
    # `chatlens all -w DIR` work: a researcher should not have to remember on
    # which side of the verb the option goes.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('-w', '--workspace', type=Path,
                        default=argparse.SUPPRESS, help=argparse.SUPPRESS)

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
        sp.add_argument('--max-calls', type=int, default=None,
                        metavar='N',
                        help=f'refuse a run needing more than N paid calls '
                             f'(default {spend_defaults()[1]})')
        sp.add_argument('--yes', action='store_true',
                        help='do not ask for confirmation before paid calls')

        sp.add_argument('--llm', action='store_true',
                        help='run the validation rubric')
        sp.add_argument('--llm-provider', default=None,
                        choices=['openai', 'anthropic', 'ollama'],
                        help='rubric provider; if omitted, chosen from the keys '
                             'available')
        sp.add_argument('--llm-models', default=None,
                        help='judge models, comma separated')
        sp.add_argument('--llm-replicates', type=int, default=1,
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
    sp_tgpt = sub.add_parser(
        'install-topicgpt', parents=[common],
        help='clone and install TopicGPT (needed only for the topics)')
    sp_tgpt.add_argument('--repo', type=Path, default=None,
                         help='where to clone it (default: this machine\'s '
                              'application data directory)')

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

    _paths, stem = resolve_dataset(args)
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

    _paths, stem = resolve_dataset(args)
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

    serve(port=args.port, open_browser=not args.no_browser)
    return 0


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
    installed = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', str(repo)]
    )
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


COMMANDS = {
    'all': cmd_all,
    'merge': cmd_merge,
    'analyze': cmd_analyze,
    'report': cmd_report,
    'runs': cmd_runs,
    'dashboard': cmd_dashboard,
    'install-topicgpt': cmd_install_topicgpt,
    'keys': cmd_keys,
    'status': cmd_status,
}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    # First of all, because every path below is read from the workspace.
    config.use_workspace(
        config.resolve_workspace(getattr(args, 'workspace', None)))
    try:
        config.use_experiment(experiment.load(config.WORKSPACE))
    except experiment.ConfigError as exc:
        raise SystemExit(f'\n{exc}\n') from None
    config.ensure_dirs()
    config.load_env()
    try:
        return COMMANDS[args.command](args)
    except config.InputError as exc:
        # A file is missing or there is more than one: something to fix in
        # input/, not a program error.
        raise SystemExit(f'\n{exc}\n') from None


if __name__ == '__main__':
    sys.exit(main())
