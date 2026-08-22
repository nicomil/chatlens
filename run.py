"""
Analisi del testo delle chat — punto di ingresso unico.

    python run.py all         unisce i dati ed esegue l'analisi
    python run.py merge       solo l'unione di scelte e chat
    python run.py analyze     solo l'analisi del testo
    python run.py keys        configura le chiavi API
    python run.py status      cosa c'è in input, in output e fra le chiavi

I file da analizzare vanno messi in `input/`: vengono riconosciuti dal nome, non
si passano da riga di comando. Tutto ciò che viene prodotto finisce in
`output/`.

Esempi:

    python run.py all                                  misure automatiche
    python run.py all --llm --llm-replicates 2         + rubrica di validazione
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
                        help="export all_apps_wide, se non è quello in input/")
        sp.add_argument('--chat', type=Path, default=None,
                        help="export ChatMessages, se non è quello in input/")
        sp.add_argument('--keep-all', action='store_true',
                        help='non filtrare: tiene anche le sessioni di collaudo '
                             'e chi non ha mai fatto parte di un gruppo')

    def add_analysis_options(sp):
        sp.add_argument('--verbose', action='store_true')

        sp.add_argument('--llm', action='store_true',
                        help='esegue la rubrica di validazione')
        sp.add_argument('--llm-provider', default=None,
                        choices=['openai', 'anthropic', 'ollama'],
                        help='fornitore della rubrica; se omesso sceglie in base '
                             'alle chiavi disponibili')
        sp.add_argument('--llm-models', default=None,
                        help='modelli giudice, separati da virgola')
        sp.add_argument('--llm-replicates', type=int, default=1,
                        help='valutazioni indipendenti per unità (affidabilità)')
        sp.add_argument('--llm-levels', nargs='+',
                        default=['dyad_directed', 'group'],
                        choices=['dyad_directed', 'dyad', 'sender_group', 'group'])
        sp.add_argument('--llm-batch', action='store_true',
                        help='Batches API a metà prezzo (solo fornitore anthropic)')
        sp.add_argument('--llm-dry-run', action='store_true',
                        help='mostra la richiesta senza contattare il servizio')

        sp.add_argument('--topics', action='store_true',
                        help='esegue TopicGPT')
        sp.add_argument('--topicgpt-repo', default='./topicGPT',
                        help='repository clonato di TopicGPT (contiene i prompt)')
        sp.add_argument('--topicgpt-api', default='openai',
                        choices=['openai', 'azure', 'vertex', 'gemini',
                                 'ollama', 'vllm'])
        sp.add_argument('--topicgpt-model', default='gpt-4o')
        sp.add_argument('--topicgpt-unit', default='dyad_directed',
                        choices=['dyad_directed', 'dyad', 'sender_group', 'group'])
        sp.add_argument('--topicgpt-no-refine', action='store_true',
                        help='salta il raffinamento dei topic')
        sp.add_argument('--topicgpt-dry-run', action='store_true',
                        help='scrive solo il file di input, senza chiamate')

    sp_all = sub.add_parser('all', help='unione + analisi')
    add_input_options(sp_all)
    add_analysis_options(sp_all)

    sp_merge = sub.add_parser('merge', help='solo unione di scelte e chat')
    add_input_options(sp_merge)

    sp_analyze = sub.add_parser('analyze', help="solo analisi del testo")
    add_input_options(sp_analyze)
    add_analysis_options(sp_analyze)

    sub.add_parser('keys', help='configura le chiavi API')
    sub.add_parser('status', help='cosa c\'è in input, in output e fra le chiavi')

    return parser


def resolve_dataset(args) -> tuple[Path, Path, str]:
    """Individua gli export e il prefisso dei file prodotti."""
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


def cmd_keys(_args) -> int:
    from src import setup_keys

    return setup_keys.main([])


def cmd_status(_args) -> int:
    print(f'Progetto : {config.PROJECT_ROOT}')
    print()
    print('Input:')
    for kind, pattern in config.INPUT_PATTERNS.items():
        matches = sorted(config.INPUT_DIR.glob(pattern))
        if not matches:
            print(f'  mancante  {pattern}')
        for match in matches:
            size = match.stat().st_size // 1024
            print(f'  presente  {match.name} ({size} KB)')

    print()
    print('Output:')
    produced = sorted(config.OUTPUT_DIR.rglob('*.csv')) if config.OUTPUT_DIR.is_dir() else []
    if not produced:
        print('  (vuoto)')
    for path in produced:
        print(f'  {path.relative_to(config.OUTPUT_DIR)}')

    print()
    print(f'Chiavi API (file {config.ENV_FILE.name}):')
    ignored = config.is_git_ignored(config.ENV_FILE)
    etichetta = {True: 'sì', False: 'NO — da sistemare', None: 'non verificabile'}[ignored]
    print(f'  git lo ignora: {etichetta}')
    for name, purpose, present in config.key_status():
        print(f'  {"presente" if present else "assente ":9s} {name:20s} {purpose}')
    return 0


COMMANDS = {
    'all': cmd_all,
    'merge': cmd_merge,
    'analyze': cmd_analyze,
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
        # Manca un file o ce n'è più d'uno: è una cosa da sistemare in input/,
        # non un errore del programma.
        raise SystemExit(f'\n{exc}\n') from None


if __name__ == '__main__':
    sys.exit(main())
