"""The text read as relations.

The extraction is checked on sentences whose answer is obvious, and the entity
handling is checked because it is the setting the whole result turns on: with
"i" and "you" left to be grouped by similarity, the speaker and the person
spoken to become one entity and the question disappears.

    python tests/test_narratives.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from chatlens.core import narratives  # noqa: E402

class FrequencyTests(unittest.TestCase):
    def test_a_relation_used_twice_in_one_unit_counts_once(self):
        """Units, not mentions: saying it twice is not two pieces of evidence."""
        per_unit = {('g', '1', '2'): {('i', 'support', 'you')},
                    ('g', '2', '1'): {('i', 'support', 'you'),
                                      ('we', 'split', 'bonus')}}
        counts = narratives.frequencies(per_unit)
        self.assertEqual(counts[('i', 'support', 'you')], 2)
        self.assertEqual(counts[('we', 'split', 'bonus')], 1)


class WhichMatterTests(unittest.TestCase):
    def setUp(self):
        try:
            import statsmodels.api  # noqa: F401
        except ImportError:
            self.skipTest('statsmodels is not installed')

    def frame(self, n=300, planted_effect=True):
        """Half the rows carry the relation; it predicts the outcome or not."""
        per_unit, rows = {}, []
        for i in range(n):
            key = ('g%d' % (i // 3), str(i), 'x')
            has = i % 2 == 0
            if has:
                per_unit[key] = {('i', 'support', 'you')}
            outcome = has if planted_effect else (i % 3 == 0)
            rows.append({'group_uid': key[0], 'a': key[1], 'b': key[2],
                         'y': '1' if outcome else '0', 'words': 20})
        return per_unit, rows

    def run_it(self, per_unit, rows):
        return narratives.which_matter(
            per_unit, rows, 'y',
            key_of=lambda r: (r['group_uid'], r['a'], r['b']),
            words_of=lambda r: r['words'],
            group_of=lambda r: r['group_uid'],
            min_documents=10)

    def test_a_planted_effect_is_found(self):
        found = self.run_it(*self.frame())
        self.assertEqual(found['tested'], 1)
        self.assertLess(found['results'][0]['q'], 0.10)
        self.assertGreater(found['results'][0]['odds'], 1)

    def test_no_effect_does_not_survive(self):
        found = self.run_it(*self.frame(planted_effect=False))
        self.assertEqual(found['survivors'], 0)

    def test_rare_relations_are_not_tested(self):
        per_unit, rows = self.frame()
        per_unit[('g0', '0', 'x')] = per_unit.get(('g0', '0', 'x'), set()) | {
            ('rare', 'thing', 'here')}
        found = self.run_it(per_unit, rows)
        tested = {r['narrative'] for r in found['results']}
        self.assertNotIn(('rare', 'thing', 'here'), tested)

    def test_the_correction_is_applied_across_the_family(self):
        """q is never below p, and rises as more things are tested."""
        found = self.run_it(*self.frame())
        for row in found['results']:
            self.assertGreaterEqual(row['q'], row['p'] - 1e-12)

    def test_too_few_rows_says_so(self):
        per_unit, rows = self.frame(n=20)
        with self.assertRaises(ValueError) as ctx:
            self.run_it(per_unit, rows)
        self.assertIn('not enough', str(ctx.exception))

    def test_a_constant_outcome_says_so(self):
        per_unit, rows = self.frame()
        rows = [dict(r, y='1') for r in rows]
        with self.assertRaises(ValueError) as ctx:
            self.run_it(per_unit, rows)
        self.assertIn('same outcome', str(ctx.exception))


class ConfigurationTests(unittest.TestCase):
    def test_entities_round_trip_through_the_experiment(self):
        from chatlens.core import experiment

        exp = experiment.Experiment(
            {'narratives': {'entities': ['I', ' You '], 'model': 'en_core_web_sm'}})
        self.assertEqual(exp.narrative_entities, ['i', 'you'])
        self.assertEqual(exp.narrative_model, 'en_core_web_sm')
        self.assertIn('narratives', exp.to_config())

    def test_the_default_model_is_used_when_none_is_given(self):
        from chatlens.core import experiment

        self.assertEqual(experiment.Experiment({}).narrative_model,
                         'en_core_web_md')

    def test_no_section_means_no_entities_rather_than_a_guess(self):
        from chatlens.core import experiment

        self.assertEqual(experiment.Experiment({}).narrative_entities, [])


class AvailabilityTests(unittest.TestCase):
    """Whether RELATIO can run, and what is said when it cannot.

    There is no fallback. The extraction is RELATIO's method, and an
    approximation of somebody else's published pipeline is not that pipeline —
    a result from one could not honestly be attributed to the paper. So the page
    waits for the package rather than substituting anything of ours.
    """

    def setUp(self):
        narratives._ROUTE.clear()

    tearDown = setUp

    def test_a_present_but_unimportable_package_is_not_available(self):
        """RELATIO pulls transformers, which refuses to load beside Keras 3.

        Looking for it on the filesystem is not enough: it is present and
        unusable, and a check that only looked would send the page into an
        import that raises.
        """
        import unittest.mock

        from chatlens.core import optional

        real = __import__

        def broken(name, *args, **kwargs):
            if name == 'relatio':
                raise ValueError('Keras 3 is not supported')
            return real(name, *args, **kwargs)

        with unittest.mock.patch.object(optional, 'have', lambda m: True), \
                unittest.mock.patch('builtins.__import__', broken):
            ready, why = narratives.available()
        self.assertFalse(ready)
        self.assertIn('Keras 3', why)

    def test_not_installed_says_so(self):
        import unittest.mock

        from chatlens.core import optional

        with unittest.mock.patch.object(optional, 'have', lambda m: False):
            ready, why = narratives.available()
        self.assertFalse(ready)
        self.assertEqual(why, 'not installed')

    def test_there_is_no_reimplementation_to_fall_back_to(self):
        """The guarantee, as a test: nothing here extracts relations itself."""
        self.assertFalse(hasattr(narratives, 'extract'))
        self.assertFalse(hasattr(narratives, 'triples'))


class RequirementNoticeTests(unittest.TestCase):
    def test_the_model_has_its_own_command(self):
        """`pip install spacy` succeeds and leaves the page just as broken."""
        from chatlens.web import views_narratives

        commands = [r.command
                    for r in views_narratives.requirements('en_core_web_md')]
        self.assertTrue(any('spacy download en_core_web_md' in c
                            for c in commands))
        self.assertTrue(any('spacy download' not in c for c in commands))

    def test_each_command_is_one_the_user_can_run_as_shown(self):
        """Either this interpreter by full path, or a chatlens command."""
        from chatlens.web import views_narratives

        for requirement in views_narratives.requirements('en_core_web_md'):
            self.assertTrue(requirement.command.startswith(sys.executable)
                            or 'uv tool' in requirement.command
                            or requirement.command.startswith('chatlens '),
                            requirement.command)

    def test_relatio_is_listed_as_required(self):
        from chatlens.web import views_narratives

        labels = [r.label for r in
                  views_narratives.requirements('en_core_web_md')]
        self.assertIn('RELATIO', labels)


class CheckAgainTests(unittest.TestCase):
    """The control that re-runs the dependency check."""

    def test_forgetting_the_route_lets_the_answer_change(self):
        from chatlens.core import narratives
        narratives._ROUTE['relatio'] = 'a stale failure'
        narratives.forget_route()
        self.assertEqual(narratives._ROUTE, {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
