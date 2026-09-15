"""Every representation of the text, against the same outcome.

Each page in this tool offers a different way of turning conversations into
numbers: how much was written, lexical indices, a bag of words, relations
between entities. Each looks reasonable in isolation. The question none of them
answers alone is which is worth using, and on the experiment this was built for
the answer was not the one anybody expected — the strongest signal was not in
the text at all, and two of the representations turned out to be measuring
length in disguise.

What makes the comparison mean anything
---------------------------------------
**The same rows and the same folds.** A representation scored on a different
sample, or on a different split, is not being compared to anything. Every
feature set here is fitted on identical training rows and scored on identical
test rows, with whole groups held out so no model is scored on text from a
conversation it has already seen.

**Volume is always in the table.** It is the null hypothesis of text analysis:
longer documents contain more of everything, and a representation that does not
beat "how much was written" has not shown that content matters. It is listed
first so the rest are read against it.

**Absences are stated, not skipped.** A representation that is unavailable —
because its extra is not installed, because no entities were declared — appears
with the reason. Silently comparing three things when the user believes they are
seeing five is worse than showing an empty row.
"""

from __future__ import annotations

# The smallest difference in AUC anybody would act on. A floor, and only a
# floor: the bar a block actually has to clear is the higher of this and the
# smallest difference the design can observe at all, which on one study of a few
# hundred groups is about twice this figure. The experimenter's rule, given when
# the two papers were split: an effect the design and the sample size cannot
# observe is not considered, because a claim below that size is one a referee
# can rightly take apart. See `detectable` in `_paired`.
MEANINGFUL = 0.02

# What a block's verdict can be. The third one is the honest answer in the
# commonest case: on a few hundred groups the interval around a difference in
# AUC is wide, and a rule that must say yes or no says one of them by accident.
YES, NO, UNCLEAR = 'yes', 'no', 'unclear'


def _lexical_columns(rows) -> list:
    """The constructed indices, whichever of them this dataset carries."""
    candidates = ['nlp_sent_analytic_100', 'nlp_sent_clout_100',
                  'nlp_sent_authenticity_100', 'nlp_sent_tone_100',
                  'nlp_sent_sentiment_compound_mean']
    return [c for c in candidates if rows and c in rows[0]]


def build(rows, outcome_column, text_column, group_column='group_uid',
          per_unit=None, key_of=None, narrative_terms=None):
    """Assemble every feature set that can be built from what is here."""
    import numpy as np
    from sklearn.feature_extraction.text import CountVectorizer

    from chatlens.core import outcome as outcome_module
    from chatlens.core import words as words_module

    usable = [r for r in rows
              if outcome_module.as_binary(r.get(outcome_column)) is not None
              and words_module.clean(r.get(text_column)).strip()]
    if len(usable) < 50:
        raise ValueError(f'Only {len(usable)} rows have both text and an '
                         f'outcome: not enough to compare anything on.')

    y = np.array([outcome_module.as_binary(r[outcome_column])
                  for r in usable])
    if len(set(y)) < 2:
        raise ValueError('Every row has the same outcome: nothing to separate.')

    groups = np.array([str(r.get(group_column, '')) for r in usable])
    texts = [words_module.clean(r.get(text_column)) for r in usable]

    sets = []
    volume = np.array([[np.log1p(len(t.split()))] for t in texts], float)
    sets.append({'name': 'How much was written', 'matrix': volume,
                 'features': 1, 'kind': 'volume', 'sparse': False})

    lexical = _lexical_columns(usable)
    if lexical:
        def number(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        sets.append({
            'name': 'Lexical indices',
            'matrix': np.array([[number(r.get(c)) for c in lexical]
                                for r in usable], float),
            'features': len(lexical), 'kind': 'lexical', 'sparse': False})
    else:
        sets.append({'name': 'Lexical indices', 'matrix': None,
                     'kind': 'lexical',
                     'why': 'this dataset carries none of them'})

    # The same tokenisation as the words page, one-letter words included: two
    # rows of this table are meant to be the same representation seen twice,
    # and they were not.
    vectoriser = CountVectorizer(lowercase=True, ngram_range=(1, 2),
                                 min_df=10, binary=True,
                                 token_pattern=words_module.TOKEN_PATTERN)
    try:
        bag = vectoriser.fit_transform(texts)
        # The matrix is kept for one purpose — saying how large the vocabulary
        # is — and `score` does not use it: `from_text` tells it to build the
        # vocabulary again inside each fold, from the training rows alone. See
        # the note on separation in `score`.
        sets.append({'name': 'Words', 'matrix': bag,
                     'features': bag.shape[1], 'kind': 'words',
                     'sparse': True, 'from_text': True})
    except ValueError:
        sets.append({'name': 'Words', 'matrix': None, 'kind': 'words',
                     'why': 'no term appears in ten or more documents'})

    if per_unit is not None and key_of and narrative_terms:
        present = np.array(
            [[float(term in per_unit.get(key_of(r), ()))
              for term in narrative_terms] for r in usable])
        sets.append({'name': 'Narrative relations', 'matrix': present,
                     'features': len(narrative_terms), 'kind': 'narratives',
                     'sparse': False})
    elif per_unit is not None:
        # Extracted, and none of it frequent enough to be a variable. That is
        # an answer about this corpus, not a missing package — it used to be
        # reported as "needs RELATIO" on a machine that had just run it.
        sets.append({'name': 'Narrative relations', 'matrix': None,
                     'kind': 'narratives', 'answered': True,
                     'why': 'no relation appears in enough units to be a '
                            'variable — see the narratives page'})
    else:
        sets.append({'name': 'Narrative relations', 'matrix': None,
                     'kind': 'narratives',
                     'why': 'needs RELATIO and declared entities — '
                            'see the narratives page'})

    sets.append(_emotion_set(texts))

    # `texts` and `volume` travel with the result because the fold does the
    # fitting now: the vocabulary is chosen on the training rows of each fold,
    # and the baseline every block is measured against is length.
    return {'y': y, 'groups': groups, 'sets': sets, 'rows': len(usable),
            'texts': texts, 'volume': volume}


def _emotion_set(texts) -> dict:
    """The NRC categories as a representation of their own.

    They had never been in this table, although the emotions page has scored
    them since it existed — so the one question the table is for, *is this worth
    building on*, could not be asked about them. Ten shares per document, the
    same numbers that page reports.
    """
    import numpy as np

    from chatlens.core import nrc

    if not nrc.available():
        return {'name': 'Emotions', 'matrix': None, 'kind': 'emotions',
                'why': 'needs the NRC lexicon — see the emotions page'}
    try:
        marked = nrc.load()
    except (OSError, ValueError) as exc:
        return {'name': 'Emotions', 'matrix': None, 'kind': 'emotions',
                'why': f'the word list could not be read ({exc})'}

    scored = [nrc.score(text, marked) for text in texts]
    if not any(s['measured'] for s in scored):
        return {'name': 'Emotions', 'matrix': None, 'kind': 'emotions',
                'answered': True,
                'why': 'no document contains a word from the list — see the '
                       'emotions page'}
    matrix = np.array([[s['shares'][c] for c in nrc.CATEGORIES]
                       for s in scored], float)
    return {'name': 'Emotions', 'matrix': matrix,
            'features': len(nrc.CATEGORIES), 'kind': 'emotions',
            'sparse': False}


def _fit_auc(xtr, xte, ytr, yte):
    """One model, one fold, out of sample.

    A ridge throughout, and deliberately not the lasso the words page uses. The
    two have different jobs: selection, for showing a reader which terms carry
    signal, and prediction, for asking whether a block adds anything. Putting a
    lasso here breaks the comparison in a way that is easy to miss — length is a
    control we insist on keeping, and a lasso is entitled to drop it. On the test
    fixture it did exactly that: the penalised baseline sat at 0.500 in every
    fold with the length coefficient at zero, so every difference was inflated
    by half an AUC and had no variance at all. A ridge shrinks and never
    discards, so length survives in both models and the difference is the block.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score

    from chatlens.core.words import _lasso_kwargs

    model = LogisticRegression(C=1.0, solver='liblinear', max_iter=6000,
                               random_state=0,
                               **_lasso_kwargs(False)).fit(xtr, ytr)
    return roc_auc_score(yte, model.predict_proba(xte)[:, 1])


def _scaled(matrix, train, test):
    """A dense block, standardised on the training rows alone.

    Fitted inside the fold, which is the whole of the separation this function
    exists for: nothing the test rows contain may take part in a choice made
    from the data.
    """
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler().fit(matrix[train])
    return scaler.transform(matrix[train]), scaler.transform(matrix[test])


def _vectorise(texts, train, test, min_df=10):
    """The bag of words, with the vocabulary chosen on the training rows.

    Returns None when no term reaches `min_df` inside the training fold, which
    on a small corpus can happen for one fold and not the others.
    """
    import numpy as np
    from sklearn.feature_extraction.text import CountVectorizer

    from chatlens.core import words as words_module

    texts = np.asarray(texts, dtype=object)
    fitted = CountVectorizer(lowercase=True, ngram_range=(1, 2), min_df=min_df,
                             binary=True,
                             token_pattern=words_module.TOKEN_PATTERN)
    try:
        xtr = fitted.fit_transform(texts[train])
    except ValueError:
        return None, None
    return xtr, fitted.transform(texts[test])


def _paired(differences, ratio: float):
    """The mean difference, its standard error, a 95% interval and a p-value.

    The two AUCs being differenced are scored on the *same* folds, so their
    errors are correlated and the paired difference is what has a standard error
    worth quoting — differencing two marginal intervals would throw away most of
    the precision the design has.

    The correction is Nadeau and Bengio (2003): the naive `sd/sqrt(k)`
    understates the truth because the k training sets overlap heavily, and the
    variance has to carry a `n_test/n_train` term as well as `1/k`. On five
    folds that is about one and a half times the naive figure — the difference
    between an interval that excludes zero and one that does not, on exactly the
    comparisons this table exists to make.
    """
    import numpy as np
    from scipy import stats

    d = np.asarray(differences, float)
    k = len(d)
    mean = float(d.mean())
    if k < 2:
        return {'delta': mean, 'se': None, 'ci_low': None, 'ci_high': None,
                'p': None, 'folds_used': k}
    se = float(d.std(ddof=1) * np.sqrt(1.0 / k + ratio))
    if se <= 0:
        # Every fold agreed exactly. Rare, and not evidence of infinite
        # precision: reported as no interval rather than a zero-width one.
        return {'delta': mean, 'se': 0.0, 'ci_low': mean, 'ci_high': mean,
                'p': 0.0 if mean else 1.0, 'folds_used': k, 'detectable': 0.0}
    half = float(stats.t.ppf(0.975, k - 1) * se)
    p = float(2 * (1 - stats.t.cdf(abs(mean) / se, k - 1)))
    # The smallest mean difference whose interval would exclude zero, given this
    # spread across folds: the half-width of the interval. It is what the
    # design can observe, and it is reported so the threshold a block is held
    # to is a number on the page rather than a property of the code.
    return {'delta': mean, 'se': se, 'ci_low': mean - half,
            'ci_high': mean + half, 'p': p, 'folds_used': k,
            'detectable': half}


def _holm(rows) -> None:
    """Holm across the blocks compared against length, in place.

    One family: every block is asked the same question of the same baseline on
    the same folds, so the chance of one of them clearing the bar by luck grows
    with how many are tried. The same correction `ANALYSIS_PLAN.md` already
    applies within a family of hypotheses.
    """
    tested = [row for row in rows if row.get('p') is not None]
    tested.sort(key=lambda row: row['p'])
    total = len(tested)
    running = 0.0
    for index, row in enumerate(tested):
        running = max(running, min(1.0, row['p'] * (total - index)))
        row['q'] = running


def score(assembled, penalty=0.1, folds=5, min_effect=MEANINGFUL):
    """Does a representation add anything to knowing how much was written?

    Not "does it score higher on its own". Every block is put **beside** length
    in the same model and compared with length alone on the same folds, which is
    the question a paper can act on: *the lexical features of the message improve
    the prediction of the outcome even after accounting for the quantity of
    text.* A block that only rediscovers length adds nothing here by
    construction, where a table of separate AUCs left the reader to subtract two
    numbers and hope the difference meant something.

    Each block is measured against a baseline fitted **the same way it is** —
    the dense blocks against length under a ridge, the bag of words against
    length under a lasso — so the difference is the block and never a change of
    estimator. The two baselines are reported separately when they disagree.
    """
    import numpy as np
    from sklearn.model_selection import GroupKFold

    y, groups = assembled['y'], assembled['groups']
    splits = min(folds, len(set(groups)))
    if splits < 2:
        raise ValueError('Every row is in the same group: there is nothing to '
                         'hold out.')
    # Computed once and reused, because the comparison is only a comparison if
    # every representation faces the same test rows.
    folds_ = list(GroupKFold(n_splits=splits).split(
        np.zeros(len(y)), y, groups))
    usable_folds = [(train, test) for train, test in folds_
                    if len(set(y[train])) > 1 and len(set(y[test])) > 1]
    if not usable_folds:
        raise ValueError('No fold holds both outcomes, so nothing can be '
                         'scored out of sample.')
    ratio = float(np.mean([len(test) / len(train)
                          for train, test in usable_folds]))

    volume = assembled['volume']
    texts = assembled.get('texts') or []

    # Length alone, on each fold: the one baseline every block is measured
    # against, and the figure the register quotes.
    base, scaled_volume = [], []
    for train, test in usable_folds:
        vtr, vte = _scaled(volume, train, test)
        scaled_volume.append((vtr, vte))
        base.append(_fit_auc(vtr, vte, y[train], y[test]))

    results = []
    for feature_set in assembled['sets']:
        if feature_set['kind'] == 'volume':
            results.append({**feature_set, 'matrix': None,
                            'auc': float(np.mean(base)),
                            'spread': float(np.std(base)),
                            'alone': float(np.mean(base)),
                            'delta': None, 'beats_volume': None,
                            'verdict': None})
            continue
        if feature_set['matrix'] is None:
            results.append({**feature_set, 'auc': None, 'delta': None,
                            'beats_volume': None, 'verdict': None})
            continue

        sparse = bool(feature_set.get('sparse'))
        from_text = bool(feature_set.get('from_text'))
        matrix = feature_set['matrix']

        alone, nested, differences = [], [], []
        for index, (train, test) in enumerate(usable_folds):
            if from_text:
                block_tr, block_te = _vectorise(texts, train, test)
                if block_tr is None:
                    continue
            else:
                block_tr, block_te = _scaled(matrix, train, test)

            alone.append(_fit_auc(block_tr, block_te, y[train], y[test]))
            vtr, vte = scaled_volume[index]
            with_volume = _stack(vtr, vte, block_tr, block_te, sparse)
            nested.append(_fit_auc(with_volume[0], with_volume[1],
                                   y[train], y[test]))
            differences.append(nested[-1] - base[index])

        if not differences:
            results.append({
                **feature_set, 'matrix': None, 'auc': None, 'delta': None,
                'beats_volume': None, 'verdict': None, 'answered': True,
                'why': 'no fold had enough of it to fit anything'})
            continue

        paired = _paired(differences, ratio)
        results.append({
            **feature_set, 'matrix': None,
            # `auc` stays the nested model's, which is what the table shows and
            # what the register's note quotes.
            'auc': float(np.mean(nested)),
            'spread': float(np.std(nested)),
            'alone': float(np.mean(alone)),
            **paired})

    _holm([row for row in results if row.get('p') is not None])

    baseline = float(np.mean(base))
    for row in results:
        if row['kind'] == 'volume' or row.get('delta') is None:
            continue
        row['verdict'] = _call(row, min_effect)
        row['threshold'] = threshold(row, min_effect)
        row['beats_volume'] = (True if row['verdict'] == YES
                               else False if row['verdict'] == NO else None)

    # Kept for the pages and the register, which have always read them: the
    # headline length figure, and the bar it has to clear. The bar is the higher
    # of length and chance, because length can score below chance and then
    # "beats length" would be cleared by anything at all.
    return {'rows': assembled['rows'], 'folds': len(usable_folds),
            'volume': baseline, 'bar': max(baseline, 0.5),
            'min_effect': min_effect, 'results': results}


def _stack(vtr, vte, block_tr, block_te, sparse):
    """Length beside a block, in the shape the estimator wants.

    The length column arrives standardised and the bag of words does not: its
    columns are already 0/1 on one scale, and centring a sparse matrix would
    make it dense — tens of thousands of columns turning into a full array.
    """
    import numpy as np

    if not sparse:
        return np.hstack([vtr, block_tr]), np.hstack([vte, block_te])
    from scipy import sparse as sp

    return (sp.hstack([sp.csr_matrix(vtr), block_tr], format='csr'),
            sp.hstack([sp.csr_matrix(vte), block_te], format='csr'))


def _call(row, min_effect: float) -> str:
    """Yes, no, or too close to say — from the interval, not the point.

    Both halves have to hold for a yes: the interval must exclude zero *after*
    the correction for how many blocks were tried, and the improvement must be
    at least the smallest one anybody would act on. A no needs the interval to
    rule that improvement out. Anything else is the third answer, which on a few
    hundred groups is the commonest one.
    """
    low, high = row.get('ci_low'), row.get('ci_high')
    q = row.get('q')
    if low is None or high is None:
        return UNCLEAR
    floor = threshold(row, min_effect)
    if low > 0 and row['delta'] >= floor and (q is None or q < 0.05):
        return YES
    if high < floor:
        return NO
    return UNCLEAR


def threshold(row, min_effect: float = MEANINGFUL) -> float:
    """The difference a block has to clear: the declared floor, or what the
    design can observe, whichever is larger.

    An effect below the detectable size would be reported on the strength of an
    interval that cannot tell it from zero, so it is not considered at all.
    """
    return max(min_effect, row.get('detectable') or 0.0)


def verdict(scored) -> str:
    """What the table says, in a sentence, because a table does not say it.

    Three groups now, and the third is the one worth spelling out: a block whose
    interval straddles the threshold has not been shown to add anything and has
    not been shown not to. Calling that a no, as a point-estimate rule had to,
    asserts more than the sample can carry.
    """
    volume = scored['volume']
    if volume is None:
        return ''
    content = [r for r in scored['results']
               if r['kind'] != 'volume' and r['delta'] is not None]
    if not content:
        return ('Only length could be scored, so there is nothing to compare '
                'it against yet.')

    winners = [r for r in content if r['verdict'] == YES]
    unclear = [r for r in content if r['verdict'] == UNCLEAR]
    names = lambda rows: ', '.join(r['name'].lower() for r in rows)
    floor = scored.get('min_effect', MEANINGFUL)

    if winners:
        best = max(winners, key=lambda r: r['delta'])
        sentence = (
            f'{best["name"]} adds the most to knowing how much was written: '
            f'{best["delta"]:+.3f} in AUC, interval {best["ci_low"]:+.3f} to '
            f'{best["ci_high"]:+.3f}, against {volume:.3f} for length alone. '
            f'Adding something: {names(winners)}.')
    else:
        sentence = (
            f'No representation of the content adds anything to how much was '
            f'written, which stands at {volume:.3f} on its own. That is a '
            f'finding rather than a failure: the measurable difference between '
            f'speakers on this corpus is length, and a model built on these '
            f'columns is largely reading it.')

    if unclear:
        sentence += (
            f' Too close to call for {names(unclear)}: the interval covers both '
            f'nothing and more than the smallest difference this design can '
            f'observe (at least {floor:.2f}), so this sample cannot separate '
            f'them from length either way. More groups would, a different '
            f'threshold would not.')
    return sentence
