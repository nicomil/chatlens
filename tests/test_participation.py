"""Who spoke to whom, and who did not.

The comparisons here are the ones the experiment turned on, so they are checked
against hand-built grids where the right answer is countable by eye, and the
degenerate designs are checked to refuse rather than to produce a number.

    python tests/test_participation.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from chatlens.core import participation  # noqa: E402


def message(group, sender, receiver, body='hello'):
    return {'group_uid': group, 'sender_id_in_group': str(sender),
            'receiver_id_in_group': str(receiver), 'body': body}


class MembershipTests(unittest.TestCase):
    def test_the_roster_is_preferred_and_says_so(self):
        messages = [message('g1', 1, 2)]
        roster = [{'group_uid': 'g1', 'focal_id_in_group': str(i)}
                  for i in (1, 2, 3)]
        members, source = participation.membership(messages, roster=roster)
        self.assertEqual(members['g1'], {'1', '2', '3'})
        self.assertEqual(source, 'the aggregated dataset')

    def test_without_a_roster_a_silent_member_is_invisible(self):
        """The limitation, stated as a test so it cannot be forgotten.

        Player 3 exists but never wrote and was never written to, so the
        messages cannot show them and the grid is short by four cells.
        """
        messages = [message('g1', 1, 2), message('g1', 2, 1)]
        members, source = participation.membership(messages)
        self.assertEqual(members['g1'], {'1', '2'})
        self.assertEqual(source, 'the messages')

    def test_a_roster_for_other_groups_is_not_used(self):
        """A roster keyed on something else would produce groups of one."""
        messages = [message('g1', 1, 2)]
        roster = [{'group_uid': 'elsewhere', 'focal_id_in_group': '9'}]
        _members, source = participation.membership(messages, roster=roster)
        self.assertEqual(source, 'the aggregated dataset')


class GridTests(unittest.TestCase):
    def test_every_ordered_pair_appears_including_the_empty_ones(self):
        messages = [message('g1', 1, 2)]
        roster = [{'group_uid': 'g1', 'focal_id_in_group': str(i)}
                  for i in (1, 2, 3)]
        members, _ = participation.membership(messages, roster=roster)
        cells = participation.grid(messages, members)
        self.assertEqual(len(cells), 6)          # 3 people, ordered pairs
        self.assertEqual(cells[('g1', '1', '2')]['messages'], 1)
        self.assertEqual(cells[('g1', '3', '1')]['messages'], 0)

    def test_nobody_is_paired_with_themselves(self):
        members = {'g1': {'1', '2'}}
        cells = participation.grid([], members)
        self.assertNotIn(('g1', '1', '1'), cells)

    def test_coverage_counts_what_was_used(self):
        messages = [message('g1', 1, 2), message('g1', 1, 2)]
        members = {'g1': {'1', '2', '3'}}
        cover = participation.coverage(participation.grid(messages, members),
                                       members)
        self.assertEqual(cover['cells'], 6)
        self.assertEqual(cover['used'], 1)
        self.assertEqual(cover['empty'], 5)


class ContrastTests(unittest.TestCase):
    def test_the_two_groups_are_counted_separately(self):
        members = {'g1': {'1', '2', '3'}}
        cells = participation.grid([message('g1', 1, 2)], members)
        outcomes = {('g1', '1', '2'): 1, ('g1', '2', '1'): 0,
                    ('g1', '1', '3'): 0}
        found = participation.contrast(cells, outcomes)
        self.assertEqual(found['wrote']['n'], 1)
        self.assertEqual(found['wrote']['share'], 1.0)
        self.assertEqual(found['silent']['n'], 2)
        self.assertEqual(found['silent']['share'], 0.0)

    def test_cells_with_no_outcome_are_counted_not_treated_as_zero(self):
        members = {'g1': {'1', '2', '3'}}
        cells = participation.grid([message('g1', 1, 2)], members)
        found = participation.contrast(cells, {('g1', '1', '2'): 1,
                                               ('g1', '2', '1'): 0})
        self.assertEqual(found['unknown'], 4)
        self.assertEqual(found['silent']['n'], 1)

    def test_one_side_missing_gives_nothing_rather_than_a_ratio(self):
        members = {'g1': {'1', '2'}}
        cells = participation.grid([message('g1', 1, 2), message('g1', 2, 1)],
                                   members)
        self.assertIsNone(participation.contrast(
            cells, {('g1', '1', '2'): 1, ('g1', '2', '1'): 1}))


class WithinReceiverTests(unittest.TestCase):
    """The comparison that holds the receiver fixed."""

    def grid_for(self, wrote, chosen, members=('1', '2', '3')):
        """One group; `wrote` are the senders who wrote to receiver 3."""
        messages = [message('g1', s, 3) for s in wrote]
        cells = participation.grid(messages, {'g1': set(members)})
        outcomes = {('g1', s, '3'): int(s == chosen)
                    for s in members if s != '3'}
        return cells, outcomes

    def test_the_writer_is_credited(self):
        cells, outcomes = self.grid_for(wrote=['1'], chosen='1')
        found = participation.within_receiver(cells, outcomes)
        self.assertEqual(found['chose_writer'], 1)
        self.assertEqual(found['chose_silent'], 0)

    def test_the_silent_one_is_credited(self):
        cells, outcomes = self.grid_for(wrote=['1'], chosen='2')
        found = participation.within_receiver(cells, outcomes)
        self.assertEqual(found['chose_writer'], 0)
        self.assertEqual(found['chose_silent'], 1)

    def test_receivers_everyone_wrote_to_carry_no_comparison(self):
        cells, outcomes = self.grid_for(wrote=['1', '2'], chosen='1')
        found = participation.within_receiver(cells, outcomes)
        self.assertEqual(found['decided'], 0)
        self.assertGreaterEqual(found['both_wrote'], 1)

    def test_a_design_with_one_possible_sender_refuses(self):
        """Two people cannot produce a within-receiver comparison, and the
        honest answer is to say so rather than return a number."""
        cells = participation.grid([message('g1', 1, 2)], {'g1': {'1', '2'}})
        self.assertIsNone(participation.within_receiver(cells, {}))


class BinomialTests(unittest.TestCase):
    def test_a_fair_split_is_not_significant(self):
        self.assertAlmostEqual(participation.binomial_p(5, 10), 1.0, places=6)

    def test_a_lopsided_split_is(self):
        self.assertLess(participation.binomial_p(357, 392), 1e-50)

    def test_it_is_symmetric(self):
        self.assertAlmostEqual(participation.binomial_p(3, 20),
                               participation.binomial_p(17, 20))

    def test_no_trials_is_not_a_crash(self):
        self.assertEqual(participation.binomial_p(0, 0), 1.0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
