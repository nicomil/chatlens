"""Tests for the experiment library and the TOML writer.

Two things are covered here that the rest of the suite does not touch: paths
built from text that arrived over HTTP, and writing a file the interface will
later have to read back. Both are places where a mistake is silent.

    python tests/test_library.py
"""

import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

# Runs from a source checkout without installing: the package is under src/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from chatlens.core import experiment, library, tomlwrite  # noqa: E402


class SlugTests(unittest.TestCase):
    """The folder name is generated, never taken from what was typed."""

    def test_ordinary_names(self):
        self.assertEqual(library.slug('Coalition Formation'),
                         'coalition-formation')
        self.assertEqual(library.slug('Ultimatum 2026!'), 'ultimatum-2026')

    def test_accents_are_folded_not_dropped(self):
        """"accentata" with a hole in the middle would be worse than useless."""
        self.assertEqual(library.slug('accentàta è'), 'accentata-e')

    def test_path_separators_cannot_survive(self):
        for name in ('../../etc/passwd', 'a/b', r'a\b', '..'):
            produced = library.slug(name)
            self.assertNotIn('/', produced)
            self.assertNotIn('\\', produced)
            self.assertNotIn('..', produced)

    def test_names_windows_refuses(self):
        """CON and friends cannot be folder names on a platform we support."""
        for reserved in ('CON', 'nul', 'COM1'):
            self.assertNotEqual(library.slug(reserved), reserved.lower())

    def test_a_name_with_nothing_usable_gives_nothing(self):
        self.assertEqual(library.slug('   '), '')
        self.assertEqual(library.slug('!!!'), '')

    def test_it_is_bounded(self):
        self.assertLessEqual(len(library.slug('x ' * 400)), 64)


class PathConfinementTests(unittest.TestCase):
    """Whatever arrives from the browser must stay inside the library."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        library.use_library(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_good_name_resolves_inside(self):
        path = library.path_for('coalition-formation')
        self.assertEqual(path.parent.resolve(), library.ROOT.resolve())

    def test_traversal_is_refused(self):
        for attempt in ('..', '../..', 'a/b', '/etc', 'Coalition Formation',
                        '', '.', 'UPPER'):
            with self.assertRaises(library.LibraryError, msg=attempt):
                library.path_for(attempt)

    def test_only_a_slug_is_accepted(self):
        """Anything that is not already its own slug is refused outright."""
        with self.assertRaises(library.LibraryError):
            library.path_for('Not A Slug')


class CreateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        library.use_library(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_it_makes_a_workspace(self):
        path = library.create('My Study')
        self.assertTrue((path / 'input').is_dir())
        self.assertTrue((path / 'output').is_dir())
        self.assertTrue((path / 'experiment.toml').is_file())

    def test_the_typed_name_is_kept_even_though_the_folder_is_a_slug(self):
        path = library.create('Ultimatum 2026')
        self.assertEqual(path.name, 'ultimatum-2026')
        self.assertEqual(experiment.load(path).name, 'Ultimatum 2026')

    def test_a_duplicate_is_refused_by_name_not_by_folder(self):
        library.create('My Study')
        with self.assertRaises(library.LibraryError) as raised:
            library.create('my   study')      # same slug, different typing
        self.assertIn('already exists', str(raised.exception))

    def test_a_name_with_nothing_usable_is_refused_helpfully(self):
        with self.assertRaises(library.LibraryError) as raised:
            library.create('!!!')
        self.assertIn('no letters or digits', str(raised.exception))

    def test_archiving_hides_it_without_removing_anything(self):
        path = library.create('My Study')
        (path / 'input' / 'data.csv').write_text('a,b\n1,2\n', encoding='utf-8')

        library.archive('my-study')
        self.assertEqual(library.entries(), [])
        self.assertEqual(len(library.entries(include_archived=True)), 1)
        # The point of archiving rather than deleting.
        self.assertTrue((path / 'input' / 'data.csv').is_file())

        library.archive('my-study', archived=False)
        self.assertEqual(len(library.entries()), 1)

    def test_a_broken_configuration_is_reported_not_raised(self):
        """One unreadable experiment must not take the whole list down."""
        path = library.create('My Study')
        (path / 'experiment.toml').write_text('[experiment\n', encoding='utf-8')
        entries = library.entries()
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]['problem'])


class TomlWriterTests(unittest.TestCase):
    """The writer only has to cover our schema, and has to be exact about it."""

    def test_a_string_survives_the_round_trip(self):
        for awkward in ('plain', 'with "quotes"', 'back\\slash', 'new\nline',
                        'tab\there', 'accentata è', 'emoji 🎲', 'ctrl\x01char'):
            text = tomlwrite.dumps({'experiment': {'name': awkward}})
            self.assertEqual(tomllib.loads(text)['experiment']['name'], awkward)

    def test_keys_from_the_data_are_quoted_when_they_have_to_be(self):
        """Treatment names are column values: they can be anything."""
        config = {'treatments': {'50/50': 'Even', 'Condition A': 'First',
                                 'with "quotes"': 'Odd', 'plain': 'Plain'}}
        parsed = tomllib.loads(tomlwrite.dumps(config))
        self.assertEqual(parsed['treatments'], config['treatments'])

    def test_lists_and_numbers_and_booleans(self):
        config = {'lexicons': {'commitment': ['a', 'b']},
                  'rubric': {'context': 'x'},
                  'experiment': {'name': 'n', 'adapter': 'a'}}
        parsed = tomllib.loads(tomlwrite.dumps(config))
        self.assertEqual(parsed['lexicons']['commitment'], ['a', 'b'])

    def test_empty_values_are_left_out_rather_than_written_empty(self):
        text = tomlwrite.dumps({'experiment': {'name': 'x', 'adapter': ''},
                                'input': {}})
        parsed = tomllib.loads(text)
        self.assertNotIn('adapter', parsed['experiment'])
        self.assertNotIn('input', parsed)

    def test_the_array_of_tables_for_the_rubric(self):
        config = {'rubric': {'context': 'c', 'dimensions': [
            {'name': 'a', 'kind': 'scale'}, {'name': 'b', 'kind': 'flag'}]}}
        parsed = tomllib.loads(tomlwrite.dumps(config))
        self.assertEqual([d['name'] for d in parsed['rubric']['dimensions']],
                         ['a', 'b'])

    def test_a_type_it_cannot_write_is_refused_not_guessed(self):
        with self.assertRaises(tomlwrite.TomlWriteError):
            tomlwrite.dumps({'experiment': {'name': {'nested': 'table'}}})
        with self.assertRaises(tomlwrite.TomlWriteError):
            tomlwrite.dumps({'experiment': {'name': 3.5}})

    def test_an_empty_key_is_refused(self):
        with self.assertRaises(tomlwrite.TomlWriteError):
            tomlwrite.dumps({'treatments': {'': 'nameless'}})

    def test_save_verifies_before_it_replaces(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'experiment.toml'
            tomlwrite.save(path, {'experiment': {'name': 'x', 'adapter': 'y'}})
            self.assertTrue(path.is_file())
            # No half-written file left where a reader might find it.
            self.assertEqual(list(Path(tmpdir).glob('*.tmp')), [])

    def test_save_does_not_destroy_what_is_there_when_it_cannot_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'experiment.toml'
            tomlwrite.save(path, {'experiment': {'name': 'good'}})
            with self.assertRaises(tomlwrite.TomlWriteError):
                tomlwrite.save(path, {'experiment': {'name': 3.5}})
            # The previous configuration is still readable.
            self.assertEqual(tomllib.loads(path.read_text())['experiment']['name'],
                             'good')


class RoundTripTests(unittest.TestCase):
    """What was declared comes back; what was worked out afterwards does not."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        library.use_library(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_declaration_survives_being_read_and_written(self):
        path = library.create('Ultimatum')
        original = {
            'experiment': {'name': 'Ultimatum', 'adapter': 'generic_chat',
                           'group_noun': 'team'},
            'input': {'messages': 'chat*.csv'},
            'columns': {'group': 'team', 'body': 'text'},
            'treatments': {'a': 'First', 'b': 'Second'},
        }
        tomlwrite.save(path / 'experiment.toml', original)

        loaded = experiment.load(path)
        loaded.save()
        again = tomllib.loads((path / 'experiment.toml').read_text())
        self.assertEqual(again, original)

    def test_values_the_adapter_supplied_are_not_written_back(self):
        """The trap this guards against.

        Loading resolves `group_noun` to the adapter's word and fills in the
        treatment labels it declares. Writing those into the file would freeze
        one adapter's defaults into an experiment that never asked for them,
        and they would survive a change of adapter.
        """
        from chatlens.core import config

        path = library.create('Coalition', adapter='otree_coalition')
        loaded = experiment.load(path)
        config.use_experiment(loaded)
        self.assertEqual(loaded.group_noun, 'triad')      # derived
        self.assertTrue(loaded.treatments)                # derived

        loaded.save()
        written = tomllib.loads((path / 'experiment.toml').read_text())
        self.assertNotIn('group_noun', written['experiment'])
        self.assertNotIn('treatments', written)

    def test_setting_a_table_updates_what_is_read_as_well_as_what_is_written(self):
        path = library.create('Ultimatum')
        loaded = experiment.load(path)
        loaded.set('columns', {'group': 'team', 'body': 'text', 'sender': ''})
        # Empty means "not set", so it is not written at all.
        self.assertEqual(loaded.to_config()['columns'],
                         {'group': 'team', 'body': 'text'})
        # And the read side agrees straight away, without a reload.
        self.assertEqual(loaded.columns['group'], 'team')
        self.assertEqual(loaded.columns['sender'], 'sender')   # the default

    def test_setting_an_unknown_table_is_refused(self):
        path = library.create('Ultimatum')
        loaded = experiment.load(path)
        with self.assertRaises(experiment.ConfigError):
            loaded.set('nonsense', {'a': 'b'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
