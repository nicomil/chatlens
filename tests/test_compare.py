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
    def test_it_names_what_adds_the_most(self):
        """The winner is the one that adds most *to length*, not the one with
        the highest AUC of its own: a block can score well by rediscovering how
        much was written, and that is the thing this table exists to catch."""
        scored = compare.score(compare.build(rows(), 'y', 'text'))
        verdict = compare.verdict(scored)
        adding = [r for r in scored['results']
                  if r['verdict'] == compare.YES]
        self.assertTrue(adding, 'the planted signal added nothing')
        best = max(adding, key=lambda r: r['delta'])
        self.assertIn(best['name'], verdict)
        self.assertIn('Adding something', verdict)

    def test_nothing_beating_length_is_called_a_finding(self):
        scored = compare.score(compare.build(rows(800, signal=False), 'y',
                                             'text'))
        verdict = compare.verdict(scored)
        self.assertIn('finding rather than a failure', verdict)


class NestedComparisonTests(unittest.TestCase):
    """The question is whether a block adds anything *to length*.

    Not whether it scores well on its own: a bag of words on a corpus where the
    winners simply wrote more will score well and add nothing, and separate AUCs
    left the reader to subtract two numbers and hope the difference meant
    something.
    """

    def scored(self, **kwargs):
        return compare.score(compare.build(rows(**kwargs), 'y', 'text'))

    def test_a_block_carries_an_interval_not_just_a_point(self):
        for row in self.scored()['results']:
            if row['kind'] == 'volume' or row['delta'] is None:
                continue
            with self.subTest(block=row['kind']):
                self.assertIsNotNone(row['se'])
                self.assertLess(row['ci_low'], row['ci_high'])
                self.assertLessEqual(row['ci_low'], row['delta'])
                self.assertGreaterEqual(row['ci_high'], row['delta'])

    def test_the_interval_is_wider_than_the_naive_one(self):
        """Nadeau and Bengio: the k training sets overlap, so `sd/sqrt(k)`
        understates the error. On five folds the correction is about 1.5x, and
        that is the difference between excluding zero and not."""
        import numpy as np

        row = next(r for r in self.scored()['results']
                   if r['kind'] == 'words')
        naive = row['spread'] / np.sqrt(row['folds_used'])
        self.assertGreater(row['se'], naive)

    def test_a_planted_signal_adds_something(self):
        words = next(r for r in self.scored()['results']
                     if r['kind'] == 'words')
        self.assertEqual(words['verdict'], compare.YES)
        self.assertGreater(words['delta'], 0)
        self.assertGreater(words['ci_low'], 0)

    def test_noise_adds_nothing_and_the_interval_says_so(self):
        for row in self.scored(n=800, signal=False)['results']:
            if row['kind'] == 'volume' or row['delta'] is None:
                continue
            with self.subTest(block=row['kind']):
                self.assertNotEqual(row['verdict'], compare.YES)
                self.assertLessEqual(row['ci_low'], 0)

    def test_the_third_state_exists(self):
        """A rule that must answer yes or no answers one of them by accident."""
        self.assertEqual(
            compare._call({'delta': 0.015, 'ci_low': -0.005, 'ci_high': 0.035,
                           'q': 0.2}, 0.02),
            compare.UNCLEAR)

    def test_a_yes_needs_both_halves(self):
        """The interval must exclude zero *and* the improvement must reach the
        smallest one anybody would act on."""
        clears = {'delta': 0.08, 'ci_low': 0.04, 'ci_high': 0.12, 'q': 0.01}
        self.assertEqual(compare._call(clears, 0.02), compare.YES)
        # Reliable, and too small to matter.
        tiny = {'delta': 0.004, 'ci_low': 0.002, 'ci_high': 0.006, 'q': 0.01}
        self.assertEqual(compare._call(tiny, 0.02), compare.NO)
        # Large, and indistinguishable from nothing.
        noisy = {'delta': 0.09, 'ci_low': -0.02, 'ci_high': 0.20, 'q': 0.3}
        self.assertEqual(compare._call(noisy, 0.02), compare.UNCLEAR)

    def test_an_effect_the_design_cannot_observe_is_not_considered(self):
        """The bar is the larger of the declared floor and the half-width of
        the interval. The experimenter's rule: if the sample cannot see an
        effect of 0.02, an effect of 0.02 is not claimed."""
        # 0.03 above zero, but the design can only resolve 0.05.
        row = {'delta': 0.055, 'ci_low': 0.005, 'ci_high': 0.105, 'q': 0.01,
               'detectable': 0.05}
        self.assertEqual(compare.threshold(row, 0.02), 0.05)
        self.assertEqual(compare._call(row, 0.02), compare.YES)
        below = dict(row, delta=0.045, ci_low=-0.005, ci_high=0.095)
        self.assertEqual(compare._call(below, 0.02), compare.UNCLEAR)
        # A precise design keeps the declared floor.
        precise = {'delta': 0.03, 'ci_low': 0.02, 'ci_high': 0.04, 'q': 0.01,
                   'detectable': 0.01}
        self.assertEqual(compare.threshold(precise, 0.02), 0.02)

    def test_the_detectable_difference_is_the_half_width(self):
        found = compare._paired([0.01, 0.03, 0.02, 0.04, 0.00], 0.25)
        self.assertAlmostEqual(found['detectable'],
                               found['ci_high'] - found['delta'])

    def test_the_correction_across_blocks_is_applied(self):
        rows_ = [{'p': 0.01}, {'p': 0.02}, {'p': 0.5}]
        compare._holm(rows_)
        self.assertAlmostEqual(rows_[0]['q'], 0.03)
        self.assertAlmostEqual(rows_[1]['q'], 0.04)
        self.assertAlmostEqual(rows_[2]['q'], 0.5)
        # Monotone, like every step-down correction.
        self.assertEqual([r['q'] for r in rows_],
                         sorted(r['q'] for r in rows_))

    def test_one_baseline_and_one_estimator_for_every_block(self):
        """A difference has to be the block and never a change of estimator.

        A lasso would be entitled to drop length, and on this fixture it did:
        the penalised baseline sat at 0.500 in every fold, so every difference
        was inflated by half an AUC and had no variance at all.
        """
        scored = self.scored()
        volume = next(r for r in scored['results'] if r['kind'] == 'volume')
        self.assertEqual(volume['auc'], scored['volume'])
        self.assertNotAlmostEqual(scored['volume'], 0.5, places=6)

    def test_a_block_that_only_repeats_length_adds_nothing(self):
        """The whole point, put to the test: a feature that *is* length."""
        built = compare.build(rows(), 'y', 'text')
        built['sets'] = [s for s in built['sets'] if s['kind'] == 'volume']
        built['sets'].append({'name': 'Length again', 'kind': 'lexical',
                              'matrix': built['volume'].copy(),
                              'features': 1, 'sparse': False})
        row = next(r for r in compare.score(built)['results']
                   if r['kind'] == 'lexical')
        self.assertNotEqual(row['verdict'], compare.YES)
        self.assertLess(abs(row['delta']), 0.02)


class EmotionBlockTests(unittest.TestCase):
    """The NRC categories had never been in this table."""

    def test_it_is_present_either_as_a_block_or_as_a_reason(self):
        built = compare.build(rows(), 'y', 'text')
        found = next(s for s in built['sets'] if s['kind'] == 'emotions')
        if found['matrix'] is None:
            self.assertIn('NRC', found['why'])
        else:
            self.assertEqual(found['features'], 10)

    def test_a_missing_lexicon_is_a_reason_and_not_a_crash(self):
        import unittest.mock

        from chatlens.core import nrc

        with unittest.mock.patch.object(nrc, 'available', lambda: False):
            found = compare._emotion_set(['ok', 'fine'])
        self.assertIsNone(found['matrix'])
        self.assertIn('emotions page', found['why'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
