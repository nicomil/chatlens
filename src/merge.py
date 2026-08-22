"""
Unisce l'export delle scelte (``all_apps_wide``) con quello della chat
(``ChatMessages``) e costruisce le variabili di analisi dell'esperimento.

Chi entra nell'analisi
----------------------
Vengono tenuti i partecipanti che soddisfano due condizioni: hanno un
identificativo Prolific valido in ``participant.label``, il che scarta le
sessioni di collaudo interne, e hanno fatto parte di una triade, il che tiene
solo chi ha potuto comunicare. Chi e' stato poi escluso per inattivita' resta
nel dataset: la sua esclusione dalle analisi principali si governa con
``group_valid``. Con ``keep_all`` non si filtra nulla, per ispezionare i dati
grezzi.

Produce tre file:

``<stem>_messages_long.csv``
    Una riga per messaggio, con mittente e destinatario risolti in modo
    esatto. È l'input della pipeline NLP (TopicGPT e misure testuali).

``<stem>_chat_by_partner.csv``
    Una riga per coppia ordinata i -> j (sei per triade). Porta le variabili
    diadiche: segnale inviato, persuasione, coerenza segnale-scelta e le
    misure di conversazione della coppia.

``<stem>_chat_aggregated.csv``
    Una riga per partecipante, con la conversazione dell'intero gruppo e le
    variabili individuali (inganno strategico, coerenza media, validità).

Chiave di join
--------------
L'unica chiave affidabile è ``participant.code``: ``group.id_in_subsession``
non identifica la triade, perché chi non viene mai raggruppato resta
parcheggiato in un gruppo residuale insieme ad altri non raggruppati. La
triade viene quindi ricostruita da ``participant.part1_group_id`` quando
presente (export recenti) e, in subordine, dal prefisso del canale di chat,
che contiene lo stesso identificativo.

Uso (dal punto di ingresso del progetto):
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

# --- Costanti del gioco, allineate a bargaining_tdl_common/utils.py ---------

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

# Colonne MTurk: lo studio non gira su MTurk, vanno via dai dataset di analisi.
MTURK_COLS = {
    'participant.mturk_worker_id',
    'participant.mturk_assignment_id',
    'session.mturk_HITId',
    'session.mturk_HITGroupId',
}

CHANNEL_RE = re.compile(r'^(?P<prefix>.*)-(?P<group>\d+)_(?P<a>\d)_(?P<b>\d)$')


# --- Utilità ---------------------------------------------------------------


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
    """Il terzo membro della triade, dati due id_in_group."""
    return ({1, 2, 3} - {i, j}).pop()


def _partner_side(focal: int, target: int):
    """'left' / 'right' secondo la topologia circolare, altrimenti None."""
    partners = TOPOLOGY.get(focal, {})
    if partners.get('left') == target:
        return 'left'
    if partners.get('right') == target:
        return 'right'
    return None


def _decision_target(focal: int, decision: str):
    """id_in_group del giocatore effettivamente sostenuto, o None per NoOne."""
    if decision == 'Left':
        return TOPOLOGY[focal]['left']
    if decision == 'Right':
        return TOPOLOGY[focal]['right']
    return None


def _signal_declared_target(focal: int, target: int, signal: str):
    """Chi il segnale *dichiara* di voler sostenere.

    ``split_you``  -> il destinatario del segnale;
    ``split_other``-> il terzo giocatore;
    ``support_none``-> nessuno (None).
    """
    if signal == 'split_you':
        return target
    if signal == 'split_other':
        return _third_player(focal, target)
    return None


def _word_count(text: str) -> int:
    return len([t for t in re.split(r'\s+', text.strip()) if t])


# --- Lettura e ricostruzione delle triadi ----------------------------------


def load_wide(path: Path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def load_chat(path: Path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def is_grouped(row) -> bool:
    """True se il partecipante è entrato in una triade.

    ``main.player.treatment`` viene scritto solo in
    ``GroupingAfterControlQuestions.after_all_players_arrive``: è quindi il
    marcatore esatto della formazione del gruppo, e resta valorizzato anche
    per le triadi che si interrompono a metà.
    """
    return bool((row.get(MAIN + 'player.treatment') or '').strip()) and _int(
        row.get(MAIN + 'player.id_in_group')
    ) in (1, 2, 3)


# Un PROLIFIC_PID e' una stringa di 24 caratteri esadecimali. Il formato separa
# in modo netto i partecipanti reali da chi ha digitato un identificativo a mano
# durante i collaudi interni.
PROLIFIC_PID_RE = re.compile(r'^[0-9a-f]{24}$')


def has_prolific_label(row) -> bool:
    """True se il partecipante arriva davvero da Prolific.

    Si legge ``participant.label``, che oTree scrive dall'URL e il partecipante
    non puo' modificare, e non ``prolific_id``, che e' un campo di modulo e
    accetta anche testo digitato a mano.
    """
    return bool(PROLIFIC_PID_RE.match((row.get('participant.label') or '').strip()))


def select_participants(wide_rows):
    """Tiene i partecipanti reali che hanno fatto parte di una triade.

    Sono le due condizioni volute per l'analisi: identificativo Prolific valido,
    che scarta le sessioni di collaudo interne, ed effettiva appartenenza a un
    gruppo, che tiene solo chi ha potuto comunicare.

    Chi e' stato poi escluso per inattivita' resta dentro: ha comunicato, e la
    sua esclusione dalle analisi principali si governa con ``group_valid``, non
    togliendolo dal dataset.

    Restituisce le righe tenute e il conteggio degli scarti per motivo.
    """
    kept, dropped = [], {'mai_raggruppati': 0, 'senza_pid_prolific': 0}
    for row in wide_rows:
        if not is_grouped(row):
            dropped['mai_raggruppati'] += 1
        elif not has_prolific_label(row):
            dropped['senza_pid_prolific'] += 1
        else:
            kept.append(row)
    return kept, dropped


def build_groups(wide_rows, chat_rows):
    """Assegna a ogni partecipante raggruppato un ``group_uid`` stabile.

    Ordine di preferenza per l'identificativo:
      1. ``participant.part1_group_id`` (colonna nativa, export recenti);
      2. prefisso numerico del canale di chat del partecipante;
      3. chiave sintetica ``<session>-g<id_in_subsession>``, che resta corretta
         perché applicata ai soli partecipanti raggruppati.

    Restituisce ``(group_uid_per_code, groups, warnings)``.
    """
    warnings = []

    # Group id ricavato dai canali di chat, per participant.code.
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
                f'participant {code}: canali di chat con group id diversi '
                f'({previous} e {gid})'
            )
        chat_group_by_code[code] = gid

    # Passo 1: raggruppa i soli partecipanti raggruppati per (sessione,
    # id_in_subsession). Escludendo i non raggruppati, questa coppia torna a
    # essere una chiave valida: il gruppo residuale che li conteneva sparisce.
    clusters = defaultdict(list)
    for row in wide_rows:
        if not is_grouped(row):
            continue
        key = (row['session.code'], row.get(MAIN + 'group.id_in_subsession'))
        clusters[key].append(row)

    # Passo 2: assegna a ogni cluster un identificativo unico, preferendo
    # quello nativo del database (uguale al prefisso dei canali di chat), che
    # e' stabile fra sessioni diverse.
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
                f'{session}/g{id_in_subsession}: part1_group_id discordanti '
                f'{sorted(native_ids)}'
            )
        if len(chat_ids) > 1:
            warnings.append(
                f'{session}/g{id_in_subsession}: canali di chat con group id '
                f'discordanti {sorted(chat_ids)}'
            )
        if native_ids and chat_ids and native_ids != chat_ids:
            warnings.append(
                f'{session}/g{id_in_subsession}: part1_group_id {sorted(native_ids)} '
                f'diverso dal group id dei canali {sorted(chat_ids)}'
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
                    f'gruppo {uid}: id_in_group {pid} assegnato a piu partecipanti'
                )
            by_pid[pid] = row
            uid_by_code[row['participant.code']] = uid

        if set(by_pid) != {1, 2, 3}:
            warnings.append(
                f'gruppo {uid}: composizione anomala, id presenti {sorted(by_pid)}'
            )
        groups[uid] = by_pid

    return uid_by_code, groups, warnings


# --- Messaggi --------------------------------------------------------------


def build_messages(chat_rows, wide_by_code, uid_by_code):
    """Risolve mittente e destinatario di ogni messaggio.

    Il mittente è ``participant_code`` (dato esatto). Il destinatario è
    l'altro id della coppia contenuta nel canale. Il campo ``nickname`` NON
    viene usato: è relativo a chi legge, non a chi scrive.
    """
    messages = []
    anomalies = []

    for raw in chat_rows:
        code = raw.get('participant_code')
        row = wide_by_code.get(code)
        match = CHANNEL_RE.match(raw.get('channel', ''))
        if row is None or match is None:
            anomalies.append(
                f'messaggio non risolvibile: participant={code} '
                f'channel={raw.get("channel")!r}'
            )
            continue

        sender = _int(row.get(MAIN + 'player.id_in_group'))
        pair = (_int(match.group('a')), _int(match.group('b')))
        if sender not in pair:
            anomalies.append(
                f'messaggio di {code}: mittente id {sender} non presente nel '
                f'canale {raw.get("channel")!r}'
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

    # Indici progressivi: nel gruppo e nella coppia.
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


# --- Variabili derivate ----------------------------------------------------


def player_facts(row):
    """Estrae dalla riga wide i campi comportamentali usati nelle formule."""
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
    """Segnale che il focale ha inviato a ``target``."""
    side = _partner_side(facts['pid'], target)
    if side == 'left':
        return facts['signal_left']
    if side == 'right':
        return facts['signal_right']
    return ''


def timeout_flag(row) -> int:
    """1 se il partecipante ha fatto scadere un timer o è stato escluso."""
    hits = (
        row.get(MAIN + 'player.decision_inactive') == '99',
        row.get(MAIN + 'player.signal_inactive') == '99',
        (row.get('participant.inactive_excluded') or '').strip() in ('1', 'True'),
    )
    return int(any(hits))


def group_validity(members):
    """Validità della triade: basta un membro compromesso per invalidarla."""
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
    """Aggregati di conversazione per una lista di messaggi già filtrata."""
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
    """Trascrizione leggibile, un turno per riga, in ordine cronologico."""
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


# --- Costruzione degli output ----------------------------------------------


def clean_columns(fieldnames):
    """Colonne wide da riportare in output, senza quelle MTurk."""
    return [c for c in fieldnames if c not in MTURK_COLS]


def build_by_partner(wide_rows, wide_cols, groups, uid_by_code, messages):
    """Una riga per coppia ordinata i -> j, più i mai raggruppati."""
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
                # Coerenza segnale-scelta: l'azione dichiarata coincide con
                # quella effettivamente compiuta. Vale anche per il segnale
                # "non sostengo nessuno" seguito dalla scelta NoOne.
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

    # Mai raggruppati: una riga ciascuno, così nessun partecipante sparisce.
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
    """Una riga per partecipante, con la conversazione dell'intero gruppo."""
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

        # Inganno strategico: promette sostegno a entrambi e poi non sostiene
        # nessuno dei due.
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
    """Passo 1: unisce scelte e chat e costruisce le variabili dell'esperimento.

    Per impostazione predefinita tiene i soli partecipanti reali che hanno fatto
    parte di una triade (vedi `select_participants`). Con ``keep_all`` non
    filtra nulla: serve a ispezionare i dati grezzi, non ad analizzarli.

    Restituisce un riepilogo con i percorsi prodotti e i numeri da controllare.
    """
    wide_cols, all_rows = load_wide(wide_path)
    chat_rows = load_chat(chat_path)

    if keep_all:
        wide_rows, dropped = all_rows, {}
    else:
        wide_rows, dropped = select_participants(all_rows)

    wide_by_code = {r['participant.code']: r for r in wide_rows}

    # I messaggi di chi e' stato filtrato via non sono anomalie: si contano a
    # parte, cosi' il totale torna e non si confondono con quelli irrisolvibili.
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
            chat_kept.append(message)  # mittente ignoto: lo tratta build_messages

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

    return dict(
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


def print_summary(summary: dict) -> None:
    dropped = summary.get('dropped') or {}
    print(f"Partecipanti nell'export  : {summary['n_input']}")
    if dropped:
        print(f"  esclusi, mai raggruppati       : {dropped['mai_raggruppati']}")
        print(f"  esclusi, senza PID Prolific    : {dropped['senza_pid_prolific']}")
    print(f"Partecipanti analizzati   : {summary['n_participants']}")
    print(f"Triadi ricostruite        : {summary['n_groups']}")
    print(f"Triadi valide             : {summary['n_valid_groups']}"
          f"   (le altre hanno un membro escluso per inattivita', "
          f"ma restano nel dataset)")
    print(f"Messaggi nell'export      : {summary['n_messages_in']}")
    if summary.get('n_messages_filtered'):
        print(f"  di partecipanti esclusi : {summary['n_messages_filtered']}")
    print(f"Messaggi analizzati       : {summary['n_messages_resolved']}")

    atteso = summary['n_messages_in'] - summary.get('n_messages_filtered', 0)
    if summary['n_messages_resolved'] != atteso:
        print('  ATTENZIONE: non tutti i messaggi sono stati ricondotti a un '
              'partecipante; vedi gli avvisi qui sotto.')
    print()
    for path in summary['paths'].values():
        print(f'  {path}')
    for warning in summary['warnings']:
        print(f'ATTENZIONE: {warning}', file=sys.stderr)
