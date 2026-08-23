"""
Merges the choices export (``all_apps_wide``) with the chat export
(``ChatMessages``) and builds the experiment's analysis variables.

Who enters the analysis
-----------------------
Participants are kept when they satisfy two conditions: they have a valid
Prolific identifier in ``participant.label``, which discards internal test
sessions, and they were part of a triad, which keeps only those who could
communicate. Anyone later excluded for inactivity stays in the dataset: their
exclusion from the main analyses is governed by ``group_valid``. With
``keep_all`` nothing is filtered, for inspecting the raw data.

Produces three files:

``<stem>_messages_long.csv``
    One row per message, with sender and receiver resolved exactly. This is the
    input of the NLP pipeline (TopicGPT and the text measures).

``<stem>_chat_by_partner.csv``
    One row per directed pair i -> j (six per triad). Carries the dyadic
    variables: signal sent, persuasion, choice-signal consistency and the
    pair's conversation measures.

``<stem>_chat_aggregated.csv``
    One row per participant, with the whole group's conversation and the
    individual variables (strategic deception, mean consistency, validity).

Join key
--------
The only reliable key is ``participant.code``: ``group.id_in_subsession`` does
not identify the triad, because whoever is never grouped stays parked in a
residual group together with other ungrouped participants. The triad is
therefore reconstructed from ``participant.part1_group_id`` when present
(recent exports) and, failing that, from the chat channel prefix, which carries
the same identifier.

Usage (from the project entry point):
    python run.py merge
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# --- Game constants, aligned with bargaining_tdl_common/utils.py -----------

TOPOLOGY = {
    1: {'left': 3, 'right': 2},
    2: {'left': 1, 'right': 3},
    3: {'left': 2, 'right': 1},
}
COLOR_MAPPING = {1: 'Yellow', 2: 'Orange', 3: 'Purple'}
ID_TO_ROLE = {1: 'A', 2: 'B', 3: 'C'}

VALID_SIGNALS = ('split_you', 'split_other', 'support_none')
VALID_DECISIONS = ('Left', 'Right', 'NoOne')

MAIN = 'bargaining_tdl_main.1.'

# MTurk columns: the study does not run on MTurk, so they leave the datasets.
MTURK_COLS = {
    'participant.mturk_worker_id',
    'participant.mturk_assignment_id',
    'session.mturk_HITId',
    'session.mturk_HITGroupId',
}

CHANNEL_RE = re.compile(r'^(?P<prefix>.*)-(?P<group>\d+)_(?P<a>\d)_(?P<b>\d)$')


# --- Utilities -------------------------------------------------------------


def _int(value, default=None):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _float(value, default=None):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _third_player(i: int, j: int) -> int:
    """The third member of the triad, given two id_in_group values."""
    return ({1, 2, 3} - {i, j}).pop()


def _partner_side(focal: int, target: int):
    """'left' / 'right' per the circular topology, otherwise None."""
    partners = TOPOLOGY.get(focal, {})
    if partners.get('left') == target:
        return 'left'
    if partners.get('right') == target:
        return 'right'
    return None


def _decision_target(focal: int, decision: str):
    """id_in_group of the player actually supported, or None for NoOne."""
    if decision == 'Left':
        return TOPOLOGY[focal]['left']
    if decision == 'Right':
        return TOPOLOGY[focal]['right']
    return None


def _signal_declared_target(focal: int, target: int, signal: str):
    """Who the signal *declares* an intention to support.

    ``split_you``   -> the signal's recipient;
    ``split_other`` -> the third player;
    ``support_none``-> nobody (None).
    """
    if signal == 'split_you':
        return target
    if signal == 'split_other':
        return _third_player(focal, target)
    return None


def _word_count(text: str) -> int:
    return len([t for t in re.split(r'\s+', text.strip()) if t])


# --- Reading and reconstructing the triads ---------------------------------


def load_wide(path: Path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def load_chat(path: Path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def is_grouped(row) -> bool:
    """True if the participant entered a triad.

    ``main.player.treatment`` is written only in
    ``GroupingAfterControlQuestions.after_all_players_arrive``: it is therefore
    the exact marker of group formation, and stays set even for triads that
    break off halfway.
    """
    return bool((row.get(MAIN + 'player.treatment') or '').strip()) and _int(
        row.get(MAIN + 'player.id_in_group')
    ) in (1, 2, 3)


# A PROLIFIC_PID is a 24-character hexadecimal string. The format cleanly
# separates real participants from anyone who typed an identifier by hand during
# internal testing.
PROLIFIC_PID_RE = re.compile(r'^[0-9a-f]{24}$')


def has_prolific_label(row) -> bool:
    """True if the participant really came from Prolific.

    We read ``participant.label``, which oTree writes from the URL and the
    participant cannot change, rather than ``prolific_id``, which is a form
    field and also accepts hand-typed text.
    """
    return bool(PROLIFIC_PID_RE.match((row.get('participant.label') or '').strip()))


def select_participants(wide_rows):
    """Keep the real participants who were part of a triad.

    These are the two conditions the analysis calls for: a valid Prolific
    identifier, which discards internal test sessions, and actual membership of
    a group, which keeps only those who could communicate.

    Anyone later excluded for inactivity stays in: they did communicate, and
    their exclusion from the main analyses is governed by ``group_valid``, not
    by removing them from the dataset.

    Returns the rows kept and the count of discards by reason.
    """
    kept, dropped = [], {'never_grouped': 0, 'no_prolific_id': 0}
    for row in wide_rows:
        if not is_grouped(row):
            dropped['never_grouped'] += 1
        elif not has_prolific_label(row):
            dropped['no_prolific_id'] += 1
        else:
            kept.append(row)
    return kept, dropped


def build_groups(wide_rows, chat_rows):
    """Give every grouped participant a stable ``group_uid``.

    Order of preference for the identifier:
      1. ``participant.part1_group_id`` (native column, recent exports);
      2. the numeric prefix of the participant's chat channel;
      3. the synthetic key ``<session>-g<id_in_subsession>``, which stays
         correct because it is applied only to grouped participants.

    Returns ``(group_uid_per_code, groups, warnings)``.
    """
    warnings = []

    # Group id taken from the chat channels, keyed by participant.code.
    chat_group_by_code = {}
    for message in chat_rows:
        match = CHANNEL_RE.match(message.get('channel', ''))
        if not match:
            continue
        code = message.get('participant_code')
        gid = match.group('group')
        previous = chat_group_by_code.get(code)
        if previous is not None and previous != gid:
            warnings.append(
                f'participant {code}: chat channels with differing group ids '
                f'({previous} and {gid})'
            )
        chat_group_by_code[code] = gid

    # Step 1: bucket only the grouped participants by (session,
    # id_in_subsession). Once the ungrouped are excluded, that pair is a valid
    # key again: the residual group that held them disappears.
    clusters = defaultdict(list)
    for row in wide_rows:
        if not is_grouped(row):
            continue
        key = (row['session.code'], row.get(MAIN + 'group.id_in_subsession'))
        clusters[key].append(row)

    # Step 2: give every cluster a unique identifier, preferring the native
    # database one (the same as the chat channel prefix), which is stable across
    # sessions.
    uid_by_code = {}
    groups = {}
    for (session, id_in_subsession), members in clusters.items():
        native_ids, chat_ids = set(), set()
        for row in members:
            native = (row.get('participant.part1_group_id') or '').strip()
            if native:
                native_ids.add(native)
            from_chat = chat_group_by_code.get(row['participant.code'])
            if from_chat:
                chat_ids.add(from_chat)

        if len(native_ids) > 1:
            warnings.append(
                f'{session}/g{id_in_subsession}: conflicting part1_group_id '
                f'{sorted(native_ids)}'
            )
        if len(chat_ids) > 1:
            warnings.append(
                f'{session}/g{id_in_subsession}: chat channels with '
                f'conflicting group ids {sorted(chat_ids)}'
            )
        if native_ids and chat_ids and native_ids != chat_ids:
            warnings.append(
                f'{session}/g{id_in_subsession}: part1_group_id '
                f'{sorted(native_ids)} differs from the channels\' group id '
                f'{sorted(chat_ids)}'
            )

        resolved = sorted(native_ids or chat_ids)
        uid = (
            f'{session}-db{resolved[0]}' if resolved
            else f'{session}-g{id_in_subsession}'
        )

        by_pid = {}
        for row in members:
            pid = _int(row.get(MAIN + 'player.id_in_group'))
            if pid in by_pid:
                warnings.append(
                    f'group {uid}: id_in_group {pid} assigned to several participants'
                )
            by_pid[pid] = row
            uid_by_code[row['participant.code']] = uid

        if set(by_pid) != {1, 2, 3}:
            warnings.append(
                f'group {uid}: unexpected composition, ids present {sorted(by_pid)}'
            )
        groups[uid] = by_pid

    return uid_by_code, groups, warnings


# --- Messages --------------------------------------------------------------


def build_messages(chat_rows, wide_by_code, uid_by_code):
    """Resolve the sender and receiver of every message.

    The sender is ``participant_code`` (an exact datum). The receiver is the
    other id of the pair contained in the channel. The ``nickname`` field is
    NOT used: it is relative to the reader, not to the writer.
    """
    messages = []
    anomalies = []

    for raw in chat_rows:
        code = raw.get('participant_code')
        row = wide_by_code.get(code)
        match = CHANNEL_RE.match(raw.get('channel', ''))
        if row is None or match is None:
            anomalies.append(
                f'unresolvable message: participant={code} '
                f'channel={raw.get("channel")!r}'
            )
            continue

        sender = _int(row.get(MAIN + 'player.id_in_group'))
        pair = (_int(match.group('a')), _int(match.group('b')))
        if sender not in pair:
            anomalies.append(
                f'message from {code}: sender id {sender} is not present in '
                f'channel {raw.get("channel")!r}'
            )
            continue
        receiver = pair[0] if pair[1] == sender else pair[1]

        messages.append(
            dict(
                session_code=raw.get('session_code', ''),
                group_uid=uid_by_code.get(code, ''),
                channel=raw.get('channel', ''),
                treatment=row.get(MAIN + 'player.treatment', ''),
                timestamp=_float(raw.get('timestamp'), 0.0),
                sender_participant_code=code,
                sender_id_in_group=sender,
                sender_color=COLOR_MAPPING.get(sender, ''),
                sender_role=ID_TO_ROLE.get(sender, ''),
                receiver_id_in_group=receiver,
                receiver_color=COLOR_MAPPING.get(receiver, ''),
                receiver_role=ID_TO_ROLE.get(receiver, ''),
                dyad_key=f'{min(pair)}_{max(pair)}',
                body=raw.get('body', ''),
                n_words=_word_count(raw.get('body', '')),
                n_chars=len(raw.get('body', '')),
            )
        )

    messages.sort(key=lambda m: (m['group_uid'], m['timestamp']))

    # Running indices: within the group and within the pair.
    seq_group = defaultdict(int)
    seq_dyad = defaultdict(int)
    for message in messages:
        gkey = message['group_uid']
        seq_group[gkey] += 1
        message['msg_index_group'] = seq_group[gkey]
        dkey = (gkey, message['dyad_key'])
        seq_dyad[dkey] += 1
        message['msg_index_dyad'] = seq_dyad[dkey]

    return messages, anomalies


# --- Derived variables -----------------------------------------------------


def player_facts(row):
    """Pull from the wide row the behavioural fields used in the formulas."""
    pid = _int(row.get(MAIN + 'player.id_in_group'))
    decision = (row.get(MAIN + 'player.decision_choice') or '').strip()
    return dict(
        pid=pid,
        decision=decision if decision in VALID_DECISIONS else '',
        decision_target=_decision_target(pid, decision) if decision else None,
        signal_left=(row.get(MAIN + 'player.signal_left') or '').strip(),
        signal_right=(row.get(MAIN + 'player.signal_right') or '').strip(),
        payoff_paid=_float(row.get(MAIN + 'player.payoff')),
        payoff_theoretical=_float(row.get(MAIN + 'player.part1_calculated_payoff')),
    )


def signal_to(facts, target: int):
    """The signal the focal participant sent to ``target``."""
    side = _partner_side(facts['pid'], target)
    if side == 'left':
        return facts['signal_left']
    if side == 'right':
        return facts['signal_right']
    return ''


def timeout_flag(row) -> int:
    """1 if the participant let a timer expire or was excluded."""
    hits = (
        row.get(MAIN + 'player.decision_inactive') == '99',
        row.get(MAIN + 'player.signal_inactive') == '99',
        (row.get('participant.inactive_excluded') or '').strip() in ('1', 'True'),
    )
    return int(any(hits))


def group_validity(members):
    """Triad validity: one compromised member is enough to invalidate it."""
    dropped = any(
        (row.get(MAIN + 'group.group_dropped') or '').strip() in ('1', 'True')
        for row in members.values()
    )
    any_timeout = any(timeout_flag(row) for row in members.values())
    complete = set(members) == {1, 2, 3}
    return dict(
        group_dropped_flag=int(dropped),
        group_any_timeout=int(any_timeout),
        group_complete=int(complete),
        group_valid=int(complete and not dropped and not any_timeout),
    )


def dyad_measures(messages):
    """Conversation aggregates for an already filtered list of messages."""
    if not messages:
        return dict(
            n_messages=0, n_words=0, n_chars=0,
            first_timestamp='', last_timestamp='', duration_seconds='',
        )
    timestamps = [m['timestamp'] for m in messages]
    return dict(
        n_messages=len(messages),
        n_words=sum(m['n_words'] for m in messages),
        n_chars=sum(m['n_chars'] for m in messages),
        first_timestamp=min(timestamps),
        last_timestamp=max(timestamps),
        duration_seconds=round(max(timestamps) - min(timestamps), 3),
    )


def transcript_text(messages) -> str:
    """Readable transcript, one turn per line, in chronological order."""
    return '\n'.join(
        f"{m['sender_color']}->{m['receiver_color']}: {m['body']}" for m in messages
    )


def transcript_json(messages) -> str:
    return json.dumps(
        [
            dict(
                timestamp=m['timestamp'],
                from_id=m['sender_id_in_group'],
                from_color=m['sender_color'],
                to_id=m['receiver_id_in_group'],
                to_color=m['receiver_color'],
                body=m['body'],
            )
            for m in messages
        ],
        ensure_ascii=False,
    )


# --- Building the outputs --------------------------------------------------


def clean_columns(fieldnames):
    """Wide columns to carry into the output, minus the MTurk ones."""
    return [c for c in fieldnames if c not in MTURK_COLS]


def build_by_partner(wide_rows, wide_cols, groups, uid_by_code, messages):
    """One row per directed pair i -> j, plus the never-grouped."""
    by_group_dyad = defaultdict(list)
    for message in messages:
        by_group_dyad[(message['group_uid'], message['dyad_key'])].append(message)

    base_cols = clean_columns(wide_cols)
    rows = []

    for uid, members in sorted(groups.items()):
        validity = group_validity(members)
        facts = {pid: player_facts(row) for pid, row in members.items()}

        for pid, row in sorted(members.items()):
            if pid not in TOPOLOGY:
                continue
            me = facts[pid]
            for side in ('left', 'right'):
                target = TOPOLOGY[pid][side]
                if target not in facts:
                    continue
                other = facts[target]
                third = _third_player(pid, target)

                signal = signal_to(me, target)
                declared = _signal_declared_target(pid, target, signal)
                s_ij = int(signal == 'split_you')
                a_ji = int(
                    other['decision_target'] is not None
                    and other['decision_target'] == pid
                )
                # Choice-signal consistency: the declared action matches the
                # one actually taken. This holds for the "I support no one"
                # signal followed by the NoOne choice too.
                if signal in VALID_SIGNALS and me['decision']:
                    consistent = int(declared == me['decision_target'])
                else:
                    consistent = ''

                dyad_msgs = by_group_dyad.get((uid, f'{min(pid, target)}_{max(pid, target)}'), [])
                sent = [m for m in dyad_msgs if m['sender_id_in_group'] == pid]
                received = [m for m in dyad_msgs if m['sender_id_in_group'] == target]

                record = {c: row.get(c, '') for c in base_cols}
                record.update(
                    group_uid=uid,
                    treatment=row.get(MAIN + 'player.treatment', ''),
                    focal_id_in_group=pid,
                    focal_color=COLOR_MAPPING.get(pid, ''),
                    focal_role=ID_TO_ROLE.get(pid, ''),
                    partner_id_in_group=target,
                    partner_color=COLOR_MAPPING.get(target, ''),
                    partner_role=ID_TO_ROLE.get(target, ''),
                    partner_side=side,
                    partner_participant_code=members[target]['participant.code'],
                    third_id_in_group=third,
                    third_color=COLOR_MAPPING.get(third, ''),
                    dyad_key=f'{min(pid, target)}_{max(pid, target)}',
                    dyad_uid=f'{uid}-{min(pid, target)}_{max(pid, target)}',
                    dyad_status='matched' if dyad_msgs else 'grouped_no_messages',
                    focal_decision=me['decision'],
                    focal_decision_target_id=me['decision_target'] or '',
                    focal_decision_target_color=COLOR_MAPPING.get(me['decision_target'], ''),
                    partner_decision=other['decision'],
                    partner_decision_target_id=other['decision_target'] or '',
                    signal_ij=signal,
                    signal_ij_declared_target_id=declared or '',
                    signal_ij_declared_target_color=COLOR_MAPPING.get(declared, ''),
                    signal_ji=signal_to(other, pid),
                    S_ij=s_ij,
                    A_ji=a_ji,
                    persuasion_ij=s_ij * a_ji,
                    C_ij=consistent,
                    focal_payoff_paid=me['payoff_paid'] if me['payoff_paid'] is not None else '',
                    focal_payoff_theoretical=(
                        me['payoff_theoretical'] if me['payoff_theoretical'] is not None else ''
                    ),
                    focal_timeout_flag=timeout_flag(row),
                    partner_timeout_flag=timeout_flag(members[target]),
                    **validity,
                )
                for prefix, subset in (
                    ('dyad', dyad_msgs), ('sent', sent), ('recv', received)
                ):
                    for key, value in dyad_measures(subset).items():
                        record[f'{prefix}_{key}'] = value
                record['dyad_transcript_text'] = transcript_text(dyad_msgs)
                record['dyad_transcript_json'] = transcript_json(dyad_msgs)
                record['sent_transcript_text'] = transcript_text(sent)
                rows.append(record)

    # Never grouped: one row each, so no participant disappears.
    for row in wide_rows:
        if row['participant.code'] in uid_by_code:
            continue
        record = {c: row.get(c, '') for c in base_cols}
        record.update(
            group_uid='',
            treatment=row.get('participant.treatment', ''),
            dyad_status='never_grouped',
            group_valid=0,
            group_complete=0,
            group_dropped_flag='',
            group_any_timeout='',
            focal_timeout_flag=timeout_flag(row),
        )
        rows.append(record)

    return rows


def build_aggregated(wide_rows, wide_cols, groups, uid_by_code, messages):
    """One row per participant, with the whole group's conversation."""
    by_group = defaultdict(list)
    for message in messages:
        by_group[message['group_uid']].append(message)

    base_cols = clean_columns(wide_cols)
    by_code_group = {}
    for uid, members in groups.items():
        for row in members.values():
            by_code_group[row['participant.code']] = (uid, members)

    rows = []
    for row in wide_rows:
        code = row['participant.code']
        record = {c: row.get(c, '') for c in base_cols}

        if code not in by_code_group:
            record.update(
                group_uid='',
                treatment=row.get('participant.treatment', ''),
                chat_status='never_grouped',
                group_valid=0,
                group_complete=0,
                group_dropped_flag='',
                group_any_timeout='',
                focal_timeout_flag=timeout_flag(row),
            )
            rows.append(record)
            continue

        uid, members = by_code_group[code]
        validity = group_validity(members)
        facts = {pid: player_facts(r) for pid, r in members.items()}
        pid = _int(row.get(MAIN + 'player.id_in_group'))
        me = facts[pid]

        group_msgs = by_group.get(uid, [])
        sent = [m for m in group_msgs if m['sender_id_in_group'] == pid]
        received = [m for m in group_msgs if m['receiver_id_in_group'] == pid]

        left_id = TOPOLOGY[pid]['left']
        right_id = TOPOLOGY[pid]['right']
        signal_left = signal_to(me, left_id)
        signal_right = signal_to(me, right_id)

        consistencies = []
        for target in (left_id, right_id):
            signal = signal_to(me, target)
            if signal in VALID_SIGNALS and me['decision']:
                declared = _signal_declared_target(pid, target, signal)
                consistencies.append(int(declared == me['decision_target']))
        cc = sum(consistencies) / len(consistencies) if len(consistencies) == 2 else ''

        # Strategic deception: promises support to both, then supports
        # neither.
        if signal_left in VALID_SIGNALS and signal_right in VALID_SIGNALS and me['decision']:
            deception = int(
                signal_left == 'split_you'
                and signal_right == 'split_you'
                and me['decision'] == 'NoOne'
            )
        else:
            deception = ''

        persuaded_count = sum(
            int(
                signal_to(me, target) == 'split_you'
                and facts[target]['decision_target'] == pid
            )
            for target in (left_id, right_id)
            if target in facts
        )
        supported_by_count = sum(
            int(facts[target]['decision_target'] == pid)
            for target in (left_id, right_id)
            if target in facts
        )

        payoffs = [
            f['payoff_theoretical'] for f in facts.values()
            if f['payoff_theoretical'] is not None
        ]

        record.update(
            group_uid=uid,
            treatment=row.get(MAIN + 'player.treatment', ''),
            chat_status='matched' if group_msgs else 'grouped_no_messages',
            focal_id_in_group=pid,
            focal_color=COLOR_MAPPING.get(pid, ''),
            focal_role=ID_TO_ROLE.get(pid, ''),
            left_partner_id=left_id,
            left_partner_color=COLOR_MAPPING.get(left_id, ''),
            left_partner_code=members[left_id]['participant.code'] if left_id in members else '',
            right_partner_id=right_id,
            right_partner_color=COLOR_MAPPING.get(right_id, ''),
            right_partner_code=members[right_id]['participant.code'] if right_id in members else '',
            focal_decision=me['decision'],
            focal_decision_target_id=me['decision_target'] or '',
            focal_decision_target_color=COLOR_MAPPING.get(me['decision_target'], ''),
            signal_to_left=signal_left,
            signal_to_right=signal_right,
            strategic_deception=deception,
            cc_i=cc,
            n_partners_persuaded=persuaded_count,
            n_partners_supporting_me=supported_by_count,
            focal_payoff_paid=me['payoff_paid'] if me['payoff_paid'] is not None else '',
            focal_payoff_theoretical=(
                me['payoff_theoretical'] if me['payoff_theoretical'] is not None else ''
            ),
            group_outcome=row.get(MAIN + 'group.group_outcome', ''),
            group_coordinate=row.get(MAIN + 'group.grp_coordinate', ''),
            group_total_payoff=sum(payoffs) if len(payoffs) == 3 else '',
            group_mean_payoff=round(sum(payoffs) / 3, 4) if len(payoffs) == 3 else '',
            focal_timeout_flag=timeout_flag(row),
            **validity,
        )
        for prefix, subset in (
            ('chat_group', group_msgs), ('chat_sent', sent), ('chat_recv', received)
        ):
            for key, value in dyad_measures(subset).items():
                record[f'{prefix}_{key}'] = value
        record['group_transcript_text'] = transcript_text(group_msgs)
        record['group_transcript_json'] = transcript_json(group_msgs)
        record['sent_transcript_text'] = transcript_text(sent)
        rows.append(record)

    return rows


def write_csv(path: Path, rows):
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    fieldnames = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def run(wide_path: Path, chat_path: Path, outdir: Path, stem: str,
        keep_all: bool = False) -> dict:
    """Step 1: merge choices and chat, and build the experiment's variables.

    By default only real participants who were part of a triad are kept (see
    `select_participants`). With ``keep_all`` nothing is filtered: that is for
    inspecting the raw data, not for analysing it.

    Returns a summary with the paths produced and the figures to check.
    """
    wide_cols, all_rows = load_wide(wide_path)
    chat_rows = load_chat(chat_path)

    if keep_all:
        wide_rows, dropped = all_rows, {}
    else:
        wide_rows, dropped = select_participants(all_rows)

    wide_by_code = {r['participant.code']: r for r in wide_rows}

    # Messages from filtered-out participants are not anomalies: they are
    # counted separately, so the total adds up and they are not confused with
    # the unresolvable ones.
    kept_codes = set(wide_by_code)
    all_codes = {r['participant.code'] for r in all_rows}
    chat_kept, chat_filtered = [], 0
    for message in chat_rows:
        code = message.get('participant_code')
        if code in kept_codes:
            chat_kept.append(message)
        elif code in all_codes:
            chat_filtered += 1
        else:
            chat_kept.append(message)  # unknown sender: build_messages handles it

    uid_by_code, groups, warnings = build_groups(wide_rows, chat_rows=chat_kept)
    messages, anomalies = build_messages(chat_kept, wide_by_code, uid_by_code)

    outdir.mkdir(parents=True, exist_ok=True)
    paths = dict(
        messages_long=outdir / f'{stem}_messages_long.csv',
        chat_by_partner=outdir / f'{stem}_chat_by_partner.csv',
        chat_aggregated=outdir / f'{stem}_chat_aggregated.csv',
    )

    write_csv(paths['messages_long'], messages)
    write_csv(
        paths['chat_by_partner'],
        build_by_partner(wide_rows, wide_cols, groups, uid_by_code, messages),
    )
    write_csv(
        paths['chat_aggregated'],
        build_aggregated(wide_rows, wide_cols, groups, uid_by_code, messages),
    )

    summary = dict(
        paths=paths,
        n_input=len(all_rows),
        n_participants=len(wide_rows),
        n_grouped=len(uid_by_code),
        n_groups=len(groups),
        n_valid_groups=sum(
            group_validity(m)['group_valid'] for m in groups.values()
        ),
        dropped=dropped,
        n_messages_in=len(chat_rows),
        n_messages_filtered=chat_filtered,
        n_messages_resolved=len(messages),
        warnings=warnings + anomalies,
    )

    # Written to file, so the report can be regenerated without redoing the
    # merge.
    serialisable = {k: v for k, v in summary.items() if k != 'paths'}
    (outdir / f'{stem}_summary.json').write_text(
        json.dumps(serialisable, indent=2, ensure_ascii=False), encoding='utf-8'
    )
    return summary


def print_summary(summary: dict) -> None:
    dropped = summary.get('dropped') or {}
    print(f"Participants in export : {summary['n_input']}")
    if dropped:
        print(f"  excluded, never grouped      : {dropped['never_grouped']}")
        print(f"  excluded, no Prolific ID     : {dropped['no_prolific_id']}")
    print(f"Participants analysed  : {summary['n_participants']}")
    print(f"Triads reconstructed   : {summary['n_groups']}")
    print(f"Valid triads           : {summary['n_valid_groups']}"
          f"   (the others have a member excluded for inactivity, "
          f"but stay in the dataset)")
    print(f"Messages in export     : {summary['n_messages_in']}")
    if summary.get('n_messages_filtered'):
        print(f"  from excluded participants : {summary['n_messages_filtered']}")
    print(f"Messages analysed      : {summary['n_messages_resolved']}")

    expected = summary['n_messages_in'] - summary.get('n_messages_filtered', 0)
    if summary['n_messages_resolved'] != expected:
        print('  WARNING: not every message could be traced back to a '
              'participant; see the warnings below.')
    print()
    for path in summary['paths'].values():
        print(f'  {path}')
    for warning in summary['warnings']:
        print(f'WARNING: {warning}', file=sys.stderr)
