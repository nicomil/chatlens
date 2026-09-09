"""The conversations, and the path from a number back to them.

The interface measured text and never showed it: from a coefficient there was
no way to reach the sentences behind it, which makes every figure something to
be taken on trust. These tests pin the two things that path has to get right —
matching whole words, and keeping units and messages apart.

    python tests/test_corpus.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from chatlens.core import corpus  # noqa: E402


def message(group, sender, receiver, body, at=None):
    return {'group_uid': group, 'sender_id_in_group': str(sender),
            'receiver_id_in_group': str(receiver), 'body': body,
            'timestamp': '' if at is None else str(at)}


class FindingTests(unittest.TestCase):
    """What a term is made of."""

    def setUp(self):
        self.messages = [
            message('g1', 1, 2, 'that is not enough for me', 100),
            message('g1', 1, 2, 'still not enough', 160),
            message('g2', 1, 2, 'not   enough', 50),
            message('g3', 2, 1, 'ok, that is a broken deal', 10),
        ]

    def test_a_term_matches_whole_words_only(self):
        """Without the boundaries "ok" matches "broken", and the inspector
        shows messages that have nothing to do with the number clicked."""
        self.assertEqual(corpus.find(self.messages, 'ok')['n_messages'], 1)
        self.assertEqual(corpus.find(self.messages, 'enou')['n_messages'], 0)

    def test_a_phrase_matches_across_the_whitespace_it_happens_to_have(self):
        """The model saw documents that had been collapsed; the messages were
        not."""
        found = corpus.find(self.messages, 'not enough')
        self.assertEqual(found['n_messages'], 3)

    def test_units_and_messages_are_counted_separately(self):
        """The commonest misreading: a term's "documents" are units, and one
        unit can hold several messages. Reporting the message count under that
        heading overstates the evidence."""
        found = corpus.find(self.messages, 'not enough', unit='group')
        self.assertEqual(found['n_messages'], 3)
        self.assertEqual(found['n_units'], 2)

    def test_the_unit_changes_the_count_and_not_the_messages(self):
        by_group = corpus.find(self.messages, 'not enough', unit='group')
        by_pair = corpus.find(self.messages, 'not enough', unit='dyad_directed')
        self.assertEqual(by_group['n_messages'], by_pair['n_messages'])
        self.assertEqual(by_group['n_units'], 2)
        self.assertEqual(by_pair['n_units'], 2)

    def test_a_long_result_says_how_much_it_cut(self):
        many = [message('g1', 1, 2, 'not enough', n) for n in range(60)]
        found = corpus.find(many, 'not enough', limit=10)
        self.assertEqual(len(found['messages']), 10)
        self.assertEqual(found['truncated'], 50)

    def test_nothing_asked_finds_nothing(self):
        self.assertEqual(corpus.find(self.messages, '   ')['n_messages'], 0)


class HighlightTests(unittest.TestCase):
    """Marked as data, not as markup: escaping belongs to the layer that
    writes HTML."""

    def test_the_match_is_marked_and_the_rest_is_not(self):
        runs = corpus.highlight('that is not enough for me', 'not enough')
        self.assertEqual(runs, [('that is ', False), ('not enough', True),
                                (' for me', False)])

    def test_no_match_returns_the_body_whole(self):
        self.assertEqual(corpus.highlight('hello', 'goodbye'),
                         [('hello', False)])

    def test_markup_in_the_body_is_not_escaped_here(self):
        """It is escaped by the caller. A function here that returned
        `<mark>` would be one that has to be trusted to escape."""
        runs = corpus.highlight('<b>not enough</b>', 'not enough')
        self.assertIn(('<b>', False), runs)


class ShapeTests(unittest.TestCase):
    """How the exchange went — figures the tool computed and never showed."""

    def test_duration_and_pace(self):
        shape = corpus.shape([
            message('g1', 1, 2, 'one', 0),
            message('g1', 2, 1, 'two', 30),
            message('g1', 1, 2, 'three', 90),
        ])
        self.assertEqual(shape['messages'], 3)
        self.assertEqual(shape['duration_seconds'], 90.0)
        self.assertEqual(shape['median_gap_seconds'], 45.0)
        self.assertEqual(shape['speakers'], 2)

    def test_without_timestamps_there_is_no_shape_to_report(self):
        shape = corpus.shape([message('g1', 1, 2, 'one'),
                              message('g1', 2, 1, 'two')])
        self.assertIsNone(shape['duration_seconds'])
        self.assertIsNone(shape['median_gap_seconds'])
        self.assertEqual(shape['messages'], 2)


class ConversationTests(unittest.TestCase):
    def test_messages_come_back_in_the_order_they_were_sent(self):
        out = corpus.conversations([
            message('g1', 1, 2, 'second', 200),
            message('g1', 2, 1, 'first', 100),
        ])
        self.assertEqual([m['body'] for m in out[0]['messages']],
                         ['first', 'second'])

    def test_one_entry_per_group_sorted_by_name(self):
        out = corpus.conversations([
            message('g2', 1, 2, 'b', 1), message('g1', 1, 2, 'a', 1)])
        self.assertEqual([entry['group'] for entry in out], ['g1', 'g2'])


if __name__ == '__main__':
    unittest.main()
