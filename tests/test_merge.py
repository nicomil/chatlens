"""Test per src/merge.py.

Girano su dati sintetici scritti su file temporanei: non serve ne' il database
ne' un export reale. Il controllo piu' forte e' la proprieta' di coerenza con
la funzione di payoff del gioco: se la mappatura fra ``decision_choice``
(relativa alla topologia circolare) e i giocatori assoluti fosse sbagliata, i
payoff ricalcolati dal profilo di scelte non coinciderebbero con quelli
esportati da oTree.

    python tests/test_merge.py
"""

import contextlib
import csv
import importlib.util
import io
import itertools
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def custom_calculate_payoff_vector(decisions, no_deadweight_loss=False):
    """Regola di payoff del gioco, riprodotta qui.

    Il progetto di analisi è autonomo e non deve dipendere dal codice
    dell'esperimento per poter girare. La regola è però la stessa, e
    `PayoffRuleMatchesExperimentTests` verifica che le due implementazioni
    coincidano quando il codice dell'esperimento è raggiungibile: così la copia
    non può divergere in silenzio.

    Topologia: P1.left=P3, P1.right=P2; P2.left=P1, P2.right=P3;
    P3.left=P2, P3.right=P1.
    """
    c1, c2, c3 = decisions

    # Coalizione minima vincente: sostegno strettamente reciproco.
    if c1 == 'Right' and c2 == 'Left':
        return (3, 3, 0), 'mutual_12'
    if c2 == 'Right' and c3 == 'Left':
        return (0, 3, 3), 'mutual_23'
    if c3 == 'Right' and c1 == 'Left':
        return (3, 0, 3), 'mutual_31'

    if no_deadweight_loss:
        # Due sostengono lo stesso terzo, che a sua volta non sostiene nessuno.
        if c1 == 'NoOne' and c2 == 'Left' and c3 == 'Right':
            return (6, 0, 0), 'no_dwl_star_1'
        if c2 == 'NoOne' and c1 == 'Right' and c3 == 'Left':
            return (0, 6, 0), 'no_dwl_star_2'
        if c3 == 'NoOne' and c1 == 'Left' and c2 == 'Right':
            return (0, 0, 6), 'no_dwl_star_3'

    return (0, 0, 0), 'disagreement'


def _experiment_payoff_rule():
    """Implementazione dell'esperimento, se raggiungibile da qui.

    L'import trascina la configurazione di oTree, che pretende di girare dalla
    cartella dell'esperimento e può fallire per ragioni che non riguardano
    questo progetto: qualunque problema si traduce in "non disponibile", e il
    confronto viene saltato anziché segnalare un falso errore.
    """
    import os

    experiment_root = PROJECT_ROOT.parent
    if not (experiment_root / 'bargaining_tdl_common').is_dir():
        return None

    previous_cwd = os.getcwd()
    sys.path.insert(0, str(experiment_root))
    try:
        os.chdir(experiment_root)
        from bargaining_tdl_common.utils import (
            custom_calculate_payoff_vector as reference,
        )
        return reference
    except Exception:  # noqa: BLE001 - dipende dall'ambiente, non dal codice
        return None
    finally:
        os.chdir(previous_cwd)
        if sys.path and sys.path[0] == str(experiment_root):
            sys.path.pop(0)


def _load_module():
    path = Path(__file__).resolve().parent.parent / 'src' / 'merge.py'
    spec = importlib.util.spec_from_file_location('merge', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load_module()
MAIN = mod.MAIN

WIDE_COLUMNS = [
    'participant.id_in_session', 'participant.code', 'participant.label',
    'participant.mturk_worker_id', 'participant.mturk_assignment_id',
    'participant.treatment', 'participant.inactive_excluded',
    'participant.part1_group_id',
    'session.code', 'session.mturk_HITId',
    MAIN + 'player.id_in_group', MAIN + 'player.treatment',
    MAIN + 'player.signal_left', MAIN + 'player.signal_right',
    MAIN + 'player.decision_choice', MAIN + 'player.payoff',
    MAIN + 'player.part1_calculated_payoff',
    MAIN + 'player.decision_inactive', MAIN + 'player.signal_inactive',
    MAIN + 'group.id_in_subsession', MAIN + 'group.group_outcome',
    MAIN + 'group.grp_coordinate', MAIN + 'group.group_dropped',
]


def make_player(session, code, pid, treatment, decision, sig_left, sig_right,
                payoff, group_db_id='', id_in_subsession='2', dropped='0',
                decision_inactive='0'):
    row = {c: '' for c in WIDE_COLUMNS}
    row.update({
        'participant.id_in_session': str(pid),
        'participant.code': code,
        'participant.treatment': treatment,
        'participant.part1_group_id': group_db_id,
        'session.code': session,
        MAIN + 'player.id_in_group': str(pid),
        MAIN + 'player.treatment': treatment,
        MAIN + 'player.signal_left': sig_left,
        MAIN + 'player.signal_right': sig_right,
        MAIN + 'player.decision_choice': decision,
        MAIN + 'player.payoff': str(payoff),
        MAIN + 'player.part1_calculated_payoff': str(payoff),
        MAIN + 'player.decision_inactive': decision_inactive,
        MAIN + 'player.signal_inactive': '0',
        MAIN + 'group.id_in_subsession': id_in_subsession,
        MAIN + 'group.group_dropped': dropped,
    })
    return row


def make_ungrouped(session, code, pid):
    row = {c: '' for c in WIDE_COLUMNS}
    row.update({
        'participant.id_in_session': str(pid),
        'participant.code': code,
        'session.code': session,
        MAIN + 'player.id_in_group': str(pid),
        MAIN + 'group.id_in_subsession': '1',
    })
    return row


def run_merge(wide_rows, chat_rows, tmpdir):
    wide_path = Path(tmpdir) / 'wide.csv'
    chat_path = Path(tmpdir) / 'chat.csv'
    outdir = Path(tmpdir) / 'out'

    with wide_path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=WIDE_COLUMNS)
        writer.writeheader()
        writer.writerows(wide_rows)

    chat_cols = ['session_code', 'id_in_session', 'participant_code', 'channel',
                 'nickname', 'body', 'timestamp']
    with chat_path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=chat_cols)
        writer.writeheader()
        writer.writerows(chat_rows)

    # Il riepilogo su stdout renderebbe illeggibile l'output dei test.
    with contextlib.redirect_stdout(io.StringIO()):
        mod.run(wide_path, chat_path, outdir, 't')

    def read(name):
        with (outdir / f't_{name}.csv').open(encoding='utf-8-sig', newline='') as handle:
            return list(csv.DictReader(handle))

    return read('messages_long'), read('chat_by_partner'), read('chat_aggregated')


class PayoffRuleMatchesExperimentTests(unittest.TestCase):
    """La copia locale della regola di payoff non deve divergere dall'originale."""

    def test_identical_on_all_27_profiles(self):
        reference = _experiment_payoff_rule()
        if reference is None:
            self.skipTest(
                'codice dell esperimento non raggiungibile: progetto usato in '
                'modo autonomo'
            )
        for decisions in itertools.product(mod.VALID_DECISIONS, repeat=3):
            for no_dwl in (False, True):
                self.assertEqual(
                    custom_calculate_payoff_vector(decisions, no_dwl),
                    reference(decisions, no_dwl),
                    msg=f'profilo {decisions}, no_dwl={no_dwl}',
                )


class TopologyTests(unittest.TestCase):
    def test_decision_target_follows_topology(self):
        self.assertEqual(mod._decision_target(1, 'Left'), 3)
        self.assertEqual(mod._decision_target(1, 'Right'), 2)
        self.assertEqual(mod._decision_target(2, 'Left'), 1)
        self.assertEqual(mod._decision_target(3, 'Right'), 1)
        self.assertIsNone(mod._decision_target(1, 'NoOne'))

    def test_signal_declared_target(self):
        # P1 scrive a P2 (il suo 'right'); il terzo e' P3.
        self.assertEqual(mod._signal_declared_target(1, 2, 'split_you'), 2)
        self.assertEqual(mod._signal_declared_target(1, 2, 'split_other'), 3)
        self.assertIsNone(mod._signal_declared_target(1, 2, 'support_none'))

    def test_third_player(self):
        self.assertEqual(mod._third_player(1, 2), 3)
        self.assertEqual(mod._third_player(2, 3), 1)


class PayoffConsistencyTests(unittest.TestCase):
    """Il merge deve riprodurre i payoff su tutti i 27 profili di scelta."""

    def _check_profile(self, decisions, no_dwl):
        treatment = 'private_no_dwl' if no_dwl else 'private'
        payoffs, _outcome = custom_calculate_payoff_vector(decisions, no_dwl)
        wide = [
            make_player('s1', f'c{pid}', pid, treatment, decisions[pid - 1],
                        'split_you', 'split_you', payoffs[pid - 1],
                        group_db_id='10')
            for pid in (1, 2, 3)
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            _long, by_partner, aggregated = run_merge(wide, [], tmpdir)

        # Ogni riga i->j deve dichiarare A_ji coerente con la scelta di j.
        for row in by_partner:
            i = int(row['focal_id_in_group'])
            j = int(row['partner_id_in_group'])
            expected = int(mod._decision_target(j, decisions[j - 1]) == i)
            self.assertEqual(int(row['A_ji']), expected,
                             msg=f'profilo {decisions}, coppia {i}->{j}')

        # Il payoff di gruppo riportato deve coincidere con quello del gioco.
        total = sum(payoffs)
        for row in aggregated:
            self.assertEqual(float(row['group_total_payoff']), float(total),
                             msg=f'profilo {decisions}')

    def test_all_27_profiles_tdl(self):
        for decisions in itertools.product(mod.VALID_DECISIONS, repeat=3):
            self._check_profile(decisions, no_dwl=False)

    def test_all_27_profiles_no_dwl(self):
        for decisions in itertools.product(mod.VALID_DECISIONS, repeat=3):
            self._check_profile(decisions, no_dwl=True)


class DerivedVariableTests(unittest.TestCase):
    def _triad(self, signals, decisions, treatment='private'):
        """signals: {pid: (signal_to_left, signal_to_right)}"""
        return [
            make_player('s1', f'c{pid}', pid, treatment, decisions[pid - 1],
                        signals[pid][0], signals[pid][1], 0, group_db_id='10')
            for pid in (1, 2, 3)
        ]

    def test_persuasion_requires_signal_and_support(self):
        # P1 promette sostegno a P2 (right) e P2 sceglie 'Left', cioe' P1.
        wide = self._triad(
            signals={1: ('split_other', 'split_you'),
                     2: ('split_you', 'split_other'),
                     3: ('split_other', 'split_other')},
            decisions=['Right', 'Left', 'NoOne'],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            _long, by_partner, _agg = run_merge(wide, [], tmpdir)
        rows = {(int(r['focal_id_in_group']), int(r['partner_id_in_group'])): r
                for r in by_partner if r['group_uid']}

        self.assertEqual(int(rows[(1, 2)]['S_ij']), 1)
        self.assertEqual(int(rows[(1, 2)]['A_ji']), 1)
        self.assertEqual(int(rows[(1, 2)]['persuasion_ij']), 1)

        # P1 verso P3: nessuna promessa di sostegno, quindi niente persuasione
        # anche se P3 non lo sostiene comunque.
        self.assertEqual(int(rows[(1, 3)]['S_ij']), 0)
        self.assertEqual(int(rows[(1, 3)]['persuasion_ij']), 0)

    def test_consistency_covers_all_three_signals(self):
        # P1 dichiara a P3 (left) di sostenere l'altro, cioe' P2, e poi
        # sceglie davvero P2 ('Right'): coerente.
        # P1 dichiara a P2 (right) di sostenere lui, ma sceglie P2: coerente.
        wide = self._triad(
            signals={1: ('split_other', 'split_you'),
                     2: ('support_none', 'support_none'),
                     3: ('split_you', 'split_you')},
            decisions=['Right', 'NoOne', 'Left'],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            _long, by_partner, aggregated = run_merge(wide, [], tmpdir)
        rows = {(int(r['focal_id_in_group']), int(r['partner_id_in_group'])): r
                for r in by_partner if r['group_uid']}

        self.assertEqual(int(rows[(1, 3)]['C_ij']), 1)
        self.assertEqual(int(rows[(1, 2)]['C_ij']), 1)
        # P2 annuncia 'nessuno' a entrambi e sceglie NoOne: pienamente coerente.
        self.assertEqual(int(rows[(2, 1)]['C_ij']), 1)
        self.assertEqual(int(rows[(2, 3)]['C_ij']), 1)
        # P3 promette sostegno a entrambi ma ne sostiene uno solo: 0.5.
        agg = {int(r['focal_id_in_group']): r for r in aggregated if r['group_uid']}
        self.assertEqual(float(agg[2]['cc_i']), 1.0)
        self.assertEqual(float(agg[3]['cc_i']), 0.5)

    def test_strategic_deception(self):
        # P1 promette sostegno a entrambi e poi non sostiene nessuno.
        wide = self._triad(
            signals={1: ('split_you', 'split_you'),
                     2: ('split_you', 'split_you'),
                     3: ('split_other', 'split_other')},
            decisions=['NoOne', 'Left', 'Left'],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            _long, _by_partner, aggregated = run_merge(wide, [], tmpdir)
        agg = {int(r['focal_id_in_group']): r for r in aggregated if r['group_uid']}

        self.assertEqual(int(agg[1]['strategic_deception']), 1)
        # P2 promette a entrambi ma poi sceglie: non e' inganno strategico.
        self.assertEqual(int(agg[2]['strategic_deception']), 0)
        self.assertEqual(int(agg[3]['strategic_deception']), 0)


class GroupingTests(unittest.TestCase):
    def test_ungrouped_do_not_form_a_group(self):
        """Chi non e' mai stato raggruppato resta nel gruppo residuale 1.

        Se venisse trattato come una triade, il gruppo 1 diventerebbe un
        finto gruppo con molti membri.
        """
        wide = [
            make_player('s1', 'a1', 1, 'private', 'Right', 'split_you',
                        'split_you', 3, group_db_id='7'),
            make_player('s1', 'a2', 2, 'private', 'Left', 'split_you',
                        'split_you', 3, group_db_id='7'),
            make_player('s1', 'a3', 3, 'private', 'NoOne', 'split_you',
                        'split_you', 0, group_db_id='7'),
        ]
        wide += [make_ungrouped('s1', f'u{n}', n) for n in range(4, 10)]

        with tempfile.TemporaryDirectory() as tmpdir:
            _long, by_partner, aggregated = run_merge(wide, [], tmpdir)

        self.assertEqual(len(aggregated), 9)
        never = [r for r in aggregated if r['chat_status'] == 'never_grouped']
        self.assertEqual(len(never), 6)
        # Sei coppie ordinate per l'unica triade, piu' una riga per ciascun
        # partecipante mai raggruppato: nessuno viene perso.
        self.assertEqual(len(by_partner), 6 + 6)

    def test_group_uid_survives_members_without_chat(self):
        """Un membro silenzioso non deve finire in una triade separata."""
        wide = [
            make_player('s1', 'a1', 1, 'private', 'Right', 'split_you',
                        'split_you', 3),
            make_player('s1', 'a2', 2, 'private', 'Left', 'split_you',
                        'split_you', 3),
            make_player('s1', 'a3', 3, 'private', 'NoOne', 'split_you',
                        'split_you', 0),
        ]
        # Solo P1 e P2 scrivono: P3 non compare in nessun canale.
        chat = [
            dict(session_code='s1', id_in_session='1', participant_code='a1',
                 channel='4-bargaining_tdl_main-7_1_2', nickname='LeftPartner',
                 body='ciao', timestamp='100.0'),
            dict(session_code='s1', id_in_session='2', participant_code='a2',
                 channel='4-bargaining_tdl_main-7_1_2', nickname='RightPartner',
                 body='ok', timestamp='101.0'),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            _long, _by_partner, aggregated = run_merge(wide, chat, tmpdir)

        uids = {r['group_uid'] for r in aggregated}
        self.assertEqual(uids, {'s1-db7'})

    def test_group_validity_flags_timeout(self):
        wide = [
            make_player('s1', 'a1', 1, 'private', 'Right', 'split_you',
                        'split_you', 3, group_db_id='7'),
            make_player('s1', 'a2', 2, 'private', 'Left', 'split_you',
                        'split_you', 3, group_db_id='7'),
            make_player('s1', 'a3', 3, 'private', 'NoOne', 'split_you',
                        'split_you', 0, group_db_id='7',
                        decision_inactive='99'),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            _long, _by_partner, aggregated = run_merge(wide, [], tmpdir)

        # Il timeout di un solo membro invalida l'intera triade.
        for row in aggregated:
            self.assertEqual(int(row['group_valid']), 0)
            self.assertEqual(int(row['group_any_timeout']), 1)
        flags = {int(r['focal_id_in_group']): int(r['focal_timeout_flag'])
                 for r in aggregated}
        self.assertEqual(flags, {1: 0, 2: 0, 3: 1})


class MessageDirectionTests(unittest.TestCase):
    def test_sender_comes_from_participant_code_not_nickname(self):
        """Il nickname e' relativo a chi legge: non deve determinare il mittente."""
        wide = [
            make_player('s1', 'a1', 1, 'private', 'Right', 'split_you',
                        'split_you', 3, group_db_id='7'),
            make_player('s1', 'a2', 2, 'private', 'Left', 'split_you',
                        'split_you', 3, group_db_id='7'),
            make_player('s1', 'a3', 3, 'private', 'NoOne', 'split_you',
                        'split_you', 0, group_db_id='7'),
        ]
        chat = [
            # Nickname deliberatamente fuorviante: il mittente e' P1.
            dict(session_code='s1', id_in_session='1', participant_code='a1',
                 channel='4-bargaining_tdl_main-7_1_2', nickname='LeftPartner',
                 body='sono P1', timestamp='100.0'),
            dict(session_code='s1', id_in_session='3', participant_code='a3',
                 channel='4-bargaining_tdl_main-7_1_3', nickname='LeftPartner',
                 body='sono P3', timestamp='102.0'),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            long_rows, by_partner, _agg = run_merge(wide, chat, tmpdir)

        first = long_rows[0]
        self.assertEqual(int(first['sender_id_in_group']), 1)
        self.assertEqual(int(first['receiver_id_in_group']), 2)
        second = long_rows[1]
        self.assertEqual(int(second['sender_id_in_group']), 3)
        self.assertEqual(int(second['receiver_id_in_group']), 1)

        # Nella coppia 1->2, il messaggio conta come inviato da P1 e ricevuto
        # da P2, senza doppi conteggi.
        rows = {(int(r['focal_id_in_group']), int(r['partner_id_in_group'])): r
                for r in by_partner if r['group_uid']}
        self.assertEqual(int(rows[(1, 2)]['sent_n_messages']), 1)
        self.assertEqual(int(rows[(1, 2)]['recv_n_messages']), 0)
        self.assertEqual(int(rows[(2, 1)]['sent_n_messages']), 0)
        self.assertEqual(int(rows[(2, 1)]['recv_n_messages']), 1)
        self.assertEqual(int(rows[(1, 2)]['dyad_n_messages']), 1)


class OutputHygieneTests(unittest.TestCase):
    def test_mturk_columns_are_dropped(self):
        wide = [make_ungrouped('s1', 'u1', 1)]
        with tempfile.TemporaryDirectory() as tmpdir:
            _long, by_partner, aggregated = run_merge(wide, [], tmpdir)
        for rows in (by_partner, aggregated):
            for column in mod.MTURK_COLS:
                self.assertNotIn(column, rows[0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
