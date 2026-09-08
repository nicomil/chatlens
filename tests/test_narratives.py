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

try:
    import spacy
    NLP = spacy.load('en_core_web_md')
except Exception:                        # noqa: BLE001 - an optional extra
    NLP = None


@unittest.skipIf(NLP is None, 'spaCy or its model is not installed')
class TripleTests(unittest.TestCase):
    ENTITIES = {'i', 'you', 'we', 'purple', 'orange'}

    def triples(self, text):
        return narratives.triples(NLP(text), self.ENTITIES)

    def test_a_plain_clause(self):
        self.assertIn(('i', 'support', 'you'), self.triples('I support you'))

    def test_the_direction_is_kept(self):
        """The distinction a bag of words cannot represent."""
        one = self.triples('I support you')
        other = self.triples('You support me')
        self.assertIn(('i', 'support', 'you'), one)
        self.assertIn(('you', 'support', 'i'), other)
        self.assertNotEqual(one, other)

    def test_naming_a_third_party_is_a_different_relation(self):
        self.assertIn(('i', 'support', 'purple'),
                      self.triples('I will support purple'))

    def test_negation_changes_the_verb(self):
        found = self.triples('I do not support you')
        self.assertTrue(any(v.startswith('not ') for _a, v, _p in found))

    def test_an_entity_inside_a_longer_phrase_is_still_found(self):
        """Matching is per token, so an entity buried in a phrase is found."""
        found = self.triples('I will support the purple player')
        self.assertTrue(any(p == 'purple' for _a, _v, p in found), found)

    def test_an_entity_in_adjective_position_is_found(self):
        """Participants named by colour are tagged as adjectives, so "I am
        orange" puts the entity in an adjectival complement. Without `acomp`
        every statement of who someone is would be silently dropped."""
        found = self.triples('I am orange')
        self.assertIn(('i', 'be', 'orange'), found)

    def test_a_clause_without_an_object_produces_nothing(self):
        self.assertEqual(self.triples('I agree'), [])

    def test_an_unmatched_phrase_falls_back_to_its_head(self):
        found = self.triples('We should split the bonus')
        self.assertTrue(any(p == 'bonus' for _a, _v, p in found))


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


class RouteTests(unittest.TestCase):
    """Which implementation runs, and what happens when the big one is broken."""

    def test_a_present_but_unimportable_package_falls_back_and_says_why(self):
        """RELATIO pulls transformers, which refuses to load beside Keras 3.

        Looking for the package on the filesystem is not enough here: it is
        present and unusable, and a check that only looked would send the page
        down a route that raises.
        """
        import unittest.mock

        from chatlens.core import optional

        narratives._ROUTE.clear()
        real_import = __builtins__['__import__'] if isinstance(
            __builtins__, dict) else __builtins__.__import__

        def broken(name, *args, **kwargs):
            if name == 'relatio':
                raise ValueError('Keras 3 is not supported')
            return real_import(name, *args, **kwargs)

        with unittest.mock.patch.object(optional, 'have', lambda m: True), \
                unittest.mock.patch('builtins.__import__', broken):
            route, note = narratives.available_route()
        narratives._ROUTE.clear()
        self.assertEqual(route, 'spacy')
        self.assertIn('cannot be imported', note)
        self.assertIn('Keras 3', note)

    def test_without_either_there_is_no_route(self):
        import unittest.mock

        from chatlens.core import optional

        narratives._ROUTE.clear()
        with unittest.mock.patch.object(optional, 'have', lambda m: False):
            route, _note = narratives.available_route()
        self.assertEqual(route, '')

    def test_the_light_route_is_used_when_asked_for(self):
        import unittest.mock

        from chatlens.core import optional

        with unittest.mock.patch.object(optional, 'have', lambda m: True):
            route, _note = narratives.available_route(prefer_package=False)
        self.assertEqual(route, 'spacy')


class RequirementNoticeTests(unittest.TestCase):
    def test_the_model_has_its_own_command(self):
        """`pip install spacy` succeeds and leaves the page just as broken."""
        from chatlens.web import views_narratives

        commands = [r.command
                    for r in views_narratives.requirements('en_core_web_md')]
        self.assertTrue(any('spacy download en_core_web_md' in c
                            for c in commands))
        self.assertTrue(any('spacy download' not in c for c in commands))

    def test_each_command_names_this_interpreter(self):
        from chatlens.web import views_narratives

        for requirement in views_narratives.requirements('en_core_web_md'):
            self.assertTrue(requirement.command.startswith(sys.executable)
                            or 'uv tool' in requirement.command,
                            requirement.command)


if __name__ == '__main__':
    unittest.main(verbosity=2)
