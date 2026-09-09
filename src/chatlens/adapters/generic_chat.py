"""An adapter for chat data that is already one message per row.

The oTree adapter has to reconstruct a great deal: who was in which group, who
each channel joined, what the choices meant. Most exports need none of that,
because the messages already carry a group, a sender and a recipient. For those
this adapter is enough, and no Python has to be written at all — the column
names go in `experiment.toml`.

    [experiment]
    adapter = "generic_chat"

    [input]
    messages     = "messages*.csv"
    participants = "participants*.csv"    # optional

    [columns]
    group     = "group_id"
    sender    = "sender"
    receiver  = "recipient"
    body      = "text"

What it produces is the three canonical tables of `core/schema.py`. The two
grafting tables are built from the pairs the messages themselves reveal, so
they need no separate source; a participants file, if there is one, is joined
onto the aggregated table so that treatment, payoff and any other attribute
travel with the analysis.

Two things it does **not** do, because guessing would be worse than saying so:

- it does not invent a recipient. A row without one is a message to the whole
  group, and there is no directed pair for it to belong to. Those rows are
  counted and reported, not silently attributed to somebody;
- it computes no experimental variable. Persuasion, consistency, coalition
  outcomes — those are the experiment's own, and belong in an adapter that
  knows the game.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from chatlens.core import tables

from chatlens.core import privacy, schema

# `participants` is optional: None means "use it if it is there".
INPUTS = {
    'messages': 'messages*.csv',
    'participants': None,
}
OPTIONS = ('columns',)


class AdapterError(RuntimeError):
    """The export does not hold what the configuration says it holds."""


def _read(path: Path) -> list[dict]:
    return tables.read(path)


def _get(row, columns, key, default=''):
    return str(row.get(columns.get(key, key), default) or '').strip()


def build_messages(raw, columns) -> tuple[list[dict], dict]:
    """Turn the export's rows into the canonical message table."""
    messages = []
    skipped = {'no_group': 0, 'no_sender': 0, 'no_receiver': 0, 'no_body': 0}
    per_group = defaultdict(int)
    per_dyad = defaultdict(int)

    for raw_row in raw:
        group = _get(raw_row, columns, 'group')
        sender = _get(raw_row, columns, 'sender')
        receiver = _get(raw_row, columns, 'receiver')
        body = _get(raw_row, columns, 'body')

        if not group:
            skipped['no_group'] += 1
            continue
        if not sender:
            skipped['no_sender'] += 1
            continue
        if not receiver:
            # A message to the whole group. Real, but not a directed pair.
            skipped['no_receiver'] += 1
            continue
        if not body:
            skipped['no_body'] += 1
            continue

        key = schema.dyad_key(sender, receiver)
        per_group[group] += 1
        per_dyad[(group, key)] += 1

        messages.append({
            'session_code': _get(raw_row, columns, 'session'),
            'group_uid': group,
            'treatment': _get(raw_row, columns, 'treatment'),
            'timestamp': _get(raw_row, columns, 'timestamp'),
            'sender_participant_code': _get(raw_row, columns, 'participant'),
            'sender_id_in_group': sender,
            'receiver_id_in_group': receiver,
            'dyad_key': key,
            'body': body,
            'n_words': len(body.split()),
            'n_chars': len(body),
            'msg_index_group': per_group[group],
            'msg_index_dyad': per_dyad[(group, key)],
        })
    return messages, skipped


def transcript(messages) -> str:
    """One turn per line, in the order they were sent.

    The sender is named so a transcript reads as a conversation rather than a
    wall of text. Chronological where there are timestamps, and in file order
    where there are none — an arbitrary order is still better than shuffling.
    """
    if not messages:
        return ''
    ordered = sorted(messages, key=lambda m: str(m.get('timestamp') or ''))
    return '\n'.join(
        f"{m.get('sender_id_in_group')}->{m.get('receiver_id_in_group')}: "
        f"{m.get('body') or ''}" for m in ordered)


def build_tables(messages, participants, columns):
    """The two tables the measures get grafted onto.

    Built from what the messages show rather than from a roster: a participant
    who never wrote and was never written to leaves no trace in a chat dataset,
    and inventing a row for them would put an empty conversation in the data.
    """
    treatments, sessions = {}, {}
    pairs, people = set(), set()
    # The transcript belongs on the row. Without it the built tables carry the
    # measures but not the text they were computed from, and every page that
    # needs both — which term goes with the outcome, which relation, which
    # emotion — has nothing to read. The coalition adapter has always emitted
    # it; this one did not, and the gap only showed on a walk through the
    # interface, not in any test.
    sent, received = defaultdict(list), defaultdict(list)
    for message in messages:
        group = message['group_uid']
        sender = message['sender_id_in_group']
        receiver = message['receiver_id_in_group']
        sent[(group, sender, receiver)].append(message)
        received[(group, receiver, sender)].append(message)
        pairs.add((group, sender, receiver))
        people.update({(group, sender), (group, receiver)})
        treatments.setdefault(group, message.get('treatment', ''))
        sessions.setdefault(group, message.get('session_code', ''))

    attributes = {}
    if participants:
        for row in participants:
            group = _get(row, columns, 'group')
            who = _get(row, columns, 'sender') or _get(row, columns, 'participant')
            if group and who:
                attributes[(group, who)] = row

    by_partner = [
        {
            'group_uid': group,
            'session_code': sessions.get(group, ''),
            'treatment': treatments.get(group, ''),
            'focal_id_in_group': focal,
            'partner_id_in_group': partner,
            'dyad_key': schema.dyad_key(focal, partner),
            'sent_transcript_text': transcript(sent.get((group, focal, partner))),
            'recv_transcript_text': transcript(
                received.get((group, focal, partner))),
        }
        for group, focal, partner in sorted(pairs)
    ]

    # Grouped once rather than rescanned per person: the comprehension this
    # replaces walked the whole `sent` dict for every (group, person), which is
    # quadratic in the number of pairs and was the slowest thing in the adapter
    # on a large export.
    by_sender = {}
    for (group, sender, _receiver), group_messages in sent.items():
        by_sender.setdefault((group, sender), []).extend(group_messages)

    aggregated = []
    for group, who in sorted(people):
        row = {
            'group_uid': group,
            'session_code': sessions.get(group, ''),
            'treatment': treatments.get(group, ''),
            'focal_id_in_group': who,
            # Everything this person wrote in the group, whoever it went to.
            'sent_transcript_text': transcript(by_sender.get((group, who), [])),
        }
        extra = attributes.get((group, who))
        if extra:
            # Their own columns keep their own names: this adapter does not
            # rename anybody's variables.
            row.update({k: v for k, v in extra.items() if k not in row})
        aggregated.append(row)

    return by_partner, aggregated


def write_csv(path: Path, rows) -> None:
    # Through the shared writer, which means a byte-order mark: this adapter
    # was the only one writing plain UTF-8, so its merged tables were not the
    # same kind of file as the other adapter's. Every reader here opens with
    # `utf-8-sig` and accepts both, which is why nobody had noticed.
    tables.write(path, rows)


def run(messages: Path, participants=None, outdir: Path = None,
        stem: str = 'dataset', columns=None, pseudonymise: bool = False,
        **_ignored) -> dict:
    """Read the export and write the three canonical tables."""
    columns = columns or {}
    messages_path = Path(messages)
    raw = _read(messages_path)
    if not raw:
        raise AdapterError(f'{messages_path} holds no rows.')

    declared = {columns.get(k, k) for k in ('group', 'sender', 'receiver', 'body')}
    missing = declared - set(raw[0])
    if missing:
        raise AdapterError(
            f'{messages_path} does not have the columns the configuration '
            f'names: {", ".join(sorted(missing))}.\n'
            f'  Present: {", ".join(sorted(raw[0]))}\n'
            f'  Set them under [columns] in experiment.toml.'
        )

    roster = _read(Path(participants)) if participants else []
    canonical, skipped = build_messages(raw, columns)
    if not canonical:
        raise AdapterError(
            f'No usable message in {messages_path}: '
            f'{skipped}\n'
            f'  Check that [columns] names the right columns.'
        )

    by_partner, aggregated = build_tables(canonical, roster, columns)

    pseudonymised = []
    if pseudonymise:
        key = privacy.load_or_create_key(outdir.parent)
        for table in (canonical, by_partner, aggregated):
            pseudonymised = privacy.pseudonymise_rows(table, key) or pseudonymised

    outdir.mkdir(parents=True, exist_ok=True)
    paths = dict(
        messages_long=outdir / f'{stem}_messages_long.csv',
        chat_by_partner=outdir / f'{stem}_chat_by_partner.csv',
        chat_aggregated=outdir / f'{stem}_chat_aggregated.csv',
    )
    write_csv(paths['messages_long'], canonical)
    write_csv(paths['chat_by_partner'], by_partner)
    write_csv(paths['chat_aggregated'], aggregated)

    warnings = []
    if skipped['no_receiver']:
        warnings.append(
            f"{skipped['no_receiver']} messages have no recipient and were left "
            f"out: they are addressed to the whole group, and a directed pair "
            f"is what the analysis is built on. If your chat is group-wide, "
            f"write one row per recipient before running this."
        )

    return dict(
        paths=paths,
        pseudonymised=pseudonymised,
        n_input=len(raw),
        n_participants=len(aggregated),
        n_groups=len({m['group_uid'] for m in canonical}),
        n_messages_in=len(raw),
        n_messages_resolved=len(canonical),
        skipped=skipped,
        warnings=warnings,
    )


def print_summary(summary: dict) -> None:
    skipped = summary.get('skipped') or {}
    print(f"Rows in export         : {summary['n_messages_in']}")
    for reason, label in (('no_group', 'without a group'),
                          ('no_sender', 'without a sender'),
                          ('no_receiver', 'without a recipient'),
                          ('no_body', 'with no text')):
        if skipped.get(reason):
            print(f'  left out, {label:<22}: {skipped[reason]}')
    print(f"Messages analysed      : {summary['n_messages_resolved']}")
    print(f"Groups                 : {summary['n_groups']}")
    print(f"Participants           : {summary['n_participants']}")
    if summary.get('pseudonymised'):
        print(f"Identifiers replaced   : "
              f"{len(summary['pseudonymised'])} columns")
    print()
    for path in summary['paths'].values():
        print(f'  {path}')
    import sys
    for warning in summary['warnings']:
        print(f'WARNING: {warning}', file=sys.stderr)
