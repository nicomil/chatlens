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
