"""Building one study's datasets out of a run that covered them all.

`core/studies.py` says which rows belong to which sample. This builds, for one
of those samples, the same two tables the pipeline writes — and it has to,
because three of the columns in them are properties of the sample rather than of
the participant:

    nlp_*_analytic_z / _100      z-scores and the 0-100 scale
    nlp_*_clout_z / _100         standardised against the units that were in
    nlp_*_authenticity_z / _100  the analysis, by design: see
    nlp_*_tone_z / _100          text_metrics.standardize

Everything else is absolute. `analytic_cdi`, `clout_raw`, the word counts, the
sentiment, the rubric's 0-100 ratings and the topics mean the same thing whoever
else is in the file. So a study's dataset is not a re-run of the analysis: it is
the measures stage re-applied to a subset, with the paid columns carried across.

**Why the measures stage is re-run rather than the columns re-standardised in
place.** In the two final tables a unit's values are *repeated* — `nlp_group_*`
appears on each of a group's three participants, `nlp_dyad_*` on both directions
of a pair. Taking the mean and the deviation over those rows would weight each
group by how many rows it happens to have, which is not what the pipeline did.
Re-running `aggregate_all` on the study's messages reproduces the original
semantics exactly, and on this corpus it costs a couple of seconds: no key, no
network, no model.

What is *not* re-run is anything that costs money. The rubric ratings and the
topic assignments are looked up from the pooled dataset by row key and copied
across, so a study's tables carry them without a single call.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import aggregate as agg
from . import config, optional, studies, tables

FOLDER = 'studies'

# The two tables a study gets, and the key that identifies one of their rows.
# Both are what the adapter wrote and what the pipeline grafts onto.
ROW_KEYS = {
    'chat_by_partner': ('group_uid', 'focal_id_in_group', 'partner_id_in_group'),
    'chat_aggregated': ('group_uid', 'focal_id_in_group'),
}

# Copied from the pooled dataset rather than recomputed: these cost money, and
# they do not depend on who else is in the sample. A rubric rating is a 0-100
# judgement of one transcript; a topic is a label attached to one document.
CARRIED = ('_llm_', '_topic')


class StudyBuildError(RuntimeError):
    """The study's tables cannot be built, and why."""


def carried_columns(rows) -> list:
    """The sample-independent columns present in a built dataset."""
    if not rows:
        return []
    return [column for column in rows[0]
            if any(marker in column for marker in CARRIED)]


def directory(study, root: Path | None = None) -> Path:
    """Where one study's replication package lives.

    Under `output/studies/<slug>/`, and deliberately **not** in
    `output/datasets/`: the Stata do-files find their input by globbing that
    folder for `*_chat_by_partner_nlp.csv` and abort when the glob matches more
    than one file. Two studies written beside the pooled dataset would break
    `01_prepare.do` for all three.
    """
    base = Path(root) if root else config.OUTPUT_DIR / FOLDER
    return base / study.slug


def build(study, stem: str, messages=None) -> dict:
    """One study's two tables, in memory, plus what was left out and why."""
    merged = config.MERGED_DIR
    messages_path = merged / f'{stem}_messages_long.csv'
    if messages is None:
        if not messages_path.is_file():
            raise StudyBuildError(
                f'No {messages_path.name} in {merged}: run the merge first.')
        messages = tables.read(messages_path)

    mine = studies.rows_for(study, messages)
    if not mine:
        raise StudyBuildError(
            f'No message belongs to "{study.slug}". It selects '
            f'{", ".join(study.treatments)}; the corpus carries '
            f'{", ".join(sorted({str(m.get("treatment") or "(blank)") for m in messages}))}.')

    # The measures, on this sample alone. This is the whole point: standardize()
    # is called inside aggregate_level over exactly these units.
    features = agg.aggregate_all(agg.analyze_messages(mine))

    built, notes = {}, []
    for key, row_key in ROW_KEYS.items():
        source = merged / f'{stem}_{key}.csv'
        if not source.is_file():
            raise StudyBuildError(f'No {source.name} in {merged}.')
        # Selected on each table's own treatment, **not** on the groups that
        # appear in the messages. A triad that exchanged nothing at all leaves
        # no message row, so taking the groups from the corpus dropped it from
        # the study — which is the very mistake the participation page exists to
        # expose: a sample conditional on having spoken. On this experiment it
        # was six triads, silent and randomised like every other.
        #
        # A row with no group is left out whatever its treatment says: it has no
        # partner and no conversation, so it is in no comparison.
        rows = [row for row in tables.read(source)
                if str(row.get('group_uid') or '').strip()
                and study.holds(row.get('treatment'))]
        if not rows:
            raise StudyBuildError(
                f'{source.name} has no row in this study\'s treatments.')
        if key == 'chat_by_partner':
            agg.merge_into_by_partner(rows, features)
        else:
            agg.merge_into_aggregated(rows, features)

        carried = _carry_over(key, row_key, rows, stem)
        if carried['columns'] and carried['matched'] < len(rows):
            notes.append(
                f'{key}: {len(rows) - carried["matched"]} of {len(rows)} rows '
                f'found no match in the pooled dataset, so the rubric and topic '
                f'columns are blank on them.')
        if not carried['columns']:
            notes.append(
                f'{key}: the pooled dataset carries no rubric or topic columns, '
                f'so this study has none either. Run the paid stages once on the '
                f'whole collection and build the studies again — they are the '
                f'same ratings whichever sample reads them.')
        built[key] = rows

    # The sample is what the tables hold, not what the corpus spoke. Counting
    # groups from the messages would leave out the triads that exchanged
    # nothing — and those are in the sample, randomised like every other.
    census = studies.census(study, messages)
    pairs = built.get('chat_by_partner') or []
    per_arm = {}
    for row in pairs:
        per_arm.setdefault(str(row.get('treatment') or ''), set()).add(
            str(row.get('group_uid') or ''))
    groups = set().union(*per_arm.values()) if per_arm else set()
    spoke = {str(row.get('group_uid') or '') for row in mine}
    census.update(n_groups=len(groups),
                  groups_per_treatment={k: len(v) for k, v
                                        in sorted(per_arm.items())},
                  n_silent_groups=len(groups - spoke))

    # The study's messages travel with the result: the Stata layout needs the
    # chat channel, which lives on a message and on nothing else.
    return {'study': study, 'stem': stem, 'tables': built, 'notes': notes,
            'messages': mine, 'census': census}


def _carry_over(key: str, row_key, rows, stem: str) -> dict:
    """Copy the paid columns from the pooled dataset onto these rows."""
    pooled_path = config.DATASETS_DIR / f'{stem}_{key}_nlp.csv'
    if not pooled_path.is_file():
        return {'columns': [], 'matched': 0}
    pooled = tables.read(pooled_path)
    columns = carried_columns(pooled)
    if not columns:
        return {'columns': [], 'matched': 0}

    index = {tuple(str(row.get(k, '')) for k in row_key): row for row in pooled}
    matched = 0
    for row in rows:
        found = index.get(tuple(str(row.get(k, '')) for k in row_key))
        if found is None:
            row.update(dict.fromkeys(columns, ''))
            continue
        matched += 1
        for column in columns:
            row[column] = found.get(column, '')
    return {'columns': columns, 'matched': matched}


def applies_to(rows) -> bool:
    """Whether this experiment has the layout `core/stata_profile.py` describes.

    Decided by the export rather than by the adapter's name: the profile is a
    map from that experiment's oTree columns, so the honest test is whether
    those columns are here.
    """
    from . import stata_profile

    return bool(rows) and stata_profile.MAIN + 'player.treatment' in rows[0]


def regressors_table(stem: str, rows, notes: list):
    """The study's directed pairs with every block of measures as regressors.

    On a copy of the rows, so the datasets the do-files read are left as they
    are. Adds, in this order: the relations and the NRC emotions (which the
    datasets do not carry), the 1-4 ordinal versions of the category shares, and
    one indicator per topic. The standardised copies of the measures are then
    left out of the list of columns. Returns the rows, the measure columns in
    order and a label for each derived one.
    """
    from . import fulltables, narratives, nrc, regressors

    rows = [dict(row) for row in rows]
    table = fulltables.Table('chat_by_partner', list(rows[0]) if rows else [],
                             rows)

    found = fulltables._relations(stem, config.EXPERIMENT, False, notes)
    if found is not None:
        unit, per_unit = found
        # Narrowed to this study before the frequency threshold, which is a
        # property of the sample: the same rule the relations page follows.
        groups = {str(row.get('group_uid') or '') for row in rows}
        per_unit = {key: value for key, value in per_unit.items()
                    if str(key[0]) in groups}
        counts = narratives.frequencies(per_unit)
        terms = sorted((term for term, n in counts.items()
                        if n >= narratives.MIN_DOCUMENTS),
                       key=lambda term: (-counts[term], term))
        if not fulltables._add_relations(table, unit, per_unit, terms, counts):
            notes.append('Relations left out of the Stata files: they were '
                         f'extracted per {unit}, which a directed pair cannot '
                         'be read out of.')
    if nrc.available():
        try:
            fulltables._add_emotions(table, nrc.load())
        except (OSError, ValueError) as exc:
            notes.append(f'Emotions left out of the Stata files: {exc}')
    else:
        notes.append('Emotions left out of the Stata files: the NRC word list '
                     'is not installed.')

    labels = dict(table.labels)
    for column in regressors.ordinal_columns(table.columns):
        labels[f'{column}_lik'] = regressors.ordinal(table.rows, column)
        table.columns.append(f'{column}_lik')
    for column in [c for c in table.columns if regressors.TOPIC_LIST.match(c)]:
        for name, topic in regressors.topic_indicators(table.rows,
                                                       column).items():
            table.columns.append(name)
            labels[name] = f'Topic present: {topic} (TopicGPT)'

    return table.rows, regressors.raw_only(table.columns), labels


def write_stata(study, stem: str, rows, root: Path | None = None,
                messages=None, notes=None,
                bow_min_documents: int | None = None) -> list:
    """The directed pairs in the layout the experimenter's do-files use.

    Two files, the second a superset of the first:

    `<stem>_<slug>_goodshape`
        His 111 columns, then every block of our measures as raw values, the 1-4
        ordinal versions and the topic indicators. The file for the logit.
    `<stem>_<slug>_complete`
        The same, plus the bag of words: one raw-count column per unigram and
        bigram in at least `BOW_MIN_DOCUMENTS` documents of this study. The file
        for a LASSO.

    Each as CSV, and as `.dta` when pandas is installed. One codebook, for the
    complete file, which names every column of both.
    """
    from . import regressors, stata_profile

    notes = notes if notes is not None else []
    minimum = (regressors.BOW_MIN_DOCUMENTS if bow_min_documents is None
               else bow_min_documents)
    enriched, measures, labels = regressors_table(stem, rows, notes)

    out = directory(study, root) / 'stata'
    out.mkdir(parents=True, exist_ok=True)
    written = []

    shaped = stata_profile.build(enriched, messages=messages,
                                 measures=measures, label_of=labels)
    _check_names(shaped['columns'])
    target = out / f'{stem}_{study.slug}_goodshape.csv'
    tables.write(target, shaped['rows'], shaped['columns'])
    written.append(target)
    if optional.have('pandas'):
        dta = _write_dta(target.with_suffix('.dta'), shaped,
                         f'{stem}: {study.name}')
        written += [dta] if dta else []

    bow = regressors.bag_of_words(enriched, regressors.BOW_TEXT['chat_by_partner'],
                                  minimum)
    for name, term in bow.items():
        labels[name] = f'Count of "{term}" in what was sent (bag of words)'
    complete = stata_profile.build(enriched, messages=messages,
                                   measures=measures + list(bow),
                                   label_of=labels)
    _check_names(complete['columns'])
    target = out / f'{stem}_{study.slug}_complete.csv'
    tables.write(target, complete['rows'], complete['columns'])
    written.append(target)
    if optional.have('pandas'):
        dta = _write_dta(target.with_suffix('.dta'), complete,
                         f'{stem}: {study.name}, with the bag of words')
        written += [dta] if dta else []
    notes.append(f'Bag of words: {sum(" " not in t for t in bow.values())} '
                 f'unigrams and {sum(" " in t for t in bow.values())} bigrams '
                 f'in at least {minimum} documents of this study.')

    codebook = out / f'{stem}_{study.slug}_codebook.csv'
    tables.write(codebook, [
        {'name': name,
         'original': complete['ours'].get(name, '(from the oTree export)'),
         'label': complete['labels'].get(name, 'the experiment and its chat'),
         'in_goodshape': '1' if name in set(shaped['columns']) else '0'}
        for name in complete['columns']
    ], ['name', 'original', 'label', 'in_goodshape'])
    written.append(codebook)
    return written


def _check_names(columns) -> None:
    from . import stata_profile

    problems = stata_profile.problems(columns)
    if problems:
        raise StudyBuildError(
            'The Stata layout came out with names Stata would refuse: '
            + '; '.join(problems[:3]))


def _write_dta(path: Path, built: dict, label: str):
    """The same rows as a Stata file, or None if it could not be written.

    Reuses `fulltables`, which already knows the two things that matter: which
    columns are numbers, and that a value above 2045 bytes has to be stored as
    `strL` or Stata refuses the file. The transcript is always above it.

    Returns None rather than raising: the CSV is the deliverable, and a study
    whose text defeats the Stata writer should still be written out.
    """
    from . import fulltables

    table = fulltables.Table('chat_by_partner', list(built['columns']),
                             built['rows'])
    table.labels.update(built['labels'])
    try:
        fulltables._write_dta(path, table, {c: c for c in built['columns']},
                              label)
    except Exception:                       # noqa: BLE001 - pandas or Stata limits
        path.unlink(missing_ok=True)
        return None
    return path


def write(study, stem: str, root: Path | None = None, messages=None,
          bow_min_documents: int | None = None) -> dict:
    """Write one study's datasets and the record of what its sample was."""
    result = build(study, stem, messages=messages)
    out = directory(study, root) / 'datasets'
    out.mkdir(parents=True, exist_ok=True)

    written = []
    for key, rows in result['tables'].items():
        target = out / f'{stem}_{key}_nlp.csv'
        agg.write_csv(target, rows)
        written.append(target)

    pairs = result['tables'].get('chat_by_partner') or []
    if applies_to(pairs):
        written += write_stata(study, stem, pairs, root,
                               messages=result.get('messages'),
                               notes=result['notes'],
                               bow_min_documents=bow_min_documents)
    else:
        result['notes'].append(
            'No Stata layout written: this export does not carry the '
            'coalition experiment\'s columns, so the only names available are '
            'the ones chatlens makes itself. `chatlens tables` writes those.')

    # Beside the data, because a reader six months on needs to know the sample
    # was 361 groups and not 538 — every interval in the paper follows from it.
    record = directory(study, root) / 'study.json'
    record.write_text(
        json.dumps({**result['census'], 'stem': stem,
                    'notes': result['notes']}, indent=2, ensure_ascii=False),
        encoding='utf-8')
    written.append(record)
    return {'paths': written, 'notes': result['notes'],
            'census': result['census'], 'tables': result['tables']}
