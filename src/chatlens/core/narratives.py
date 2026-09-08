"""What was said, read as relations rather than as words.

RELATIO (Ash, Gauthier and Widmer, *Political Analysis* 2024) reads a corpus as
(agent, verb, patient) triples: who does what to whom. Two properties make that
fit a chat corpus where topic modelling does not.

**Triples come out of a sentence**, so nothing has to be generalisable at the
level of a document. A topic model is asked for one label that describes a whole
conversation and, on a corpus where every group performs the same task, declines
for most of them. A relation needs only a clause.

**A relation has a direction**, which a bag of words cannot represent. In a game
about who supports whom, "I support you" and "I support the other player" are
opposite moves containing the same words, and any model built on word counts
scores them identically.

On the experiment this was built for, this was the only representation of
content that survived a control for how much was written, where lexical indices
and a bag-of-words lasso did not.

Entities are declared, not discovered
-------------------------------------
The `[narratives]` section of the experiment names the entities:

    [narratives]
    entities = ["i", "you", "we", "yellow", "orange", "purple"]

This is not a convenience. Left to be clustered by similarity, "i" and "you"
land together — they are used in the same positions and mean the same kind of
thing — and the speaker and the person spoken to stop being distinguishable,
which in a game about who supports whom erases the entire question. Nothing but
the experiment can know which words are its participants.

Phrases that match nothing declared are kept under their head word, which is a
crude stand-in for RELATIO's clustering. Where the full package is installed it
is used instead and does the clustering properly.
"""

from __future__ import annotations

from collections import Counter, defaultdict

SUBJECT = {'nsubj', 'nsubjpass', 'csubj'}
# `acomp` is here because entities are often adjectives. Participants named by
# colour are tagged ADJ, so "I am orange" and "I back purple" put the entity in
# an adjectival complement rather than a direct object, and without this the
# relations that identify who someone is are silently never extracted.
OBJECT = {'dobj', 'dative', 'attr', 'oprd', 'pobj', 'acomp'}

# A narrative has to appear this often before it is worth testing. Below it the
# estimate is driven by a handful of rows and the multiple-testing correction
# has to carry a family of noise.
MIN_DOCUMENTS = 25


def _head(token, entities) -> str:
    """The argument, as a declared entity when it names one.

    Matching is by token rather than by whole phrase: "my favourite colour is
    purple" names purple, and requiring the phrase to *be* "purple" would miss
    it. The head word is the fallback, so an unmatched phrase still carries
    something rather than being dropped.
    """
    for child in token.subtree:
        lemma = child.lemma_.lower()
        if lemma in entities:
            return lemma
    return token.lemma_.lower()


def triples(doc, entities):
    """(agent, verb, patient) for every clause that has all three."""
    found = []
    for token in doc:
        if token.pos_ not in ('VERB', 'AUX'):
            continue
        subjects = [c for c in token.children if c.dep_ in SUBJECT]
        objects = [c for c in token.children if c.dep_ in OBJECT]
        objects += [g for c in token.children if c.dep_ == 'prep'
                    for g in c.children if g.dep_ == 'pobj']
        if not subjects or not objects:
            continue
        negated = any(c.dep_ == 'neg' for c in token.children)
        verb = ('not ' if negated else '') + token.lemma_.lower()
        for subject in subjects:
            for obj in objects:
                found.append((_head(subject, entities), verb,
                              _head(obj, entities)))
    return found


def _default_unit_key(message):
    return (message.get('group_uid'), str(message.get('sender_id_in_group')),
            str(message.get('receiver_id_in_group')))


_ROUTE = {}


def available_route(prefer_package=True) -> tuple:
    """Which implementation this machine can run, and why not the other.

    Returns ``(route, note)``. The two answer the same question and differ in
    what happens to the phrases that are *not* declared entities: the light
    route keeps each under its head word, the package clusters them and chooses
    how many clusters to use. On a corpus with three known participants that
    changed nothing; on one with many entities and no list of them it is the
    whole value.

    RELATIO is **imported** rather than looked for, which the rest of this
    codebase deliberately avoids doing. Checking the filesystem is the right
    test for a library that imports cleanly, and RELATIO does not: it pulls
    sentence-transformers, which pulls transformers, which refuses to load
    beside Keras 3. The package is then present and unusable, and a check that
    only looked would send the page down a route that raises. The import is
    attempted once and the answer kept.
    """
    from chatlens.core import optional

    if prefer_package and optional.have('relatio'):
        if 'relatio' not in _ROUTE:
            try:
                import relatio  # noqa: F401
                _ROUTE['relatio'] = ''
            except Exception as exc:            # noqa: BLE001 - any failure
                _ROUTE['relatio'] = str(exc).strip().splitlines()[-1][:200]
        broken = _ROUTE['relatio']
        if not broken:
            return 'relatio', ''
        if optional.have('spacy'):
            return 'spacy', (f'RELATIO is installed but cannot be imported '
                             f'here ({broken}), so the lighter route was used.')
        return '', broken
    if optional.have('spacy'):
        return 'spacy', ''
    return '', ''


def extract_with_relatio(messages, entities, model='en_core_web_sm',
                         clusters=None, unit_key=None):
    """The published package, on its dependency-parsing path.

    Its semantic-role path needs AllenNLP, which caps Python at 3.10; this one
    needs none of it. The entities are passed as ``known_entities`` and matched
    directly, which is the package's own mechanism for exactly this case — and
    necessary, because left to its clustering it put "i" and "you" in one group
    and the narratives came back as "i | support | i".
    """
    import pandas as pd
    from relatio import Preprocessor
    from relatio.narrative_models import NarrativeModel

    unit_key = unit_key or _default_unit_key
    kept = [(i, m) for i, m in enumerate(messages)
            if str(m.get('body') or '').strip()]
    frame = pd.DataFrame({'id': [i for i, _m in kept],
                          'doc': [str(m['body']).strip() for _i, m in kept]})

    preprocessor = Preprocessor(spacy_model=model, remove_punctuation=True,
                                remove_digits=False, lowercase=True,
                                lemmatize=True, stop_words=[], n_process=1,
                                batch_size=200)
    sentences = preprocessor.split_into_sentences(frame)
    index, roles = preprocessor.extract_svos(sentences['sentence'],
                                             expand_nouns=True,
                                             only_triplets=False)
    processed = preprocessor.process_roles(roles, max_length=50)

    model_kwargs = dict(
        clustering='kmeans', PCA=True, UMAP=True,
        roles_considered=['ARG0', 'B-V', 'B-ARGM-NEG', 'ARG1'],
        roles_with_known_entities=['ARG0', 'ARG1'],
        known_entities=list(entities or ()),
        assignment_to_known_entities='character_matching',
        roles_with_unknown_entities=['ARG0', 'ARG1'])
    narrative_model = NarrativeModel(**model_kwargs)
    narrative_model.fit(processed)
    predicted = narrative_model.predict(processed)

    doc_ids = sentences['id'].tolist()
    per_unit = defaultdict(set)
    for position, narrative in zip(index, predicted):
        agent = str(narrative.get('ARG0') or '').strip()
        verb = str(narrative.get('B-V') or '').strip()
        patient = str(narrative.get('ARG1') or '').strip()
        if not (agent and verb and patient):
            continue
        if narrative.get('B-ARGM-NEG'):
            verb = 'not ' + verb
        message = messages[doc_ids[position]]
        per_unit[unit_key(message)].add((agent, verb, patient))
    return dict(per_unit)


def extract(messages, entities, model='en_core_web_md', unit_key=None):
    """Narratives per unit of analysis, from the messages.

    ``unit_key`` maps a message to the row it belongs to; the default is the
    directed pair, which is where a relation between two people lives.
    """
    import spacy

    nlp = spacy.load(model)
    entities = set(entities or ())
    if unit_key is None:
        def unit_key(m):
            return (m.get('group_uid'), str(m.get('sender_id_in_group')),
                    str(m.get('receiver_id_in_group')))

    texts = [str(m.get('body') or '').strip() for m in messages]
    per_unit = defaultdict(set)
    for message, doc in zip(messages, nlp.pipe(texts, batch_size=256)):
        for relation in triples(doc, entities):
            per_unit[unit_key(message)].add(relation)
    return dict(per_unit)


def frequencies(per_unit) -> Counter:
    return Counter(n for narratives in per_unit.values() for n in narratives)


def which_matter(per_unit, rows, outcome_column, key_of, words_of,
                 group_of, min_documents=MIN_DOCUMENTS):
    """Which narratives go with the outcome, holding length constant.

    Every narrative common enough to test is tested, and the p-values carry a
    Benjamini-Hochberg correction across that whole family. Reporting the one
    that came out significant, out of dozens tried, is how a list of nothing
    becomes a finding.

    **Length is in the model rather than subset away.** Whoever writes more has
    more chances to contain any given relation — on the corpus this was built
    for, the count of relations a speaker used correlated 0.51 with how much
    they wrote. Restricting to speakers who wrote comparable amounts answers the
    question on a fraction of the data; putting log words in the regression
    answers it on all of it.

    Standard errors are clustered by group, because several rows come from the
    same conversation.
    """
    import numpy as np
    import statsmodels.api as sm

    usable = []
    for row in rows:
        raw = str(row.get(outcome_column, '')).strip()
        if raw not in ('0', '1', 'True', 'False', 'true', 'false'):
            continue
        usable.append(row)
    if len(usable) < 50:
        raise ValueError(f'Only {len(usable)} rows carry the outcome. There is '
                         f'not enough here to test anything.')

    y = np.array([int(str(r[outcome_column]).strip() in ('1', 'True', 'true'))
                  for r in usable])
    if len(set(y)) < 2:
        raise ValueError('Every row has the same outcome: nothing to separate.')

    volume = np.array([[np.log1p(words_of(r))] for r in usable], float)
    clusters = np.unique(np.array([str(group_of(r)) for r in usable]),
                         return_inverse=True)[1]
    keys = [key_of(r) for r in usable]

    counts = Counter()
    for key in keys:
        for narrative in per_unit.get(key, ()):
            counts[narrative] += 1
    testable = [n for n, c in counts.items() if c >= min_documents]

    results = []
    for narrative in testable:
        present = np.array([[float(narrative in per_unit.get(k, ()))]
                            for k in keys])
        if len(set(present.ravel())) < 2:
            continue
        design = np.hstack([present, volume, np.ones((len(y), 1))])
        try:
            model = sm.Logit(y, design).fit(
                disp=0, cov_type='cluster', cov_kwds={'groups': clusters})
        except Exception:        # separation, singular design, no convergence
            continue
        results.append({
            'narrative': narrative,
            'documents': counts[narrative],
            'coef': float(model.params[0]),
            'odds': float(np.exp(model.params[0])),
            'p': float(model.pvalues[0]),
        })

    results.sort(key=lambda r: r['p'])
    total = len(results)
    for rank, row in enumerate(results, start=1):
        row['q'] = min(1.0, row['p'] * total / rank)
    return {'tested': total, 'candidates': len(counts), 'rows': len(usable),
            'results': results,
            'survivors': sum(1 for r in results if r['q'] < 0.10)}
