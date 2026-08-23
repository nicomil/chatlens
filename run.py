"""
Chat text analysis — single entry point.

    python run.py all         merge the data and analyse it
    python run.py merge       merge choices and chat only
    python run.py analyze     text analysis only
    python run.py keys        configure the API keys
    python run.py status      what is in input, in output and among the keys

The files to analyse go in `input/`: they are recognised by name, not passed on
the command line. Everything produced lands in `output/`.

Examples:

    python run.py all                                  automatic measures
    python run.py all --llm --llm-replicates 2         + validation rubric
    python run.py all --topics --topicgpt-repo ~/src/topicGPT
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import config  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest='command', required=True)

    def add_input_options(sp):
        sp.add_argument('--wide', type=Path, default=None,
                        help='all_apps_wide export, if not the one in input/')
        sp.add_argument('--chat', type=Path, default=None,
                        help='ChatMessages export, if not the one in input/')
        sp.add_argument('--keep-all', action='store_true',
                        help='do not filter: keep the test sessions and anyone '
                             'who was never part of a group')

    def add_analysis_options(sp):
        sp.add_argument('--verbose', action='store_true')

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
        sp.add_argument('--topicgpt-repo', default='./topicGPT',
                        help='cloned TopicGPT repository (holds the prompts)')
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
        sp.add_argument('--topicgpt-seed', default='prompts/seed_coalition_formation.md',
                        help='starting topic list; the repository seed belongs '
                             'to another domain')
        sp.add_argument('--topicgpt-no-refine', action='store_true',
                        help='skip topic refinement')
        sp.add_argument('--topicgpt-dry-run', action='store_true',
                        help='write the input file only, with no calls')

    sp_all = sub.add_parser('all', help='merge + analysis')
    add_input_options(sp_all)
    add_analysis_options(sp_all)

    sp_merge = sub.add_parser('merge', help='merge choices and chat only')
    add_input_options(sp_merge)

    sp_analyze = sub.add_parser('analyze', help='text analysis only')
    add_input_options(sp_analyze)
    add_analysis_options(sp_analyze)

    sp_report = sub.add_parser(
        'report', help='regenerate the readable summary from existing files')
    add_input_options(sp_report)

    sp_runs = sub.add_parser('runs', help='list the archived runs')
    sp_runs.add_argument('--prune', type=int, metavar='N',
                         help='keep the N most recent and delete the rest')
    sp_dash = sub.add_parser('dashboard', help='open the dashboard in a browser')
    sp_dash.add_argument('--port', type=int, default=8765)
    sp_dash.add_argument('--no-browser', action='store_true')
    sub.add_parser('keys', help='configure the API keys')
    sub.add_parser('status', help='what is in input, output and among the keys')

    return parser


def resolve_dataset(args) -> tuple[Path, Path, str]:
    """Locate the exports and the prefix of the files produced."""
    wide = config.find_input('wide', args.wide)
    chat = config.find_input('chat', args.chat)
    return wide, chat, config.dataset_stem(wide)


def cmd_merge(args) -> int:
    from src import merge

    wide, chat, stem = resolve_dataset(args)
    print(f'Input:  {wide.name}')
    print(f'        {chat.name}')
    print()
    summary = merge.run(wide, chat, config.MERGED_DIR, stem,
                        keep_all=getattr(args, 'keep_all', False))
    merge.print_summary(summary)
    return 0


def cmd_analyze(args) -> int:
    from src import pipeline

    _wide, _chat, stem = resolve_dataset(args)
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
    from src import report

    _wide, _chat, stem = resolve_dataset(args)
    paths = report.write(config.OUTPUT_DIR, stem)
    print('Readable summary:')
    for path in paths:
        print(f'  {path}')
    return 0


def cmd_runs(args) -> int:
    from src import archive

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
    from web.server import serve

    serve(port=args.port, open_browser=not args.no_browser)
    return 0


def cmd_keys(_args) -> int:
    from src import setup_keys

    return setup_keys.main([])


def cmd_status(_args) -> int:
    print(f'Project : {config.PROJECT_ROOT}')
    print()
    print('Input:')
    for kind, pattern in config.INPUT_PATTERNS.items():
        matches = sorted(config.INPUT_DIR.glob(pattern))
        if not matches:
            print(f'  missing  {pattern}')
        for match in matches:
            size = match.stat().st_size // 1024
            print(f'  present  {match.name} ({size} KB)')

    print()
    print('Output:')
    produced = sorted(config.OUTPUT_DIR.rglob('*.csv')) if config.OUTPUT_DIR.is_dir() else []
    if not produced:
        print('  (empty)')
    for path in produced:
        print(f'  {path.relative_to(config.OUTPUT_DIR)}')

    print()
    print(f'API keys (file {config.ENV_FILE.name}):')
    ignored = config.is_git_ignored(config.ENV_FILE)
    label = {True: 'yes', False: 'NO — needs fixing',
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
    'keys': cmd_keys,
    'status': cmd_status,
}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
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
