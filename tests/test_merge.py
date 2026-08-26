"""Tests for src/merge.py.

They run on synthetic data written to temporary files: neither the database
nor a real export is needed. The strongest check is the consistency property
with the game's payoff function: if the mapping between ``decision_choice``
(relative to the circular topology) and the absolute players were wrong, the
payoffs recomputed from the choice profile would not match the ones oTree
exported.

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
    """The game's payoff rule, reproduced here.

    The analysis project is self-contained and must not depend on the
    experiment's code in order to run. The rule is however the same, and
    `PayoffRuleMatchesExperimentTests` checks that the two implementations
    agree whenever the experiment's code is reachable: that way the copy cannot
    drift in silence.

    Topology: P1.left=P3, P1.right=P2; P2.left=P1, P2.right=P3;
    P3.left=P2, P3.right=P1.
    """
    c1, c2, c3 = decisions

    # Minimal winning coalition: strictly reciprocal support.
    if c1 == 'Right' and c2 == 'Left':
        return (3, 3, 0), 'mutual_12'
    if c2 == 'Right' and c3 == 'Left':
        return (0, 3, 3), 'mutual_23'
    if c3 == 'Right' and c1 == 'Left':
        return (3, 0, 3), 'mutual_31'

    if no_deadweight_loss:
        # Two support the same third, who in turn supports no one.
        if c1 == 'NoOne' and c2 == 'Left' and c3 == 'Right':
            return (6, 0, 0), 'no_dwl_star_1'
        if c2 == 'NoOne' and c1 == 'Right' and c3 == 'Left':
            return (0, 6, 0), 'no_dwl_star_2'
        if c3 == 'NoOne' and c1 == 'Left' and c2 == 'Right':
            return (0, 0, 6), 'no_dwl_star_3'

    return (0, 0, 0), 'disagreement'


EXPERIMENT_UTILS = PROJECT_ROOT.parent / 'bargaining_tdl_common' / 'utils.py'


def _experiment_payoff_rule():
    """Extract the payoff rule from the experiment's source, if present.

    The function is isolated from the file with the syntax analyser and
    executed on its own, without importing the package: importing it would drag
    in oTree, which is not installed in this project and must not be. That way
    the comparison really runs in the normal flow, instead of being skipped
    every time and giving a false sense of coverage.

    Returns None only when the experiment's file is unreachable, that is when
    this project is used on its own.
    """
    import ast

    if not EXPERIMENT_UTILS.is_file():
        return None

    tree = ast.parse(EXPERIMENT_UTILS.read_text(encoding='utf-8'))
    wanted = 'custom_calculate_payoff_vector'
    node = next(
        (n for n in tree.body
         if isinstance(n, ast.FunctionDef) and n.name == wanted),
        None,
    )
    if node is None:
        return None

    namespace = {'VALID_DECISIONS': mod.VALID_DECISIONS}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(EXPERIMENT_UTILS),
                 'exec'), namespace)
    return namespace[wanted]


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
    MAIN + 'player.id_player_visualized_on_the_left',
    MAIN + 'player.id_player_visualized_on_the_right',
    MAIN + 'player.decision_option_1', MAIN + 'player.decision_option_2',
    MAIN + 'player.decision_option_3',
    MAIN + 'group.id_in_subsession', MAIN + 'group.group_outcome',
    MAIN + 'group.grp_coordinate', MAIN + 'group.group_dropped',
]


# A plausible Prolific identifier: 24 hexadecimal characters. It is needed
# because the merge keeps only real participants, and the fixtures represent
# exactly that.
def fake_prolific_pid(seed) -> str:
    return f'{abs(hash(str(seed))):024x}'[:24]


def make_player(session, code, pid, treatment, decision, sig_left, sig_right,
                payoff, group_db_id='', id_in_subsession='2', dropped='0',
                decision_inactive='0', label=None):
    row = {c: '' for c in WIDE_COLUMNS}
    row.update({
        'participant.id_in_session': str(pid),
        'participant.code': code,
        'participant.label': fake_prolific_pid(code) if label is None else label,
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


def _run_raw(wide_rows, chat_rows, tmpdir, keep_all=False):
    """Run the merge and return the summary."""
    wide_path = Path(tmpdir) / 'wide.csv'
    chat_path = Path(tmpdir) / 'chat.csv'
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
    with contextlib.redirect_stdout(io.StringIO()):
        return mod.run(wide_path, chat_path, Path(tmpdir) / 'out', 't',
                       keep_all=keep_all)


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

    # The summary on stdout would make the test output unreadable.
    with contextlib.redirect_stdout(io.StringIO()):
        mod.run(wide_path, chat_path, outdir, 't')

    def read(name):
        with (outdir / f't_{name}.csv').open(encoding='utf-8-sig', newline='') as handle:
            return list(csv.DictReader(handle))

    return read('messages_long'), read('chat_by_partner'), read('chat_aggregated')


class PayoffRuleMatchesExperimentTests(unittest.TestCase):
    """The three copies of the payoff rule must not drift apart.

    The rule lives in the experiment, in this test file, and — since the
    consistency flag needs it — in the pipeline itself. Three copies is two too
    many, but the alternative is importing oTree into an analysis project that
    must run without it. This test is what keeps them a single rule.
    """

    def test_identical_on_all_27_profiles(self):
        reference = _experiment_payoff_rule()
        if reference is None:
            self.skipTest(
                "the experiment's code is not reachable: project used on its own"
            )
        for decisions in itertools.product(mod.VALID_DECISIONS, repeat=3):
            for no_dwl in (False, True):
                self.assertEqual(
                    custom_calculate_payoff_vector(decisions, no_dwl),
                    reference(decisions, no_dwl),
                    msg=f'profilo {decisions}, no_dwl={no_dwl}',
                )

    def test_the_pipeline_uses_the_same_rule(self):
        """The copy inside merge.py, checked against the same 27 profiles."""
        reference = _experiment_payoff_rule()
        if reference is None:
            self.skipTest(
                "the experiment's code is not reachable: project used on its own"
            )
        for decisions in itertools.product(mod.VALID_DECISIONS, repeat=3):
            for no_dwl in (False, True):
                self.assertEqual(
                    mod.payoff_vector(decisions, no_deadweight_loss=no_dwl),
                    reference(decisions, no_dwl),
                    msg=f'profilo {decisions}, no_dwl={no_dwl}',
                )


class PayoffConsistencyTests2(unittest.TestCase):
    """Il payoff registrato deve essere ricostruibile dalle decisioni salvate.

    Quando non lo e', la riga va marcata: la scelta sostituita non e'
    nell'export e non si recupera, ma la contraddizione deve essere visibile
    invece di essere scambiata per corruzione dei dati mesi dopo.
    """

    def _triad(self, decisions, outcome, treatment='private'):
        rows = [
            make_player('s1', f'c{pid}', pid, treatment, decisions[pid - 1],
                        'split_you', 'split_you', 0, group_db_id='7')
            for pid in (1, 2, 3)
        ]
        for row in rows:
            row[MAIN + 'group.group_outcome'] = outcome
        return rows

    def test_flag_off_when_outcome_follows_from_the_decisions(self):
        wide = self._triad(['Right', 'Left', 'NoOne'], 'mutual_12')
        with tempfile.TemporaryDirectory() as tmpdir:
            _long, by_partner, aggregated = run_merge(wide, [], tmpdir)
        rows = [r for r in by_partner if r['group_uid']]
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row['group_outcome_recomputed'], 'mutual_12')
            self.assertEqual(row['payoff_decision_mismatch'], '0')
        for row in (r for r in aggregated if r['group_uid']):
            self.assertEqual(row['payoff_decision_mismatch'], '0')

    def test_flag_on_when_the_stored_decision_was_overwritten(self):
        """Il caso vero: esito da coalizione, decisioni da disaccordo."""
        wide = self._triad(['Right', 'NoOne', 'Left'], 'mutual_12')
        with tempfile.TemporaryDirectory() as tmpdir:
            _long, by_partner, aggregated = run_merge(wide, [], tmpdir)
        rows = [r for r in by_partner if r['group_uid']]
        for row in rows:
            self.assertEqual(row['group_outcome_recomputed'], 'disagreement')
            self.assertEqual(row['payoff_decision_mismatch'], '1')
        for row in (r for r in aggregated if r['group_uid']):
            self.assertEqual(row['payoff_decision_mismatch'], '1')

    def test_no_dwl_star_is_not_read_as_a_contradiction(self):
        """Nel trattamento senza deadweight loss lo star e' un esito legittimo."""
        wide = self._triad(['NoOne', 'Left', 'Right'], 'no_dwl_star_1',
                           treatment='private_no_dwl')
        with tempfile.TemporaryDirectory() as tmpdir:
            _long, by_partner, _agg = run_merge(wide, [], tmpdir)
        for row in (r for r in by_partner if r['group_uid']):
            self.assertEqual(row['group_outcome_recomputed'], 'no_dwl_star_1')
            self.assertEqual(row['payoff_decision_mismatch'], '0')

    def test_pending_outcome_leaves_the_flag_empty(self):
        """Non ancora calcolato non e' la stessa cosa di controllato e a posto."""
        wide = self._triad(['Right', 'Left', 'NoOne'], 'pending')
        with tempfile.TemporaryDirectory() as tmpdir:
            _long, by_partner, _agg = run_merge(wide, [], tmpdir)
        for row in (r for r in by_partner if r['group_uid']):
            self.assertEqual(row['payoff_decision_mismatch'], '')
            self.assertEqual(row['group_outcome_recomputed'], 'mutual_12')


class TopologyTests(unittest.TestCase):
    def test_decision_target_follows_topology(self):
        self.assertEqual(mod._decision_target(1, 'Left'), 3)
        self.assertEqual(mod._decision_target(1, 'Right'), 2)
        self.assertEqual(mod._decision_target(2, 'Left'), 1)
        self.assertEqual(mod._decision_target(3, 'Right'), 1)
        self.assertIsNone(mod._decision_target(1, 'NoOne'))

    def test_signal_declared_target(self):
        # P1 writes to P2 (their 'right'); the third is P3.
        self.assertEqual(mod._signal_declared_target(1, 2, 'split_you'), 2)
        self.assertEqual(mod._signal_declared_target(1, 2, 'split_other'), 3)
        self.assertIsNone(mod._signal_declared_target(1, 2, 'support_none'))

    def test_third_player(self):
        self.assertEqual(mod._third_player(1, 2), 3)
        self.assertEqual(mod._third_player(2, 3), 1)


class PayoffConsistencyTests(unittest.TestCase):
    """The merge must reproduce the payoffs on all 27 choice profiles."""

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

        # Every i->j row must declare A_ji consistent with j's choice.
        for row in by_partner:
            i = int(row['focal_id_in_group'])
            j = int(row['partner_id_in_group'])
            expected = int(mod._decision_target(j, decisions[j - 1]) == i)
            self.assertEqual(int(row['A_ji']), expected,
                             msg=f'profile {decisions}, pair {i}->{j}')

        # The reported group payoff must match the game's.
        total = sum(payoffs)
        for row in aggregated:
            self.assertEqual(float(row['group_total_payoff']), float(total),
                             msg=f'profile {decisions}')

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
        # P1 promises support to P2 (right) and P2 chooses 'Left', that is P1.
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

        # P1 towards P3: no promise of support, hence no persuasion even
        # though P3 does not support them anyway.
        self.assertEqual(int(rows[(1, 3)]['S_ij']), 0)
        self.assertEqual(int(rows[(1, 3)]['persuasion_ij']), 0)

    def test_consistency_covers_all_three_signals(self):
        # P1 tells P3 (left) they will support the other, that is P2, and
        # then really chooses P2 ('Right'): consistent.
        # P1 tells P2 (right) they will support them, and chooses P2:
        # consistent.
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
        # P2 announces 'no one' to both and chooses NoOne: fully consistent.
        self.assertEqual(int(rows[(2, 1)]['C_ij']), 1)
        self.assertEqual(int(rows[(2, 3)]['C_ij']), 1)
        # P3 promises support to both but supports only one: 0.5.
        agg = {int(r['focal_id_in_group']): r for r in aggregated if r['group_uid']}
        self.assertEqual(float(agg[2]['cc_i']), 1.0)
        self.assertEqual(float(agg[3]['cc_i']), 0.5)

    def test_strategic_deception(self):
        # P1 promises support to both and then supports no one.
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
        # P2 promises to both but then does choose: not strategic deception.
        self.assertEqual(int(agg[2]['strategic_deception']), 0)
        self.assertEqual(int(agg[3]['strategic_deception']), 0)


class GroupingTests(unittest.TestCase):
    def test_ungrouped_are_excluded_from_the_analysis(self):
        """Whoever was never grouped did not communicate: they stay out.

        The residual group where oTree parks the ungrouped is not a triad, and
        its members never had a chance to exchange messages.
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

        # The triad only: six directed pairs and three participants.
        self.assertEqual(len(aggregated), 3)
        self.assertEqual(len(by_partner), 6)
        self.assertEqual({r['group_uid'] for r in aggregated}, {'s1-db7'})

    def test_group_uid_survives_members_without_chat(self):
        """A silent member must not end up in a triad of their own."""
        wide = [
            make_player('s1', 'a1', 1, 'private', 'Right', 'split_you',
                        'split_you', 3),
            make_player('s1', 'a2', 2, 'private', 'Left', 'split_you',
                        'split_you', 3),
            make_player('s1', 'a3', 3, 'private', 'NoOne', 'split_you',
                        'split_you', 0),
        ]
        # Only P1 and P2 write: P3 appears in no channel.
        chat = [
            dict(session_code='s1', id_in_session='1', participant_code='a1',
                 channel='4-bargaining_tdl_main-7_1_2', nickname='LeftPartner',
                 body='hi', timestamp='100.0'),
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

        # A single member's timeout invalidates the whole triad.
        for row in aggregated:
            self.assertEqual(int(row['group_valid']), 0)
            self.assertEqual(int(row['group_any_timeout']), 1)
        flags = {int(r['focal_id_in_group']): int(r['focal_timeout_flag'])
                 for r in aggregated}
        self.assertEqual(flags, {1: 0, 2: 0, 3: 1})


class MessageDirectionTests(unittest.TestCase):
    def test_sender_comes_from_participant_code_not_nickname(self):
        """The nickname is relative to the reader: it must not set the sender."""
        wide = [
            make_player('s1', 'a1', 1, 'private', 'Right', 'split_you',
                        'split_you', 3, group_db_id='7'),
            make_player('s1', 'a2', 2, 'private', 'Left', 'split_you',
                        'split_you', 3, group_db_id='7'),
            make_player('s1', 'a3', 3, 'private', 'NoOne', 'split_you',
                        'split_you', 0, group_db_id='7'),
        ]
        chat = [
            # Deliberately misleading nickname: the sender is P1.
            dict(session_code='s1', id_in_session='1', participant_code='a1',
                 channel='4-bargaining_tdl_main-7_1_2', nickname='LeftPartner',
                 body='I am P1', timestamp='100.0'),
            dict(session_code='s1', id_in_session='3', participant_code='a3',
                 channel='4-bargaining_tdl_main-7_1_3', nickname='LeftPartner',
                 body='I am P3', timestamp='102.0'),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            long_rows, by_partner, _agg = run_merge(wide, chat, tmpdir)

        first = long_rows[0]
        self.assertEqual(int(first['sender_id_in_group']), 1)
        self.assertEqual(int(first['receiver_id_in_group']), 2)
        second = long_rows[1]
        self.assertEqual(int(second['sender_id_in_group']), 3)
        self.assertEqual(int(second['receiver_id_in_group']), 1)

        # In the 1->2 pair the message counts as sent by P1 and received by
        # P2, with no double counting.
        rows = {(int(r['focal_id_in_group']), int(r['partner_id_in_group'])): r
                for r in by_partner if r['group_uid']}
        self.assertEqual(int(rows[(1, 2)]['sent_n_messages']), 1)
        self.assertEqual(int(rows[(1, 2)]['recv_n_messages']), 0)
        self.assertEqual(int(rows[(2, 1)]['sent_n_messages']), 0)
        self.assertEqual(int(rows[(2, 1)]['recv_n_messages']), 1)
        self.assertEqual(int(rows[(1, 2)]['dyad_n_messages']), 1)


class ParticipantFilterTests(unittest.TestCase):
    """Only real participants who were part of a triad get in."""

    def _triad(self, prefix, group_db_id, **kw):
        # A distinct id_in_subsession per triad, as in real data: two groups
        # of the same session never share that number.
        kw.setdefault('id_in_subsession', str(group_db_id))
        return [
            make_player('s1', f'{prefix}1', 1, 'private', 'Right', 'split_you',
                        'split_you', 3, group_db_id=group_db_id, **kw),
            make_player('s1', f'{prefix}2', 2, 'private', 'Left', 'split_you',
                        'split_you', 3, group_db_id=group_db_id, **kw),
            make_player('s1', f'{prefix}3', 3, 'private', 'NoOne', 'split_you',
                        'split_you', 0, group_db_id=group_db_id, **kw),
        ]

    def test_prolific_label_recognises_only_real_identifiers(self):
        self.assertTrue(mod.has_prolific_label(
            {'participant.label': '665b7b047373d8da553237a6'}))
        for fake in ('test', 'shshaga', '', '665b7b047373d8da553237a', 'ABCDEF'):
            self.assertFalse(
                mod.has_prolific_label({'participant.label': fake}), msg=fake)

    def test_internal_test_sessions_are_excluded(self):
        """Whoever has no Prolific identifier comes from an internal test."""
        wide = self._triad('a', '7')
        wide += self._triad('t', '8', label='test')

        with tempfile.TemporaryDirectory() as tmpdir:
            _long, _by_partner, aggregated = run_merge(wide, [], tmpdir)

        self.assertEqual(len(aggregated), 3)
        self.assertEqual({r['group_uid'] for r in aggregated}, {'s1-db7'})

    def test_inactive_participants_stay_in(self):
        """They did communicate: exclude via group_valid, not here."""
        wide = self._triad('a', '7')
        wide[2][MAIN + 'player.decision_inactive'] = '99'

        with tempfile.TemporaryDirectory() as tmpdir:
            _long, _by_partner, aggregated = run_merge(wide, [], tmpdir)

        self.assertEqual(len(aggregated), 3)
        # The triad stays in the dataset, but is marked invalid.
        self.assertTrue(all(int(r['group_valid']) == 0 for r in aggregated))
        flags = {int(r['focal_id_in_group']): int(r['focal_timeout_flag'])
                 for r in aggregated}
        self.assertEqual(flags, {1: 0, 2: 0, 3: 1})

    def test_keep_all_disables_the_filter(self):
        wide = self._triad('a', '7') + [make_ungrouped('s1', 'u9', 9)]
        wide += self._triad('t', '8', label='test')

        with tempfile.TemporaryDirectory() as tmpdir:
            summary = _run_raw(wide, [], tmpdir, keep_all=True)
        self.assertEqual(summary['n_participants'], 7)
        self.assertEqual(summary['n_groups'], 2)

    def test_summary_reports_what_was_excluded(self):
        wide = self._triad('a', '7') + [make_ungrouped('s1', 'u9', 9)]
        wide += self._triad('t', '8', label='test')

        with tempfile.TemporaryDirectory() as tmpdir:
            summary = _run_raw(wide, [], tmpdir)
        self.assertEqual(summary['n_input'], 7)
        self.assertEqual(summary['n_participants'], 3)
        self.assertEqual(summary['dropped']['never_grouped'], 1)
        self.assertEqual(summary['dropped']['no_prolific_id'], 3)

    def test_messages_of_excluded_participants_are_counted_not_lost(self):
        """The totals must add up: filtered + analysed = those in input."""
        wide = self._triad('a', '7') + self._triad('t', '8', label='test')
        chat = [
            dict(session_code='s1', id_in_session='1', participant_code='a1',
                 channel='4-bargaining_tdl_main-7_1_2', nickname='LeftPartner',
                 body='a real message', timestamp='100.0'),
            dict(session_code='s1', id_in_session='1', participant_code='t1',
                 channel='4-bargaining_tdl_main-8_1_2', nickname='LeftPartner',
                 body='a test message', timestamp='101.0'),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = _run_raw(wide, chat, tmpdir)

        self.assertEqual(summary['n_messages_in'], 2)
        self.assertEqual(summary['n_messages_filtered'], 1)
        self.assertEqual(summary['n_messages_resolved'], 1)
        self.assertEqual(summary['warnings'], [])


class DisplayOrderTests(unittest.TestCase):
    """The randomised display order is a control, and must survive the merge.

    Two things are randomised per player and persisted by the experiment: which
    partner is shown in the left column, and the order of the three options on
    the Decision page. Neither changes the topology or the payoffs, but both are
    what a position effect would ride on.
    """

    def _triad(self, **extra):
        rows = [
            make_player('s1', f'a{pid}', pid, 'private', decision, 'split_you',
                        'split_you', 3, group_db_id='7')
            for pid, decision in ((1, 'Right'), (2, 'Left'), (3, 'NoOne'))
        ]
        for row in rows:
            row.update(extra)
        return rows

    def test_columns_are_carried_through(self):
        """Columns the export gains must reach the datasets on their own."""
        wide = self._triad()
        # P1 sees P2 on the left, P3 on the right; the options were shown in
        # the order NoOne, Right, Left.
        wide[0][MAIN + 'player.id_player_visualized_on_the_left'] = 'a2'
        wide[0][MAIN + 'player.id_player_visualized_on_the_right'] = 'a3'
        wide[0][MAIN + 'player.decision_option_1'] = 'NoOne'
        wide[0][MAIN + 'player.decision_option_2'] = 'Right'
        wide[0][MAIN + 'player.decision_option_3'] = 'Left'

        with tempfile.TemporaryDirectory() as tmpdir:
            _long, by_partner, aggregated = run_merge(wide, [], tmpdir)

        rows = {(int(r['focal_id_in_group']), int(r['partner_id_in_group'])): r
                for r in by_partner if r['group_uid']}
        self.assertEqual(int(rows[(1, 2)]['partner_shown_left']), 1)
        self.assertEqual(int(rows[(1, 3)]['partner_shown_left']), 0)

        # P1 chose Right, which was the second option on the screen.
        self.assertEqual(rows[(1, 2)]['decision_option_order'], 'NoOne|Right|Left')
        self.assertEqual(int(rows[(1, 2)]['focal_decision_position']), 2)

        agg = {int(r['focal_id_in_group']): r for r in aggregated if r['group_uid']}
        self.assertEqual(int(agg[1]['focal_decision_position']), 2)
        # P1's topological left partner is P3, and P3 was shown on the right.
        self.assertEqual(int(agg[1]['left_partner_shown_left']), 0)

    def test_display_order_does_not_touch_the_topology(self):
        """Seeing a partner on the left does not make them the left partner."""
        wide = self._triad()
        wide[0][MAIN + 'player.id_player_visualized_on_the_left'] = 'a2'
        wide[0][MAIN + 'player.id_player_visualized_on_the_right'] = 'a3'

        with tempfile.TemporaryDirectory() as tmpdir:
            _long, by_partner, _agg = run_merge(wide, [], tmpdir)

        rows = {(int(r['focal_id_in_group']), int(r['partner_id_in_group'])): r
                for r in by_partner if r['group_uid']}
        # P1's topological sides are unchanged: right is P2, left is P3.
        self.assertEqual(rows[(1, 2)]['partner_side'], 'right')
        self.assertEqual(rows[(1, 3)]['partner_side'], 'left')
        # And the payoff logic still reads the topology, not the screen.
        self.assertEqual(int(rows[(1, 2)]['A_ji']), 1)

    def test_older_exports_stay_empty_not_zero(self):
        """No information must not be read as "was shown on the right"."""
        wide = self._triad()
        with tempfile.TemporaryDirectory() as tmpdir:
            _long, by_partner, aggregated = run_merge(wide, [], tmpdir)

        rows = [r for r in by_partner if r['group_uid']]
        self.assertTrue(all(r['partner_shown_left'] == '' for r in rows))
        self.assertTrue(all(r['decision_option_order'] == '' for r in rows))
        self.assertTrue(all(r['focal_decision_position'] == '' for r in rows))
        self.assertTrue(all(r['left_partner_shown_left'] == ''
                            for r in aggregated if r['group_uid']))

    def test_incomplete_option_order_is_discarded(self):
        """Two options out of three is a broken record, not a shorter one."""
        wide = self._triad()
        wide[0][MAIN + 'player.decision_option_1'] = 'Left'
        wide[0][MAIN + 'player.decision_option_2'] = 'Right'

        with tempfile.TemporaryDirectory() as tmpdir:
            _long, by_partner, _agg = run_merge(wide, [], tmpdir)

        rows = {(int(r['focal_id_in_group']), int(r['partner_id_in_group'])): r
                for r in by_partner if r['group_uid']}
        self.assertEqual(rows[(1, 2)]['decision_option_order'], '')
        self.assertEqual(rows[(1, 2)]['focal_decision_position'], '')


class OutputHygieneTests(unittest.TestCase):
    def test_mturk_columns_are_dropped(self):
        wide = [
            make_player('s1', 'a1', 1, 'private', 'Right', 'split_you',
                        'split_you', 3, group_db_id='7'),
            make_player('s1', 'a2', 2, 'private', 'Left', 'split_you',
                        'split_you', 3, group_db_id='7'),
            make_player('s1', 'a3', 3, 'private', 'NoOne', 'split_you',
                        'split_you', 0, group_db_id='7'),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            _long, by_partner, aggregated = run_merge(wide, [], tmpdir)
        for rows in (by_partner, aggregated):
            for column in mod.MTURK_COLS:
                self.assertNotIn(column, rows[0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
