"""The text measures shaped as regressors, for an analysis run somewhere else.

The papers this was written for estimate their models in Stata. The text
analysis is exploratory there: it supplies covariates that may move the
probability of a binary outcome, and the experimenter chooses which ones enter
a model, standardises them himself and runs his own LASSO. So the job of this
module is not to judge the measures but to hand all of them over in a form that
imposes no choice of scale:

- **raw values only.** The `_z` and `_100` columns are the same measure
  rescaled on the sample under analysis. In a regression a rescaling chosen by
  somebody else is a nuisance at best, and a column that changes value when the
  sample changes is a trap. They are dropped here and kept in the datasets the
  do-files read.
- **an ordinal version, 1 to 4**, for the measures where "absent" means
  something: the share of words in a category. 1 is none at all; 2, 3 and 4 are
  the lower, middle and upper third of the rows where the category occurs. The
  cut points are the study's own and are written into the codebook label.
- **one indicator per topic**, because a topic arrives as text
  (`"Commitment|Payoff Reasoning"`) and a regression cannot read text.
- **the bag of words**: unigrams and bigrams as raw counts, one column per term
  frequent enough to be worth a coefficient, so a LASSO can be run on them
  directly.

Nothing here looks at the outcome. Every choice — the vocabulary, the frequency
threshold, the thirds — is made on the text alone, so none of it can have
learnt anything a later model is then credited with.
"""

from __future__ import annotations

import re
from collections import Counter

from . import fulltables, tokens, words as words_module

# How many documents a term has to occur in to get a column. Ten is the default
# of the words page, and on one study of the coalition collection it gives about
# four hundred unigrams and five hundred bigrams: enough for a LASSO to choose
# from, and few enough that the file opens in every edition of Stata, including
# the one limited to 2 048 variables.
BOW_MIN_DOCUMENTS = 10

# Which transcript the bag of words is built on, per table. What the focal
# participant sent: in a study of persuasion the speaker's words are the ones a
# partner's choice can respond to.
BOW_TEXT = {
    'chat_by_partner': 'sent_transcript_text',
    'chat_aggregated': 'sent_transcript_text',
}

# The measures that get an ordinal version: shares of words in a category, from
# the dictionaries and from the NRC lexicon. They have a natural zero, which is
# what makes "1 = absent" true. The composite indices (analytic, clout,
# authenticity, tone) and the sentiment score have no such zero and are left as
# they are.
ORDINAL = (re.compile(r'^nlp_[a-z]+_pct_(?!funcwords)'),
           re.compile(r'^nrc_[a-z]+_(?!matched$)[a-z]+$'))

RESCALED = ('_z', '_100')

TOPIC_LIST = re.compile(r'^nlp_([a-z]+)_topics$')


def is_rescaled(column: str) -> bool:
    return column.startswith('nlp_') and column.endswith(RESCALED)


def raw_only(columns) -> list:
    """The columns without the sample-standardised copies of the measures."""
    return [c for c in columns if not is_rescaled(c)]


def _number(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _cut_points(values) -> tuple:
    """The two values that split the positive ones into thirds."""
    ordered = sorted(values)
    n = len(ordered)
    return (ordered[max(0, -(-n // 3) - 1)],
            ordered[max(0, -(-2 * n // 3) - 1)])


def ordinal(rows, column: str):
    """Add `<column>_lik` to every row; return its label, or None if not added.

    1 when the value is zero, 2 to 4 for the thirds of the positive values,
    blank where the measure is blank — a unit with no text has no measurement,
    and 1 would say it had one and found nothing.
    """
    positive = [v for v in (_number(r.get(column)) for r in rows)
                if v is not None and v > 0]
    name = f'{column}_lik'
    if not positive:
        for row in rows:
            value = _number(row.get(column))
            row[name] = '' if value is None else '1'
        return f'{column}, 1-4: never present in this sample'
    low, high = _cut_points(positive)
    for row in rows:
        value = _number(row.get(column))
        if value is None:
            row[name] = ''
        elif value <= 0:
            row[name] = '1'
        elif value <= low:
            row[name] = '2'
        elif value <= high:
            row[name] = '3'
        else:
            row[name] = '4'
    return (f'{column}, 1-4: 1 = 0; 2 <= {low:g}; 3 <= {high:g}; 4 > {high:g}')


def ordinal_columns(columns) -> list:
    return [c for c in columns if any(p.match(c) for p in ORDINAL)]


def topic_indicators(rows, column: str) -> dict:
    """One 0/1 column per topic named in a `nlp_<block>_topics` column.

    Returns {new column: topic}. Blank stays blank: a document with no text has
    no topic, which is not the same as a document without this one.
    """
    block = TOPIC_LIST.match(column).group(1)
    found = Counter()
    for row in rows:
        for topic in _topics(row.get(column)):
            found[topic] += 1
    names = {f'topic_{block}_{fulltables._clean(t).lower()}': t
             for t in sorted(found, key=lambda t: (-found[t], t))}
    for row in rows:
        present = set(_topics(row.get(column)))
        spoke = bool(str(row.get(f'{block}_transcript_text') or
                         row.get(f'nlp_{block}_wc') or '').strip())
        for name, topic in names.items():
            row[name] = ('1' if topic in present else '0') if spoke else ''
    return names


def _topics(value) -> list:
    return [t.strip() for t in str(value or '').split('|') if t.strip()]


def _document_terms(text) -> set:
    """The unigrams and bigrams of one transcript, as a set of strings.

    Bigrams are taken within a message, never across two: the last word of one
    message and the first of the next were not written as a phrase, and on a
    chat of short turns they would be a large share of every bigram.
    """
    return set(_document_counts(text))


def _document_counts(text) -> Counter:
    counts = Counter()
    for line in str(text or '').splitlines():
        found = tokens.terms(words_module.clean(line))
        counts.update(found)
        counts.update(f'{a} {b}' for a, b in zip(found, found[1:]))
    return counts


def vocabulary(rows, text_column: str,
               min_documents: int = BOW_MIN_DOCUMENTS) -> list:
    """The terms in at least `min_documents` documents, most frequent first."""
    document_frequency = Counter()
    for row in rows:
        document_frequency.update(_document_terms(row.get(text_column)))
    kept = [t for t, n in document_frequency.items() if n >= min_documents]
    return sorted(kept, key=lambda t: (' ' in t, -document_frequency[t], t))


def bag_of_words(rows, text_column: str,
                 min_documents: int = BOW_MIN_DOCUMENTS) -> dict:
    """Add one raw-count column per term; return {column: term}.

    Counts rather than presence or weights: a LASSO can be run on either, and
    turning counts into shares or TF-IDF is a choice for whoever runs it. Blank
    where the row has no text, for the same reason as everywhere else.
    """
    terms = vocabulary(rows, text_column, min_documents)
    names = {f'bow_{fulltables._clean(t.replace(" ", "__"))}': t
             for t in terms}
    for row in rows:
        text = row.get(text_column)
        if not str(text or '').strip():
            row.update(dict.fromkeys(names, ''))
            continue
        counts = _document_counts(text)
        for name, term in names.items():
            row[name] = str(counts.get(term, 0))
    return names
