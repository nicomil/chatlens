"""Emotion counts, and the distinction the output column cannot make.

A document with no listed word scores zero on every category. That is an absence
of measurement, not an absence of feeling, and most of these tests exist to keep
the two apart — the difference decides whether a regression on those columns
means anything.

    python tests/test_emotions.py
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from chatlens.core import nrc  # noqa: E402

LONG_FORM = '''word\temotion\tvalue
happy\tjoy\t1
happy\tpositive\t1
happy\tanger\t0
angry\tanger\t1
angry\tnegative\t1
trust\ttrust\t1
trust\tpositive\t1
'''

WIDE_FORM = ('word\tanger\tjoy\tnegative\tpositive\ttrust\n'
             'happy\t0\t1\t0\t1\t0\n'
             'angry\t1\t0\t1\t0\t0\n'
             'trust\t0\t0\t0\t1\t1\n')


class LoadingTests(unittest.TestCase):
    def written(self, text):
        directory = Path(tempfile.mkdtemp())
        path = directory / 'lexicon.txt'
        path.write_text(text, encoding='utf-8')
        return path

    def test_the_distributed_long_form(self):
        marked = nrc.load(self.written(LONG_FORM))
        self.assertEqual(marked['happy'], {'joy', 'positive'})
        self.assertEqual(marked['angry'], {'anger', 'negative'})

    def test_rows_marked_zero_are_dropped(self):
        marked = nrc.load(self.written(LONG_FORM))
        self.assertNotIn('anger', marked['happy'])

    def test_the_wide_form_is_read_too(self):
        """A user who obtained the file should not have to know which one
        they were sent."""
        marked = nrc.load(self.written(WIDE_FORM))
        self.assertEqual(marked['happy'], {'joy', 'positive'})
        self.assertEqual(marked['trust'], {'positive', 'trust'})

    def test_a_missing_file_points_at_the_form(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            nrc.load(Path('/nowhere/at/all.txt'))
        self.assertIn('saifmohammad', str(ctx.exception))

    def test_a_file_that_is_not_the_lexicon_says_so(self):
        with self.assertRaises(ValueError) as ctx:
            nrc.load(self.written('some\tother\tfile\nwith\tno\tmarks\n'))
        self.assertIn('right file', str(ctx.exception))


class ScoringTests(unittest.TestCase):
    def setUp(self):
        directory = Path(tempfile.mkdtemp())
        path = directory / 'lexicon.txt'
        path.write_text(LONG_FORM, encoding='utf-8')
        self.marked = nrc.load(path)

    def test_a_document_with_listed_words_is_measured(self):
        found = nrc.score('i am happy and i trust you', self.marked)
        self.assertTrue(found['measured'])
        self.assertEqual(found['emotion_words'], 2)
        self.assertEqual(found['counts']['joy'], 1)
        self.assertEqual(found['counts']['positive'], 2)

    def test_a_document_with_none_is_not_measured_rather_than_neutral(self):
        """The whole point. Both give zeros; only one is a measurement."""
        found = nrc.score('ok sure', self.marked)
        self.assertFalse(found['measured'])
        self.assertEqual(sum(found['counts'].values()), 0)

        neutral = nrc.score('happy angry', self.marked)
        self.assertTrue(neutral['measured'])

    def test_an_empty_document(self):
        found = nrc.score('', self.marked)
        self.assertFalse(found['measured'])
        self.assertEqual(found['words'], 0)

    def test_shares_are_of_the_words_present(self):
        found = nrc.score('happy happy ok ok', self.marked)
        self.assertAlmostEqual(found['shares']['joy'], 0.5)


class CoverageTests(unittest.TestCase):
    def setUp(self):
        directory = Path(tempfile.mkdtemp())
        path = directory / 'lexicon.txt'
        path.write_text(LONG_FORM, encoding='utf-8')
        self.marked = nrc.load(path)

    def test_short_documents_failing_is_named_a_text_problem(self):
        """The shape observed on the real corpus: 77% at 1-5 words, 13% at 21+."""
        texts = (['ok'] * 40
                 + ['ok then sure right'] * 40
                 + ['this is a longer one and i am happy about it'] * 40
                 + ['a much longer message where i trust you and am happy '
                    'to say so at length'] * 40)
        cover = nrc.coverage(texts, self.marked)
        self.assertIn('documents are the constraint', cover['note'])
        self.assertGreater(cover['buckets'][0]['share'],
                           cover['buckets'][-1]['share'])

    def test_long_documents_failing_too_is_named_a_lexicon_problem(self):
        texts = ['nothing here is on the list at all whatsoever ' * (i + 1)
                 for i in range(40)]
        cover = nrc.coverage(texts, self.marked)
        self.assertIn('word list', cover['note'])

    def test_empty_texts_do_not_crash_or_count(self):
        cover = nrc.coverage(['', '   ', 'happy'], self.marked)
        self.assertEqual(cover['documents'], 1)


class TotalsTests(unittest.TestCase):
    def setUp(self):
        directory = Path(tempfile.mkdtemp())
        path = directory / 'lexicon.txt'
        path.write_text(LONG_FORM, encoding='utf-8')
        self.marked = nrc.load(path)

    def test_shares_are_over_the_measured_documents_only(self):
        """Nine unmeasurable documents must not make joy look rare.

        Dividing by everything would put every category over the same inflated
        denominator, and a corpus that cannot be measured would come out looking
        uniformly unemotional rather than unmeasured.
        """
        texts = ['happy'] + ['ok'] * 9
        rows = {r['category']: r for r in nrc.totals(texts, self.marked)}
        self.assertEqual(rows['joy']['share'], 1.0)

    def test_nothing_measurable_gives_nothing_rather_than_zeros(self):
        self.assertEqual(nrc.totals(['ok', 'sure'], self.marked), [])

    def test_emotions_and_sentiments_are_labelled_apart(self):
        rows = {r['category']: r['kind']
                for r in nrc.totals(['happy angry trust'], self.marked)}
        self.assertEqual(rows['joy'], 'emotion')
        self.assertEqual(rows['positive'], 'sentiment')


class NoticeTests(unittest.TestCase):
    def test_the_page_says_where_to_get_it_and_where_to_put_it(self):
        from chatlens.web import views_emotions

        markup = views_emotions._missing_panel()
        self.assertIn('saifmohammad', markup)
        self.assertIn(nrc.FILENAME, markup)
        self.assertIn(str(nrc.lexicon_path()), markup)

    def test_the_location_can_be_overridden(self):
        import os
        import unittest.mock

        with unittest.mock.patch.dict(
                os.environ, {'CHATLENS_NRC_LEXICON': '/tmp/mine.txt'}):
            self.assertEqual(nrc.lexicon_path(), Path('/tmp/mine.txt'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
