"""Workspace paths, API keys and input file discovery.

An installed tool cannot write inside its own package directory, and two
different experiments must not overwrite each other's results. Both problems
have the same answer: the code lives wherever pip put it, and the data lives in
a **workspace** — an ordinary folder the researcher owns.

    my_experiment/          <- the workspace
        input/              the exports to analyse
        output/             everything the pipeline produces
        .env                API keys, if you prefer them per project

The workspace is the current directory unless one is named, so running
``chatlens all`` inside a project folder does what it looks like it does. It can
also be set with ``--workspace`` or with ``CHATLENS_WORKSPACE``.

Input files are not passed on the command line: you drop them in ``input/`` and
they are recognised by name. That is why the procedure comes down to a single
command, and also why ``input/`` must contain nothing else.

The paths below are module attributes rather than an object passed from hand to
hand, and ``use_workspace()`` rebinds them. Every caller reads them as
``config.OUTPUT_DIR`` at the moment of use, so switching workspace switches all
of them at once, and a process only ever has one.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

APP_NAME = 'chatlens'

# --- Workspace -------------------------------------------------------------

# Rebound by use_workspace(). The defaults let an import-only user (a test, a
# notebook) read the module without having chosen anything yet.
WORKSPACE = Path.cwd()
INPUT_DIR = WORKSPACE / 'input'
OUTPUT_DIR = WORKSPACE / 'output'
MERGED_DIR = OUTPUT_DIR / 'merged'
FEATURES_DIR = OUTPUT_DIR / 'features'
TOPICS_DIR = OUTPUT_DIR / 'topicgpt'
DATASETS_DIR = OUTPUT_DIR / 'datasets'

# Kept under its old name so that nothing downstream had to be rewritten: it is
# the workspace, not the folder the code was installed into.
PROJECT_ROOT = WORKSPACE

ENV_FILE = WORKSPACE / '.env'


def user_config_dir() -> Path:
    """Where this machine expects an application to keep its settings.

    Three lines instead of a dependency, because the conventions are stable and
    we need exactly one path out of them.
    """
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming'
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config'
    return Path(base) / APP_NAME


def user_env_file() -> Path:
    """The keys file shared by every workspace on this machine."""
    return user_config_dir() / 'keys.env'


def user_data_dir() -> Path:
    """Where this machine expects an application to keep large local files."""
    if sys.platform == 'win32':
        base = (os.environ.get('LOCALAPPDATA')
                or Path.home() / 'AppData' / 'Local')
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share'
    return Path(base) / APP_NAME


def topicgpt_repo() -> Path:
    """The cloned TopicGPT repository, which holds the method's prompt files.

    One place decides where it lives, so the dashboard and the command line
    cannot disagree about it — they used to, and the dashboard's answer was a
    path hard-coded to one developer's home directory.
    """
    override = os.environ.get('CHATLENS_TOPICGPT_REPO', '').strip()
    if override:
        return Path(override).expanduser()
    return user_data_dir() / 'topicGPT'


def resolve_workspace(explicit=None) -> Path:
    """Which folder holds the data: what was asked for, then the environment,
    then the current directory."""
    if explicit:
        return Path(explicit).expanduser().resolve()
    from_env = os.environ.get('CHATLENS_WORKSPACE', '').strip()
    if from_env:
        return Path(from_env).expanduser().resolve()
    return Path.cwd().resolve()


def use_workspace(root) -> Path:
    """Point every path at `root`. Returns the workspace resolved."""
    global WORKSPACE, PROJECT_ROOT, INPUT_DIR, OUTPUT_DIR
    global MERGED_DIR, FEATURES_DIR, TOPICS_DIR, DATASETS_DIR, ENV_FILE

    WORKSPACE = Path(root).expanduser().resolve()
    PROJECT_ROOT = WORKSPACE
    INPUT_DIR = WORKSPACE / 'input'
    OUTPUT_DIR = WORKSPACE / 'output'
    MERGED_DIR = OUTPUT_DIR / 'merged'
    FEATURES_DIR = OUTPUT_DIR / 'features'
    TOPICS_DIR = OUTPUT_DIR / 'topicgpt'
    DATASETS_DIR = OUTPUT_DIR / 'datasets'

    # A .env in the workspace wins: whoever keeps their keys per project keeps
    # doing so, and the project this tool grew out of goes on working unchanged.
    workspace_env = WORKSPACE / '.env'
    ENV_FILE = workspace_env if workspace_env.is_file() else user_env_file()
    return WORKSPACE


# How the files in input/ are recognised, as role -> filename pattern. Set from
# the active adapter by use_experiment(); the default is the oTree coalition
# adapter, which is what a workspace with no experiment.toml gets.
INPUT_PATTERNS = {
    'wide': 'all_apps_wide*.csv',
    'chat': 'ChatMessages*.csv',
}

# The workspace's experiment.toml, or the defaults. Set by use_experiment().
EXPERIMENT = None


def use_experiment(experiment) -> None:
    """Adopt an experiment: its adapter decides what input/ should hold."""
    global EXPERIMENT, INPUT_PATTERNS

    from chatlens import adapters

    EXPERIMENT = experiment

    # An adapter knows what its own experiment calls things. The workspace's
    # file wins where it says something; where it is silent, these do.
    module = adapters.load(experiment.adapter)
    if not experiment.treatments:
        experiment.treatments = dict(getattr(module, 'TREATMENT_LABELS', {}))
    if experiment.group_noun == 'group':
        experiment.group_noun = getattr(module, 'GROUP_NOUN', 'group')
        experiment.group_target = getattr(
            module, 'GROUP_TARGET', f'everyone in the {experiment.group_noun}')

    patterns = adapters.inputs(experiment.adapter)
    # The workspace may rename its own files; roles it does not mention keep
    # the adapter's pattern.
    for role, pattern in (experiment.input or {}).items():
        if role in patterns:
            patterns[role] = pattern
    INPUT_PATTERNS = patterns

KNOWN_KEYS = {
    'OPENAI_API_KEY': 'TopicGPT and, optionally, the validation rubric',
    'ANTHROPIC_API_KEY': 'validation rubric (alternative to OpenAI, optional)',
    'OPENAI_BASE_URL': 'alternative OpenAI-compatible endpoint (optional)',
}


def ensure_dirs() -> None:
    for path in (INPUT_DIR, OUTPUT_DIR, MERGED_DIR, DATASETS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def cache_dir(stem: str) -> Path:
    """Rubric cache for one dataset.

    Scoped by dataset: two experiments in the same workspace would otherwise
    share one cache file, and the only thing keeping their ratings apart would
    be the hash of the transcript text.
    """
    return OUTPUT_DIR / 'cache' / stem


def topics_dir(stem: str) -> Path:
    """TopicGPT's working directory for one dataset.

    Scoped for the same reason, and more urgently: TopicGPT writes fixed names
    (`generation_1.md`, `assignment.jsonl`), so a second dataset used to
    overwrite the first one's topics outright.
    """
    return OUTPUT_DIR / 'topicgpt' / stem


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
    if pattern is None:
        raise InputError(f'The "{kind}" file is optional and was not given.')

    matches = sorted(INPUT_DIR.glob(pattern))
    if not matches:
        raise InputError(
            f'No "{pattern}" file in {INPUT_DIR}.\n'
            f'  Export it from your experiment and put it in input/, or point '
            f'at it with --input {kind}=<path>.'
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
    parent = path.parent if path.parent.is_dir() else WORKSPACE
    try:
        result = subprocess.run(
            ['git', 'check-ignore', '-q', str(path)],
            cwd=str(parent),
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode in (0, 1):
        return result.returncode == 0
    return None


def _warn_if_exposed(path: Path) -> None:
    # Only a file inside a repository can be committed by accident. The one in
    # the user configuration directory is outside any repository by
    # construction, which is the whole point of keeping it there.
    if is_git_ignored(path) is False:
        print(
            f'\nWARNING: {path.name} is NOT ignored by git.\n'
            f'  Add ".env" to .gitignore before making any commit,\n'
            f'  or move the keys out of the repository with: chatlens keys\n',
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
    keys their own way is not overridden. The shared file is read first and the
    workspace one second, so a project can carry a key of its own without
    disturbing the machine-wide default.
    """
    if path is not None:
        candidates = [Path(path)]
    else:
        candidates = [user_env_file(), WORKSPACE / '.env']

    loaded = []
    for candidate in candidates:
        if not candidate.is_file():
            continue
        _warn_if_exposed(candidate)
        for key, value in parse_env(candidate.read_text(encoding='utf-8')).items():
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
        f'    chatlens keys\n\n'
        f'It is saved in {user_env_file()}, outside any repository.\n'
    )


def key_status() -> list[tuple[str, str, bool]]:
    return [(name, purpose, has_key(name)) for name, purpose in KNOWN_KEYS.items()]
