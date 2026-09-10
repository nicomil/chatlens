"""Tests for packing an experiment and opening one somebody sent.

Two things here are worth more than the round trip, and both are places where
a mistake is silent:

- **what does not travel.** The pseudonym key is the file that turns the
  pseudonyms back into Prolific ids. Sending it with the data it protects is
  not a smaller mistake than not pseudonymising at all;
- **what arrives.** A tar archive can name any path it likes. Python grew a
  filter for this in 3.12, later than the version this tool supports, so the
  checking is ours and has to be tested as ours.

    python tests/test_bundle.py
"""

import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

# Runs from a source checkout without installing: the package is under src/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from chatlens.core import bundle, library, tables  # noqa: E402


def make_experiment(root: Path, slug: str = 'a-study') -> Path:
    """An experiment with one of everything the packer has an opinion about."""
    folder = root / slug
    (folder / 'input').mkdir(parents=True)
    (folder / 'output' / 'merged').mkdir(parents=True)
    (folder / 'output' / 'runs' / '2026-01-01_000000').mkdir(parents=True)
    (folder / 'output' / 'cache' / 'stem').mkdir(parents=True)
    (folder / 'output' / 'topicgpt').mkdir(parents=True)

    (folder / 'experiment.toml').write_text(
        '[experiment]\nname = "A Study"\nadapter = "generic_chat"\n',
        encoding='utf-8')
    tables.write(folder / 'input' / 'chat.csv', [
        {'participant.prolific_id': 'REAL123', 'body': 'hello'},
        {'participant.prolific_id': 'REAL456', 'body': 'hi'},
    ])
    tables.write(folder / 'output' / 'merged' / 'messages.csv', [
        {'sender_participant_code': 'REAL123', 'body': 'hello'},
    ])
    (folder / 'output' / 'runs' / '2026-01-01_000000' / 'run.json').write_text(
        '{}', encoding='utf-8')
    (folder / 'output' / 'cache' / 'stem' / 'rubrica_group.jsonl').write_text(
        '{"paid": true}\n', encoding='utf-8')
    (folder / 'output' / 'topicgpt' / 'assignment.jsonl').write_text(
        '{"topic": "Cooperation"}\n', encoding='utf-8')
    (folder / 'output' / '.pseudonym_key').write_bytes(b'secret-key-material')
    (folder / '.env').write_text('OPENAI_API_KEY=sk-real\n', encoding='utf-8')
    return folder


class WhatTravelsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.folder = make_experiment(self.root)
        self.addCleanup(self.tmp.cleanup)

    def names(self, **kwargs):
        archive = bundle.pack(self.folder, self.root / 'out.tar.gz', **kwargs)
        with tarfile.open(archive) as handle:
            return set(handle.getnames())

    def test_the_pseudonym_key_never_travels(self):
        """It undoes the pseudonymisation it is packed beside."""
        names = self.names(with_runs=True)
        self.assertNotIn('a-study/output/.pseudonym_key', names)

    def test_the_api_keys_never_travel(self):
        self.assertNotIn('a-study/.env', self.names(with_runs=True))

    def test_the_paid_stages_do_travel(self):
        """The whole point: nobody pays twice for the same answers."""
        names = self.names()
        self.assertIn('a-study/output/cache/stem/rubrica_group.jsonl', names)
        self.assertIn('a-study/output/topicgpt/assignment.jsonl', names)

    def test_the_history_travels_but_its_copied_tables_do_not(self):
        """What was run and with which options is a few kilobytes and worth
        having. The copied datasets were 77 MB of the 79 on the real study,
        and the current run has a newer version of them at a fixed path."""
        run = 'a-study/output/runs/2026-01-01_000000/run.json'
        bulk = 'a-study/output/runs/2026-01-01_000000/datasets/old.csv'
        (self.folder / 'output' / 'runs' / '2026-01-01_000000'
         / 'datasets').mkdir()
        tables.write(self.folder / 'output' / 'runs' / '2026-01-01_000000'
                     / 'datasets' / 'old.csv', [{'a': '1'}])

        self.assertIn(run, self.names())
        self.assertNotIn(bulk, self.names())
        self.assertIn(bulk, self.names(with_runs=True))

    def test_a_hand_made_input_backup_stays_behind(self):
        (self.folder / 'input.2026-01-01.bak').mkdir()
        (self.folder / 'input.2026-01-01.bak' / 'old.csv').write_text(
            'a\n1\n', encoding='utf-8')
        self.assertNotIn('a-study/input.2026-01-01.bak/old.csv', self.names())

    def test_the_manifest_says_what_is_inside(self):
        archive = bundle.pack(self.folder, self.root / 'out.tar.gz')
        manifest = bundle.inspect(archive)
        self.assertEqual(manifest['name'], 'A Study')
        self.assertEqual(manifest['slug'], 'a-study')
        self.assertTrue(manifest['has_rubric'])
        self.assertTrue(manifest['has_topics'])
        self.assertFalse(manifest['pseudonymised'])

    def test_a_folder_without_a_configuration_is_not_an_experiment(self):
        plain = self.root / 'not-a-study'
        plain.mkdir()
        with self.assertRaises(bundle.BundleError):
            bundle.pack(plain, self.root / 'out.tar.gz')


class PseudonymiseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.folder = make_experiment(self.root)
        self.addCleanup(self.tmp.cleanup)

    def unpacked(self, **kwargs):
        archive = bundle.pack(self.folder, self.root / 'out.tar.gz', **kwargs)
        library.use_library(self.root / 'library')
        return bundle.unpack(archive, self.root / 'library')

    def test_identifiers_are_replaced_everywhere_they_appear(self):
        folder = self.unpacked(pseudonymise=True)
        rows = tables.read(folder / 'input' / 'chat.csv')
        self.assertNotIn('REAL123', str(rows))
        self.assertTrue(rows[0]['participant.prolific_id'].startswith('p_'))

    def test_the_same_person_keeps_one_pseudonym_across_the_tables(self):
        """Otherwise the recipient cannot join the chat to anything."""
        folder = self.unpacked(pseudonymise=True)
        chat = tables.read(folder / 'input' / 'chat.csv')
        merged = tables.read(folder / 'output' / 'merged' / 'messages.csv')
        self.assertEqual(chat[0]['participant.prolific_id'],
                         merged[0]['sender_participant_code'])

    def test_the_text_is_untouched(self):
        """People write their names in the chat. This does not make a dataset
        anonymous and must not be described as if it did."""
        folder = self.unpacked(pseudonymise=True)
        rows = tables.read(folder / 'input' / 'chat.csv')
        self.assertEqual(rows[0]['body'], 'hello')

    def test_a_pseudonym_keeps_the_shape_the_pipeline_checks(self):
        """The bug this pins returned nothing rather than failing.

        An adapter decides who is a real participant by matching
        `participant.label` against the shape of a Prolific id. A pseudonym of
        another shape fails that match on every row, and the pipeline then runs
        to completion on an empty dataset — which it did, on a pseudonymised
        copy of a real study: 8 579 messages in, none out.
        """
        from chatlens.core import privacy

        key = b'k' * 32
        real = 'a1b2c3d4e5f6a1b2c3d4e5f6'          # twenty-four hex, as they are
        fake = privacy.pseudonym(real, key)
        self.assertEqual(len(fake), len(real))
        self.assertRegex(fake, r'^[0-9a-f]{24}$')
        self.assertNotEqual(fake, real)

    def test_something_that_is_not_hexadecimal_is_marked_as_a_pseudonym(self):
        """Where no shape is depended on, saying so is worth more."""
        from chatlens.core import privacy

        self.assertTrue(
            privacy.pseudonym('Nicola M.', b'k' * 32).startswith('p_'))

    def test_two_people_do_not_become_one(self):
        from chatlens.core import privacy

        key = b'k' * 32
        self.assertNotEqual(privacy.pseudonym('a' * 80, key),
                            privacy.pseudonym('b' * 80, key))

    def test_without_the_option_the_identifiers_are_as_they_were(self):
        folder = self.unpacked()
        rows = tables.read(folder / 'input' / 'chat.csv')
        self.assertEqual(rows[0]['participant.prolific_id'], 'REAL123')


class UnpackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.folder = make_experiment(self.root)
        self.archive = bundle.pack(self.folder, self.root / 'out.tar.gz')
        self.library = self.root / 'library'
        library.use_library(self.library)
        self.addCleanup(self.tmp.cleanup)

    def test_the_round_trip_keeps_the_files(self):
        folder = bundle.unpack(self.archive, self.library)
        self.assertTrue((folder / 'experiment.toml').is_file())
        self.assertTrue(
            (folder / 'output' / 'cache' / 'stem' / 'rubrica_group.jsonl')
            .is_file())

    def test_importing_twice_refuses_rather_than_overwrites(self):
        """The usual case is a colleague's copy of work you also have."""
        bundle.unpack(self.archive, self.library)
        with self.assertRaises(bundle.BundleError):
            bundle.unpack(self.archive, self.library)

    def test_it_can_be_imported_under_another_name(self):
        """Both halves of the name: renaming only the folder leaves the
        library showing two cards with the same title, which is the thing
        --name exists to avoid."""
        from chatlens.core import experiment as experiment_module

        bundle.unpack(self.archive, self.library)
        folder = bundle.unpack(self.archive, self.library, name='Their Copy')
        self.assertEqual(folder.name, 'their-copy')
        self.assertEqual(experiment_module.load(folder).name, 'Their Copy')

    def test_without_a_name_it_keeps_the_one_it_was_sent_under(self):
        folder = bundle.unpack(self.archive, self.library)
        from chatlens.core import experiment as experiment_module
        self.assertEqual(experiment_module.load(folder).name, 'A Study')

    def test_nothing_is_left_behind_when_it_refuses(self):
        bundle.unpack(self.archive, self.library)
        before = sorted(p.name for p in self.library.iterdir())
        with self.assertRaises(bundle.BundleError):
            bundle.unpack(self.archive, self.library)
        self.assertEqual(sorted(p.name for p in self.library.iterdir()), before)


class HostileArchiveTests(unittest.TestCase):
    """A bundle arrives from somebody else. Python's own extraction did not
    check these until 3.12, which is later than this tool supports."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.library = self.root / 'library'
        library.use_library(self.library)
        self.addCleanup(self.tmp.cleanup)

    def write(self, path: Path, members) -> Path:
        """An archive with a valid manifest and whatever members are given."""
        manifest = json.dumps({'format': 1, 'slug': 'a-study',
                               'name': 'A Study', 'adapter': 'generic_chat',
                               'n_files': 1, 'bytes': 1,
                               'has_rubric': False, 'has_topics': False,
                               'has_runs': False,
                               'pseudonymised': False}).encode()
        with tarfile.open(path, 'w:gz') as archive:
            info = tarfile.TarInfo(bundle.MANIFEST)
            info.size = len(manifest)
            archive.addfile(info, io.BytesIO(manifest))
            for member in members:
                if member.type == tarfile.REGTYPE:
                    member.size = 1
                    archive.addfile(member, io.BytesIO(b'x'))
                else:
                    archive.addfile(member)
        return path

    def refuses(self, member):
        path = self.write(self.root / 'hostile.tar.gz', [member])
        with self.assertRaises(bundle.BundleError):
            bundle.unpack(path, self.library)
        self.assertFalse((self.library / 'a-study').exists())

    def test_a_path_climbing_out_of_the_folder(self):
        self.refuses(tarfile.TarInfo('a-study/../../escaped.csv'))

    def test_an_absolute_path(self):
        self.refuses(tarfile.TarInfo('/etc/passwd'))

    def test_a_member_outside_the_folder_the_manifest_names(self):
        self.refuses(tarfile.TarInfo('somewhere-else/file.csv'))

    def test_a_symlink(self):
        link = tarfile.TarInfo('a-study/key')
        link.type = tarfile.SYMTYPE
        link.linkname = '/etc/passwd'
        self.refuses(link)

    def test_a_hard_link(self):
        link = tarfile.TarInfo('a-study/key')
        link.type = tarfile.LNKTYPE
        link.linkname = 'a-study/experiment.toml'
        self.refuses(link)

    def test_an_archive_that_is_not_one_of_ours(self):
        plain = self.root / 'plain.tar.gz'
        with tarfile.open(plain, 'w:gz') as archive:
            info = tarfile.TarInfo('readme.txt')
            info.size = 1
            archive.addfile(info, io.BytesIO(b'x'))
        with self.assertRaises(bundle.BundleError):
            bundle.inspect(plain)

    def test_a_file_that_is_not_an_archive_at_all(self):
        plain = self.root / 'notes.txt'
        plain.write_text('hello', encoding='utf-8')
        with self.assertRaises(bundle.BundleError):
            bundle.inspect(plain)

    def test_a_format_from_a_later_chatlens_says_so(self):
        path = self.root / 'future.tar.gz'
        manifest = json.dumps({'format': bundle.FORMAT + 1,
                               'slug': 'a-study'}).encode()
        with tarfile.open(path, 'w:gz') as archive:
            info = tarfile.TarInfo(bundle.MANIFEST)
            info.size = len(manifest)
            archive.addfile(info, io.BytesIO(manifest))
        with self.assertRaises(bundle.BundleError) as caught:
            bundle.inspect(path)
        self.assertIn('later chatlens', str(caught.exception))


if __name__ == '__main__':
    unittest.main(verbosity=2)
