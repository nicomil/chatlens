"""The conversations themselves: reading them, and finding a term inside them.

Every other module here turns text into numbers. This one goes the other way,
and the interface had no way of doing that at all: from a coefficient of +1.409
on «not enough» there was no path back to the eleven documents it came from, so
a reader had to take the number on trust.

Two things live here.

**Reading.** Conversations grouped as they happened, in order, with the shape of
the exchange beside them — how long it lasted, how fast the turns came. Those
figures were already being computed for every aggregation level and shown
nowhere.

**Finding.** Which messages contain a term, and — separately, because they are
different numbers and confusing them misrepresents the model — how many *units*
contain it. A term's "11 documents" are eleven units at the outcome's level, not
eleven messages, and an inspector that showed eleven messages under that
heading would be quietly wrong.
"""

from __future__ import annotations

import re
from statistics import median

from . import schema, tables


def load(path) -> list[dict]:
    """The messages table, as it was written by the merge."""
    return tables.read(path)


def conversations(messages, limit: int | None = None) -> list[dict]:
    """One entry per group, its messages in the order they were sent.

    Ordered by group so that the same study always reads the same way. Messages
    without a timestamp keep their file order, which is the merge's order and
    the best available answer.
    """
    grouped: dict[str, list[dict]] = {}
    for message in messages:
        grouped.setdefault(str(message.get('group_uid') or ''), []).append(message)

    out = []
    for group in sorted(grouped):
        bucket = grouped[group]
        ordered = sorted(
            bucket,
            key=lambda m: (schema.parse_timestamp(m.get('timestamp')) is None,
                           schema.parse_timestamp(m.get('timestamp')) or 0.0))
        out.append({
            'group': group,
            'messages': ordered,
            'treatment': str(bucket[0].get('treatment') or ''),
            'shape': shape(ordered),
        })
    return out[:limit] if limit else out


def shape(messages) -> dict:
    """How the exchange went, not what was in it.

    Duration and pace are what distinguish a conversation from a list of
    sentences, and neither had ever been on a screen.
    """
    stamps = sorted(
        t for t in (schema.parse_timestamp(m.get('timestamp'))
                    for m in messages) if t is not None)
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    words = [len(str(m.get('body') or '').split()) for m in messages]
    return {
        'messages': len(messages),
        'words': sum(words),
        'mean_words': round(sum(words) / len(words), 1) if words else 0.0,
        'duration_seconds': round(stamps[-1] - stamps[0], 1) if len(stamps) > 1 else None,
        'median_gap_seconds': round(median(gaps), 1) if gaps else None,
        'speakers': len({str(m.get('sender_id_in_group')) for m in messages}),
    }


def _pattern(term: str):
    """A term matched as words, not as a substring.

    Without the boundaries, "ok" matches "broken" and the inspector shows
    messages that had nothing to do with the coefficient the reader clicked.
    A bigram is matched with flexible whitespace, because the model saw the
    documents collapsed and the messages are not.
    """
    words = [re.escape(word) for word in str(term).split()]
    if not words:
        return None
    return re.compile(r'\b' + r'\s+'.join(words) + r'\b', re.IGNORECASE)


def find(messages, term: str, unit: str = 'group', limit: int = 40) -> dict:
    """The messages containing `term`, and how many units contain it.

    The two counts are both returned and both labelled, because they are the
    thing most likely to be misread: the models here are fitted on documents at
    one of the four aggregation levels, so a term's document count is a count
    of units. Reporting the message count under that heading would overstate
    the evidence by however many messages a unit happens to hold.
    """
    pattern = _pattern(term)
    if pattern is None:
        return {'term': term, 'messages': [], 'n_messages': 0, 'n_units': 0,
                'unit': unit, 'truncated': 0}

    keys = _unit_keys(unit)
    hits, units = [], set()
    for message in messages:
        if not pattern.search(str(message.get('body') or '')):
            continue
        hits.append(message)
        units.add(tuple(str(message.get(key) or '') for key in keys))

    return {
        'term': term,
        'messages': hits[:limit],
        'n_messages': len(hits),
        'n_units': len(units),
        'unit': unit,
        'truncated': max(0, len(hits) - limit),
    }


def _unit_keys(unit: str):
    from .aggregate import LEVEL_KEYS

    return LEVEL_KEYS.get(unit, LEVEL_KEYS['group'])


def search(messages, text: str, limit: int = 60) -> dict:
    """Free-text search over the bodies, for reading rather than for evidence."""
    return find(messages, text, limit=limit) if text.strip() else {
        'term': '', 'messages': [], 'n_messages': 0, 'n_units': 0,
        'unit': 'group', 'truncated': 0}


def highlight(body: str, term: str) -> list[tuple[str, bool]]:
    """The body split into runs, each marked as matching the term or not.

    Returned as data rather than as markup: escaping belongs to the layer that
    writes HTML, and a function here that returned `<mark>` would be a function
    that has to be trusted to escape.
    """
    pattern = _pattern(term)
    if pattern is None:
        return [(body, False)]
    parts, last = [], 0
    for match in pattern.finditer(body):
        if match.start() > last:
            parts.append((body[last:match.start()], False))
        parts.append((match.group(0), True))
        last = match.end()
    if last < len(body):
        parts.append((body[last:], False))
    return parts or [(body, False)]
