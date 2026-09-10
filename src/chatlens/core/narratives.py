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

Phrases that match nothing declared are clustered by RELATIO itself, and how
many clusters to use is its choice too.

**The extraction is RELATIO's, not ours.** This module prepares the input,
passes the declared entities to the package's own `known_entities` mechanism,
and maps what comes back onto the experiment's keys. It does not reimplement the
method: an approximation of somebody else's published pipeline is not the
pipeline, and results from it could not honestly be attributed to the paper.
That is why the page refuses to run without the package rather than falling back
to something of ours.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import Counter, defaultdict
from pathlib import Path

# A narrative has to appear this often before it is worth testing. Below it the
# estimate is driven by a handful of rows and the multiple-testing correction
# has to carry a family of noise.
MIN_DOCUMENTS = 25


def _default_unit_key(message):
    return (message.get('group_uid'), str(message.get('sender_id_in_group')),
            str(message.get('receiver_id_in_group')))


def keys_for(unit: str):
    """How to key a message and a dataset row, for one unit of analysis.

    Both sides have to agree or the join finds nothing, and they are written in
    different places — the messages carry sender and receiver, the built rows
    carry focal and partner. Returning the pair together is what stops them
    drifting apart, which they had: the narratives page keyed rows by directed
    pair whatever the outcome's unit was, and raised a KeyError the moment an
    experiment declared one per person.
    """
    if unit == 'dyad_directed':
        return (_default_unit_key,
                lambda r: (r['group_uid'], r['focal_id_in_group'],
                           r['partner_id_in_group']))
    if unit == 'dyad':
        def message_key(m):
            a, b = sorted([str(m.get('sender_id_in_group')),
                           str(m.get('receiver_id_in_group'))])
            return (m.get('group_uid'), a, b)

        def row_key(r):
            a, b = sorted([r['focal_id_in_group'], r['partner_id_in_group']])
            return (r['group_uid'], a, b)

        return message_key, row_key
    if unit == 'sender_group':
        return (lambda m: (m.get('group_uid'),
                           str(m.get('sender_id_in_group'))),
                lambda r: (r['group_uid'], r['focal_id_in_group']))
    return (lambda m: (m.get('group_uid'),),
            lambda r: (r['group_uid'],))


_ROUTE = {}


def available() -> tuple:
    """Whether RELATIO can actually run here, and why not when it cannot.

    Returns ``(ready, reason)``.

    The package is **imported**, not looked for, which the rest of this codebase
    deliberately avoids doing. Checking the filesystem is the right test for a
    library that imports cleanly, and RELATIO does not: it pulls
    sentence-transformers, which pulls transformers, which refuses to load
    beside Keras 3. Present and unusable is a state a check that only looks
    cannot see. The import is attempted once and the answer kept.
    """
    from chatlens.core import optional

    if not optional.have('relatio'):
        return False, 'not installed'
    if 'relatio' not in _ROUTE:
        try:
            import relatio  # noqa: F401
            _ROUTE['relatio'] = ''
        except Exception as exc:            # noqa: BLE001 - any failure
            _ROUTE['relatio'] = str(exc).strip().splitlines()[-1][:200]
    broken = _ROUTE['relatio']
    return (not broken), broken


def forget_route() -> None:
    """Ask again next time whether RELATIO can be imported.

    The answer is cached for the life of the process, which is right — the
    import is slow and its failure mode is a dependency clash that will not
    resolve itself. But the page offers a "check again" control, and without
    this that control could only ever repeat the cached answer, so someone who
    had just run the install command was told to run it again.
    """
    _ROUTE.clear()


def extract_with_relatio(messages, entities, model='en_core_web_md',
                         clusters=None, unit_key=None):
    """The published package, on its dependency-parsing path.

    The default is the model the experiment declares and the page tells you to
    install. It used to be `en_core_web_sm`, which nothing asked for and
    nothing checked was present: the screen verified `en_core_web_md` was
    there, put it in its cache key, and then parsed with the other one. The two
    do not agree — on the study this was written for they share 507 relations
    and find 319 and 277 of their own.

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

    # PCA and UMAP reduce the phrase embeddings before clustering, and both
    # need more phrases than dimensions to reduce to — RELATIO asks for 50
    # components, and a small study can easily have fewer distinct phrases than
    # that. Reducing 23 phrases to 50 dimensions is not a thing that can be
    # done, and the package raises rather than skipping it. Turning the two
    # steps off below the threshold keeps the clustering, which is the part
    # being used here; it is the same method on a corpus that does not need
    # reducing.
    phrases = {p for row in processed
               for key in ('ARG0', 'ARG1')
               for p in [str(row.get(key) or '').strip()] if p}
    reduce = len(phrases) > 60

    model_kwargs = dict(
        clustering='kmeans', PCA=reduce, UMAP=reduce,
        roles_considered=['ARG0', 'B-V', 'B-ARGM-NEG', 'ARG1'],
        roles_with_known_entities=['ARG0', 'ARG1'],
        known_entities=list(entities or ()),
        assignment_to_known_entities='character_matching',
        roles_with_unknown_entities=['ARG0', 'ARG1'])
    narrative_model = NarrativeModel(**model_kwargs)
    try:
        narrative_model.fit(processed)
    except ValueError as exc:
        raise ValueError(
            f'RELATIO could not cluster this corpus: {exc}. It has '
            f'{len(phrases)} distinct phrases, which may be too few for the '
            f'package to group.') from None
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


# --- remembering an extraction -------------------------------------------

# Bumped when a change here would make an old file wrong. It is part of the
# key, so a stale file is not read: it is simply never looked for again.
CACHE_FORMAT = 1

_MEMO: dict = {}
_MEMO_LOCK = threading.Lock()


def cache_dir():
    from . import config

    return config.OUTPUT_DIR / 'cache' / 'narratives'


def fingerprint(messages, entities, unit: str, model: str) -> str:
    """What the extraction depends on, in sixteen bytes.

    The messages themselves rather than the file they came from: a re-run
    writes a new file with the same name and, more to the point, the same
    contents, and paying a hundred seconds again for a file whose bytes did not
    change is the thing being avoided. Only the fields the extraction reads —
    the text, and the three that decide which unit a message belongs to.
    """
    digest = hashlib.blake2b(digest_size=16)
    header = f'{CACHE_FORMAT}|{unit}|{model}|{",".join(entities or ())}'
    digest.update(header.encode('utf-8'))
    for message in messages:
        for field in ('group_uid', 'sender_id_in_group',
                      'receiver_id_in_group', 'body'):
            digest.update(str(message.get(field) or '').encode('utf-8'))
            digest.update(b'\x1f')
        digest.update(b'\x1e')
    return digest.hexdigest()


def _load(path: Path):
    """The stored extraction, or None if there is not a usable one."""
    try:
        stored = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        # Absent, half-written, or from a version that wrote something else.
        # All three mean the same thing here: compute it again.
        return None
    try:
        return {tuple(key): {tuple(triple) for triple in triples}
                for key, triples in stored['per_unit']}
    except (KeyError, TypeError, ValueError):
        return None


def _store(path: Path, per_unit) -> None:
    """Write it, or carry on without. A cache that cannot be written is slow,
    not broken, and a read-only workspace is somebody's deliberate choice."""
    payload = {'format': CACHE_FORMAT,
               'per_unit': [[list(key), sorted(triples)]
                            for key, triples in sorted(per_unit.items())]}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Through a neighbour and then renamed: two dashboard requests can ask
        # for this at once, and half a file read back as none at all would be
        # a hundred seconds paid twice.
        temporary = path.with_suffix('.part')
        temporary.write_text(json.dumps(payload), encoding='utf-8')
        temporary.replace(path)
    except OSError:
        pass


def extracted(messages, entities, unit: str = 'dyad_directed',
              model: str = 'en_core_web_md'):
    """`extract_with_relatio`, remembered.

    The extraction is the expensive thing in this tool that is not paid for in
    money: a hundred and thirteen seconds on eight thousand messages. It was
    being run twice per visit — the relations and the comparison each did their
    own — and again after every restart of the dashboard, because the only
    memory of it was a dictionary in the process that died with it.

    So it is remembered twice over: in this process, and in the workspace under
    `output/cache/`. The second is what survives a restart, and what travels
    when a study is exported, so whoever opens it does not pay the hundred
    seconds either.
    """
    key = fingerprint(messages, entities, unit, model)
    with _MEMO_LOCK:
        if key in _MEMO:
            return _MEMO[key]

    path = cache_dir() / f'{key}.json'
    per_unit = _load(path)
    if per_unit is None:
        message_key, _row_key = keys_for(unit)
        per_unit = extract_with_relatio(messages, entities, model=model,
                                        unit_key=message_key)
        _store(path, per_unit)

    with _MEMO_LOCK:
        _MEMO[key] = per_unit
    return per_unit


def forget() -> None:
    """Drop what this process remembers. For tests, which change the corpus
    under it far faster than any user does."""
    with _MEMO_LOCK:
        _MEMO.clear()


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

    from chatlens.core import outcome as outcome_module

    usable = []
    for row in rows:
        if outcome_module.as_binary(row.get(outcome_column)) is None:
            continue
        usable.append(row)
    if len(usable) < 50:
        raise ValueError(f'Only {len(usable)} rows carry the outcome. There is '
                         f'not enough here to test anything.')

    y = np.array([outcome_module.as_binary(r[outcome_column])
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
