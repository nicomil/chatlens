"""The words page: the crude analysis, and the ways it misleads.

Most of these guard against a wrong answer that looks right — a lasso that
kept everything, a parameter from a browser taken at face value, an install
command naming the wrong Python.

    python tests/test_words.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from chatlens.core import optional, words  # noqa: E402


class CleanTests(unittest.TestCase):
    def test_the_speaker_prefix_is_dropped(self):
        """Left in, the participants' names predict what the participants did."""
        text = 'Yellow -> Purple: i will support you\nPurple -> Yellow: ok'
        self.assertEqual(words.clean(text), 'i will support you ok')

    def test_a_colon_inside_the_message_survives(self):
        self.assertEqual(words.clean('Yellow -> Purple: 3:1 split'),
                         '3:1 split')

    def test_empty_input(self):
        self.assertEqual(words.clean(''), '')
        self.assertEqual(words.clean(None), '')

    def test_a_message_with_no_speaker_prefix_is_left_alone(self):
        """`clean` runs on plain message columns too, not only transcripts.

        It used to cut every line at its first colon whatever stood before it,
        so a bargaining corpus lost the words before every number it argued
        about: "ratio is 2:1 and i think: yes" came back as "1 and i think:
        yes".
        """
        text = 'ratio is 2:1 and i think: yes'
        self.assertEqual(words.clean(text), text)

    def test_the_three_shapes_of_the_prefix_are_all_recognised(self):
        """The adapters and the pipeline write it three ways."""
        for line in ('Yellow->Orange: hello', 'Yellow -> Orange: hello',
                     'Yellow to Orange: hello', '1->2: hello'):
            with self.subTest(line=line):
                self.assertEqual(words.clean(line), 'hello')


class TokenPatternTests(unittest.TestCase):
    """One-letter words are the people in the conversation.

    scikit-learn's default token pattern needs two characters, so "i" and "u"
    never reached the model — in a game about who supports whom, the two words
    that say who.
    """

    def setUp(self):
        try:
            from sklearn.feature_extraction.text import CountVectorizer
        except ImportError:
            self.skipTest('scikit-learn is not installed')
        self.CountVectorizer = CountVectorizer

    def vocabulary(self, texts, **kwargs):
        fitted = self.CountVectorizer(
            binary=True, token_pattern=words.TOKEN_PATTERN,
            **kwargs).fit(texts)
        return sorted(fitted.vocabulary_)

    def test_single_letter_pronouns_survive(self):
        self.assertEqual(self.vocabulary(['i support you', 'u and i']),
                         ['and', 'i', 'support', 'u', 'you'])

    def test_the_default_pattern_is_what_dropped_them(self):
        """Pinned so the fix cannot be undone by removing one argument."""
        plain = sorted(self.CountVectorizer(binary=True)
                       .fit(['i support you', 'u and i']).vocabulary_)
        self.assertEqual(plain, ['and', 'support', 'you'])

    def test_the_comparison_page_tokenises_the_same_way(self):
        """Two rows of that table are one representation seen twice."""
        from chatlens.core import compare

        assembled = compare.build(
            [{'group_uid': f'g{i // 4}', 'text': 'i support you' if i % 2
              else 'u and i', 'y': str(i % 2)} for i in range(120)],
            'y', 'text')
        words_set = next(s for s in assembled['sets'] if s['kind'] == 'words')
        self.assertIsNotNone(words_set['matrix'])


class PenaltySpellingTests(unittest.TestCase):
    """The bug this exists to prevent: a lasso that is quietly a ridge.

    Up to scikit-learn 1.7 `l1_ratio` is ignored unless the penalty is
    elasticnet, so passing it alone fits an L2 model over the whole vocabulary,
    keeps every term, and looks like a working lasso.
    """

    def spelling(self, version):
        import unittest.mock

        with unittest.mock.patch('sklearn.__version__', version):
            return words._lasso_kwargs(True)

    def test_older_scikit_learn_uses_penalty(self):
        self.assertEqual(self.spelling('1.6.1'), {'penalty': 'l1'})

    def test_newer_scikit_learn_uses_l1_ratio(self):
        self.assertEqual(self.spelling('1.8.0'), {'l1_ratio': 1.0})

    def test_the_l2_side_matches(self):
        import unittest.mock

        with unittest.mock.patch('sklearn.__version__', '1.6.1'):
            self.assertEqual(words._lasso_kwargs(False), {'penalty': 'l2'})


class FitTests(unittest.TestCase):
    def rows(self, n=200):
        """One planted word, with filler around it so the terms are not
        perfectly collinear: among terms carrying identical information a lasso
        keeps an arbitrary one, and a test that demands a particular one is
        testing the tie-break."""
        filler = ['we should decide', 'what do you think', 'ok then',
                  'here is my plan', 'let us talk']
        out = []
        for i in range(n):
            positive = i % 2 == 0
            out.append({
                'group_uid': f'g{i // 4}',
                'text': f'{filler[i % 5]} {"yes" if positive else "never"}',
                'y': '1' if positive else '0',
            })
        return out

    def test_it_finds_the_planted_signal(self):
        found = words.fit(self.rows(), 'text', 'y', min_df=3, penalty=0.5)
        terms = {t['term'] for t in found['kept']}
        self.assertIn('yes', terms)
        self.assertFalse(found['penalty_did_nothing'])

    def test_the_same_settings_give_the_same_answer(self):
        """Moving a control back to where it was must give back what it gave.

        liblinear picks coordinates at random; without a fixed seed this page
        showed a different list of words on every draw.
        """
        rows = self.rows()
        first = words.fit(rows, 'text', 'y', min_df=3, penalty=0.5)
        second = words.fit(rows, 'text', 'y', min_df=3, penalty=0.5)
        self.assertEqual([t['term'] for t in first['kept']],
                         [t['term'] for t in second['kept']])
        self.assertEqual([t['coef'] for t in first['kept']],
                         [t['coef'] for t in second['kept']])

    def test_too_little_data_says_so(self):
        with self.assertRaises(ValueError) as ctx:
            words.fit(self.rows(10), 'text', 'y')
        self.assertIn('not enough', str(ctx.exception))

    def test_a_constant_outcome_says_so(self):
        rows = [dict(r, y='1') for r in self.rows()]
        with self.assertRaises(ValueError) as ctx:
            words.fit(rows, 'text', 'y')
        self.assertIn('same outcome', str(ctx.exception))

    def test_an_impossible_minimum_frequency_says_so(self):
        with self.assertRaises(ValueError) as ctx:
            words.fit(self.rows(), 'text', 'y', min_df=5000)
        self.assertIn('Lower the minimum frequency', str(ctx.exception))

    def test_rows_without_text_or_outcome_are_left_out(self):
        rows = self.rows() + [{'group_uid': 'gx', 'text': '', 'y': '1'},
                              {'group_uid': 'gy', 'text': 'hello', 'y': ''}]
        found = words.fit(rows, 'text', 'y', min_df=3)
        self.assertEqual(found['rows'], 200)


class ParameterTests(unittest.TestCase):
    """Everything here arrives from a browser."""

    def params(self, **query):
        from chatlens.web import views_words

        return views_words._params({k: [v] for k, v in query.items()})

    def test_defaults_when_nothing_is_given(self):
        self.assertEqual(self.params(),
                         {'ngrams': 'both', 'penalty': 0.1, 'min_df': 10})

    def test_an_unknown_term_setting_falls_back(self):
        self.assertEqual(self.params(ngrams='trigrams')['ngrams'], 'both')

    def test_nonsense_is_not_an_error(self):
        """A page that refuses to render teaches less than one showing the
        default and saying what it used."""
        found = self.params(penalty='; DROP TABLE', min_df='../../etc/passwd')
        self.assertEqual(found['penalty'], 0.1)
        self.assertEqual(found['min_df'], 10)

    def test_a_number_outside_the_range_is_pulled_into_it(self):
        self.assertEqual(self.params(penalty='9999')['penalty'],
                         max(words.PENALTIES))
        self.assertEqual(self.params(min_df='0')['min_df'], min(words.MIN_DF))


class OptionalDependencyTests(unittest.TestCase):
    """The notice has to be actionable, which is mostly about the interpreter."""

    def test_the_pip_command_names_this_interpreter(self):
        import unittest.mock

        with unittest.mock.patch.object(sys, 'executable', '/opt/py/bin/python'):
            command = optional.install_command('words', ['scikit-learn'])
        self.assertIn('/opt/py/bin/python -m pip install', command)
        self.assertIn('scikit-learn', command)

    def test_a_uv_tool_is_reinstalled_with_the_extra(self):
        """`--force` alone will not rebuild an environment uv thinks current.

        The environment is asked whether it is a uv tool, rather than its path
        matched against the default layout — `UV_TOOL_DIR` moves it, and this
        test used to simulate one by inventing a path, which is exactly the
        thing that stopped being the question.
        """
        import unittest.mock

        with unittest.mock.patch.object(optional, '_is_uv_tool',
                                        return_value=True):
            command = optional.install_command('words', ['scikit-learn'])
        self.assertIn('--reinstall', command)
        self.assertIn('chatlens[words]', command)
        self.assertNotIn('pip install', command)

    def test_a_missing_module_is_reported_not_imported(self):
        self.assertFalse(optional.have('a_module_that_is_not_installed'))

    def test_the_panel_names_what_is_missing_and_how_to_get_it(self):
        import unittest.mock

        from chatlens.web import views_words

        with unittest.mock.patch.object(optional, 'have', lambda m: False):
            markup = views_words._requirements_panel()
        self.assertIn('scikit-learn', markup)
        self.assertIn('pip install', markup + optional.install_command(
            'words', ['x']))
        self.assertIn('different Python', markup)

    def test_nothing_is_shown_when_everything_is_there(self):
        import unittest.mock

        from chatlens.web import views_words

        with unittest.mock.patch.object(optional, 'have', lambda m: True):
            self.assertEqual(views_words._requirements_panel(), '')


class CloudSvgTests(unittest.TestCase):
    """The figure on the page, which is no longer a raster on a white slab."""

    def setUp(self):
        try:
            import wordcloud  # noqa: F401
        except ImportError:
            self.skipTest('the words extra is not installed')
        from chatlens.core import words
        self.words = words
        self.selected = [
            {'term': 'trust', 'coef': 0.9, 'documents': 8},
            {'term': 'not enough', 'coef': -0.7, 'documents': 6},
            {'term': 'split it', 'coef': 0.4, 'documents': 5},
        ]

    def test_it_is_text_and_not_a_picture_of_text(self):
        svg = self.words.cloud_svg(self.selected, True)
        self.assertTrue(svg.startswith('<svg'))
        self.assertIn('>trust</text>', svg)
        self.assertNotIn('<image', svg)

    def test_every_word_carries_the_width_it_was_laid_out_with(self):
        """Without it the drawing depends on the reader having the font the
        layout was measured with, and the words overlap when they do not."""
        svg = self.words.cloud_svg(self.selected, True)
        self.assertEqual(svg.count('<text'), svg.count('textLength='))
        self.assertIn('lengthAdjust="spacingAndGlyphs"', svg)

    def test_the_colour_is_left_to_the_page(self):
        svg = self.words.cloud_svg(self.selected, True)
        self.assertIn('var(--cloud-ink', svg)

    def test_a_direction_with_nothing_in_it_says_so(self):
        empty = [{'term': 'trust', 'coef': 0.9, 'documents': 8}]
        with self.assertRaises(ValueError):
            self.words.cloud_svg(empty, False)

    def test_the_same_terms_draw_the_same_figure(self):
        """A figure that moves when nothing changed cannot be compared with
        the one in yesterday's notes."""
        first = self.words.cloud_svg(self.selected, True)
        second = self.words.cloud_svg(self.selected, True)
        self.assertEqual(first, second)


class SeparationTests(unittest.TestCase):
    """The AUC may not see the rows it is scored on — the vocabulary included.

    The list of coefficients the page draws is fitted on every row on purpose:
    it is a description of this corpus, not an estimate. The AUC beside it is
    the estimate, so its vocabulary is chosen inside each fold.
    """

    def setUp(self):
        try:
            import sklearn  # noqa: F401
        except ImportError:
            self.skipTest('scikit-learn is not installed')

    def corpus(self, n=240):
        """A word that appears only in the last fold's groups.

        Fitted on everything it enters the vocabulary; chosen inside each fold
        it is absent from the four folds that do not hold it.
        """
        import random

        rng = random.Random(11)
        filler = ['we should decide', 'what do you think', 'ok lets do it']
        out = []
        for i in range(n):
            positive = i % 2 == 0
            text = f'{rng.choice(filler)} {"yes" if positive else "nope"}'
            out.append({'group_uid': f'g{i // 4}', 'text': text,
                        'y': '1' if positive else '0'})
        return out

    def test_the_auc_is_computed_and_bounded(self):
        found = words.fit(self.corpus(), 'text', 'y')
        self.assertIsNotNone(found['auc_words'])
        self.assertGreaterEqual(found['auc_words'], 0.0)
        self.assertLessEqual(found['auc_words'], 1.0)

    def test_the_displayed_terms_still_come_from_the_whole_corpus(self):
        """Moving a control back to where it was has to give back what it
        gave before, and the table describes the corpus in front of you."""
        first = words.fit(self.corpus(), 'text', 'y')
        second = words.fit(self.corpus(), 'text', 'y')
        self.assertEqual([t['term'] for t in first['kept']],
                         [t['term'] for t in second['kept']])
        self.assertEqual(first['vocabulary'], second['vocabulary'])

    def test_the_length_baseline_is_still_there(self):
        found = words.fit(self.corpus(), 'text', 'y')
        self.assertIsNotNone(found['auc_length'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
