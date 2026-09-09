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

# Anything at or below this much above volume is not a difference worth
# reading: five folds over a few hundred groups do not resolve it.
MEANINGFUL = 0.02


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

    vectoriser = CountVectorizer(lowercase=True, ngram_range=(1, 2),
                                 min_df=10, binary=True)
    try:
        bag = vectoriser.fit_transform(texts)
        sets.append({'name': 'Words', 'matrix': bag,
                     'features': bag.shape[1], 'kind': 'words',
                     'sparse': True})
    except ValueError:
        sets.append({'name': 'Words', 'matrix': None, 'kind': 'words',
                     'why': 'no term appears in ten or more documents'})

    if per_unit and key_of and narrative_terms:
        present = np.array(
            [[float(term in per_unit.get(key_of(r), ()))
              for term in narrative_terms] for r in usable])
        sets.append({'name': 'Narrative relations', 'matrix': present,
                     'features': len(narrative_terms), 'kind': 'narratives',
                     'sparse': False})
    else:
        sets.append({'name': 'Narrative relations', 'matrix': None,
                     'kind': 'narratives',
                     'why': 'needs RELATIO and declared entities — '
                            'see the narratives page'})

    return {'y': y, 'groups': groups, 'sets': sets, 'rows': len(usable)}


def score(assembled, penalty=0.1, folds=5):
    """One set of folds, every representation scored on it."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupKFold
    from sklearn.preprocessing import StandardScaler

    from chatlens.core.words import _lasso_kwargs

    y, groups = assembled['y'], assembled['groups']
    splits = min(folds, len(set(groups)))
    if splits < 2:
        raise ValueError('Every row is in the same group: there is nothing to '
                         'hold out.')
    # Computed once and reused, because the comparison is only a comparison if
    # every representation faces the same test rows.
    folds_ = list(GroupKFold(n_splits=splits).split(
        np.zeros(len(y)), y, groups))

    results = []
    for feature_set in assembled['sets']:
        if feature_set['matrix'] is None:
            results.append({**feature_set, 'auc': None})
            continue
        matrix = feature_set['matrix']
        aucs = []
        for train, test in folds_:
            if len(set(y[train])) < 2 or len(set(y[test])) < 2:
                continue
            if feature_set['sparse']:
                xtr, xte = matrix[train], matrix[test]
                kwargs = {'C': penalty, **_lasso_kwargs(True)}
            else:
                scaler = StandardScaler().fit(matrix[train])
                xtr = scaler.transform(matrix[train])
                xte = scaler.transform(matrix[test])
                kwargs = {'C': 1.0, **_lasso_kwargs(False)}
            model = LogisticRegression(solver='liblinear', max_iter=6000,
                                       random_state=0,
                                       **kwargs).fit(xtr, y[train])
            aucs.append(roc_auc_score(y[test],
                                      model.predict_proba(xte)[:, 1]))
        results.append({**feature_set, 'matrix': None,
                        'auc': float(np.mean(aucs)) if aucs else None,
                        'spread': float(np.std(aucs)) if aucs else None})

    volume = next((r['auc'] for r in results if r['kind'] == 'volume'), None)
    # The bar is the higher of length and chance. Length can score below 0.5 —
    # on a sample where the longer document is if anything the losing one — and
    # then "beats length" would be cleared by anything at all, which is not the
    # claim the column is making.
    bar = None if volume is None else max(volume, 0.5)
    for row in results:
        if row['auc'] is None or bar is None or row['kind'] == 'volume':
            row['beats_volume'] = None
        else:
            row['beats_volume'] = row['auc'] > bar + MEANINGFUL

    return {'rows': assembled['rows'], 'folds': splits, 'volume': volume,
            'bar': bar, 'results': results}


def verdict(scored) -> str:
    """What the table says, in a sentence, because a table does not say it."""
    volume = scored['volume']
    if volume is None:
        return ''
    content = [r for r in scored['results']
               if r['kind'] != 'volume' and r['auc'] is not None]
    if not content:
        return ('Only volume could be scored, so there is nothing to compare '
                'it against yet.')
    winners = [r for r in content if r['beats_volume']]
    best = max(content, key=lambda r: r['auc'])
    if volume < 0.5:
        winners = [r for r in winners if r['auc'] > 0.5 + MEANINGFUL]
    if not winners:
        return ('No representation of the content beats how much was written. '
                'That is a finding rather than a failure: on this corpus the '
                'measurable difference between speakers is length, and a model '
                'built on any of these columns is largely reading that.')
    names = ', '.join(r['name'].lower() for r in winners)
    return (f'{best["name"]} does best at {best["auc"]:.3f} against '
            f'{volume:.3f} for length alone. Beating length: {names}. The '
            f'others are, on this corpus, mostly measuring how much was '
            f'written.')
