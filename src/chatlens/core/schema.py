"""The contract between an adapter and the core.

An adapter reads one experiment's export and writes three tables. The core
reads those three tables and knows nothing else. That boundary already existed
— it was simply never written down, which meant a wrong column surfaced as a
`KeyError` several stages later, on a machine belonging to someone who had no
way of knowing what the column was for.

The three tables:

``messages_long``
    One row per message. This is what the measures, the rubric and the topics
    are computed from, so it is the one that has to be right.

``chat_by_partner``
    One row per ordered pair *i → j* within a group. The core grafts the
    directed-pair measures onto it; everything else in the row belongs to the
    experiment and is passed through untouched.

``chat_aggregated``
    One row per participant, treated the same way.

Only the columns below are the core's business. An adapter may add as many of
its own as it likes — the coalition-formation one adds about forty, and none of
them means anything here.

Units of analysis
-----------------
The four levels are cut out of the same two identifiers, ``group_uid`` and
``*_id_in_group``. That is why a group can have any size: nothing in the core
counts the members, and a group of two or of nine aggregates the same way.

The one real assumption is that a message has **one sender and one receiver**.
A broadcast to the whole group has no directed pair to belong to, so an adapter
facing group-wide chat has to decide what to do with it — usually writing one
row per recipient, which is what makes ``dyad_directed`` meaningful.
"""

from __future__ import annotations


class SchemaError(RuntimeError):
    """A table does not carry what the core needs, and what to do about it."""


# --- messages_long ---------------------------------------------------------

# Without these the core cannot do its job at all.
MESSAGES_REQUIRED = {
    'group_uid': 'identifies the conversation group; any string, unique per '
                 'group across the whole dataset',
    'sender_id_in_group': 'who wrote the message, as a position inside the '
                          'group (1, 2, 3, ...)',
    'receiver_id_in_group': 'who it was addressed to, same numbering',
    'body': 'the text of the message',
}

# Used where present, and quietly done without where absent. The core states in
# the report which measures it could not compute rather than guessing.
MESSAGES_OPTIONAL = {
    'dyad_key': 'the unordered pair, e.g. "1-2"; derived from the two ids '
                'when missing',
    'treatment': 'experimental condition, used to break the report down',
    'timestamp': 'seconds since the epoch, or ISO 8601; without it there are '
                 'no durations and no ordering by time',
    'session_code': 'the experimental session, for tracing back',
    'channel': 'the chat channel the message came from',
    'sender_color': 'label shown to participants for the sender; used to '
                    'render transcripts the way they were seen',
    'receiver_color': 'the same for the receiver',
    'sender_role': 'a stable role name, if the experiment has one',
    'receiver_role': 'the same for the receiver',
}

# --- the two tables the measures are grafted onto --------------------------

# These are the join keys, and the only columns the core reads there.
BY_PARTNER_KEYS = ('group_uid', 'focal_id_in_group', 'partner_id_in_group')
AGGREGATED_KEYS = ('group_uid', 'focal_id_in_group')


def dyad_key(a, b) -> str:
    """The unordered pair as a string, so that i→j and j→i agree on it."""
    first, second = sorted((str(a), str(b)))
    return f'{first}-{second}'


def parse_timestamp(value):
    """A moment in time, as a float, or None.

    The canonical form is seconds since the epoch, because that is what oTree
    exports and what the durations are arithmetic on. ISO 8601 is accepted too:
    it is what most other tools write, and refusing it would push every adapter
    into converting the same thing in the same way.
    """
    text = str(value or '').strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    try:
        from datetime import datetime
        # 'Z' is valid ISO 8601 and fromisoformat only learned it in 3.11;
        # normalising costs nothing and removes the version question.
        return datetime.fromisoformat(text.replace('Z', '+00:00')).timestamp()
    except (ValueError, OSError):
        return None


def _quote(names) -> str:
    return ', '.join(sorted(names))


def validate_messages(rows, source='messages_long') -> list[str]:
    """Check the message table. Returns the optional columns that are missing.

    Raises when a required column is absent, because there is nothing sensible
    to do without one and finding out three stages later helps nobody.
    """
    if not rows:
        raise SchemaError(
            f'{source} holds no rows.\n'
            f'  Either no message survived the filters, or the adapter wrote '
            f'an empty table.'
        )

    present = set(rows[0])
    missing = [c for c in MESSAGES_REQUIRED if c not in present]
    if missing:
        explained = '\n'.join(f'    {c}: {MESSAGES_REQUIRED[c]}'
                              for c in missing)
        raise SchemaError(
            f'{source} is missing columns the analysis cannot do without:\n'
            f'{explained}\n\n'
            f'  Present: {_quote(present)}\n\n'
            f'  These come from the adapter. See chatlens/core/schema.py for '
            f'the full contract.'
        )

    empty = [c for c in MESSAGES_REQUIRED
             if all(not str(r.get(c, '')).strip() for r in rows)]
    if empty:
        raise SchemaError(
            f'{source} has {_quote(empty)} present but empty on every row.\n'
            f'  A column that is there and blank is worse than one that is '
            f'absent: it looks like data.'
        )

    return [c for c in MESSAGES_OPTIONAL if c not in present]


def validate_join_keys(rows, keys, source) -> None:
    """Check a table the measures will be grafted onto."""
    if not rows:
        return
    missing = [c for c in keys if c not in rows[0]]
    if missing:
        raise SchemaError(
            f'{source} is missing the join columns {_quote(missing)}.\n'
            f'  Without them the measures cannot be attached to the right '
            f'row, and attaching them to the wrong one would be worse than '
            f'not attaching them at all.'
        )


def fill_derived(rows) -> None:
    """Fill in what can be worked out, so an adapter need not repeat it."""
    for row in rows:
        if not row.get('dyad_key'):
            sender = row.get('sender_id_in_group', '')
            receiver = row.get('receiver_id_in_group', '')
            if sender and receiver:
                row['dyad_key'] = dyad_key(sender, receiver)
