"""
Project paths, API keys and input file discovery.

The project is self-contained: everything it needs lives in its own folder.

    text_analysis/
        input/    the CSVs exported from oTree
        output/   whatever the pipeline produces
        src/      the code
        .env      the API keys (never under version control)

Input files are not passed on the command line: you drop them in `input/` and
they are recognised by name. That is why the procedure comes down to a single
command, and also why `input/` must contain nothing else.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

# The root is the project folder, not the experiment's: if this folder is moved
# or split off, everything keeps working.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

INPUT_DIR = PROJECT_ROOT / 'input'
OUTPUT_DIR = PROJECT_ROOT / 'output'
ENV_FILE = PROJECT_ROOT / '.env'

# Output subfolders, created when needed.
MERGED_DIR = OUTPUT_DIR / 'merged'
FEATURES_DIR = OUTPUT_DIR / 'features'
TOPICS_DIR = OUTPUT_DIR / 'topicgpt'
DATASETS_DIR = OUTPUT_DIR / 'datasets'

# How the two oTree exports are recognised among the files in input/.
INPUT_PATTERNS = {
    'wide': 'all_apps_wide*.csv',
    'chat': 'ChatMessages*.csv',
}

KNOWN_KEYS = {
    'OPENAI_API_KEY': 'TopicGPT and, optionally, the validation rubric',
    'ANTHROPIC_API_KEY': 'validation rubric (alternative to OpenAI, optional)',
    'OPENAI_BASE_URL': 'alternative OpenAI-compatible endpoint (optional)',
}


def ensure_dirs() -> None:
    for path in (INPUT_DIR, OUTPUT_DIR, MERGED_DIR, DATASETS_DIR):
        path.mkdir(parents=True, exist_ok=True)


# --- Input files -----------------------------------------------------------


class InputError(RuntimeError):
    """A problem with the files in input/, along with how to fix it."""


def find_input(kind: str, override: Path | None = None) -> Path:
    """Locate an export in `input/`, or use the path given.

    With more than one file of the same kind we do not pick at random: we ask
    which one, because taking the most recent would silently analyse a dataset
    other than the one intended.
    """
    if override is not None:
        path = Path(override).expanduser()
        if not path.is_file():
            raise InputError(f'File not found: {path}')
        return path

    pattern = INPUT_PATTERNS[kind]
    matches = sorted(INPUT_DIR.glob(pattern))
    if not matches:
        raise InputError(
            f'No "{pattern}" file in {INPUT_DIR}.\n'
            f'  Download the matching export from oTree and put it in input/.'
        )
    if len(matches) > 1:
        listing = '\n'.join(f'    {m.name}' for m in matches)
        raise InputError(
            f'More than one "{pattern}" file in input/:\n{listing}\n'
            f'  Keep only the one to analyse, or point at it with '
            f'--{kind} <path>.'
        )
    return matches[0]


def dataset_stem(wide_path: Path) -> str:
    """Prefix of the files produced: the export name without its extension."""
    return wide_path.stem


# --- API keys --------------------------------------------------------------


def parse_env(text: str) -> dict:
    """Read a ``KEY=value`` file.

    Tolerates the ``export`` prefix, quotes and comments, so a file copied from
    instructions found elsewhere still works.
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
    """True if git ignores the file, None if git cannot be used here."""
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
            f'\nWARNING: {path.name} is NOT ignored by git.\n'
            f'  Add ".env" to .gitignore before making any commit.\n',
            file=sys.stderr,
        )
    if os.name == 'posix' and path.exists():
        if path.stat().st_mode & (stat.S_IRGRP | stat.S_IROTH):
            print(
                f'WARNING: {path.name} is readable by other users. '
                f'Fix with: chmod 600 {path}',
                file=sys.stderr,
            )


def load_env(path: Path | None = None) -> list[str]:
    """Load the keys into the environment. Returns the names taken from file.

    An environment variable already set takes precedence: whoever manages their
    keys their own way is not overridden.
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
    """Return the key, or exit with instructions you can act on."""
    value = os.environ.get(name, '').strip()
    if value:
        return value
    purpose = KNOWN_KEYS.get(name, 'this stage of the pipeline')
    raise SystemExit(
        f'\nMissing {name}, required for {purpose}.\n\n'
        f'To configure it:\n'
        f'    python run.py keys\n\n'
        f'It is saved in {ENV_FILE.name}, which git ignores.\n'
    )


def key_status() -> list[tuple[str, str, bool]]:
    return [(name, purpose, has_key(name)) for name, purpose in KNOWN_KEYS.items()]
