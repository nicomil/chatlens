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
import re
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


# Values whose *shape* is checked somewhere downstream. A Prolific id is
# twenty-four hex characters and an adapter reads `participant.label` to decide
# who is a real participant at all; replace it with `p_<digest>` and every row
# fails that check. The pipeline then runs to completion on nothing — which it
# did, on a pseudonymised copy of a real study: 8 579 messages in, none out.
HEX = re.compile(r'^[0-9a-f]+$')


def pseudonym(value: str, key: bytes) -> str:
    """A stable, keyed digest of the same shape as what it replaces.

    Same shape because a pseudonym has to survive the checks the data is
    already subject to. Where the original was hexadecimal the pseudonym is
    hexadecimal of the same length; everything else is marked `p_` so that it
    is visible as a pseudonym when nothing depends on its form.

    Not reversible without the key either way, which is the property that
    matters. Empty stays empty: an absent identifier is a fact about the row.
    """
    if not value:
        return ''
    text = str(value)
    digest = hashlib.blake2b(text.encode('utf-8'), key=key, digest_size=32)
    if HEX.match(text):
        # Repeated rather than truncated-and-padded: a value longer than the
        # digest is unusual, and quietly giving two of them the same tail
        # would collapse two people into one.
        raw = digest.hexdigest()
        return (raw * (len(text) // len(raw) + 1))[:len(text)]
    return f'p_{digest.hexdigest()[:16]}'


# What people write into a chat window that identifies them. Deliberately a
# short, high-precision list rather than a clever one: the point is to give an
# ethics submission a number it can cite, and a detector that cries wolf gets
# switched off. Nothing here is ever removed — the texts are the object of the
# analysis and altering them would change every measure — it is counted.
IN_TEXT = (
    ('an e-mail address', re.compile(r'[\w.+-]+@[\w-]+\.[\w.]{2,}')),
    ('a web address', re.compile(r'\bhttps?://\S+|\bwww\.\S+', re.I)),
    # Long runs of digits: a phone number, a student number, an IBAN fragment.
    # Short ones are offers and splits, which is most of this corpus.
    ('a long number', re.compile(r'\b\d{8,}\b')),
    ('a social handle', re.compile(r'(?<!\w)@[A-Za-z]\w{2,}')),
)


def scan_text(texts) -> dict:
    """What in these messages might identify somebody, counted not removed.

    `--pseudonymise` rewrites the identifier *columns*, and the module docstring
    is careful to say that this does not make a dataset anonymous: the messages
    are untouched, and people write their names, their towns and their jobs in
    them. That was true and unquantified, which left an ethics submission with
    nothing to say beyond "some risk".

    This gives it a figure. It finds what a pattern can find — addresses, links,
    long numbers, handles — and says nothing about names, which no regular
    expression recognises and which are the commonest case. So a count of zero
    here is not a clean bill of health, and the caller has to say so.
    """
    found = {label: 0 for label, _pattern in IN_TEXT}
    documents = flagged = 0
    for text in texts or ():
        text = str(text or '')
        if not text.strip():
            continue
        documents += 1
        hit = False
        for label, pattern in IN_TEXT:
            n = len(pattern.findall(text))
            if n:
                found[label] += n
                hit = True
        flagged += bool(hit)
    return {'documents': documents, 'documents_flagged': flagged,
            'found': {k: v for k, v in found.items() if v},
            'note': 'Patterns only. Names, places and occupations are the '
                    'commonest identifying detail in a chat message and no '
                    'pattern finds them, so zero here does not mean none.'}


def pseudonymise_rows(rows, key: bytes) -> list:
    """Replace every identifier column in place. Returns the columns touched."""
    touched = set()
    for row in rows:
        for column in list(row):
            if is_identifier(column):
                row[column] = pseudonym(row[column], key)
                touched.add(column)
    return sorted(touched)
