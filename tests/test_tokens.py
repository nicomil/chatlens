"""One definition of a word for the whole project.

Three modules used to answer this differently and all three answers were applied
to the same text: `don't` was one word to the dictionary measures and two to the
emotion lexicon, `i` was a word to the measures and invisible to the bag of
words, and `60` was a word to the bag of words and to nothing else.

The two token sets that remain are a deliberate distinction, not a leftover, and
these tests pin both halves of it.

    python tests/test_tokens.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from chatlens.core import nrc, text_metrics, tokens, words  # noqa: E402


class WordTests(unittest.TestCase):
    def test_a_contraction_stays_whole(self):
        self.assertEqual(tokens.words("don't do it"), ["don't", 'do', 'it'])

    def test_a_token_never_begins_with_an_apostrophe(self):
        """The emotion lexicon's own pattern allowed it, so `don't` came apart
        there and nowhere else."""
        for token in tokens.words("i'm here, 'quoted' too"):
            self.assertFalse(token.startswith("'"), token)

    def test_one_letter_words_are_words(self):
        self.assertEqual(tokens.words('i owe u'), ['i', 'owe', 'u'])

    def test_numerals_are_not_words(self):
        """LIWC does not count them, and `analytic_cdi` is a percentage of words
        in LIWC's sense — so counting them would end the replication."""
        self.assertEqual(tokens.words('split 60 40'), ['split'])

    def test_numerals_are_terms(self):
        """A bag of words should see them: in a bargaining corpus `60` is an
        offer."""
        self.assertEqual(tokens.terms('split 60 40'), ['split', '60', '40'])

    def test_it_lower_cases(self):
        self.assertEqual(tokens.words('I Support YOU'), ['i', 'support', 'you'])

    def test_empty_input(self):
        for empty in ('', None, '   ', '!!! ???'):
            self.assertEqual(tokens.words(empty), [])


class AgreementTests(unittest.TestCase):
    """The pattern and the compiled object have to be the same thing.

    `CountVectorizer` compiles the string itself, so a difference between the
    two would mean the page and the model disagreed about the vocabulary with
    nothing to show it.
    """

    def setUp(self):
        try:
            from sklearn.feature_extraction.text import CountVectorizer
        except ImportError:
            self.skipTest('scikit-learn is not installed')
        self.CountVectorizer = CountVectorizer

    def vocabulary(self, text, pattern):
        fitted = self.CountVectorizer(binary=True,
                                      token_pattern=pattern).fit([text])
        return sorted(fitted.vocabulary_)

    def test_the_term_pattern_matches_the_term_regex(self):
        for text in ("don't i'm 60/40 ok u", 'i support you', 'ratio is 2:1',
                     'A B c'):
            with self.subTest(text=text):
                self.assertEqual(
                    sorted(set(tokens.terms(text))),
                    self.vocabulary(text, tokens.TERM_PATTERN))

    def test_the_word_pattern_matches_the_word_regex(self):
        for text in ("don't i'm 60/40 ok u", 'ratio is 2:1'):
            with self.subTest(text=text):
                self.assertEqual(
                    sorted(set(tokens.words(text))),
                    self.vocabulary(text, tokens.WORD_PATTERN))


class EveryCallerAgreesTests(unittest.TestCase):
    """The three modules that used to disagree."""

    def test_the_measures_count_words(self):
        counted = text_metrics.count_categories("don't split 60 40")
        # don't, split — the numerals are not words.
        self.assertEqual(counted['wc'], 2)
        self.assertEqual(text_metrics.tokenize("don't"), ["don't"])

    def test_the_emotion_lexicon_counts_the_same_words(self):
        marked = {"don't": {'negative'}}
        scored = nrc.score("don't split 60 40", marked)
        self.assertEqual(scored['words'], 2)
        # One token, matched whole, where the old pattern split it in two.
        self.assertEqual(scored['emotion_words'], 1)

    def test_the_bag_of_words_uses_the_term_pattern(self):
        self.assertEqual(words.TOKEN_PATTERN, tokens.TERM_PATTERN)

    def test_the_measures_and_the_lexicon_agree_on_the_count(self):
        for text in ("i don't think we should", 'ok', "you're right about it"):
            with self.subTest(text=text):
                self.assertEqual(
                    text_metrics.count_categories(text)['wc'],
                    nrc.score(text, {})['words'])


class LanguageTests(unittest.TestCase):
    """Whether the dictionary measures can say anything at all.

    On a corpus in another language every index built on the English word lists
    reads near zero — which looks exactly like a measurement.
    """

    ENGLISH = ['i will support you because the payoff is better for us',
               'ok then lets do it', 'what do you think about the split',
               'i am not sure i want to promise you anything',
               'we should decide now before the timer runs out']
    ITALIAN = ['io penso che dovremmo dividere in parti uguali senza discutere',
               'va bene facciamo cosi allora',
               'non sono sicuro di volerti promettere qualcosa',
               'dobbiamo decidere adesso prima che scada il tempo',
               'tu cosa ne pensi della divisione']

    def test_english_is_recognised(self):
        found = tokens.looks_like_english(self.ENGLISH * 12)
        self.assertTrue(found['english'])
        self.assertGreater(found['share'], 0.4)

    def test_another_language_is_not(self):
        found = tokens.looks_like_english(self.ITALIAN * 12)
        self.assertFalse(found['english'])
        self.assertLess(found['share'], 0.1)

    def test_keyboard_mashing_is_not(self):
        found = tokens.looks_like_english(['asdf qwerty zxcv'] * 100)
        self.assertFalse(found['english'])

    def test_too_little_text_is_not_an_answer(self):
        """"Cannot tell" is not "no"."""
        self.assertIsNone(tokens.looks_like_english(['ok', 'yes'])['english'])
        self.assertIsNone(tokens.looks_like_english([])['english'])

    def test_the_threshold_separates_the_two_with_room(self):
        english = tokens.looks_like_english(self.ENGLISH * 12)['share']
        italian = tokens.looks_like_english(self.ITALIAN * 12)['share']
        self.assertLess(italian, tokens.ENGLISH_FUNCWORD_SHARE)
        self.assertGreater(english, tokens.ENGLISH_FUNCWORD_SHARE)
        # And not by a whisker: a threshold sitting on top of either would be
        # decided by whichever sentences happened to be in the corpus.
        self.assertGreater(english - tokens.ENGLISH_FUNCWORD_SHARE, 0.1)
        self.assertGreater(tokens.ENGLISH_FUNCWORD_SHARE - italian, 0.1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
