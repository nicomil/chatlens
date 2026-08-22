"""
Percorsi del progetto, chiavi API e riconoscimento dei file di input.

Il progetto è autonomo: tutto quello che gli serve sta nella sua cartella.

    text_analysis/
        input/    i CSV esportati da oTree
        output/   quello che la pipeline produce
        src/      il codice
        .env      le chiavi API (mai sotto controllo di versione)

I file di input non si passano da riga di comando: si mettono in `input/` e
vengono riconosciuti dal nome. È il motivo per cui la procedura si riduce a un
comando solo, ed è anche il motivo per cui `input/` non deve contenere altro.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

# La radice è la cartella del progetto, non quella dell'esperimento: se questa
# cartella viene spostata o separata, continua a funzionare.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

INPUT_DIR = PROJECT_ROOT / 'input'
OUTPUT_DIR = PROJECT_ROOT / 'output'
ENV_FILE = PROJECT_ROOT / '.env'

# Sottocartelle di output, create quando servono.
MERGED_DIR = OUTPUT_DIR / 'merged'
FEATURES_DIR = OUTPUT_DIR / 'features'
TOPICS_DIR = OUTPUT_DIR / 'topicgpt'
DATASETS_DIR = OUTPUT_DIR / 'datasets'

# Come si riconoscono i due export di oTree fra i file in input/.
INPUT_PATTERNS = {
    'wide': 'all_apps_wide*.csv',
    'chat': 'ChatMessages*.csv',
}

KNOWN_KEYS = {
    'OPENAI_API_KEY': 'TopicGPT e, volendo, la rubrica di validazione',
    'ANTHROPIC_API_KEY': 'rubrica di validazione (alternativa a OpenAI, facoltativa)',
    'OPENAI_BASE_URL': 'endpoint alternativo compatibile OpenAI (facoltativo)',
}


def ensure_dirs() -> None:
    for path in (INPUT_DIR, OUTPUT_DIR, MERGED_DIR, DATASETS_DIR):
        path.mkdir(parents=True, exist_ok=True)


# --- File di input ---------------------------------------------------------


class InputError(RuntimeError):
    """Problema con i file in input/, con l'istruzione per risolverlo."""


def find_input(kind: str, override: Path | None = None) -> Path:
    """Individua un export in `input/`, o usa il percorso indicato.

    Con più file dello stesso tipo non si sceglie a caso: si chiede quale,
    perché prendere il più recente porterebbe ad analizzare in silenzio un
    dataset diverso da quello inteso.
    """
    if override is not None:
        path = Path(override).expanduser()
        if not path.is_file():
            raise InputError(f'File non trovato: {path}')
        return path

    pattern = INPUT_PATTERNS[kind]
    matches = sorted(INPUT_DIR.glob(pattern))
    if not matches:
        raise InputError(
            f'Nessun file "{pattern}" in {INPUT_DIR}.\n'
            f'  Scarica da oTree l\'export corrispondente e mettilo in input/.'
        )
    if len(matches) > 1:
        elenco = '\n'.join(f'    {m.name}' for m in matches)
        raise InputError(
            f'Più file "{pattern}" in input/:\n{elenco}\n'
            f'  Lascia solo quello da analizzare, oppure indicalo con '
            f'--{kind} <percorso>.'
        )
    return matches[0]


def dataset_stem(wide_path: Path) -> str:
    """Prefisso dei file prodotti: il nome dell'export senza estensione."""
    return wide_path.stem


# --- Chiavi API ------------------------------------------------------------


def parse_env(text: str) -> dict:
    """Legge un file ``CHIAVE=valore``.

    Tollera il prefisso ``export``, le virgolette e i commenti, così un file
    copiato da istruzioni trovate altrove funziona comunque.
    """
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[len('export '):].strip()
        if '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def is_git_ignored(path: Path) -> bool | None:
    """True se git ignora il file, None se git non è utilizzabile qui."""
    try:
        result = subprocess.run(
            ['git', 'check-ignore', '-q', str(path)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode in (0, 1):
        return result.returncode == 0
    return None


def _warn_if_exposed(path: Path) -> None:
    if is_git_ignored(path) is False:
        print(
            f'\nATTENZIONE: {path.name} NON è ignorato da git.\n'
            f'  Aggiungi ".env" al .gitignore prima di fare qualunque commit.\n',
            file=sys.stderr,
        )
    if os.name == 'posix' and path.exists():
        if path.stat().st_mode & (stat.S_IRGRP | stat.S_IROTH):
            print(
                f'ATTENZIONE: {path.name} è leggibile da altri utenti. '
                f'Correggi con: chmod 600 {path}',
                file=sys.stderr,
            )


def load_env(path: Path | None = None) -> list[str]:
    """Carica le chiavi nell'ambiente. Restituisce i nomi presi dal file.

    Una variabile d'ambiente già impostata ha la precedenza: chi gestisce le
    chiavi a modo proprio non viene scavalcato.
    """
    path = path or ENV_FILE
    if not path.is_file():
        return []

    _warn_if_exposed(path)

    loaded = []
    for key, value in parse_env(path.read_text(encoding='utf-8')).items():
        if value and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def has_key(name: str) -> bool:
    return bool(os.environ.get(name, '').strip())


def require_key(name: str) -> str:
    """Restituisce la chiave o esce con istruzioni utilizzabili."""
    value = os.environ.get(name, '').strip()
    if value:
        return value
    purpose = KNOWN_KEYS.get(name, 'questo stadio della pipeline')
    raise SystemExit(
        f'\nManca la chiave {name}, necessaria per {purpose}.\n\n'
        f'Per configurarla:\n'
        f'    python run.py keys\n\n'
        f'Viene salvata in {ENV_FILE.name}, che git ignora.\n'
    )


def key_status() -> list[tuple[str, str, bool]]:
    return [(name, purpose, has_key(name)) for name, purpose in KNOWN_KEYS.items()]
