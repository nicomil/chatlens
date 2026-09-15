"""What counts as a word, decided once.

Three modules used to answer this differently, and all three answers were
applied to the same text:

    text_metrics    [a-z]+(?:'[a-z]+)*     keeps don't whole, no digits
    nrc             [a-z']+                an apostrophe may start a token
    words/compare   \\b\\w\\w+\\b (sklearn)     two characters minimum, digits kept

So `don't` was one token to the dictionaries and two to the emotion lexicon,
`i` was a word to the dictionaries and invisible to the bag of words, and `60`
was a word to the bag of words and to nothing else. Every page reported counts
of different things under the same names, and the comparison table put two of
them side by side as though they were the same representation seen twice.

One module, and **two** token sets, because the difference between them is a
real one rather than an accident:

``words``
    Letters, with internal apostrophes. What the dictionary measures count, and
    what a word lexicon can contain. Numerals are deliberately out: the
    Categorical-Dynamic Index is a percentage of *words* in LIWC's sense and
    LIWC does not count numerals, so admitting them here would quietly stop
    `analytic_cdi` from being the replication `handbook/measures.md` claims it
    is.

``terms``
    The same, plus runs of digits. What a bag of words should see, because in a
    bargaining corpus `60`, `40` and `50` are things people say and argue
    about — a split, an offer, a demand.

So `don't` is now one token everywhere, a token never begins with an apostrophe
anywhere, `i` reaches the bag of words, and `60` reaches the bag of words and
nothing else. Which of the two a caller wants is a decision it has to state.

**English, and visibly so.** The pattern matches a-z; the dictionaries behind
the measures are English word lists. On a conversation in another language the
volume measures still mean something while every dictionary index reads near
zero and means nothing at all. `looks_like_english` is how a page can tell, and
there is no partial credit: another language needs its own lexicons, not a wider
pattern.
"""

from __future__ import annotations

import re

# A word: letters with internal apostrophes. `re.IGNORECASE` rather than a-zA-Z
# in the class, so the intent — English letters — stays readable.
WORD_SOURCE = r"[a-z]+(?:'[a-z]+)*"
WORD = re.compile(WORD_SOURCE, re.IGNORECASE)

# A term: a word, or a number.
TERM_SOURCE = rf'{WORD_SOURCE}|\d+'
TERM = re.compile(TERM_SOURCE, re.IGNORECASE)

# The two in the form `CountVectorizer(token_pattern=...)` wants. sklearn
# compiles the string itself, so the pattern and the compiled object have to be
# the same thing written once.
WORD_PATTERN = f'(?i){WORD_SOURCE}'
TERM_PATTERN = f'(?i){TERM_SOURCE}'


def words(text) -> list:
    """The words of a text, lower-cased. No numerals: see the module docstring."""
    return [match.lower() for match in WORD.findall(text or '')]


def terms(text) -> list:
    """The words and the numbers, lower-cased."""
    return [match.lower() for match in TERM.findall(text or '')]


def count(text) -> int:
    """How many words, in the sense the dictionary measures count them."""
    return len(words(text))


# Below this share of function words a text is almost certainly not
# conversational English. The same threshold `text_metrics` uses to flag a unit,
# applied here to a whole corpus — where it answers a different question: not
# "is this row keyboard mashing" but "are these measures meaningful at all".
# Measured on this project's own material: conversational English comes out
# around 0.64, Italian around 0.03, keyboard mashing at 0.00. A single short
# Italian sentence can reach 0.10 by accident — "in" is a preposition in both
# languages — so the threshold sits well above that and far below real English.
ENGLISH_FUNCWORD_SHARE = 0.25

# Enough text for the share to mean anything. Under this the answer is "cannot
# tell", which is not the same as "no".
ENOUGH_TO_JUDGE = 200


def looks_like_english(texts) -> dict:
    """Whether the dictionary measures can say anything about this corpus.

    Returns the share of tokens that are English function words, and a verdict:
    `True`, `False`, or None when there is too little text to judge. A corpus in
    another language scores near zero here, and every index built on the
    dictionaries — analytic, clout, authenticity, tone — is then a column of
    noise that looks exactly like a measurement.
    """
    from .lexicons import (ARTICLES, AUXILIARY_VERBS, CONJUNCTIONS,
                           IMPERSONAL_PRONOUNS, NEGATIONS, PERSONAL_PRONOUNS,
                           PREPOSITIONS)

    functional = (ARTICLES | PREPOSITIONS | PERSONAL_PRONOUNS
                  | IMPERSONAL_PRONOUNS | AUXILIARY_VERBS | CONJUNCTIONS
                  | NEGATIONS)
    total = hits = 0
    for text in texts or ():
        for token in words(text):
            total += 1
            if token in functional:
                hits += 1
    share = hits / total if total else 0.0
    if total < ENOUGH_TO_JUDGE:
        verdict = None
    else:
        verdict = share >= ENGLISH_FUNCWORD_SHARE
    return {'tokens': total, 'function_words': hits, 'share': share,
            'english': verdict}
