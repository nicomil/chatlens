"""Emotion counts from the NRC Emotion Lexicon.

The lexicon (Mohammad and Turney) marks about fourteen thousand English words
for eight emotions — anger, anticipation, disgust, fear, joy, sadness, surprise,
trust — and for positive and negative sentiment. It is free for research and
distributed through a request form, so it cannot be shipped: its absence is
handled the way a missing dependency is, with the page saying where to get it
and where to put it.

Zero is the right value, and it is also a confound
--------------------------------------------------
A document with no fear word has a fear rating of zero, and that is correct:
nothing frightening was said. Zero is a measurement, not a gap, and rows should
not be dropped for it.

The difficulty is elsewhere. A document containing **no listed word at all**
scores zero on every category at once, and on a corpus of short messages that
happens constantly — here, 73% of documents of seven words or fewer against 8%
of those over thirty. Those all-zero rows are not distributed at random: they
are the short ones. So the emotion columns carry, mixed into them, a signal
about how much was written, and a model fitted on them without controlling for
length is partly reading that.

Which is the same trap the rest of this tool is built to point at, and it has
the same fix: keep the zeros, and put length in the model. The coverage figures
below say how much of these columns is at stake — a corpus measured on 95% of
its documents needs no special care, one measured on 40% needs length in every
specification that uses them.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path

EMOTIONS = ('anger', 'anticipation', 'disgust', 'fear', 'joy', 'sadness',
            'surprise', 'trust')
SENTIMENTS = ('negative', 'positive')
CATEGORIES = EMOTIONS + SENTIMENTS

FORM_URL = 'https://saifmohammad.com/WebPages/NRC-Emotion-Lexicon.htm'
FILENAME = 'NRC-Emotion-Lexicon-Wordlevel-v0.92.txt'

TOKEN = re.compile(r"[a-z']+")


def lexicon_path() -> Path:
    """Where the file is expected, once someone has asked for it.

    In the application data directory rather than a workspace: it is one file
    for the machine, not a property of any experiment, and copying it into every
    workspace would be four megabytes each time.
    """
    from chatlens.core import config

    override = os.environ.get('CHATLENS_NRC_LEXICON', '').strip()
    if override:
        return Path(override).expanduser()
    return config.user_data_dir() / FILENAME


def available() -> bool:
    return lexicon_path().is_file()


def _cells(line: str) -> list:
    """Split a row however it happens to be delimited, and unquote it."""
    stripped = line.rstrip('\r\n')
    parts = stripped.split('\t') if '\t' in stripped else stripped.split(',')
    return [p.strip().strip('"').strip("'") for p in parts]


def load(path: Path | None = None) -> dict:
    """word -> the categories it is marked for.

    Three shapes are accepted, because the lexicon reaches people three ways and
    none of them should have to be converted first.

    **The distributed file**: tab separated, one row per word *and* category with
    a 0 or 1, so most rows say nothing and are dropped.

    **The wide form**: one row per word with a column per category. Copies in
    this shape circulate and are not marked as different.

    **An export from R**: `tidytext::get_sentiments("nrc")` gives a table of
    word and sentiment, one row per pair, and `write.csv` makes it two quoted
    comma-separated columns. A row here *is* a marking, so there is no value
    column to check.
    """
    path = Path(path or lexicon_path())
    if not path.is_file():
        raise FileNotFoundError(
            f'The NRC lexicon is not at {path}. It is free for research: '
            f'request it at {FORM_URL}, or export it from R with '
            f'tidytext::get_sentiments("nrc").')

    marked = {}
    with path.open(encoding='utf-8', errors='replace') as handle:
        rows = [_cells(line) for line in handle if line.strip()]
    if not rows:
        raise ValueError(f'{path.name} is empty.')

    header = rows[0]
    # Wide when *every* column after the first names a category. Counting them
    # instead would misread a wide file carrying only two categories as the
    # three-column distributed form, where the second column is a category and
    # the third is a 0 or a 1.
    wide = (len(header) > 2
            and all(c.lower() in CATEGORIES for c in header[1:]))
    if wide:
        names = [c.lower() for c in header[1:]]
        for parts in rows[1:]:
            found = {name for name, value in zip(names, parts[1:])
                     if value not in ('', '0')}
            if found:
                marked[parts[0].lower()] = found
        return marked

    for parts in rows:
        if len(parts) < 2:
            continue
        category = parts[1].lower()
        if category not in CATEGORIES:
            continue
        # Two columns is a pairs table, where the row itself is the marking.
        # Three is the distributed form, where the third column says whether
        # the word carries the category at all.
        if len(parts) > 2 and parts[2] not in ('1', 'TRUE', 'True', 'true'):
            continue
        marked.setdefault(parts[0].lower(), set()).add(category)

    if not marked:
        raise ValueError(f'{path.name} was read but no marked words were '
                         f'found in it. Is it the right file?')
    return marked


def score(text: str, marked: dict) -> dict:
    """Counts and shares for one document, and whether any listed word was in it.

    ``measured`` is a diagnostic, not a filter. The zeros are real values and a
    caller should keep them; what the flag is for is knowing how many of the
    rows are all-zero, because those cluster among the short documents and turn
    the emotion columns into a partial proxy for length.
    """
    tokens = TOKEN.findall((text or '').lower())
    counts = Counter()
    hits = 0
    for token in tokens:
        found = marked.get(token)
        if found:
            hits += 1
            counts.update(found)

    return {
        'words': len(tokens),
        'emotion_words': hits,
        'measured': hits > 0,
        'counts': {c: counts.get(c, 0) for c in CATEGORIES},
        'shares': {c: (counts.get(c, 0) / len(tokens) if tokens else 0.0)
                   for c in CATEGORIES},
    }


def coverage(texts, marked) -> dict:
    """How much of the corpus the lexicon could measure at all, by length.

    Reported by length quartile because the shape says where the limit is. A
    rate that is high everywhere means the word list is the problem; one that
    falls with length means the documents are, and no lexicon fixes that.
    """
    scored = [(len(TOKEN.findall((t or '').lower())), score(t, marked))
              for t in texts]
    scored = [(n, s) for n, s in scored if n]
    if not scored:
        return {'documents': 0, 'measured': 0, 'buckets': [], 'note': ''}

    measured = sum(1 for _n, s in scored if s['measured'])
    scored.sort(key=lambda pair: pair[0])
    quarter = len(scored) // 4
    buckets = []
    if quarter:
        for i in range(4):
            chunk = scored[i * quarter:
                           (i + 1) * quarter if i < 3 else len(scored)]
            if not chunk:
                continue
            empty = sum(1 for _n, s in chunk if not s['measured'])
            buckets.append({'low': chunk[0][0], 'high': chunk[-1][0],
                            'n': len(chunk), 'unmeasured': empty,
                            'share': empty / len(chunk)})

    note = ''
    if buckets:
        first, last = buckets[0]['share'], buckets[-1]['share']
        if first > 0.5 and last < 0.25:
            note = ('The all-zero rows are the short documents, so these '
                    'columns carry a signal about length as well as about '
                    'emotion. Keep the zeros — they are real values — and put '
                    'length in any model that uses them. No lexicon can find '
                    'emotion in "ok" or "sure", so a larger word list would not '
                    'change this.')
        elif last > 0.4:
            note = ('Even the longest documents are mostly unmeasured, which '
                    'points at the word list rather than the text — a corpus '
                    'whose vocabulary the lexicon does not cover.')
        else:
            note = ('Most documents contain at least one listed word, so the '
                    'scores rest on something in most rows.')

    return {'documents': len(scored), 'measured': measured,
            'share_measured': measured / len(scored), 'buckets': buckets,
            'note': note}


def totals(texts, marked) -> list:
    """Each category's prevalence, over the documents that could be measured.

    Over the measured ones rather than all of them: including documents with no
    listed word would divide every category by the same inflated denominator and
    make an unmeasurable corpus look uniformly unemotional.
    """
    scored = [score(t, marked) for t in texts]
    usable = [s for s in scored if s['measured']]
    if not usable:
        return []
    out = []
    for category in CATEGORIES:
        with_it = sum(1 for s in usable if s['counts'][category])
        out.append({
            'category': category,
            'documents': with_it,
            'share': with_it / len(usable),
            'kind': 'emotion' if category in EMOTIONS else 'sentiment',
        })
    return sorted(out, key=lambda row: -row['share'])
