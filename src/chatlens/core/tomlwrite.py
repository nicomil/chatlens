"""Writing `experiment.toml`, since `tomllib` only reads.

The standard library gained a TOML parser and no writer, so a configuration
built in the interface has to be serialised by hand. That is a small job with a
sharp edge: an escaping mistake produces a file that looks right, saves without
complaint, and fails to parse days later in front of somebody who did not write
it.

Two decisions follow from that.

**Only our own schema.** This is not a general TOML serialiser. It emits
strings, lists of strings, tables and one array of tables, which is everything
`core/experiment.py` reads and nothing more. A value it does not recognise is
refused rather than guessed at.

**The file is verified before it counts as saved.** `save()` writes to a
temporary file, reads it back with `tomllib`, compares the result with what it
meant to write, and only then puts it in place. A mismatch raises instead of
leaving a broken file where a working one used to be.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

# A key that needs no quoting, per the TOML specification.
BARE_KEY = re.compile(r'^[A-Za-z0-9_-]+$')

ESCAPES = {
    '\\': '\\\\',
    '"': '\\"',
    '\b': '\\b',
    '\t': '\\t',
    '\n': '\\n',
    '\f': '\\f',
    '\r': '\\r',
}


class TomlWriteError(RuntimeError):
    """The configuration could not be written, and why."""


def escape(value: str) -> str:
    """A TOML basic string, quotes included."""
    out = []
    for char in str(value):
        if char in ESCAPES:
            out.append(ESCAPES[char])
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            # Control characters have no literal form: \u is the only way.
            out.append(f'\\u{ord(char):04X}')
        else:
            out.append(char)
    return '"' + ''.join(out) + '"'


def key(name: str) -> str:
    """A key, quoted only where it has to be.

    Treatment names come from the data — a column value like `50/50` or
    `Condition A` is entirely possible — so quoting cannot be skipped just
    because our own keys never need it.
    """
    name = str(name)
    if not name:
        raise TomlWriteError('A key cannot be empty.')
    return name if BARE_KEY.match(name) else escape(name)


def value(item) -> str:
    if isinstance(item, str):
        return escape(item)
    if isinstance(item, bool):
        # Before int: bool is a subclass of it, and True would come out as 1.
        return 'true' if item else 'false'
    if isinstance(item, int):
        return str(item)
    if isinstance(item, (list, tuple)):
        return '[' + ', '.join(value(x) for x in item) + ']'
    raise TomlWriteError(
        f'Cannot write a value of type {type(item).__name__}: {item!r}.\n'
        f'  This writer covers the experiment schema — strings, whole numbers, '
        f'true/false and lists of strings — and nothing else.'
    )


def _table(name: str, values: dict, out: list) -> None:
    """One `[table]`, skipped entirely when it has nothing in it."""
    pairs = [(k, v) for k, v in values.items() if v not in (None, '', [], {})]
    if not pairs:
        return
    out.append(f'[{name}]')
    for k, v in pairs:
        out.append(f'{key(k)} = {value(v)}')
    out.append('')


def dumps(config: dict, header: str = '') -> str:
    """The configuration as TOML text.

    Tables come out in a fixed order — the order somebody reads them in, not
    the order a dictionary happens to hold them.
    """
    out = []
    if header:
        out += [f'# {line}' if line else '#' for line in header.splitlines()]
        out.append('')

    for name in ('experiment', 'input', 'columns', 'treatments', 'outcome',
                 'narratives', 'lexicons'):
        _table(name, config.get(name) or {}, out)

    rubric = dict(config.get('rubric') or {})
    dimensions = rubric.pop('dimensions', None)
    _table('rubric', rubric, out)
    for dimension in dimensions or []:
        out.append('[[rubric.dimensions]]')
        for k, v in dimension.items():
            if v not in (None, '', [], {}):
                out.append(f'{key(k)} = {value(v)}')
        out.append('')

    while out and out[-1] == '':
        out.pop()
    return '\n'.join(out) + '\n'


def _comparable(config: dict) -> dict:
    """The configuration as it will look once read back.

    Empty values are dropped on the way out, so they must be dropped here too
    or every comparison would fail on something that was never written.
    """
    cleaned = {}
    for name, table in config.items():
        if name == 'rubric':
            rubric = {k: v for k, v in (table or {}).items()
                      if k != 'dimensions' and v not in (None, '', [], {})}
            dimensions = [
                {k: v for k, v in d.items() if v not in (None, '', [], {})}
                for d in (table or {}).get('dimensions') or []
            ]
            if dimensions:
                rubric['dimensions'] = dimensions
            if rubric:
                cleaned[name] = rubric
            continue
        kept = {k: v for k, v in (table or {}).items()
                if v not in (None, '', [], {})}
        if kept:
            cleaned[name] = kept
    return cleaned


def save(path: Path, config: dict, header: str = '') -> Path:
    """Write the configuration, but only once it has been read back intact."""
    path = Path(path)
    text = dumps(config, header)

    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise TomlWriteError(
            f'The configuration produced a file that cannot be read back: '
            f'{exc}\n  Nothing was written.'
        ) from None

    expected = _comparable(config)
    if parsed != expected:
        # Reached only through a bug in this module, which is the case worth
        # catching: the alternative is a file that saves and breaks later.
        raise TomlWriteError(
            f'The configuration did not survive being written and read back.\n'
            f'  expected: {expected}\n'
            f'  got:      {parsed}\n'
            f'  Nothing was written.'
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)
    return path
