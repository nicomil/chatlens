"""The complete tables for Stata and R.

Checked on a workspace small enough to reason about by hand: two datasets, a
stored extraction, and a word list of two entries. The names are checked
against the cases that broke Stata on the study this was written for.

    python tests/test_tables.py
"""

import re
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from chatlens.core import (config, experiment, fulltables, narratives,  # noqa: E402
                           nrc, optional, tables)

VALID = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,31}$')


class NameTests(unittest.TestCase):
    def test_every_name_is_one_stata_accepts(self):
        columns = ['participant.id_in_session', 'participant._is_bot',
                   'session.config.real_world_currency_per_point', 'if',
                   '1st', 'nlp_sent_wc', 'a name with spaces']
        for name in fulltables.safe_names(columns).values():
            self.assertRegex(name, VALID)
            self.assertNotIn(name, fulltables.RESERVED)

    def test_otree_names_keep_their_field(self):
        """Cut at 32 characters, four prolific_ columns were one name."""
        columns = [f'bargaining_tdl_intro.1.player.prolific_{f}'
                   for f in ('id', 'pid_url', 'study_id', 'session_id')]
        names = fulltables.safe_names(columns)
        self.assertEqual(names[columns[2]], 'bti_1_p_prolific_study_id')
        self.assertEqual(len(set(names.values())), 4)

    def test_a_name_that_fits_is_only_cleaned(self):
        names = fulltables.safe_names(['nlp_sent_sentiment_compound_mean',
                                       'persuasion_ij', 'participant.code'])
        self.assertEqual(list(names.values()),
                         ['nlp_sent_sentiment_compound_mean', 'persuasion_ij',
                          'participant_code'])

    def test_the_long_chatlens_names_fit_whole(self):
        names = fulltables.safe_names([
            'nlp_group_sentiment_compound_mean',
            'nlp_group_llm_contains_support_commitment',
            'nlp_sent_llm_contains_support_request'])
        self.assertEqual(list(names.values()),
                         ['nlp_group_sentiment_cmp_mean',
                          'nlp_group_llm_support_commitment',
                          'nlp_sent_llm_support_request'])

    def test_a_collision_is_numbered_rather_than_merged(self):
        self.assertEqual(fulltables.safe_names(['a.b', 'a_b']),
                         {'a.b': 'a_b', 'a_b': 'a_b_2'})


class Workspace(unittest.TestCase):
    """Three members of one group; member 3 never wrote to member 1."""

    MARKED = {'happy': {'joy', 'positive'}, 'angry': {'anger', 'negative'}}
    RELATIONS = {('g1', '1', '2'): {('i', 'support', 'you')},
                 ('g1', '2', '1'): {('you', 'support', 'i'),
                                    ('i', 'support', 'you')}}
    LONG = 'x' * 3000

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        previous = (config.WORKSPACE, config.EXPERIMENT)
        config.use_workspace(self.tmp.name)
        config.EXPERIMENT = experiment.Experiment(
            {'narratives': {'entities': ['i', 'you']}})

        def restore():
            config.use_workspace(previous[0])
            config.EXPERIMENT = previous[1]

        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(restore)
        self.addCleanup(narratives.forget)
        narratives.forget()

        config.DATASETS_DIR.mkdir(parents=True)
        config.MERGED_DIR.mkdir(parents=True)
        pair = lambda focal, partner, text: {
            'group_uid': 'g1', 'focal_id_in_group': focal,
            'partner_id_in_group': partner, 'participant.code': f'p{focal}',
            'nlp_sent_wc': str(len(text.split(':')[-1].split())),
            'sent_transcript_text': text,
            'dyad_transcript_text': text}
        tables.write(config.DATASETS_DIR / 's_chat_by_partner_nlp.csv', [
            pair('1', '2', 'Yellow->Orange: i am happy'),
            pair('2', '1', 'Orange->Yellow: angry angry'),
            pair('3', '1', '')])
        person = lambda focal, text, wc: {
            'group_uid': 'g1', 'focal_id_in_group': focal,
            'participant.code': f'p{focal}', 'nlp_sent_wc': wc,
            'sent_transcript_text': text, 'group_transcript_text': text,
            'session.randomization_schedule': self.LONG,
            'payoff': '0.5'}
        tables.write(config.DATASETS_DIR / 's_chat_aggregated_nlp.csv', [
            person('1', 'Yellow->Orange: i am happy', '3'),
            person('2', 'Orange->Yellow: angry angry', '2'),
            person('3', '', '0')])
        tables.write(config.MERGED_DIR / 's_messages_long.csv', [
            {'group_uid': 'g1', 'sender_id_in_group': '1',
             'receiver_id_in_group': '2', 'body': 'i am happy'},
            {'group_uid': 'g1', 'sender_id_in_group': '2',
             'receiver_id_in_group': '1', 'body': 'angry angry'}])

    def store_relations(self):
        """As the relations page leaves them."""
        messages = tables.read(config.MERGED_DIR / 's_messages_long.csv')
        with unittest.mock.patch.object(narratives, 'extract_with_relatio',
                                        return_value=self.RELATIONS):
            narratives.extracted(messages, ['i', 'you'], 'dyad_directed')
        narratives.forget()

    def with_lexicon(self):
        return unittest.mock.patch.multiple(
            nrc, available=lambda: True, load=lambda path=None: self.MARKED)

    def build(self, min_documents=1, **kwargs):
        with self.with_lexicon():
            built, notes = fulltables.build('s', min_documents=min_documents,
                                            **kwargs)
        rows = {key: {tuple(r.get(k) for k in ('focal_id_in_group',
                                                'partner_id_in_group')): r
                      for r in table.rows}
                for key, table in built.items()}
        return built, notes, rows


class RelationTests(Workspace):
    def test_the_pair_table_carries_what_each_pair_sent(self):
        self.store_relations()
        _built, _notes, rows = self.build()
        pairs = rows['chat_by_partner']
        self.assertEqual(pairs[('1', '2')]['rel_i_support_you'], '1')
        self.assertEqual(pairs[('1', '2')]['rel_you_support_i'], '0')
        self.assertEqual(pairs[('2', '1')]['rel_you_support_i'], '1')
        self.assertEqual(pairs[('2', '1')]['rel_sent_n'], '2')

    def test_every_relation_is_there_as_text_most_frequent_first(self):
        """The indicators hold only the frequent relations; a keyword search
        for a rare verb needs all of them."""
        self.store_relations()
        _built, _notes, rows = self.build(min_documents=2)
        pairs = rows['chat_by_partner']
        self.assertEqual(pairs[('2', '1')]['rel_sent_all'],
                         'i support you; you support i')
        self.assertNotIn('rel_you_support_i', pairs[('2', '1')])
        self.assertEqual(pairs[('3', '1')]['rel_sent_all'], '')
        people = rows['chat_aggregated']
        self.assertEqual(people[('1', None)]['rel_sent_all'], 'i support you')

    def test_nothing_written_is_blank_rather_than_zero(self):
        self.store_relations()
        _built, _notes, rows = self.build()
        silent = rows['chat_by_partner'][('3', '1')]
        self.assertEqual(silent['rel_sent_n'], '')
        self.assertEqual(silent['rel_i_support_you'], '')

    def test_a_participant_has_the_union_of_what_they_sent(self):
        self.store_relations()
        _built, _notes, rows = self.build()
        people = rows['chat_aggregated']
        self.assertEqual(people[('2', None)]['rel_i_support_you'], '1')
        self.assertEqual(people[('2', None)]['rel_you_support_i'], '1')
        self.assertEqual(people[('1', None)]['rel_you_support_i'], '0')

    def test_the_dashboard_never_extracts(self):
        """A download that spent two minutes in RELATIO would look hung."""
        with unittest.mock.patch.object(
                narratives, 'available', return_value=(True, '')), \
                unittest.mock.patch.object(
                    narratives, 'extract_with_relatio',
                    side_effect=AssertionError('extracted')):
            built, notes, _rows = self.build(extract=False)
        self.assertNotIn('rel_sent_n', built['chat_by_partner'].columns)
        self.assertTrue(any('relations page' in n for n in notes))

    def test_without_entities_the_tables_are_still_built(self):
        config.EXPERIMENT = experiment.Experiment({})
        built, notes, _rows = self.build()
        self.assertNotIn('rel_sent_n', built['chat_aggregated'].columns)
        self.assertTrue(any('entities' in n for n in notes))


class EmotionTests(Workspace):
    def test_a_category_is_a_share_of_the_words_without_the_prefix(self):
        """"Yellow->Orange:" is structure, not speech: three words, not five."""
        _built, _notes, rows = self.build()
        first = rows['chat_by_partner'][('1', '2')]
        self.assertEqual(first['nrc_sent_joy'], '33.3333')
        self.assertEqual(first['nrc_sent_anger'], '0.0')
        self.assertEqual(first['nrc_sent_matched'], '1')

    def test_no_text_is_blank(self):
        _built, _notes, rows = self.build()
        self.assertEqual(rows['chat_by_partner'][('3', '1')]['nrc_dyad_joy'],
                         '')

    def test_each_table_has_its_own_blocks(self):
        built, _notes, _rows = self.build()
        self.assertIn('nrc_dyad_joy', built['chat_by_partner'].columns)
        self.assertIn('nrc_group_joy', built['chat_aggregated'].columns)

    def test_without_the_word_list_it_says_so(self):
        with unittest.mock.patch.object(nrc, 'available', lambda: False):
            built, notes = fulltables.build('s')
        self.assertFalse(any(c.startswith('nrc_')
                             for c in built['chat_by_partner'].columns))
        self.assertTrue(any('NRC' in n for n in notes))


class WrittenTests(Workspace):
    def write(self):
        self.store_relations()
        out = Path(self.tmp.name) / 'out'
        with self.with_lexicon():
            return out, fulltables.write('s', out, min_documents=1)

    def test_the_csv_has_no_byte_order_mark_and_stata_names(self):
        out, _result = self.write()
        raw = (out / 's_chat_aggregated_full.csv').read_bytes()
        self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))
        header = raw.decode('utf-8').splitlines()[0].split(',')
        for name in header:
            self.assertRegex(name, VALID)
        self.assertIn('participant_code', header)

    def test_the_codebook_names_every_column_and_its_original(self):
        out, _result = self.write()
        book = tables.read(out / 's_codebook.csv')
        full = tables.columns_of(out / 's_chat_by_partner_full.csv')
        listed = [r['name'] for r in book
                  if r['table'] == 's_chat_by_partner_full']
        self.assertEqual(listed, full)
        code = next(r for r in book if r['original'] == 'participant.code')
        self.assertEqual((code['name'], code['source']),
                         ('participant_code', 'oTree export'))

    def test_the_dta_reads_back_as_written(self):
        if not optional.have('pandas'):
            self.skipTest('pandas is not installed')
        import pandas as pd

        out, _result = self.write()
        path = out / 's_chat_aggregated_full.dta'
        frame = pd.read_stata(path)
        self.assertEqual(list(frame.columns),
                         tables.columns_of(out / 's_chat_aggregated_full.csv'))
        # Numbers are numbers, long text survives whole as a strL, and blanks
        # are missing values rather than zeros.
        self.assertEqual(frame['payoff'].tolist(), [0.5, 0.5, 0.5])
        self.assertEqual(frame['session_randomization_schedule'][0],
                         self.LONG)
        self.assertTrue(pd.isna(frame['rel_sent_n'][2]))
        with pd.io.stata.StataReader(path) as reader:
            labels = reader.variable_labels()
        self.assertEqual(labels['participant_code'], 'participant.code')
        self.assertEqual(labels['rel_i_support_you'],
                         'Sent the relation: i | support | you')

    def test_a_code_with_a_leading_zero_stays_text(self):
        if not optional.have('pandas'):
            self.skipTest('pandas is not installed')
        import pandas as pd

        self.assertIsNone(fulltables._as_number(pd.Series(['007', '12'])))
        self.assertIsNone(fulltables._as_number(
            pd.Series(['12345678901234567'])))
        self.assertEqual(
            fulltables._as_number(pd.Series(['0.5', ''])).iloc[0], 0.5)

    def test_without_pandas_the_csvs_are_written_and_it_says_why(self):
        out, _result = self.write()
        self.assertTrue((out / 's_chat_by_partner_full.dta').exists()
                        or not optional.have('pandas'))
        real = optional.have
        with unittest.mock.patch.object(
                optional, 'have',
                lambda m: False if m == 'pandas' else real(m)), \
                self.with_lexicon():
            result = fulltables.write('s', out, min_documents=1)
        self.assertFalse((out / 's_chat_by_partner_full.dta').exists())
        self.assertTrue((out / 's_chat_by_partner_full.csv').exists())
        self.assertTrue(any('pandas' in n for n in result['notes']))

    def test_no_datasets_is_an_error_that_says_what_to_do(self):
        for path in config.DATASETS_DIR.glob('*.csv'):
            path.unlink()
        with self.assertRaises(fulltables.TablesError) as caught:
            fulltables.write('s', Path(self.tmp.name) / 'out')
        self.assertIn('run the analysis', str(caught.exception))


if __name__ == '__main__':
    unittest.main(verbosity=2)
