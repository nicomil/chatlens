"""Who spoke to whom at all — including the pairs where nobody did.

On the experiment this tool was built for, the strongest result in the dataset
was not in the text. It was in the cells with no text: holding the receiver
fixed, when only one of their two partners had written to them, they chose that
one 357 times against 35. Whether you address someone at all separated the
outcome better than anything extracted from what was said once you did.

Those cells are invisible to a chat dataset by construction. A row is built from
a message, so a pair who never exchanged one leaves no row, and every text
measure is therefore computed on a sample **conditional on having spoken** — a
selection that is easy to forget precisely because it never appears.

This module reconstructs the complete grid: for every group, every ordered pair
of its members, whether or not anything passed between them.

Where the membership comes from, and what that costs
----------------------------------------------------
The grid needs to know who was in each group, which the messages alone cannot
say: someone who never wrote and was never written to leaves no trace at all.
Three sources, in order of preference, and the page states which one was used.

**The aggregated dataset** the pipeline builds, one row per person per group.
Where the adapter knows the roster it puts it here, so this sees everybody.

**A participants file**, when the experiment declares one and the aggregated
dataset is not there yet.

**The messages themselves** otherwise — everyone who sent or received in that
group. This finds every pair where at least one direction was used, but it
cannot see a member who said nothing to anyone and to whom nobody spoke, and the
error is not small or random. On the coalition data it turned 82 of 503 triads
into pairs, dropped 328 of the 3,018 directed cells, and moved the headline
comparison from 357-against-35 to 215-against-29. It removes exactly the people
the analysis is about, so it is reported at the top of the page rather than
mentioned in a footnote.
"""

from __future__ import annotations

from collections import Counter, defaultdict


def membership(messages, participants=None, roster=None) -> tuple[dict, str]:
    """Who was in each group, and which source said so.

    ``roster`` is the aggregated dataset, one row per person per group. It is
    preferred over everything else because it is the only source that has been
    through the adapter, which is where knowledge of who took part lives.
    """
    if roster:
        groups = defaultdict(set)
        for row in roster:
            group = row.get('group_uid')
            who = row.get('focal_id_in_group') or row.get('sender_id_in_group')
            if group and who not in (None, ''):
                groups[group].add(str(who))
        if groups:
            return dict(groups), 'the aggregated dataset'

    groups = defaultdict(set)
    for message in messages:
        group = message.get('group_uid')
        if not group:
            continue
        for role in ('sender_id_in_group', 'receiver_id_in_group'):
            who = message.get(role)
            if who not in (None, ''):
                groups[group].add(str(who))

    source = 'the messages'
    if participants:
        # A roster only helps if it names the same groups; one keyed on
        # something else would quietly produce groups of one.
        extra = defaultdict(set)
        for row in participants:
            group = row.get('group_uid')
            who = row.get('sender_id_in_group') or row.get('focal_id_in_group')
            if group and who not in (None, ''):
                extra[group].add(str(who))
        if extra and set(extra) & set(groups):
            for group, people in extra.items():
                groups[group] |= people
            source = 'the participants file'

    return dict(groups), source


def grid(messages, members) -> dict:
    """Every ordered pair of every group, with how much passed along it."""
    counts = Counter()
    words = Counter()
    for message in messages:
        key = (message.get('group_uid'), str(message.get('sender_id_in_group')),
               str(message.get('receiver_id_in_group')))
        counts[key] += 1
        words[key] += len(str(message.get('body') or '').split())

    cells = {}
    for group, people in members.items():
        for sender in people:
            for receiver in people:
                if sender == receiver:
                    continue
                key = (group, sender, receiver)
                cells[key] = {'messages': counts.get(key, 0),
                              'words': words.get(key, 0)}
    return cells


def coverage(cells, members) -> dict:
    """How much of the possible communication actually happened."""
    used = sum(1 for c in cells.values() if c['messages'])
    per_group = Counter()
    for (group, _s, _r), cell in cells.items():
        if cell['messages']:
            per_group[group] += 1

    sizes = Counter(len(people) for people in members.values())
    possible_by_group = {g: len(p) * (len(p) - 1) for g, p in members.items()}
    silent_groups = [g for g in members if not per_group.get(g)]

    return {
        'groups': len(members),
        'cells': len(cells),
        'used': used,
        'empty': len(cells) - used,
        'share_used': used / len(cells) if cells else 0.0,
        'group_sizes': sorted(sizes.items()),
        'per_group': per_group,
        'possible_by_group': possible_by_group,
        'silent_groups': len(silent_groups),
        'directions_histogram': sorted(
            Counter(per_group.get(g, 0) for g in members).items()),
    }


def contrast(cells, outcomes) -> dict | None:
    """The outcome where someone wrote, against where they did not.

    ``outcomes`` maps (group, sender, receiver) to 0 or 1. Cells with no outcome
    are counted and excluded rather than treated as zero.

    This is the raw comparison, and it is **not** the finding. A receiver who can
    choose only one of several partners bounds the rate mechanically, and people
    who write a lot may simply be different people. It is reported because it is
    the obvious thing to look at, with the caution attached, and
    :func:`within_receiver` is what removes both objections.
    """
    wrote = [0, 0]
    silent = [0, 0]
    unknown = 0
    for key, cell in cells.items():
        value = outcomes.get(key)
        if value is None:
            unknown += 1
            continue
        bucket = wrote if cell['messages'] else silent
        bucket[0] += 1
        bucket[1] += int(value)

    if not wrote[0] or not silent[0]:
        return None
    return {
        'wrote': {'n': wrote[0], 'positive': wrote[1],
                  'share': wrote[1] / wrote[0]},
        'silent': {'n': silent[0], 'positive': silent[1],
                   'share': silent[1] / silent[0]},
        'unknown': unknown,
    }


def within_receiver(cells, outcomes) -> dict | None:
    """The same comparison with the receiver held fixed.

    For each receiver, look at the senders who could have written to them. Where
    exactly one did, and the outcome is positive for exactly one of the
    candidates, the two differ in whether they spoke and in nothing else — not in
    who they were facing, not in the group, not in the treatment.

    Returns None when the design cannot support it: a receiver with fewer than
    two possible senders has nothing to compare, and saying so is better than
    producing a number.
    """
    by_receiver = defaultdict(list)
    for (group, sender, receiver), cell in cells.items():
        by_receiver[(group, receiver)].append((sender, cell))

    comparable = 0
    chose_writer = chose_silent = chose_neither = 0
    both = neither = 0
    for (group, receiver), candidates in by_receiver.items():
        if len(candidates) < 2:
            continue
        comparable += 1
        writers = [(s, c) for s, c in candidates if c['messages']]
        if len(writers) == len(candidates):
            both += 1
            continue
        if not writers:
            neither += 1
            continue
        if len(writers) != 1:
            continue          # more than one wrote but not all: not a clean pair
        writer = writers[0][0]
        silent = [s for s, c in candidates if not c['messages']]
        chosen = [s for s, _c in candidates
                  if outcomes.get((group, s, receiver))]
        if len(chosen) != 1:
            chose_neither += 1
            continue
        if chosen[0] == writer:
            chose_writer += 1
        elif chosen[0] in silent:
            chose_silent += 1

    if not comparable:
        return None
    decided = chose_writer + chose_silent
    return {
        'receivers': comparable,
        'both_wrote': both,
        'none_wrote': neither,
        'exactly_one': chose_writer + chose_silent + chose_neither,
        'chose_writer': chose_writer,
        'chose_silent': chose_silent,
        'chose_neither': chose_neither,
        'decided': decided,
        'share': chose_writer / decided if decided else None,
        'p': binomial_p(chose_writer, decided) if decided else None,
    }


def binomial_p(successes: int, n: int) -> float:
    """Two-sided tail against a fair coin.

    Exact rather than normal-approximate: the counts that matter here can be
    small, and an approximation is worst exactly where the question is closest.
    """
    from math import comb

    if not n:
        return 1.0
    extreme = max(successes, n - successes)
    tail = sum(comb(n, i) for i in range(extreme, n + 1))
    return min(1.0, 2 * tail / 2 ** n)
