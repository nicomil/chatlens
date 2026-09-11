"""Comparing the representations, and the ways a comparison stops being one.

Most of these guard the arrangement rather than the arithmetic: the same rows,
the same folds, length always present, and an unavailable representation shown
rather than quietly dropped.

    python tests/test_compare.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from chatlens.core import compare  # noqa: E402


def rows(n=240, signal=True):
    """Half the rows carry a word that predicts the outcome, or do not.

    Without the signal the outcome is drawn from a seeded generator rather than
    from the row number: anything periodic lines up with the text, which is
    still a signal and makes a "no signal" test assert the opposite of what it
    says.
    """
    import random

    rng = random.Random(7)
    out = []
    # Filler is drawn at random rather than cycled, and the two markers are the
    # same length. Otherwise the label lines up with the length of the sentence
    # and "how much was written" scores a perfect 1.000 — a fixture in which
    # nothing can be shown to beat length, for a reason that has nothing to do
    # with the code under test.
    filler = ['we should decide now', 'what do you think about',
              'ok then lets do', 'here is my plan for']
    for i in range(n):
        positive = i % 2 == 0
        out.append({
            'group_uid': f'g{i // 4}',
            'text': f'{rng.choice(filler)} {"yes" if positive else "nope"}',
            'y': ('1' if positive else '0') if signal
                 else str(rng.randint(0, 1)),
            'nlp_sent_clout_100': '60' if positive else '40',
        })
    return out


class BuildTests(unittest.TestCase):
    def test_length_is_always_there(self):
        """It is the null hypothesis, so it can never be the missing one."""
        built = compare.build(rows(), 'y', 'text')
        kinds = [s['kind'] for s in built['sets']]
        self.assertIn('volume', kinds)
        volume = next(s for s in built['sets'] if s['kind'] == 'volume')
        self.assertIsNotNone(volume['matrix'])

    def test_an_unavailable_representation_is_listed_with_a_reason(self):
        """Comparing three things while the reader believes they see five is
        the worse failure."""
        built = compare.build(rows(), 'y', 'text')
        narratives = next(s for s in built['sets']
                          if s['kind'] == 'narratives')
        self.assertIsNone(narratives['matrix'])
        self.assertIn('narratives page', narratives['why'])

    def test_lexical_indices_are_used_when_present(self):
        built = compare.build(rows(), 'y', 'text')
        lexical = next(s for s in built['sets'] if s['kind'] == 'lexical')
        self.assertEqual(lexical['features'], 1)

    def test_lexical_indices_are_absent_when_the_dataset_lacks_them(self):
        bare = [{k: v for k, v in r.items() if not k.startswith('nlp_')}
                for r in rows()]
        built = compare.build(bare, 'y', 'text')
        lexical = next(s for s in built['sets'] if s['kind'] == 'lexical')
        self.assertIsNone(lexical['matrix'])
        self.assertIn('none of them', lexical['why'])

    def test_narratives_are_used_when_supplied(self):
        data = rows()
        per_unit = {r['group_uid'] + r['text']: {('i', 'support', 'you')}
                    for r in data if 'yes' in r['text']}
        built = compare.build(
            data, 'y', 'text', per_unit=per_unit,
            key_of=lambda r: r['group_uid'] + r['text'],
            narrative_terms=[('i', 'support', 'you')])
        found = next(s for s in built['sets'] if s['kind'] == 'narratives')
        self.assertEqual(found['features'], 1)

    def test_relations_too_rare_to_use_are_an_answer_not_a_missing_package(self):
        """On a small corpus nothing reaches the threshold. That was reported
        as "needs RELATIO" on a machine that had just run it."""
        data = rows()
        built = compare.build(
            data, 'y', 'text',
            per_unit={'g0': {('i', 'support', 'you')}},
            key_of=lambda r: r['group_uid'], narrative_terms=[])
        found = next(s for s in built['sets'] if s['kind'] == 'narratives')
        self.assertIsNone(found['matrix'])
        self.assertTrue(found['answered'])
        self.assertNotIn('RELATIO', found['why'])

    def test_no_extraction_at_all_is_still_unavailable(self):
        built = compare.build(rows(), 'y', 'text')
        found = next(s for s in built['sets'] if s['kind'] == 'narratives')
        self.assertFalse(found.get('answered'))

    def test_too_little_data_says_so(self):
        with self.assertRaises(ValueError) as ctx:
            compare.build(rows(10), 'y', 'text')
        self.assertIn('not enough', str(ctx.exception))

    def test_a_constant_outcome_says_so(self):
        with self.assertRaises(ValueError) as ctx:
            compare.build([dict(r, y='1') for r in rows()], 'y', 'text')
        self.assertIn('same outcome', str(ctx.exception))


class ScoreTests(unittest.TestCase):
    def test_every_representation_faces_the_same_folds(self):
        """The one property that makes it a comparison.

        Run twice: identical folds mean identical numbers, and a fresh split per
        representation would not reproduce.
        """
        built = compare.build(rows(), 'y', 'text')
        first = compare.score(built)
        second = compare.score(compare.build(rows(), 'y', 'text'))
        self.assertEqual([r['auc'] for r in first['results']],
                         [r['auc'] for r in second['results']])

    def test_a_planted_signal_beats_length(self):
        scored = compare.score(compare.build(rows(), 'y', 'text'))
        words = next(r for r in scored['results'] if r['kind'] == 'words')
        self.assertTrue(words['beats_volume'])

    def test_noise_does_not_beat_length(self):
        # Generously sized: with a couple of hundred rows the sampling noise on
        # an AUC is itself worth more than the 0.02 the code calls meaningful,
        # and the test would be asserting against chance.
        scored = compare.score(compare.build(rows(800, signal=False), 'y',
                                             'text'))
        for row in scored['results']:
            if row['kind'] != 'volume' and row['auc'] is not None:
                self.assertFalse(row['beats_volume'])

    def test_length_is_never_compared_to_itself(self):
        scored = compare.score(compare.build(rows(), 'y', 'text'))
        volume = next(r for r in scored['results'] if r['kind'] == 'volume')
        self.assertIsNone(volume['beats_volume'])

    def test_a_single_group_cannot_be_held_out(self):
        same = [dict(r, group_uid='one') for r in rows()]
        with self.assertRaises(ValueError) as ctx:
            compare.score(compare.build(same, 'y', 'text'))
        self.assertIn('nothing to hold out', str(ctx.exception))

    def test_an_unavailable_representation_scores_nothing_not_zero(self):
        scored = compare.score(compare.build(rows(), 'y', 'text'))
        narratives = next(r for r in scored['results']
                          if r['kind'] == 'narratives')
        self.assertIsNone(narratives['auc'])


class BarTests(unittest.TestCase):
    """Length can score below chance, and then beating it means nothing."""

    def test_the_bar_is_never_below_chance(self):
        scored = compare.score(compare.build(rows(800, signal=False), 'y',
                                             'text'))
        self.assertGreaterEqual(scored['bar'], 0.5)


class VerdictTests(unittest.TestCase):
    def test_it_names_the_winner(self):
        """Whichever it is: two representations can tie, and which one `max`
        returns then is an implementation detail rather than a claim."""
        scored = compare.score(compare.build(rows(), 'y', 'text'))
        verdict = compare.verdict(scored)
        best = max((r for r in scored['results'] if r['auc'] is not None),
                   key=lambda r: r['auc'])
        self.assertIn(best['name'], verdict)
        self.assertIn('Beating length', verdict)

    def test_nothing_beating_length_is_called_a_finding(self):
        scored = compare.score(compare.build(rows(800, signal=False), 'y',
                                             'text'))
        verdict = compare.verdict(scored)
        self.assertIn('finding rather than a failure', verdict)


if __name__ == '__main__':
    unittest.main(verbosity=2)
