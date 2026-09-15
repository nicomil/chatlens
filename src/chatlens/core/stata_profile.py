"""The coalition experiment's own Stata layout, as the experimenter writes it.

`core/fulltables.py` makes a name Stata will accept out of whatever the export
called a column, mechanically: `bargaining_tdl_survey.1.player.sd3_mach_01`
becomes `bts_1_p_sd3_mach_01`. That is the right default for an experiment
nobody has seen before, and it is the wrong answer here, because this experiment
already has a naming: the experimenter keeps a script that produces a
111-column, Stata-19-clean table, his do-files are written against those names,
and a second set of names for the same variables would mean two files that
cannot be told apart at a glance and diverge at the first change.

So the names are **his**, copied from that script — `STATA_RENAMES`,
`BASE_COLUMNS`, `DROPS`, `CHOICE_COLUMNS`, `PARTNER_COLUMNS` below — and the
resolved-target and dyadic-chat columns are computed the way he computes them.
What this module adds is the part he does not have: the language measures, the
rubric, the topics, the relations and the emotions, appended with the names
`fulltables.safe_names` gives them, and the whole thing produced per study so
the standardised columns belong to the sample of one paper.

Two honest limits, both stated rather than papered over:

**Only the participants who were in a group.** His table carries two rows for
every participant in the wide export, including the 3 510 rows of people who
never entered a triad and therefore have no treatment. Those belong to no study
— a study selects treatments — so they are not written here. The rows that
matter for any analysis are the 3 228 with a treatment, and those are compared
against his file column by column by `tests/test_stata_profile.py`.

**The transcript is ours, not his.** He writes a JSON array with a UTC
timestamp per message; we carry `sent_transcript_text`, one turn per line, which
is what every page and every measure in this tool reads. Reproducing his exact
bytes would mean keeping a second transcript format alive for no analytical
gain, so the column is ours and the codebook says so.
"""

from __future__ import annotations

from . import fulltables

# --- his layout ------------------------------------------------------------

# The topology of the three-player game, as both his script and our adapter
# state it. Kept here too because the resolved-target columns below are computed
# from it and a file that disagreed with him about who sits where would be worse
# than no file.
TOPOLOGY = {1: {'left': 3, 'right': 2},
            2: {'left': 1, 'right': 3},
            3: {'left': 2, 'right': 1}}
COLORS = {1: 'Yellow', 2: 'Orange', 3: 'Purple'}

MAIN = 'bargaining_tdl_main.1.'
SURVEY = 'bargaining_tdl_survey.1.player.'

# oTree column -> the name his do-files use. Verbatim from his script.
STATA_RENAMES = {
    'participant.id_in_session': 'id_in_session',
    'participant.code': 'code',
    'participant.label': 'label',
    'participant._index_in_pages': 'index_pages',
    'participant.payoff': 'payoff',
    'participant.group_dropped': 'group_dropped',
    'participant.part1_payoff_eligible': 'payoff_eligible',
    'participant.part1_group_id': 'group_id',
    'session.code': 'sessioncode',
    MAIN + 'player.id_in_group': 'id_in_group',
    MAIN + 'player.player_color': 'player_color',
    MAIN + 'player.treatment': 'treatment',
    MAIN + 'player.signal_left': 'sendsignal_left',
    MAIN + 'player.signal_right': 'sendsignal_right',
    MAIN + 'player.guess_left_confidence': 'guess_left_confidence',
    MAIN + 'player.guess_right_confidence': 'guess_right_confidence',
    MAIN + 'player.time_chat': 'time_chat',
    MAIN + 'player.time_signals': 'time_signals',
    MAIN + 'player.decision_choice': 'final_decision',
    MAIN + 'player.decision_option_1': 'decision_option_1',
    MAIN + 'player.decision_option_2': 'decision_option_2',
    MAIN + 'player.decision_option_3': 'decision_option_3',
    MAIN + 'player.received_signal_left': 'received_signal_left',
    MAIN + 'player.received_signal_right': 'received_signal_right',
    MAIN + 'player.id_player_on_the_left': 'player_on_the_left',
    MAIN + 'player.id_player_on_the_right': 'player_on_the_right',
    MAIN + 'player.id_player_visualized_on_the_left': 'player_visual_left',
    MAIN + 'player.id_player_visualized_on_the_right': 'player_visual_right',
    MAIN + 'player.time_decision': 'time_decision',
    MAIN + 'player.time_post_decision_confidence': 'time_guess',
    MAIN + 'player.chat_interrupted': 'chat_interrupted',
    MAIN + 'player.decision_inactive': 'decision_inactive',
    MAIN + 'player.signal_inactive': 'signal_inactive',
    MAIN + 'player.received_signal_left_inactive': 'rcvd_sig_left_inactive',
    MAIN + 'player.received_signal_right_inactive': 'rcvd_sig_right_inactive',
    MAIN + 'player.guess_left_choice': 'guess_left',
    MAIN + 'player.guess_right_choice': 'guess_right',
    MAIN + 'group.grp_coordinate': 'grp_coordinate',
    MAIN + 'group.group_outcome': 'group_outcome',
    MAIN + 'group.group_dropped': 'grp_drop',
    SURVEY + 'gender': 'gender',
    SURVEY + 'birth_year': 'birth_year',
    SURVEY + 'field_of_study': 'field_study',
    SURVEY + 'university_years': 'uni_years',
    SURVEY + 'main_situation': 'status',
    SURVEY + 'job_type': 'job',
    **{SURVEY + f'sd3_mach_{n:02d}': f'mach_{n:02d}' for n in range(1, 10)},
    **{SURVEY + f'sd3_narc_{n:02d}': f'narc_{n:02d}' for n in range(1, 10)},
    **{SURVEY + f'sd3_psych_{n:02d}': f'psych_{n:02d}' for n in range(1, 10)},
    SURVEY + 'willingness_future': 'patience',
    SURVEY + 'willingness_risk': 'risk',
    SURVEY + 'reciprocity_positive': 'reciprocity_positive',
    SURVEY + 'reciprocity_negative': 'reciprocity_negative',
    SURVEY + 'willingness_donate': 'altruism',
    SURVEY + 'trust_general': 'trust',
    SURVEY + 'beauty_contest_guess': 'level_k',
    SURVEY + 'time_survey_page4': 'time_falk',
    SURVEY + 'time_survey_page10': 'time_levelk',
}

# The order his table has. Anything absent from the export comes out blank
# rather than missing, so the header is the same whichever session was exported.
BASE_ORDER = [
    'participant.id_in_session', 'participant.code', 'participant.label',
    'participant._index_in_pages', 'participant.payoff',
    'participant.group_dropped', 'participant.part1_payoff_eligible',
    'participant.part1_group_id', 'session.code',
    MAIN + 'player.id_in_group', MAIN + 'player.player_color',
    MAIN + 'player.treatment',
    MAIN + 'player.signal_left', MAIN + 'player.signal_right',
    MAIN + 'player.guess_left_confidence',
    MAIN + 'player.guess_right_confidence',
    MAIN + 'player.time_chat', MAIN + 'player.time_signals',
    MAIN + 'player.decision_choice',
    MAIN + 'player.decision_option_1', MAIN + 'player.decision_option_2',
    MAIN + 'player.decision_option_3',
    MAIN + 'player.received_signal_left',
    MAIN + 'player.received_signal_right',
    MAIN + 'player.id_player_on_the_left',
    MAIN + 'player.id_player_on_the_right',
    MAIN + 'player.id_player_visualized_on_the_left',
    MAIN + 'player.id_player_visualized_on_the_right',
    MAIN + 'player.time_decision',
    MAIN + 'player.time_post_decision_confidence',
    MAIN + 'player.chat_interrupted', MAIN + 'player.decision_inactive',
    MAIN + 'player.signal_inactive',
    MAIN + 'player.received_signal_left_inactive',
    MAIN + 'player.received_signal_right_inactive',
    MAIN + 'player.guess_left_choice', MAIN + 'player.guess_right_choice',
    MAIN + 'group.grp_coordinate', MAIN + 'group.group_outcome',
    MAIN + 'group.group_dropped',
    SURVEY + 'gender', SURVEY + 'birth_year', SURVEY + 'field_of_study',
    SURVEY + 'university_years', SURVEY + 'main_situation', SURVEY + 'job_type',
    *(SURVEY + f'sd3_mach_{n:02d}' for n in range(1, 10)),
    *(SURVEY + f'sd3_narc_{n:02d}' for n in range(1, 10)),
    *(SURVEY + f'sd3_psych_{n:02d}' for n in range(1, 10)),
    SURVEY + 'willingness_future', SURVEY + 'willingness_risk',
    SURVEY + 'reciprocity_positive', SURVEY + 'reciprocity_negative',
    SURVEY + 'willingness_donate', SURVEY + 'trust_general',
    SURVEY + 'beauty_contest_guess',
    SURVEY + 'time_survey_page4', SURVEY + 'time_survey_page10',
]

# The sixteen resolved-choice columns, in his order and with his two shortened
# names (the `received_..._color` pair would otherwise pass 32 characters).
CHOICE_COLUMNS = [
    'focal_player_id', 'focal_player_color',
    'decision_target_id', 'decision_target_color',
    'guess_left_target_id', 'guess_left_target_color',
    'guess_right_target_id', 'guess_right_target_color',
    'signal_left_target_id', 'signal_left_target_color',
    'signal_right_target_id', 'signal_right_target_color',
    'received_signal_left_target_id', 'rcvd_sig_left_target_color',
    'received_signal_right_target_id', 'rcvd_sig_right_target_color',
]

PARTNER_COLUMNS = [
    'topology_side', 'partner_id', 'partner_color', 'chat_group_key',
    'chat_status', 'chat_channel', 'chat_message_count',
    'chat_message_count_focal_sent', 'chat_message_count_partner_sent',
    'first_mover_chat', 'number_of_words', 'number_of_messages',
    'chat_transcript',
]


def layout() -> list:
    """His 111 column names, in his order."""
    return ([STATA_RENAMES[c] for c in BASE_ORDER]
            + CHOICE_COLUMNS + PARTNER_COLUMNS)


# --- resolving who a choice was about --------------------------------------
#
# Ported from his script. Each answers "which player does this field point at",
# which the raw export does not say: it records `Left` / `Right` / `NoOne` and
# `split_you` / `split_other` / `support_none`, relative to a seat.


def _target_from_choice(choice: str, focal: int):
    if choice == 'NoOne':
        return 'NoOne', 'NoOne'
    if choice not in ('Left', 'Right') or focal not in TOPOLOGY:
        return '', ''
    target = TOPOLOGY[focal][choice.lower()]
    return str(target), COLORS[target]


def _target_from_guess(choice: str, focal: int, side: str):
    """A guess about what the player on `side` will do.

    The guess names a direction from *their* seat, so "the left partner will go
    Right" can mean the focal player, which is the case that makes this more
    than a lookup.
    """
    if choice == 'NoOne':
        return 'NoOne', 'NoOne'
    if choice not in ('Left', 'Right') or focal not in TOPOLOGY:
        return '', ''
    if (side == 'left' and choice == 'Right') or (side == 'right'
                                                  and choice == 'Left'):
        target = focal
    else:
        target = TOPOLOGY[focal]['right' if side == 'left' else 'left']
    return str(target), COLORS[target]


def _target_from_signal(signal: str, focal: int, side: str,
                        received: bool = False):
    """Who a signal promises support to.

    `split_you` means the recipient, `split_other` the third player — and when
    the signal was *received* rather than sent, `split_you` means the focal
    player, because it was addressed to them.
    """
    if signal == 'support_none':
        return 'NoOne', 'NoOne'
    if signal not in ('split_you', 'split_other') or focal not in TOPOLOGY:
        return '', ''
    if received and signal == 'split_you':
        target = focal
    else:
        where = side if signal == 'split_you' else ('right' if side == 'left'
                                                    else 'left')
        target = TOPOLOGY[focal][where]
    return str(target), COLORS[target]


def _int(value):
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def choice_values(row) -> dict:
    """The sixteen resolved-target columns for one participant."""
    focal = _int(row.get(MAIN + 'player.id_in_group'))
    values = dict.fromkeys(CHOICE_COLUMNS, '')
    if focal not in TOPOLOGY:
        return values

    field = lambda name: str(row.get(MAIN + 'player.' + name) or '').strip()
    resolved = [
        ('focal_player', (str(focal), COLORS[focal])),
        ('decision_target', _target_from_choice(field('decision_choice'), focal)),
        ('guess_left_target',
         _target_from_guess(field('guess_left_choice'), focal, 'left')),
        ('guess_right_target',
         _target_from_guess(field('guess_right_choice'), focal, 'right')),
        ('signal_left_target',
         _target_from_signal(field('signal_left'), focal, 'left')),
        ('signal_right_target',
         _target_from_signal(field('signal_right'), focal, 'right')),
        ('received_signal_left_target',
         _target_from_signal(field('received_signal_left'), focal, 'left', True)),
        ('received_signal_right_target',
         _target_from_signal(field('received_signal_right'), focal, 'right',
                             True)),
    ]
    for stem, (target, colour) in resolved:
        values[f'{stem}_id'] = target
        # The two he had to shorten to stay inside Stata's 32 characters.
        if stem == 'received_signal_left_target':
            values['rcvd_sig_left_target_color'] = colour
        elif stem == 'received_signal_right_target':
            values['rcvd_sig_right_target_color'] = colour
        else:
            values[f'{stem}_color'] = colour
    return values


# --- the dyadic chat block -------------------------------------------------

# His three states for a pair. Ours are named differently and mean the same.
CHAT_STATUS = {'matched': 'matched',
               'grouped_no_messages': 'no_messages',
               'never_grouped': 'no_group'}


def _number(value, default=''):
    """A count as text, blank where the measure does not exist."""
    text = str(value or '').strip()
    if not text:
        return default
    try:
        return str(int(float(text)))
    except ValueError:
        return default


def first_mover(row) -> str:
    """1 when the focal player opened the pair's conversation, 0 when the
    partner did, blank when nothing was said.

    Read off `nlp_dyad_first_sender_id_in_group`, the opener of the pair taken
    over both directions — which is why the measure is computed at the dyad
    level in `core/aggregate.py` and not here. Blank rather than 0 for a silent
    pair: "nobody went first" is not "the partner went first", and Stata reads
    the empty string as missing.
    """
    opener = str(row.get('nlp_dyad_first_sender_id_in_group') or '').strip()
    if not opener:
        return ''
    focal = str(row.get('focal_id_in_group') or '').strip()
    partner = str(row.get('partner_id_in_group') or '').strip()
    if opener == focal:
        return '1'
    if opener == partner:
        return '0'
    return ''


def channels(messages) -> dict:
    """(group, pair) -> the oTree channel the pair talked in.

    Taken from the messages because that is where it is: a channel is a property
    of the conversation, and the merge does not carry it onto a pair row. It is
    in his layout, so it is worth going and getting rather than leaving blank.
    """
    found = {}
    for message in messages or []:
        key = (str(message.get('group_uid') or ''),
               str(message.get('dyad_key') or ''))
        channel = str(message.get('channel') or '').strip()
        if channel and key not in found:
            found[key] = channel
    return found


def partner_values(row, channel_of=None) -> dict:
    """His thirteen dyadic chat columns for one directed pair."""
    session = str(row.get('session.code') or row.get('session_code') or '').strip()
    group = str(row.get('participant.part1_group_id') or '').strip()
    status = CHAT_STATUS.get(str(row.get('dyad_status') or '').strip(), '')
    channel = (channel_of or {}).get(
        (str(row.get('group_uid') or ''), str(row.get('dyad_key') or '')), '')
    return {
        'topology_side': str(row.get('partner_side') or ''),
        'partner_id': str(row.get('partner_id_in_group') or ''),
        'partner_color': str(row.get('partner_color') or ''),
        'chat_group_key': f'{session}|{group}' if session and group else '',
        'chat_status': status,
        'chat_channel': channel,
        'chat_message_count': _number(row.get('dyad_n_messages')),
        'chat_message_count_focal_sent': _number(row.get('sent_n_messages')),
        'chat_message_count_partner_sent': _number(row.get('recv_n_messages')),
        'first_mover_chat': first_mover(row),
        'number_of_words': _number(row.get('sent_n_words')),
        'number_of_messages': _number(row.get('sent_n_messages')),
        # Ours, one turn per line, and the codebook says so. See the module
        # docstring for why his JSON form is not reproduced.
        'chat_transcript': str(row.get('sent_transcript_text') or ''),
    }


# --- building the table ----------------------------------------------------

# Columns of ours that would repeat something his layout already carries under
# another name. Dropped so the file has one column per quantity.
REDUNDANT = frozenset({
    'group_uid', 'session_code', 'treatment', 'focal_id_in_group',
    'partner_id_in_group', 'dyad_status', 'partner_side', 'partner_color',
    'focal_color', 'sent_transcript_text', 'dyad_transcript_text',
    'dyad_transcript_json', 'recv_transcript_text',
})


def measure_columns(rows) -> list:
    """Everything of ours worth appending, in the order it appears.

    His 111 are the experiment; these are what this tool adds to it. The dotted
    oTree columns are left out — they are already in the table under his names —
    and so is anything that would say the same thing twice.
    """
    if not rows:
        return []
    return [column for column in rows[0]
            if '.' not in column and column not in REDUNDANT]


def build(rows, messages=None, measures=None, label_of=None) -> dict:
    """His layout, plus our measures, for the rows that belong to a study.

    `measures` is which of our columns to append, in order; by default every
    one `measure_columns` finds. `label_of` overrides the codebook label of any of
    them, which is how a derived column says how it was derived.

    Returns the columns, the rows, and the labels for the codebook.
    """
    if measures is None:
        ours = measure_columns(rows)
    else:
        ours = [c for c in measures if '.' not in c and c not in REDUNDANT]
    names = fulltables.safe_names(ours)
    columns = layout() + [names[c] for c in ours]
    channel_of = channels(messages)

    out = []
    for row in rows:
        # A participant who never entered a triad has no treatment and so
        # belongs to no study; they are also the rows his resolved-target
        # columns cannot be computed for.
        if not str(row.get(MAIN + 'player.treatment') or '').strip():
            continue
        built = {STATA_RENAMES[c]: str(row.get(c, '') or '')
                 for c in BASE_ORDER}
        built.update(choice_values(row))
        built.update(partner_values(row, channel_of))
        built.update({names[c]: str(row.get(c, '') or '') for c in ours})
        out.append(built)

    labels = {names[c]: (label_of or {}).get(c) or fulltables._source(c)
              for c in ours}
    return {'columns': columns, 'rows': out, 'labels': labels,
            'ours': {names[c]: c for c in ours}}


def problems(columns) -> list:
    """Whatever in a header Stata 19 would refuse.

    The three checks his script makes as assertions. Here they are a function,
    so a test can run them over a real header instead of a run aborting on the
    researcher's machine.
    """
    import re

    found = []
    seen = set()
    for name in columns:
        if len(name) > 32:
            found.append(f'{name}: {len(name)} characters, Stata allows 32')
        if '.' in name:
            found.append(f'{name}: contains a dot')
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name):
            found.append(f'{name}: not a legal Stata name')
        if name.lower() in seen:
            found.append(f'{name}: appears twice')
        seen.add(name.lower())
    return found
