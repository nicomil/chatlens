"""Looking at a CSV to work out what its columns are for.

The configuration needs to know which column holds the group, which the sender,
which the text. Asking someone to type those names means asking them to open
the file, find the header, and copy it without a typo — and a typo there
surfaces much later as an adapter error about a column that does not exist.

So the file is read instead. The header gives the choices, a guess by name puts
the likely one in front, and the treatment column's own values become the
labels. Nothing here decides anything: it prepares a form somebody confirms.

Only the header and a bounded sample are read. These files reach tens of
megabytes and this runs while somebody waits for a page.
"""

from __future__ import annotations

import csv
from pathlib import Path

# How much of a file to look at when collecting a column's distinct values.
SAMPLE_ROWS = 50_000
MAX_DISTINCT = 40

# What a column called this is probably for. Order within a list matters: the
# earlier a name, the better the match.
SYNONYMS = {
    'group': ('group', 'group_id', 'groupid', 'team', 'room', 'match',
              'session', 'triad', 'dyad', 'pair'),
    'sender': ('sender', 'from', 'author', 'speaker', 'writer', 'source',
               'sender_id', 'from_id', 'participant'),
    'receiver': ('receiver', 'recipient', 'to', 'target', 'addressee',
                 'destination', 'receiver_id', 'to_id'),
    'body': ('body', 'text', 'message', 'content', 'msg', 'chat', 'utterance'),
    'timestamp': ('timestamp', 'time', 'sent_at', 'date', 'datetime', 'when',
                  'created', 'created_at'),
    'treatment': ('treatment', 'condition', 'arm', 'cell', 'variant',
                  'manipulation'),
    'session': ('session', 'session_code', 'wave', 'batch'),
    'participant': ('participant', 'participant_code', 'subject', 'player_id'),
}


class ReadError(RuntimeError):
    """The file could not be read, said in terms worth showing."""


def header_of(path: Path) -> list[str]:
    """The column names, and nothing else read."""
    path = Path(path)
    try:
        with path.open(encoding='utf-8-sig', newline='') as handle:
            row = next(csv.reader(handle), None)
    except OSError as exc:
        raise ReadError(f'{path.name} could not be opened: {exc}') from None
    except UnicodeDecodeError:
        raise ReadError(
            f'{path.name} is not readable as text. A CSV saved as UTF-8 is '
            f'what this expects; a spreadsheet exported as "CSV UTF-8" gives '
            f'that.') from None

    if not row:
        raise ReadError(f'{path.name} is empty.')
    names = [name.strip() for name in row]
    if not any(names):
        raise ReadError(f'{path.name} has no column names in its first row.')
    return names


def _score(role: str, column: str) -> int:
    """How well a column name fits a role. Higher is better, 0 is no fit."""
    name = column.strip().lower().replace(' ', '_')
    synonyms = SYNONYMS.get(role, (role,))

    for position, synonym in enumerate(synonyms):
        if name == synonym:
            # An exact match, best for the earliest synonym.
            return 1000 - position
    for position, synonym in enumerate(synonyms):
        # A suffix beats a prefix: `msg_body` is a body, `body_length` is not.
        if name.endswith(synonym):
            return 500 - position
        if name.startswith(synonym) or synonym in name:
            return 200 - position
    return 0


def guess(columns, roles=('group', 'sender', 'receiver', 'body', 'timestamp',
                          'treatment')) -> dict:
    """A column for each role, where one looks likely.

    A column is used once: without that, `group` and `treatment` both claim a
    column called "group" and the form comes up with the same answer twice.
    Roles are resolved best-match-first rather than in list order, so the
    confident ones take their column before the doubtful ones get a chance.
    """
    scored = []
    for role in roles:
        for column in columns:
            points = _score(role, column)
            if points:
                scored.append((points, role, column))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))

    chosen, taken = {}, set()
    for _points, role, column in scored:
        if role in chosen or column in taken:
            continue
        chosen[role] = column
        taken.add(column)
    return chosen


def distinct(path: Path, column: str, limit: int = MAX_DISTINCT) -> list[str]:
    """The values a column takes, in the order they first appear.

    Bounded twice — rows read and values kept — because this runs while a page
    is loading and the column might turn out to be the message text.
    """
    path = Path(path)
    if not column:
        return []
    seen = []
    try:
        with path.open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            if column not in (reader.fieldnames or []):
                return []
            for index, row in enumerate(reader):
                if index >= SAMPLE_ROWS:
                    break
                value = (row.get(column) or '').strip()
                if value and value not in seen:
                    seen.append(value)
                    if len(seen) > limit:
                        # Too many to be a treatment: say so by returning
                        # nothing rather than by offering forty text boxes.
                        return []
    except (OSError, UnicodeDecodeError, csv.Error):
        return []
    return seen
