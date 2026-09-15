"""
Deterministic LIWC-style text measures, plus volume and sentiment.

Covers the quantities the experimenter asked for — volume, emotional tone,
sentiment, analytical thinking, Clout, Authenticity — without depending on the
LIWC software, which is commercially licensed.

What is a replication and what is an approximation
--------------------------------------------------
- **Analytic** is based on the Categorical-Dynamic Index, whose formula is
  *published* in full in Pennebaker et al. (2014):

      CDI = 30 + article + prep - ppron - ipron - auxverb - conj - adverb - negate

  with every term expressed as a percentage of total words. It is reproduced
  here to the letter: `analytic_cdi` is therefore a replication, not a proxy.

- **Clout** and **Authenticity** rest on published constructs (Kacewicz et al.
  2014 and Newman et al. 2003 respectively), but the exact weights LIWC-22 uses
  are not public. Here they are equally weighted standardised composites, with
  the signs taken from the literature, and should be read as **LIWC-style
  indices**, not as LIWC scores. The `llm_rubric` module provides a second,
  independent measurement of the same constructs, so that convergence can be
  checked.

Why counts are aggregated before the indices are computed
---------------------------------------------------------
Chat messages are very short: on the pilot the median is a handful of words. A
percentage computed over five words takes few distinct values and is dominated
by noise, and the mean of such percentages is not the percentage of the
combined text. That is why `score_counts` works on *summed* counts: counts are
extracted at message level, and the indices are computed on the real unit of
analysis (directed dyad, dyad, group).
"""

from __future__ import annotations

import math
from collections import Counter

from . import lexicons, tokens
from .lexicons import CATEGORIES, is_adverb

# One definition of a word for the whole project, in `core/tokens.py`, which is
# also where the reason there used to be three of them is written down. The
# dictionary measures count `words` and not `terms`: LIWC does not count
# numerals, and the Categorical-Dynamic Index is a percentage of words in its
# sense, so counting `60` here would stop `analytic_cdi` from being the
# replication the handbook claims.
#
# Kept as a name because tests and a docstring elsewhere refer to it.
TOKEN_RE = tokens.WORD

COUNT_KEYS = sorted(set(CATEGORIES) | {'adverb'})


# Keyed on the experiment's overrides, holding the last answer. This is called
# once per message, and when a workspace replaces a lexicon it rebuilds all
# nineteen category sets — lower-casing every word in each — every time.
_ACTIVE = {'key': object(), 'value': None}


def _inverted(active: dict) -> dict:
    """token → the categories it belongs to.

    Nineteen `in` tests per token, repeated for every token of every message,
    is the same answer arrived at nineteen times. The index is built once per
    set of lexicons and cached with it.
    """
    cached = _ACTIVE.get('index')
    if cached is not None and _ACTIVE.get('index_for') is active:
        return cached
    index = {}
    for name, vocabulary in active.items():
        for word in vocabulary:
            index.setdefault(word, []).append(name)
    _ACTIVE['index'] = index
    _ACTIVE['index_for'] = active
    return index


def _active_categories() -> dict:
    """The lexicons in force, including anything the workspace replaced."""
    from . import config

    experiment = getattr(config, 'EXPERIMENT', None)
    overrides = getattr(experiment, 'lexicons', None) if experiment else None
    if not overrides:
        return CATEGORIES

    # The overrides are a plain dict from the TOML; its items make a hashable
    # key without assuming anything about what is in them.
    key = tuple(sorted((str(k), str(v)) for k, v in overrides.items()))
    if _ACTIVE['key'] != key:
        try:
            _ACTIVE['value'] = lexicons.categories(overrides)
        except ValueError as exc:
            raise SystemExit(
                f'\nIn experiment.toml, [lexicons]: {exc}\n') from None
        _ACTIVE['key'] = key
    return _ACTIVE['value']


def tokenize(text: str) -> list[str]:
    return tokens.words(text)


def count_categories(text: str) -> dict:
    """Raw counts for a single text.

    Returns the word count and, for every category, how many words fall into
    it. Categories are not mutually exclusive: a negation such as "don't"
    counts both as an auxiliary and as a negation, exactly as in LIWC.
    """
    words = tokenize(text)
    active = _active_categories()
    index = _inverted(active)
    counts = {key: 0 for key in COUNT_KEYS}
    for token in words:
        for name in index.get(token, ()):
            counts[name] += 1
        if is_adverb(token):
            counts['adverb'] += 1

    counts['wc'] = len(words)
    counts['unique_wc'] = len(set(words))
    counts['char_count'] = len(text or '')
    # Long words: the lexical-density proxy LIWC calls "sixltr".
    counts['sixltr'] = sum(1 for t in words if len(t) > 6)
    counts['qmark'] = (text or '').count('?')
    counts['exclam'] = (text or '').count('!')
    return counts


def sum_counts(count_dicts) -> dict:
    """Sum counts across messages: the step that precedes the indices."""
    total = Counter()
    for counts in count_dicts:
        total.update(counts)
    merged = {key: int(total.get(key, 0)) for key in COUNT_KEYS}
    for key in ('wc', 'char_count', 'sixltr', 'qmark', 'exclam', 'unique_wc'):
        merged[key] = int(total.get(key, 0))
    return merged


def _pct(count: int, total: int) -> float:
    return 100.0 * count / total if total else 0.0


def score_counts(counts: dict) -> dict:
    """Compute the indices from counts that have already been summed.

    Returns the category percentages, the CDI and the raw components of Clout
    and Authenticity. The standardised indices proper need the whole sample and
    come from `standardize`.
    """
    wc = counts.get('wc', 0)
    pct = {f'pct_{key}': _pct(counts.get(key, 0), wc) for key in COUNT_KEYS}
    pct['pct_sixltr'] = _pct(counts.get('sixltr', 0), wc)

    # Categorical-Dynamic Index, the published formula.
    cdi = (
        30.0
        + pct['pct_article']
        + pct['pct_prep']
        - pct['pct_ppron']
        - pct['pct_ipron']
        - pct['pct_auxverb']
        - pct['pct_conj']
        - pct['pct_adverb']
        - pct['pct_negate']
    )

    # Components of the two composites: signs from the literature, equal
    # weights. High Clout = many references to others, few to the self, few
    # negations.
    clout_raw = (
        pct['pct_we'] + pct['pct_you'] + pct['pct_social']
        - pct['pct_i'] - pct['pct_negate'] - pct['pct_swear']
    )
    # High Authenticity = many I-words, much differentiation, little negative
    # emotion, few motion verbs (Newman et al. 2003).
    authenticity_raw = (
        pct['pct_i'] + pct['pct_exclusive']
        - pct['pct_negemo'] - pct['pct_motion']
    )
    # Emotional tone. We use the difference between percentages of total
    # words, not the ratio internal to emotion words alone: the latter
    # saturates at +/-100 as soon as the text contains a single emotion word,
    # which on chat messages it almost always does. The ratio remains available
    # as `tone_balance`, to be read only where `has_emotion_words` is 1.
    emo_total = counts.get('posemo', 0) + counts.get('negemo', 0)
    tone_raw = pct['pct_posemo'] - pct['pct_negemo']
    tone_balance = (
        100.0 * (counts['posemo'] - counts['negemo']) / emo_total if emo_total else ''
    )

    # Function-word density. This is how text that is *not* language gets
    # recognised: a keyboard string contains no articles, pronouns or
    # auxiliaries, so the CDI suffers no subtraction and the text comes out
    # paradoxically "maximally analytical". On the pilot, groups made only of
    # test strings had a median analytic_100 of 93 against 37 for groups with
    # real conversation: without this indicator the artefact would pass for
    # signal.
    funcword_pct = (
        pct['pct_article'] + pct['pct_prep'] + pct['pct_ppron']
        + pct['pct_ipron'] + pct['pct_auxverb'] + pct['pct_conj']
        + pct['pct_negate'] + pct['pct_adverb']
    )

    scores = dict(pct)
    scores.update(
        pct_funcwords=funcword_pct,
        # Conservative threshold: below 15% function words over at least five
        # words, the text is almost certainly not conversational English. Use
        # it as a filter, not as an automatic exclusion.
        low_language_flag=int(wc >= 5 and funcword_pct < 15.0),
        wc=wc,
        unique_wc=counts.get('unique_wc', 0),
        char_count=counts.get('char_count', 0),
        type_token_ratio=(counts.get('unique_wc', 0) / wc) if wc else 0.0,
        qmark=counts.get('qmark', 0),
        exclam=counts.get('exclam', 0),
        analytic_cdi=cdi,
        clout_raw=clout_raw,
        authenticity_raw=authenticity_raw,
        tone_raw=tone_raw,
        tone_balance=tone_balance,
        has_emotion_words=int(emo_total > 0),
    )
    return scores


# Indices standardised over the sample.
STANDARDIZED = ('analytic_cdi', 'clout_raw', 'authenticity_raw', 'tone_raw')

STANDARDIZED_NAMES = {
    'analytic_cdi': 'analytic',
    'clout_raw': 'clout',
    'authenticity_raw': 'authenticity',
    'tone_raw': 'tone',
}


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def standardize(rows, keys=STANDARDIZED):
    """Add z-scores and a 0-100 scale computed over the sample provided.

    LIWC reports the three composites on a 0-100 scale because it standardises
    them against a proprietary reference corpus. Here standardisation happens
    over the sample under analysis: values are therefore comparable *between*
    units of the same study, not against LIWC scores published elsewhere. That
    is the right choice for a comparison between treatments, which is exactly
    the intended use.

    Modifies `rows` in place and returns the means and deviations used.
    """
    stats = {}
    for key in keys:
        values = [r[key] for r in rows if r.get('wc', 0) > 0 and key in r]
        n = len(values)
        if n < 2:
            stats[key] = dict(mean=0.0, sd=0.0, n=n)
            continue
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / (n - 1)
        stats[key] = dict(mean=mean, sd=math.sqrt(variance), n=n)

    for row in rows:
        for key in keys:
            name = STANDARDIZED_NAMES[key]
            if row.get('wc', 0) <= 0 or key not in row:
                row[f'{name}_z'] = ''
                row[f'{name}_100'] = ''
                continue
            sd = stats[key]['sd']
            if stats[key]['n'] < 2:
                # One unit, or none. There is no sample to be standardised
                # against, so there is no position on a scale — and 0 and 50,
                # which this used to write, are indistinguishable from a real
                # reading in the middle of a real distribution. Blank says what
                # happened; `standardised_on` below says how many units there
                # were, for a caller that wants to tell its reader.
                row[f'{name}_z'] = ''
                row[f'{name}_100'] = ''
                continue
            if sd <= 0:
                # Several units, all with the same value. Unlike the case above
                # there *is* a sample here, and every unit sits exactly at its
                # mean, which is the middle. That is a reading, not a gap.
                row[f'{name}_z'] = 0.0
                row[f'{name}_100'] = 50.0
                continue
            z = (row[key] - stats[key]['mean']) / sd
            row[f'{name}_z'] = round(z, 6)
            row[f'{name}_100'] = round(100.0 * _normal_cdf(z), 4)
    return stats


def standardised_on(stats) -> dict:
    """How many units each index was standardised against.

    The scale is the sample, so the size of the sample is part of what the
    number means — and on a level with one or two units there is no scale at
    all. Returned separately rather than printed, so the caller decides whether
    its reader needs to know.
    """
    return {name: stats[key]['n'] for key, name in STANDARDIZED_NAMES.items()
            if key in stats}


# --- Sentiment -------------------------------------------------------------

_VADER = None
_VADER_TRIED = False


def _vader():
    """The VADER analyser, if the library is installed."""
    global _VADER, _VADER_TRIED
    if not _VADER_TRIED:
        _VADER_TRIED = True
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            _VADER = SentimentIntensityAnalyzer()
        except ImportError:
            _VADER = None
    return _VADER


def sentiment(text: str) -> dict:
    """Sentiment via VADER; without the library, falls back to the seed lists.

    The `sentiment_backend` field records which of the two produced the value,
    so provenance stays traceable in the final dataset.
    """
    analyzer = _vader()
    if analyzer is not None:
        scores = analyzer.polarity_scores(text or '')
        return dict(
            sentiment_compound=scores['compound'],
            sentiment_pos=scores['pos'],
            sentiment_neg=scores['neg'],
            sentiment_neu=scores['neu'],
            sentiment_backend='vader',
        )

    counts = count_categories(text)
    total = counts['posemo'] + counts['negemo']
    compound = (counts['posemo'] - counts['negemo']) / total if total else 0.0
    wc = counts['wc'] or 1
    return dict(
        sentiment_compound=compound,
        sentiment_pos=counts['posemo'] / wc,
        sentiment_neg=counts['negemo'] / wc,
        sentiment_neu=max(0.0, 1.0 - (total / wc)),
        sentiment_backend='lexicon_fallback',
    )


def analyze_message(text: str) -> dict:
    """Counts and sentiment for a single message.

    The composite indices are NOT computed here: on texts of a few words they
    would be noise. They come from aggregating the counts and passing them to
    `score_counts`.
    """
    counts = count_categories(text)
    result = dict(counts)
    result.update(sentiment(text))
    return result
