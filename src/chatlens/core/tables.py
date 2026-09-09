"""Reading and writing the project's tables, once.

There were five implementations of "open a CSV and give me a list of dicts" and
three of "write these rows out", differing in nothing that mattered except one
detail that did: two writers emitted a byte-order mark and the third did not, so
a file produced by one adapter and a file produced by the other were not the
same kind of file. Every reader here opens with `utf-8-sig`, which accepts both,
which is why nobody had noticed.

The functions are deliberately plain. A row is a dict, a table is a list of
them, and the whole table is in memory: these files are tens of megabytes at
most, and streaming would buy nothing but a harder-to-read pipeline.
"""

from __future__ import annotations

import csv
from pathlib import Path

# Some exports carry a whole conversation in one cell, which is past the
# default limit. Raised once, here, rather than as an import side effect in
# whichever module happened to hit it first.
csv.field_size_limit(10 ** 7)


def read(path) -> list[dict]:
    """A CSV as a list of dicts.

    `utf-8-sig` rather than `utf-8`: a file exported from Excel begins with a
    byte-order mark, and read as plain UTF-8 the first column's name silently
    acquires a `\\ufeff` prefix — so the column mapping stops matching and the
    error names a column that looks exactly right.
    """
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def columns_of(path) -> list[str]:
    """Just the header, for the pages that offer a column to choose from."""
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        return next(csv.reader(handle), [])


def union_of_keys(rows) -> list[str]:
    """Every key that appears, in the order it first appears.

    Order matters more than it looks: it is the column order of the output, and
    a set would make it depend on the hash seed — the same run twice would
    produce two different files.
    """
    columns, seen = [], set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    return columns


def write(path, rows, columns=None) -> Path:
    """Write rows as a CSV. An empty table writes an empty file."""
    path = Path(path)
    if not rows:
        path.write_text('', encoding='utf-8')
        return path
    columns = list(columns) if columns else union_of_keys(rows)
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns,
                                extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    return path
