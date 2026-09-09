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

from chatlens.core import experiment, library, outcome, tomlwrite  # noqa: E402


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



def multipart_body(parts, boundary=b'----test-boundary'):
    """Build an upload the way a browser would.

    `parts` is a list of (name, filename, content); filename None means a plain
    form field.
    """
    out = []
    for name, filename, content in parts:
        disposition = f'form-data; name="{name}"'
        if filename is not None:
            disposition += f'; filename="{filename}"'
        out.append(b'--' + boundary + b'\r\n')
        out.append(f'Content-Disposition: {disposition}\r\n'.encode())
        if filename is not None:
            out.append(b'Content-Type: text/csv\r\n')
        out.append(b'\r\n')
        out.append(content if isinstance(content, bytes) else content.encode())
        out.append(b'\r\n')
    out.append(b'--' + boundary + b'--\r\n')
    return b''.join(out)


class MultipartTests(unittest.TestCase):
    """The upload parser: the one place where bytes from outside are trusted
    enough to be written to disk."""

    BOUNDARY = b'----test-boundary'
    CONTENT_TYPE = 'multipart/form-data; boundary=----test-boundary'

    def setUp(self):
        from chatlens.web import multipart
        self.multipart = multipart
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def parse(self, body, content_type=None, max_bytes=10 * 1024 * 1024):
        import io

        return self.multipart.parse(
            io.BytesIO(body), len(body), content_type or self.CONTENT_TYPE,
            save_dir=self.dir, max_bytes=max_bytes)

    def leftovers(self):
        """Temporary parts nobody cleaned up."""
        return sorted(self.dir.glob('.upload-*'))

    # --- the ordinary cases ----------------------------------------------

    def test_one_file(self):
        body = multipart_body([('file', 'data.csv', 'a,b\n1,2\n')])
        fields, files = self.parse(body)
        self.assertEqual(fields, {})
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]['filename'], 'data.csv')
        self.assertEqual(files[0]['path'].read_text(), 'a,b\n1,2\n')

    def test_several_files_and_a_field(self):
        body = multipart_body([
            ('adapter', None, 'generic_chat'),
            ('file', 'one.csv', 'x\n'),
            ('file', 'two.csv', 'y\n'),
        ])
        fields, files = self.parse(body)
        self.assertEqual(fields['adapter'], 'generic_chat')
        self.assertEqual([f['filename'] for f in files], ['one.csv', 'two.csv'])

    def test_an_empty_file_input_is_not_a_file(self):
        """Browsers send the part even when nothing was chosen."""
        body = multipart_body([('file', '', '')])
        _fields, files = self.parse(body)
        self.assertEqual(files, [])

    def test_content_with_newlines_and_quotes_survives(self):
        content = 'a,b\r\n"one, two",3\r\n\r\nlast\r\n'
        body = multipart_body([('file', 'data.csv', content)])
        _fields, files = self.parse(body)
        # read_bytes, not read_text: the point is that the CRLFs arrive
        # unchanged, and read_text would translate them and prove nothing.
        self.assertEqual(files[0]['path'].read_bytes(), content.encode())

    def test_content_that_looks_like_the_boundary_but_is_not(self):
        """A line starting with the marker, without the CRLF that delimits."""
        content = 'a\n--' + self.BOUNDARY.decode() + 'x\nb\n'
        body = multipart_body([('file', 'data.csv', content)])
        _fields, files = self.parse(body)
        self.assertEqual(files[0]['path'].read_text(), content)

    def test_a_boundary_split_across_read_blocks(self):
        """The bug this parser exists to avoid.

        With the block size forced down to a few bytes, the delimiter falls
        across two reads on almost every pass.
        """
        original = self.multipart.BLOCK
        self.multipart.BLOCK = 7
        try:
            content = 'x' * 500 + '\n'
            body = multipart_body([('file', 'data.csv', content)])
            _fields, files = self.parse(body)
            self.assertEqual(files[0]['path'].read_text(), content)
        finally:
            self.multipart.BLOCK = original

    def test_a_file_larger_than_a_block(self):
        content = ('line,of,data\n' * 20000)
        body = multipart_body([('file', 'big.csv', content)])
        _fields, files = self.parse(body)
        self.assertEqual(files[0]['size'], len(content))
        self.assertEqual(files[0]['path'].read_text(), content)

    # --- what it refuses --------------------------------------------------

    def test_a_filename_cannot_be_a_path(self):
        body = multipart_body([('file', '../../etc/passwd.csv', 'x\n')])
        _fields, files = self.parse(body)
        self.assertEqual(files[0]['filename'], 'passwd.csv')
        self.assertEqual(files[0]['path'].parent, self.dir)

    def test_a_kind_we_do_not_accept(self):
        body = multipart_body([('file', 'script.sh', 'rm -rf /\n')])
        with self.assertRaises(self.multipart.UploadError) as raised:
            self.parse(body)
        self.assertIn('accepted kinds', str(raised.exception))
        self.assertEqual(self.leftovers(), [])

    def test_too_large_stops_while_it_is_going(self):
        body = multipart_body([('file', 'big.csv', 'x' * 5000)])
        with self.assertRaises(self.multipart.TooLarge):
            self.parse(body, max_bytes=1000)
        # And nothing half-written is left where it might be found.
        self.assertEqual(self.leftovers(), [])

    def test_a_body_that_declares_too_much_is_refused_before_reading(self):
        import io

        with self.assertRaises(self.multipart.TooLarge):
            self.multipart.parse(io.BytesIO(b''), 900 * 1024 * 1024,
                                 self.CONTENT_TYPE, save_dir=self.dir,
                                 max_bytes=10 * 1024 * 1024)

    def test_a_truncated_upload_leaves_nothing(self):
        body = multipart_body([('file', 'data.csv', 'x' * 5000)])
        with self.assertRaises(self.multipart.UploadError):
            self.parse(body[:2000])
        self.assertEqual(self.leftovers(), [])

    def test_a_part_without_a_name(self):
        body = (b'--' + self.BOUNDARY + b'\r\n'
                b'Content-Disposition: form-data\r\n\r\n'
                b'x\r\n--' + self.BOUNDARY + b'--\r\n')
        with self.assertRaises(self.multipart.UploadError) as raised:
            self.parse(body)
        self.assertIn('no name', str(raised.exception))

    def test_a_content_type_with_no_boundary(self):
        with self.assertRaises(self.multipart.UploadError) as raised:
            self.parse(b'', 'multipart/form-data')
        self.assertIn('boundary', str(raised.exception))

    def test_something_that_is_not_an_upload_at_all(self):
        with self.assertRaises(self.multipart.UploadError):
            self.parse(b'a=1', 'application/x-www-form-urlencoded')

    def test_a_body_that_does_not_start_with_its_boundary(self):
        with self.assertRaises(self.multipart.UploadError) as raised:
            self.parse(b'garbage\r\nmore garbage\r\n')
        self.assertIn('boundary', str(raised.exception))

    def test_a_quoted_boundary_is_understood(self):
        body = multipart_body([('file', 'data.csv', 'x\n')])
        _fields, files = self.parse(
            body, 'multipart/form-data; boundary="----test-boundary"')
        self.assertEqual(len(files), 1)



class InspectTests(unittest.TestCase):
    """Reading a CSV well enough to fill in a form about it."""

    def setUp(self):
        from chatlens.core import inspect
        self.inspect = inspect
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text, name='data.csv', encoding='utf-8'):
        path = self.dir / name
        path.write_text(text, encoding=encoding)
        return path

    # --- the header -------------------------------------------------------

    def test_the_header(self):
        path = self.write('a,b,c\n1,2,3\n')
        self.assertEqual(self.inspect.header_of(path), ['a', 'b', 'c'])

    def test_a_byte_order_mark_is_not_part_of_the_first_name(self):
        """Excel writes one, and it would become part of the column name."""
        path = self.write('\ufeffgroup,sender\n1,2\n')
        self.assertEqual(self.inspect.header_of(path)[0], 'group')

    def test_surrounding_spaces_are_trimmed(self):
        path = self.write('  group , sender \n1,2\n')
        self.assertEqual(self.inspect.header_of(path), ['group', 'sender'])

    def test_an_empty_file_says_so(self):
        path = self.write('')
        with self.assertRaises(self.inspect.ReadError) as raised:
            self.inspect.header_of(path)
        self.assertIn('empty', str(raised.exception))

    def test_a_file_that_is_not_text_says_what_to_do(self):
        path = self.dir / 'binary.csv'
        path.write_bytes(b'\xff\xfe\x00\x01binary')
        with self.assertRaises(self.inspect.ReadError) as raised:
            self.inspect.header_of(path)
        self.assertIn('UTF-8', str(raised.exception))

    # --- guessing ---------------------------------------------------------

    def test_it_guesses_the_obvious_shape(self):
        guess = self.inspect.guess(
            ['group_id', 'sender', 'receiver', 'body', 'timestamp',
             'treatment'])
        self.assertEqual(guess['group'], 'group_id')
        self.assertEqual(guess['body'], 'body')
        self.assertEqual(guess['treatment'], 'treatment')

    def test_it_guesses_a_different_vocabulary(self):
        guess = self.inspect.guess(
            ['team', 'condition', 'from_seat', 'to_seat', 'sent_at', 'text'])
        self.assertEqual(
            {k: guess.get(k) for k in ('group', 'sender', 'receiver', 'body',
                                       'timestamp', 'treatment')},
            {'group': 'team', 'sender': 'from_seat', 'receiver': 'to_seat',
             'body': 'text', 'timestamp': 'sent_at', 'treatment': 'condition'})

    def test_capitalisation_does_not_matter(self):
        guess = self.inspect.guess(
            ['Room', 'Speaker', 'Addressee', 'Utterance', 'When', 'Arm'])
        self.assertEqual(guess['sender'], 'Speaker')
        self.assertEqual(guess['body'], 'Utterance')

    def test_no_column_is_offered_for_two_roles(self):
        """"group" fits both group and treatment; only one may have it."""
        guess = self.inspect.guess(['group', 'sender', 'receiver', 'text'])
        self.assertEqual(len(set(guess.values())), len(guess))

    def test_a_suffix_beats_a_prefix(self):
        """`msg_body` is the body; `body_length` is a number about it."""
        guess = self.inspect.guess(['body_length', 'msg_body'])
        self.assertEqual(guess.get('body'), 'msg_body')

    def test_names_that_mean_nothing_are_left_alone(self):
        guess = self.inspect.guess(['col1', 'col2', 'col3'])
        self.assertEqual(guess, {})

    # --- distinct values --------------------------------------------------

    def test_the_values_a_column_takes_in_the_order_they_appear(self):
        path = self.write('t\nb\na\nb\nc\na\n')
        self.assertEqual(self.inspect.distinct(path, 't'), ['b', 'a', 'c'])

    def test_a_column_that_is_not_there(self):
        path = self.write('a\n1\n')
        self.assertEqual(self.inspect.distinct(path, 'missing'), [])

    def test_too_many_values_is_not_a_treatment(self):
        """Pointed at the message text, this must not offer a thousand boxes."""
        rows = '\n'.join(str(i) for i in range(500))
        path = self.write(f't\n{rows}\n')
        self.assertEqual(self.inspect.distinct(path, 't'), [])

    def test_blank_values_are_not_a_treatment_of_their_own(self):
        path = self.write('t\na\n\n  \nb\n')
        self.assertEqual(self.inspect.distinct(path, 't'), ['a', 'b'])


class OutcomeTests(unittest.TestCase):
    """The declaration of what an analysis is trying to explain.

    An experiment without one keeps working: everything descriptive is
    unaffected, and only the predictive pages are unavailable.
    """

    def test_absent_stays_absent(self):
        """No section, no key written back — not an empty table."""
        exp = experiment.Experiment({})
        self.assertIsNone(exp.outcome)
        self.assertNotIn('outcome', exp.to_config())

    def test_round_trip(self):
        declared = {'column': 'persuasion_ij', 'kind': 'binary',
                    'unit': 'dyad_directed'}
        exp = experiment.Experiment({'outcome': dict(declared)})
        self.assertEqual(exp.to_config()['outcome'], declared)

    def test_the_label_defaults_to_the_column_but_is_not_written_back(self):
        """Derived values must not leak into a file that never declared them."""
        exp = experiment.Experiment({'outcome': {'column': 'A_ji'}})
        self.assertEqual(exp.outcome['label'], 'A_ji')
        self.assertNotIn('label', exp.to_config()['outcome'])

    def test_setting_it_updates_the_read_side(self):
        exp = experiment.Experiment({})
        exp.set('outcome', {'column': 'A_ji', 'kind': 'binary',
                            'unit': 'dyad_directed'})
        self.assertEqual(exp.outcome['column'], 'A_ji')

    def test_clearing_it_removes_the_section(self):
        exp = experiment.Experiment({'outcome': {'column': 'A_ji'}})
        exp.set('outcome', {})
        self.assertIsNone(exp.outcome)
        self.assertNotIn('outcome', exp.to_config())

    def test_a_bad_kind_or_unit_is_reported_not_accepted(self):
        problems = outcome.problems({'column': 'x', 'kind': 'ordinal',
                                     'unit': 'dyad_directed'})
        self.assertTrue(any('Kind' in p for p in problems))
        problems = outcome.problems({'column': 'x', 'kind': 'binary',
                                     'unit': 'per_message'})
        self.assertTrue(any('Unit' in p for p in problems))

    def test_every_problem_is_reported_at_once(self):
        """The page shows them together rather than one save at a time."""
        problems = outcome.problems({'column': '', 'kind': 'ordinal',
                                     'unit': 'nope'})
        self.assertEqual(len(problems), 3)

    def test_yes_and_no_count_as_binary(self):
        """What a roster exported from a spreadsheet actually holds.

        Five modules each carried their own list of what a yes looks like, and
        none of them included the word "yes" — so the demo's own outcome column
        was binary to a reader and not binary to the tool.
        """
        rows = [{'y': 'yes'}] * 30 + [{'y': 'no'}] * 70
        found = outcome.describe(rows, {'column': 'y', 'kind': 'binary'})
        self.assertTrue(found['usable'])
        self.assertEqual(found['positive'], 30)

    def test_the_readings_agree_across_spellings(self):
        for true in ('1', 'yes', 'TRUE', 'y', 't'):
            self.assertEqual(outcome.as_binary(true), 1, true)
        for false in ('0', 'no', 'False', 'n', 'f'):
            self.assertEqual(outcome.as_binary(false), 0, false)
        for neither in ('maybe', '', None, '2'):
            self.assertIsNone(outcome.as_binary(neither), neither)

    def test_a_binary_column_is_summarised(self):
        rows = [{'y': '1'}] * 30 + [{'y': '0'}] * 70
        found = outcome.describe(rows, {'column': 'y', 'kind': 'binary'})
        self.assertTrue(found['usable'])
        self.assertEqual(found['positive'], 30)
        self.assertAlmostEqual(found['share'], 0.30)

    def test_a_column_that_is_not_binary_says_so(self):
        """The commonest wrong choice: pointing at an identifier."""
        rows = [{'y': str(i)} for i in range(40)]
        found = outcome.describe(rows, {'column': 'y', 'kind': 'binary'})
        self.assertFalse(found['usable'])
        self.assertIn('not binary', found['note'])

    def test_a_constant_column_has_nothing_to_explain(self):
        rows = [{'y': '1'}] * 50
        found = outcome.describe(rows, {'column': 'y', 'kind': 'binary'})
        self.assertFalse(found['usable'])
        self.assertIn('same value', found['note'])

    def test_a_very_rare_outcome_is_flagged_but_still_usable(self):
        rows = [{'y': '1'}] + [{'y': '0'}] * 999
        found = outcome.describe(rows, {'column': 'y', 'kind': 'binary'})
        self.assertIn('unstable', found['note'])

    def test_a_continuous_column_is_summarised(self):
        rows = [{'y': str(i)} for i in range(1, 101)]
        found = outcome.describe(rows, {'column': 'y', 'kind': 'continuous'})
        self.assertTrue(found['usable'])
        self.assertEqual(found['min'], 1.0)
        self.assertEqual(found['max'], 100.0)

    def test_text_declared_continuous_says_so(self):
        rows = [{'y': 'yes'}] * 20 + [{'y': 'no'}] * 20
        found = outcome.describe(rows, {'column': 'y', 'kind': 'continuous'})
        self.assertFalse(found['usable'])
        self.assertIn('not numbers', found['note'])

    def test_a_missing_column_is_not_a_crash(self):
        found = outcome.describe([{'a': '1'}], {'column': 'y',
                                                'kind': 'binary'})
        self.assertFalse(found['usable'])
        self.assertEqual(found['set'], 0)


class ColumnGuessTests(unittest.TestCase):
    """The guess arrives already selected, so a wrong one gets confirmed.

    That is the whole risk of this feature: a form offering nothing costs the
    user a minute, and a form offering the message text as the recipient costs
    them a dataset.
    """

    def guess(self, columns):
        from chatlens.core import inspect

        return inspect.guess(columns)

    def test_the_shape_the_demo_writes(self):
        found = self.guess(['group', 'treatment', 'sender', 'receiver',
                            'sent_at', 'text'])
        self.assertEqual(found['group'], 'group')
        self.assertEqual(found['body'], 'text')
        self.assertEqual(found['timestamp'], 'sent_at')

    def test_camel_case_is_the_same_words(self):
        """`sent_at`, `sent-at` and `sentAt` are one convention, not three."""
        found = self.guess(['teamId', 'fromSeat', 'toSeat', 'sentAt',
                            'messageBody', 'condition'])
        self.assertEqual(found['sender'], 'fromSeat')
        self.assertEqual(found['receiver'], 'toSeat')
        self.assertEqual(found['body'], 'messageBody')

    def test_a_short_synonym_does_not_match_inside_a_word(self):
        """The defect this exists for: "to" is a recipient, and also the last
        two letters of "contenuto" — which scored higher than any real match
        and put the message text in the recipient field, pre-selected."""
        found = self.guess(['squadra', 'chi_scrive', 'a_chi', 'contenuto'])
        self.assertNotEqual(found.get('receiver'), 'contenuto')
        self.assertNotEqual(found.get('body'), 'contenuto')

    def test_nothing_recognised_guesses_nothing(self):
        """Better than guessing wrong: the user is choosing either way."""
        self.assertEqual(self.guess(['alfa', 'beta', 'gamma']), {})

    def test_the_specific_synonym_beats_the_vague_one(self):
        """All three of these contain "group"."""
        found = self.guess(['group_uid', 'sender_id_in_group',
                            'receiver_id_in_group'])
        self.assertEqual(found['group'], 'group_uid')
        self.assertEqual(found['receiver'], 'receiver_id_in_group')

    def test_the_head_of_a_compound_is_its_last_word(self):
        """`msg_body` is a kind of body; `body_length` is a kind of length."""
        found = self.guess(['msg_body', 'body_length', 'sender', 'group'])
        self.assertEqual(found['body'], 'msg_body')

    def test_a_column_is_claimed_once(self):
        found = self.guess(['group', 'sender', 'receiver', 'text'])
        self.assertEqual(len(set(found.values())), len(found))


class ConfigShapeTests(unittest.TestCase):
    """A setting the tool does not act on is refused, not ignored.

    Silently dropping it is the worst of the three options: the run proceeds,
    the setting has no effect, and the only symptom is a result that does not
    match what the file appears to say.
    """

    def _load(self, body):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / 'experiment.toml').write_text(body, encoding='utf-8')
            return experiment.load(path)

    def test_a_mistyped_section_is_named_and_corrected(self):
        with self.assertRaises(experiment.ConfigError) as raised:
            self._load('[colums]\ngroup = "g"\n')
        self.assertIn('colums', str(raised.exception))
        self.assertIn('columns', str(raised.exception))

    def test_a_mistyped_key_is_named_and_corrected(self):
        with self.assertRaises(experiment.ConfigError) as raised:
            self._load('[outcome]\ncolumn = "a"\nkinde = "binary"\n')
        self.assertIn('kinde', str(raised.exception))
        self.assertIn('kind', str(raised.exception))

    def test_the_tables_whose_keys_are_the_users_own_are_left_alone(self):
        """Column roles, input roles and treatment values are named by the
        experiment, not by us: they cannot be checked against a list."""
        loaded = self._load(
            '[columns]\nbody = "text"\n[treatments]\nfoo = "Foo"\n')
        self.assertEqual(loaded.treatments, {'foo': 'Foo'})

    def test_a_file_that_says_nothing_wrong_still_loads(self):
        loaded = self._load('[experiment]\nname = "Fine"\nadapter = "generic_chat"\n')
        self.assertEqual(loaded.name, 'Fine')


if __name__ == '__main__':
    unittest.main(verbosity=2)
