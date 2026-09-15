"""Which words go with the outcome — the look before the statistics.

This is deliberately the crude analysis. A penalised logistic regression over
unigrams and bigrams, the surviving terms drawn as a cloud and listed in a
table. It is the text equivalent of plotting the raw points before fitting
anything: quick, wrong in known ways, and far better than starting from a model.

Three things it is careful about, because the easy version misleads in three
ways.

**Selection is not inference.** A lasso picks variables and shrinks them, so the
coefficients that survive are biased by having been picked. A term's presence
says it carries signal; its size says how much the penalty let it keep. Nothing
here is an estimate.

**Groups are not independent.** Several rows come from the same conversation, so
cross-validation splits by group and never by row, or the model is scored on
text it has already seen from the same table.

**Length is a confound, not a nuisance.** Longer documents contain more of every
word, so an unadjusted bag of words partly rediscovers who typed more. Every
result is reported beside a length-only baseline, and where the words do not
beat it, that is the finding.
"""

from __future__ import annotations

import re

from . import tokens

# The penalty is the parameter worth moving: watching terms appear and disappear
# says how fragile the selection is, which a single table hides. Bounded because
# it arrives from a browser, and because outside this range it either keeps
# everything or nothing.
PENALTIES = (0.02, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0)
NGRAMS = {'unigrams': (1, 1), 'bigrams': (2, 2), 'both': (1, 2)}
MIN_DF = (3, 5, 10, 20, 50)

# scikit-learn's default is `(?u)\b\w\w+\b`, which requires two characters and
# therefore throws away every one-letter word before the model ever sees it.
# In a chat corpus those are not noise: "i" and "u" are the two people in the
# conversation, and in a game about who supports whom they are the words that
# say who. On the study this was written for, `["i support you", "u and i"]`
# produced a vocabulary of {and, support, you} — the pronouns gone, the verb
# left standing on its own.
#
# `terms` rather than `words`, which is the one place in the project where the
# difference matters: a bag of words should see `60` and `40`, because in a
# bargaining corpus those are things people say. The dictionary measures must
# not, because LIWC does not count numerals. See `core/tokens.py`.
TOKEN_PATTERN = tokens.TERM_PATTERN


def _lasso_kwargs(l1: bool) -> dict:
    """How to ask this scikit-learn for an L1 or an L2 penalty.

    The two spellings are not interchangeable and the wrong one fails silently.
    Up to 1.7 the penalty is chosen with `penalty="l1"`, and `l1_ratio` is
    ignored unless the penalty is elasticnet — so passing `l1_ratio=1.0` alone
    fits a *ridge* over the whole vocabulary, keeps every term, and looks like a
    working lasso until you notice nothing was dropped. From 1.8 `penalty` is
    deprecated and `l1_ratio` is the parameter. Both spellings exist in the wild
    and this tool is installed against whichever is current.
    """
    from sklearn import __version__ as version

    try:
        recent = tuple(int(part) for part in version.split('.')[:2]) >= (1, 8)
    except ValueError:
        recent = True
    if recent:
        return {'l1_ratio': 1.0 if l1 else 0.0}
    return {'penalty': 'l1' if l1 else 'l2'}


# The speaker prefix the transcripts carry, in the three shapes the adapters
# and the pipeline write it: `Yellow->Orange:`, `Yellow -> Orange:` and
# `Yellow to Orange:`, with seat numbers in place of colours where the export
# has no colours. Neither name may contain a colon, which is what keeps the
# pattern from reaching across one.
SPEAKER_PREFIX = re.compile(r'^\s*[^\s:]+\s*(?:->|→|\sto\s)\s*[^\s:]+\s*:\s*')


def clean(text: str) -> str:
    """Drop the "Colour -> Colour:" prefix some transcripts carry per line.

    It is structure rather than speech, and left in it is learnt as if it were
    content — the names of the participants become the strongest predictors of
    what the participants did.

    Only that prefix. This used to cut each line at its first colon whatever
    stood before it, and the same function is applied to plain message columns
    as well as to transcripts: `"ratio is 2:1 and i think: yes"` came back as
    `"1 and i think: yes"`, so a bargaining corpus lost the words before every
    number it argued about. A line with no speaker prefix is now returned as it
    is.
    """
    stripped = ' '.join(SPEAKER_PREFIX.sub('', line)
                        for line in (text or '').splitlines())
    # Whitespace is collapsed so the result is predictable. Neither the
    # tokeniser nor a word count cares, but a function whose output depends on
    # how many lines happened to be joined is one that tests have to guess at.
    return ' '.join(stripped.split())


def fit(rows, text_column, outcome_column, group_column='group_uid',
        ngrams='both', min_df=10, penalty=0.1):
    """Fit the lasso and return everything the page needs to draw.

    Raises ValueError with something sayable when the data cannot support it:
    a page that renders an empty cloud teaches nothing.
    """
    import numpy as np
    from sklearn.feature_extraction.text import CountVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupKFold

    from chatlens.core import outcome as outcome_module

    usable = [r for r in rows
              if outcome_module.as_binary(r.get(outcome_column)) is not None
              and clean(r.get(text_column)).strip()]
    if len(usable) < 50:
        raise ValueError(f'Only {len(usable)} rows have both text and an '
                         f'outcome. There is not enough here to fit anything.')

    y = np.array([outcome_module.as_binary(r[outcome_column])
                  for r in usable])
    if len(set(y)) < 2:
        raise ValueError('Every row has the same outcome: nothing to separate.')

    texts = [clean(r.get(text_column)) for r in usable]
    groups = np.array([str(r.get(group_column, '')) for r in usable])

    vectoriser = CountVectorizer(lowercase=True, ngram_range=NGRAMS[ngrams],
                                 min_df=min_df, binary=True,
                                 token_pattern=TOKEN_PATTERN)
    try:
        X = vectoriser.fit_transform(texts)
    except ValueError as exc:
        raise ValueError(f'No term appears in at least {min_df} documents. '
                         f'Lower the minimum frequency.') from exc
    terms = np.array(vectoriser.get_feature_names_out())

    # Seeded, and not incidentally. liblinear picks coordinates at random, and
    # among terms that carry the same information a lasso keeps an arbitrary
    # one — so without a seed the same data and the same settings produce a
    # different list of words each time the page is drawn. Moving a control back
    # to where it was has to give back what it gave before.
    model = LogisticRegression(C=penalty, solver='liblinear', max_iter=6000,
                               random_state=0,
                               **_lasso_kwargs(True)).fit(X, y)
    coefficients = model.coef_[0]
    kept = np.flatnonzero(coefficients)

    counts = np.asarray(X.sum(axis=0)).ravel()
    selected = [{'term': terms[i], 'coef': float(coefficients[i]),
                 'documents': int(counts[i])}
                for i in kept]
    selected.sort(key=lambda t: -abs(t['coef']))

    length = np.array([[len(t.split())] for t in texts], float)
    as_array = np.array(texts, dtype=object)

    def scored(matrix, sparse):
        """Out-of-sample AUC with whole groups held out.

        For the bag of words the vocabulary is chosen **inside** each fold, from
        the training rows alone — `matrix` is then used for nothing but its
        shape. The list of coefficients above is fitted on every row on purpose:
        it is a description of this corpus, not an estimate, and the reader is
        looking at which terms survive the penalty here. The AUC is the
        estimate, and an estimate may not see the rows it is scored on.
        """
        splits = min(5, len(set(groups)))
        if splits < 2:
            return None
        aucs = []
        for train, test in GroupKFold(n_splits=splits).split(matrix, y, groups):
            if len(set(y[train])) < 2 or len(set(y[test])) < 2:
                continue
            if sparse:
                inside = CountVectorizer(lowercase=True,
                                         ngram_range=NGRAMS[ngrams],
                                         min_df=min_df, binary=True,
                                         token_pattern=TOKEN_PATTERN)
                try:
                    xtr = inside.fit_transform(as_array[train])
                except ValueError:
                    # No term frequent enough among the training rows of this
                    # fold. It happens on a small corpus, and the fold is
                    # skipped rather than scored on an empty design.
                    continue
                xte = inside.transform(as_array[test])
            else:
                xtr, xte = matrix[train], matrix[test]
            fitted = LogisticRegression(
                C=penalty if sparse else 1.0, solver='liblinear',
                max_iter=6000, random_state=0,
                **_lasso_kwargs(sparse)).fit(xtr, y[train])
            aucs.append(roc_auc_score(y[test],
                                      fitted.predict_proba(xte)[:, 1]))
        return float(np.mean(aucs)) if aucs else None

    return {
        'penalty_did_nothing': len(selected) == len(terms),
        'rows': len(usable),
        'positive': int(y.sum()),
        'share': float(y.mean()),
        'groups': len(set(groups)),
        'vocabulary': len(terms),
        'kept': selected,
        'penalty': penalty,
        'min_df': min_df,
        'ngrams': ngrams,
        'auc_words': scored(X, True),
        'auc_length': scored(length, False),
    }


def _weights(selected, positive: bool) -> dict:
    weights = {t['term']: abs(t['coef']) for t in selected
               if (t['coef'] > 0) == positive}
    if not weights:
        raise ValueError('No terms in that direction survived the penalty.')
    return weights


def _lay_out(weights, colour: str, background=None):
    """The layout itself, shared by both outputs.

    `random_state=0` is not decoration: without it the same coefficients draw a
    different picture on every request, and a figure that moves when nothing
    changed cannot be compared with the one in yesterday's notes.
    """
    from wordcloud import WordCloud

    return WordCloud(
        width=1600, height=900,
        background_color=background, mode='RGB' if background else 'RGBA',
        color_func=lambda *a, **k: colour, prefer_horizontal=0.9,
        relative_scaling=0.6,
        # The bigrams are already terms of the model; letting the library
        # invent its own on top would draw phrases nothing was fitted on.
        collocations=False, random_state=0,
    ).generate_from_frequencies(weights)


# The placeholder the layout is coloured with before the colour is handed over
# to the stylesheet. Any value would do as long as nothing else in the document
# uses it.
_INK = '#010203'


def _text_box(font, word):
    """Width, and the offsets that put the baseline where the layout put it.

    Pillow moved this API; the private call is the one the layout itself used,
    so it is tried first and the public one is the fallback.
    """
    try:
        (size_x, _size_y), (offset_x, offset_y) = font.font.getsize(word)
    except AttributeError:  # pragma: no cover - depends on the Pillow version
        left, top, right, _bottom = font.getbbox(word)
        size_x, offset_x, offset_y = right, left, top
    ascent, _descent = font.getmetrics()
    return size_x - offset_x, -offset_x, ascent - offset_y


def cloud_svg(selected, positive: bool) -> str:
    """The cloud as real text in real SVG, coloured by the page.

    The page used to show a matplotlib raster on a white canvas: a bright slab
    in the middle of a dark interface, fixed at the colours chosen when it was
    drawn, reflowing the page when it finally arrived because it carried no
    dimensions. This is vector text instead — it inherits the theme through a
    custom property, scales, and can be selected and searched like text.

    Every word carries the width the layout measured for it, as `textLength`.
    Without that the figure depends on the browser having the font the layout
    was computed with, and it does not: the library's own SVG export embeds
    that font, Chrome lays the text out before it arrives, and the words
    overlap. Fixing the width makes the drawing correct in whatever font is
    used to render it.

    Two clouds rather than one coloured both ways: a reader looking at a single
    image cannot tell a large word that predicts the outcome from a large word
    that predicts its absence, and the distinction is the whole point.
    """
    from xml.sax.saxutils import escape

    from PIL import Image, ImageFont

    cloud = _lay_out(_weights(selected, positive), _INK)
    scale = getattr(cloud, 'scale', 1)
    width, height = cloud.width * scale, cloud.height * scale

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-labelledby="cloud-title">',
        # A figure with `role="img"` and no accessible name is announced as
        # "image" and nothing else. The words themselves are in the SVG and are
        # read out, which is a list of terms with no indication of what they are.
        f'<title id="cloud-title">The terms that go '
        f'{"with" if positive else "against"} the outcome, sized by '
        f'coefficient</title>',
        # The colour is handed to the stylesheet: that is what makes the figure
        # follow the light and the dark theme without being redrawn.
        '<style>text{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;'
        'fill:var(--cloud-ink,currentColor)}</style>',
    ]

    for (word, _count), font_size, (y, x), orientation, _colour in cloud.layout_:
        size = int(font_size * scale)
        font = ImageFont.truetype(cloud.font_path, size)
        text_width, min_x, max_y = _text_box(font, word)
        left, top = x * scale, y * scale
        if orientation == Image.ROTATE_90:
            transform = f'translate({left + max_y},{top + text_width}) rotate(-90)'
        else:
            transform = f'translate({left + min_x},{top + max_y})'
        parts.append(
            f'<text transform="{transform}" font-size="{size}" '
            f'textLength="{text_width}" lengthAdjust="spacingAndGlyphs">'
            f'{escape(word)}</text>')

    parts.append('</svg>')
    return ''.join(parts)


def cloud_image(selected, positive: bool, fmt: str = 'png',
                colour: str = None, background: str = 'white') -> bytes:
    """The same cloud as a file to keep: PNG for a slide, SVG for a paper.

    This one stays on a white ground by default, because it leaves the
    interface: a figure destined for a document should not carry the colours of
    the screen it was exported from.
    """
    import io

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    if colour is None:
        colour = '#2f4c8c' if positive else '#a33a2a'
    cloud = _lay_out(_weights(selected, positive), colour, background=background)

    figure, axes = plt.subplots(figsize=(11, 6.2), dpi=170)
    axes.imshow(cloud, interpolation='bilinear')
    axes.axis('off')
    figure.tight_layout(pad=0.2)
    buffer = io.BytesIO()
    figure.savefig(buffer, format=fmt, bbox_inches='tight',
                   facecolor=background or 'none')
    plt.close(figure)
    return buffer.getvalue()


def table_csv(selected, params=None) -> str:
    """The coefficients, for a spreadsheet or an appendix.

    The settings go in the file, named as scikit-learn names them. The page
    calls the control "how selective" and the value it passes is `C`, the
    *inverse* of the regularisation strength — so a file whose column said
    `penalty` told whoever refits this in R or Stata to turn the knob the wrong
    way. Here it is `inverse_penalty_C`, which is what it is.
    """
    import csv
    import io

    params = params or {}
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    header = ['term', 'words_in_term', 'coefficient', 'direction', 'documents']
    settings = [key for key in ('inverse_penalty_C', 'min_df', 'ngrams')
                if key in params]
    writer.writerow(header + settings)
    for term in selected:
        writer.writerow([term['term'], len(term['term'].split()),
                         f'{term["coef"]:.6f}',
                         'outcome' if term['coef'] > 0 else 'not outcome',
                         term['documents']]
                        + [params[key] for key in settings])
    return buffer.getvalue()
