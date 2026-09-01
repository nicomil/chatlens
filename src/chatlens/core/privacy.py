"""Replacing participant identifiers with stable pseudonyms.

The outputs carry whatever the experiment's export carried, and for an online
study that includes the recruitment platform's participant id — a value that
follows the same person across every study they have ever taken part in. It has
no analytical use: what the analysis needs is to tell participants apart, not to
know who they are.

Pseudonymising replaces each identifier with a keyed hash. Two properties make
it usable rather than merely safe:

- **stable within a workspace**, so a pseudonym means the same person across
  runs, across the three output tables, and across a re-run months later. The
  key lives in the workspace and never in the data;
- **not reversible without the key**, which is a single file. Delete it and the
  link is gone for good — which is the point, and also the thing to be sure
  about before deleting it.

This does not make a dataset anonymous, and saying so would be wrong. The chat
texts are untouched, and people write their names, their towns and their jobs
in them. Treat the output as pseudonymised personal data, which is what it is.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path

SALT_FILE = '.pseudonym_key'

# Exact column names carrying an identifier, and suffixes that catch the same
# thing wherever a table renames it.
IDENTIFIER_COLUMNS = {
    'participant.label',
    'participant.code',
    'participant.prolific_id',
    'participant.prolific_study_id',
    'participant.prolific_session_id',
    'participant_code',
    'sender_participant_code',
    'partner_participant_code',
    'prolific_pid',
}

IDENTIFIER_SUFFIXES = (
    '_participant_code',
    '_prolific_id',
    '_prolific_pid',
)


def is_identifier(column: str) -> bool:
    return (column in IDENTIFIER_COLUMNS
            or column.endswith(IDENTIFIER_SUFFIXES))


def load_or_create_key(outdir: Path) -> bytes:
    """The workspace's key, created once and then reused.

    Kept beside the output rather than inside it: it is the one file that must
    not travel with the data it unlocks.
    """
    path = Path(outdir) / SALT_FILE
    if path.is_file():
        return path.read_bytes().strip()

    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(32).encode('ascii')
    path.write_bytes(key + b'\n')
    if os.name == 'posix':
        path.chmod(0o600)
    return key


def pseudonym(value: str, key: bytes) -> str:
    """A short, stable, keyed digest. Empty stays empty."""
    if not value:
        return ''
    digest = hashlib.blake2b(str(value).encode('utf-8'), key=key, digest_size=8)
    return f'p_{digest.hexdigest()}'


def pseudonymise_rows(rows, key: bytes) -> list:
    """Replace every identifier column in place. Returns the columns touched."""
    touched = set()
    for row in rows:
        for column in list(row):
            if is_identifier(column):
                row[column] = pseudonym(row[column], key)
                touched.add(column)
    return sorted(touched)
