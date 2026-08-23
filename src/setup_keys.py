"""
Configure the pipeline's API keys.

One command, identical on macOS, Windows and Linux:

    python run.py keys

It asks for the keys (input stays hidden), saves them in `.env` in the project
folder, checks that git really ignores that file and — on request — contacts the
services to confirm the keys work.

The file must never go under version control: the repository is public. The
script refuses to write if git is not ignoring it.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from . import config

# Keys offered during configuration, in order of importance.
PROMPTS = [
    ('OPENAI_API_KEY',
     'OpenAI — needed by TopicGPT and, if you like, by the validation rubric',
     'sk-...'),
    ('ANTHROPIC_API_KEY',
     'Anthropic — OPTIONAL: only if you prefer Claude as the rubric judge',
     'sk-ant-...'),
]

GITIGNORE_LINE = '.env'


def ensure_gitignored(path: Path) -> bool:
    """Check git ignores the file; if not, offer to add the line."""
    ignored = config.is_git_ignored(path)
    if ignored:
        return True
    if ignored is None:
        print('  git unavailable: cannot verify the file is ignored.')
        return True

    gitignore = config.PROJECT_ROOT / '.gitignore'
    print(f'\n  {path.name} is not ignored by git, and the repository is public.')
    answer = input(f'  Add "{GITIGNORE_LINE}" to .gitignore? [Y/n] ').strip().lower()
    if answer in ('n', 'no'):
        print('  Stopped: without the .gitignore line the keys risk ending up online.')
        return False

    existing = gitignore.read_text(encoding='utf-8') if gitignore.is_file() else ''
    separator = '' if existing.endswith('\n') or not existing else '\n'
    gitignore.write_text(f'{existing}{separator}{GITIGNORE_LINE}\n', encoding='utf-8')
    print(f'  Added to {gitignore}')
    return bool(config.is_git_ignored(path))


def write_secrets(path: Path, values: dict) -> None:
    lines = [
        '# API keys for the text-analysis pipeline.',
        '# Local file: never put it under version control.',
        '# Regenerate with: python run.py keys',
        '',
    ]
    lines += [f'{key}={value}' for key, value in sorted(values.items()) if value]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    if os.name == 'posix':
        path.chmod(0o600)


def _masked(value: str) -> str:
    if len(value) <= 10:
        return '*' * len(value)
    return f'{value[:6]}...{value[-4:]} ({len(value)} characters)'


def check_openai(key: str) -> tuple[bool, str]:
    request = urllib.request.Request(
        'https://api.openai.com/v1/models',
        headers={'Authorization': f'Bearer {key}'},
    )
    return _probe(request, 'OpenAI')


def check_anthropic(key: str) -> tuple[bool, str]:
    request = urllib.request.Request(
        'https://api.anthropic.com/v1/models',
        headers={'x-api-key': key, 'anthropic-version': '2023-06-01'},
    )
    return _probe(request, 'Anthropic')


def _probe(request, label: str) -> tuple[bool, str]:
    """A read-only call to confirm the key is valid."""
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode('utf-8'))
        models = payload.get('data') or []
        return True, f'{label}: key valid, {len(models)} models available'
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, f'{label}: key rejected (HTTP {exc.code})'
        return False, f'{label}: unexpected response (HTTP {exc.code})'
    except urllib.error.URLError as exc:
        return False, f'{label}: no connection ({exc.reason})'
    except (TimeoutError, OSError, ValueError) as exc:
        return False, f'{label}: check failed ({exc})'


CHECKERS = {
    'OPENAI_API_KEY': check_openai,
    'ANTHROPIC_API_KEY': check_anthropic,
}


def run_checks(values: dict) -> bool:
    print('\nChecking the keys:')
    all_ok = True
    for name, checker in CHECKERS.items():
        key = values.get(name) or os.environ.get(name, '')
        if not key.strip():
            print(f'  {name}: not configured, skipping')
            continue
        ok, message = checker(key.strip())
        print(f'  {"OK  " if ok else "FAIL"} {message}')
        all_ok = all_ok and ok
    return all_ok


def print_status() -> None:
    path = config.ENV_FILE
    config.load_env(path)
    ignored = config.is_git_ignored(path)
    ignored_label = {
        True: 'yes',
        False: 'NO — needs fixing, the repository is public',
        None: 'not verifiable',
    }[ignored]
    print(f'Key file    : {path}')
    print(f'  exists    : {"yes" if path.is_file() else "no"}')
    print(f'  git ignores it: {ignored_label}')
    print()
    for name, purpose, present in config.key_status():
        print(f'  {"present" if present else "absent "}  {name:22s} {purpose}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='check the configured keys without changing them')
    parser.add_argument('--status', action='store_true',
                        help='show what is configured and exit')
    args = parser.parse_args(argv)

    path = config.ENV_FILE
    existing = (
        config.parse_env(path.read_text(encoding='utf-8'))
        if path.is_file() else {}
    )

    if args.status:
        print_status()
        return 0

    if args.check:
        config.load_env(path)
        return 0 if run_checks(existing) else 1

    print('API key configuration')
    print(f'File: {path}\n')
    print('Paste the key and press enter. The text does not appear on screen.')
    print('Press enter on an empty line to keep the current one.\n')

    values = dict(existing)
    for name, description, hint in PROMPTS:
        current = existing.get(name, '')
        state = f'current: {_masked(current)}' if current else 'not configured'
        print(f'{description}\n  {state}')
        entered = getpass.getpass(f'  {name} ({hint}): ').strip()
        if entered:
            values[name] = entered
        print()

    if not any(values.get(name) for name, _, _ in PROMPTS):
        print('No key entered: nothing written.')
        return 1

    if not ensure_gitignored(path):
        return 1

    write_secrets(path, values)
    print(f'Saved to {path}')
    if os.name == 'posix':
        print('Permissions restricted to the owner (600).')

    ok = run_checks(values)
    print()
    if ok:
        print('All set. The pipeline will load the keys by itself:')
        print('    python run.py all --llm --topics')
    else:
        print('Some checks did not pass: see the messages above.')
        print('The keys are saved anyway; re-run with --check once fixed.')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
