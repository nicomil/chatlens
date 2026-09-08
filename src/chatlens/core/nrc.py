"""Emotion counts from the NRC Emotion Lexicon.

The lexicon (Mohammad and Turney) marks about fourteen thousand English words
for eight emotions — anger, anticipation, disgust, fear, joy, sadness, surprise,
trust — and for positive and negative sentiment. It is free for research and
distributed through a request form, so it cannot be shipped: its absence is
handled the way a missing dependency is, with the page saying where to get it
and where to put it.

Why the coverage diagnostic is not optional
-------------------------------------------
This is a word list. A document scores by containing words that are on it, and a
document that contains none scores zero on every category — which is not "no
emotion", it is "no measurement". The two are indistinguishable in the output
column and the difference decides whether a regression means anything.

On the corpus this tool was built for the constraint was not the lexicon's size
but the messages': 77% of documents of five words or fewer contained no emotion
word at all, against 13% of those over twenty. A larger word list helps at the
margin and cannot help with "ok" or "sure". So every table here carries the
share of documents it could not measure, in the same view, and a caller that
wants the scores gets the coverage whether it asked or not.
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


def load(path: Path | None = None) -> dict:
    """word -> the categories it is marked for.

    The distributed file has one row per word and category, with a 0 or 1, so
    most rows say nothing and are dropped. Some copies in circulation are the
    wide form instead, one row per word with a column per category, and both are
    accepted: a user who has obtained the file should not have to know which
    one they were sent.
    """
    path = Path(path or lexicon_path())
    if not path.is_file():
        raise FileNotFoundError(
            f'The NRC lexicon is not at {path}. It is free for research but '
            f'distributed through a form: {FORM_URL}')

    marked = {}
    with path.open(encoding='utf-8', errors='replace') as handle:
        first = handle.readline()
        columns = first.rstrip('\n').split('\t')
        wide = len(columns) > 3 and any(c.strip().lower() in CATEGORIES
                                        for c in columns[1:])
        if wide:
            names = [c.strip().lower() for c in columns[1:]]
            for line in handle:
                parts = line.rstrip('\n').split('\t')
                if len(parts) < 2:
                    continue
                found = {name for name, value in zip(names, parts[1:])
                         if value.strip() not in ('', '0')}
                if found:
                    marked[parts[0].strip().lower()] = found
            return marked

        handle.seek(0)
        for line in handle:
            parts = line.rstrip('\n').split('\t')
            if len(parts) != 3 or parts[2].strip() != '1':
                continue
            category = parts[1].strip().lower()
            if category in CATEGORIES:
                marked.setdefault(parts[0].strip().lower(),
                                  set()).add(category)
    if not marked:
        raise ValueError(f'{path.name} was read but no marked words were '
                         f'found in it. Is it the right file?')
    return marked


def score(text: str, marked: dict) -> dict:
    """Counts and shares for one document, plus whether it was measurable.

    ``measured`` is the field that matters. A document with no listed word gets
    zeros, and a caller reading only the scores cannot tell that apart from a
    document that is genuinely neutral.
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
            note = ('The documents are the constraint, not the word list: the '
                    'short ones are where nothing is found, and no lexicon can '
                    'find emotion in "ok" or "sure". A coarser unit of analysis '
                    'would leave fewer unmeasured.')
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
