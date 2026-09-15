"""The two datasets, complete, in one place — for Stata and R.

`output/datasets/` holds one file per unit of observation, with the
experiment's variables, the text measures, the rubric and the topics. Two
findings never reached those files: the relations, which the narratives page
extracts after a run, and the emotions, which the emotions page scores when it
is opened. And Stata could not take the files as they were: the oTree columns
carry dots in their names, and a few names are longer than the 32 characters
Stata allows.

`write()` produces both tables again with everything added and every name one
that Stata and R both accept, in `output/tables/`:

    <stem>_chat_by_partner_full.csv  .dta   one row per directed pair i->j
    <stem>_chat_aggregated_full.csv  .dta   one row per participant
    <stem>_codebook.csv                     each column: its name here, the
                                            original, a label, where it came from

Two tables and not one, because they are two units of observation: a single
rectangle would have to repeat the participant on every pair or lose the pairs.
Each is complete for its unit, and the participant table already carries the
group's measures.

The `.dta` is written by pandas, which chatlens does not otherwise need.
Without it the CSVs are still written and the caller is told what to install.
"""

from __future__ import annotations

import csv
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from . import config, narratives, nrc, optional, tables, words

FOLDER = 'tables'

TABLES = ('chat_by_partner', 'chat_aggregated')

# Which transcript each emotion block is scored on, per table: the same text
# the measures stage read, so `nrc_<block>_*` covers what `nlp_<block>_*` does.
EMOTION_BLOCKS = {
    'chat_by_partner': (('sent', 'sent_transcript_text'),
                        ('dyad', 'dyad_transcript_text')),
    'chat_aggregated': (('sent', 'sent_transcript_text'),
                        ('group', 'group_transcript_text')),
}

STATA_LIMIT = 32
LABEL_LIMIT = 80
# Longer than this, in bytes, a Stata string has to be a strL.
STR_LIMIT = 2045

# Names Stata keeps for itself.
RESERVED = frozenset({
    '_all', '_b', 'byte', '_coef', '_cons', 'double', 'float', 'if', 'in',
    'int', 'long', '_n', '_N', '_pi', '_pred', '_rc', '_skip', 'str', 'strL',
    'using', 'with',
})

# Tried in order on a name that is too long, before anything is cut. They are
# what makes the chatlens names that overflow fit whole, so that
# nlp_group_llm_contains_support_commitment becomes
# nlp_group_llm_support_commitment rather than losing its last word.
SHORTER = (('contains_', ''), ('compound', 'cmp'))


class TablesError(RuntimeError):
    """There is nothing to build the tables from."""


@dataclass
class Table:
    key: str
    columns: list                                  # original names, in order
    rows: list                                     # dicts keyed by them
    labels: dict = field(default_factory=dict)     # original -> label


# --- names -----------------------------------------------------------------


def _clean(text: str) -> str:
    name = re.sub(r'[^A-Za-z0-9_]+', '_', text)
    return re.sub(r'_+', '_', name).strip('_')


def _initials(part: str) -> str:
    return ''.join(word[0] for word in _clean(part).split('_') if word)


def _candidate(column: str) -> str:
    name = _clean(column)
    if len(name) > STATA_LIMIT and '.' in column:
        # oTree writes app.round.model.field, and the field is the part that
        # says what the column is. The rest is kept as initials, so
        # bargaining_tdl_intro.1.player.prolific_study_id becomes
        # bti_1_p_prolific_study_id instead of a cut at 32 that collides with
        # three other prolific_ columns.
        *heads, last = column.split('.')
        name = _clean('_'.join([_initials(h) for h in heads] + [last]))
    for long, short in SHORTER:
        if len(name) <= STATA_LIMIT:
            break
        name = name.replace(long, short)
    if not name or not name[0].isalpha():
        name = f'v_{name}'
    if name in RESERVED:
        name = f'{name}_'
    return name[:STATA_LIMIT]


def safe_names(columns) -> dict:
    """Original name -> one Stata and R both accept: unique, 32 characters."""
    out, taken = {}, set()
    for column in columns:
        base = name = _candidate(column)
        n = 1
        # Compared without case, so the result also survives a reader that
        # folds it — Stata's `import delimited, case(lower)`, for one.
        while name.lower() in taken:
            n += 1
            tail = f'_{n}'
            name = base[:STATA_LIMIT - len(tail)] + tail
        taken.add(name.lower())
        out[column] = name
    return out


def _source(column: str) -> str:
    """Where a column came from, in the codebook's words."""
    if '.' in column:
        return 'oTree export'
    if column.startswith('rel_'):
        return 'relations (RELATIO)'
    if column.startswith('nrc_'):
        return 'emotions (NRC lexicon)'
    if column.endswith(('_transcript_text', '_transcript_json')):
        return 'transcript'
    if column.startswith('nlp_') and '_llm_' in column:
        return 'rubric (LLM)'
    if column.startswith('nlp_') and '_topic' in column:
        return 'topics (TopicGPT)'
    if column.startswith('nlp_'):
        return 'text measures'
    return 'merge: the experiment and its conversations'


# --- what the pages compute -------------------------------------------------


def _spoke(row) -> bool:
    """Did the focal participant write anything in this row's unit?"""
    count = row.get('nlp_sent_wc')
    if count not in (None, ''):
        try:
            return float(count) > 0
        except ValueError:
            pass
    return bool((row.get('sent_transcript_text') or '').strip())


def _relations(stem, experiment, extract, notes):
    """(unit, per_unit) for the relations this study has, or None.

    Stored extractions are used first, the directed pair before the
    participant. Only when neither is there, and the caller allows it, is one
    made — which needs RELATIO and takes minutes.
    """
    entities = experiment.narrative_entities if experiment else []
    if not entities:
        notes.append('Relations left out: no entities are declared. Name them '
                     'on the relations page, then build the tables again.')
        return None
    path = config.MERGED_DIR / f'{stem}_messages_long.csv'
    if not path.is_file():
        notes.append(f'Relations left out: no {path.name}.')
        return None
    messages = tables.read(path)
    model = experiment.narrative_model
    for unit in ('dyad_directed', 'sender_group'):
        found = narratives.stored(messages, entities, unit, model=model)
        if found is not None:
            return unit, found
    if not extract:
        notes.append('Relations left out: they have not been extracted yet. '
                     'Open the relations page once, then build the tables '
                     'again.')
        return None
    ready, why = narratives.available()
    if not ready:
        notes.append(f'Relations left out: none are stored here and RELATIO '
                     f'cannot run ({why}).')
        return None
    try:
        return 'dyad_directed', narratives.extracted(
            messages, entities, 'dyad_directed', model=model)
    except ValueError as exc:
        notes.append(f'Relations left out: {exc}')
        return None


def _add_relations(table, unit, per_unit, terms, counts) -> bool:
    """Indicators for the frequent relations, how many each row has, and all
    of them as text.

    What is counted is what the focal participant *sent*: in persuasion the
    speaker's language is the one that matters. A participant's relations are
    the union of what they sent to each partner — RELATIO reads each message
    the same way whatever unit the result is filed under, so nothing has to be
    extracted again to have them per person.

    The indicators cover only the relations frequent enough to test, so a
    dimension built from keywords — "agree", "leave" — found nothing in them
    even where RELATIO had extracted such a relation. `rel_sent_all` carries
    every relation of the row, most frequent in the corpus first, so a keyword
    search reads the same extraction as everything else.
    """
    if table.key == 'chat_by_partner':
        if unit != 'dyad_directed':
            return False
        by_row = per_unit
        row_key = lambda r: (r.get('group_uid'), r.get('focal_id_in_group'),
                             r.get('partner_id_in_group'))
    else:
        if unit == 'dyad_directed':
            by_row = {}
            for (group, sender, _receiver), found in per_unit.items():
                by_row.setdefault((group, sender), set()).update(found)
        else:
            by_row = per_unit
        row_key = lambda r: (r.get('group_uid'), r.get('focal_id_in_group'))

    names = {term: 'rel_' + _clean('_'.join(term)) for term in terms}
    order = lambda term: (-counts.get(term, 0), term)
    for row in table.rows:
        found = by_row.get(row_key(row), set())
        if not _spoke(row):
            # No text is no measurement, not an absence of relations.
            row['rel_sent_n'] = row['rel_sent_all'] = ''
            row.update(dict.fromkeys(names.values(), ''))
            continue
        row['rel_sent_n'] = str(len(found))
        row['rel_sent_all'] = '; '.join(' '.join(term)
                                        for term in sorted(found, key=order))
        for term, name in names.items():
            row[name] = '1' if term in found else '0'

    table.columns += ['rel_sent_n', 'rel_sent_all', *names.values()]
    table.labels['rel_sent_n'] = 'Distinct relations in what was sent (RELATIO)'
    table.labels['rel_sent_all'] = ('Every relation in what was sent, most '
                                    'frequent first (RELATIO)')
    for term, name in names.items():
        table.labels[name] = 'Sent the relation: ' + ' | '.join(term)
    return True


def _add_emotions(table, marked) -> None:
    """The NRC categories as a share of the words, per block of text.

    A percentage, like the dictionary measures beside it. Zero is a real value
    and stays; only a unit with no text at all is left blank.
    """
    for block, text_column in EMOTION_BLOCKS[table.key]:
        if not table.rows or text_column not in table.rows[0]:
            continue
        added = [f'nrc_{block}_{c}' for c in nrc.CATEGORIES]
        matched = f'nrc_{block}_matched'
        for row in table.rows:
            scored = nrc.score(words.clean(row.get(text_column)), marked)
            if not scored['words']:
                row.update(dict.fromkeys(added + [matched], ''))
                continue
            for category, name in zip(nrc.CATEGORIES, added):
                row[name] = str(round(100 * scored['shares'][category], 4))
            row[matched] = str(scored['emotion_words'])
        table.columns += added + [matched]
        for category, name in zip(nrc.CATEGORIES, added):
            table.labels[name] = f'NRC {category}, % of words ({block})'
        table.labels[matched] = f'Words found in the NRC lexicon ({block})'


# --- building and writing ---------------------------------------------------


def build(stem: str, experiment=None, extract: bool = True,
          min_documents: int = narratives.MIN_DOCUMENTS, source_dir=None):
    """Both tables in memory, and what could not be added to them.

    `source_dir` is where the built datasets are read from, and it exists for
    the study selector: a study declared in `[[studies]]` has its own tables
    under `output/studies/<slug>/datasets/`, with the standardised columns
    recomputed on that sample. Defaulting it to the pooled folder keeps every
    existing caller unchanged.
    """
    experiment = experiment or config.EXPERIMENT
    source = Path(source_dir) if source_dir else config.DATASETS_DIR
    built, notes = {}, []
    for key in TABLES:
        path = source / f'{stem}_{key}_nlp.csv'
        if not path.is_file():
            raise TablesError(f'No {path.name} in {source}: run '
                              f'the analysis first.')
        rows = tables.read(path)
        columns = list(rows[0]) if rows else tables.columns_of(path)
        built[key] = Table(key, columns, rows)

    found = _relations(stem, experiment, extract, notes)
    if found is not None:
        unit, per_unit = found
        # The same relations in both tables, chosen where they were extracted:
        # the ones frequent enough for the relations page to test.
        counts = narratives.frequencies(per_unit)
        terms = sorted((t for t, n in counts.items() if n >= min_documents),
                       key=lambda t: (-counts[t], t))
        for table in built.values():
            if not _add_relations(table, unit, per_unit, terms, counts):
                notes.append(f'Relations only in the participant table: they '
                             f'were extracted per {unit}, which a directed '
                             f'pair cannot be read out of.')

    if nrc.available():
        try:
            marked = nrc.load()
        except (OSError, ValueError) as exc:
            notes.append(f'Emotions left out: the word list could not be read '
                         f'({exc}).')
        else:
            for table in built.values():
                _add_emotions(table, marked)
    else:
        notes.append('Emotions left out: the NRC word list is not installed. '
                     'The emotions page says where to get it.')
    return built, notes


def write(stem: str, out_dir=None, experiment=None, extract: bool = True,
          min_documents: int = narratives.MIN_DOCUMENTS,
          source_dir=None) -> dict:
    """Write the tables and the codebook. Returns the paths and the notes."""
    out_dir = Path(out_dir) if out_dir else config.OUTPUT_DIR / FOLDER
    built, notes = build(stem, experiment, extract, min_documents, source_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    have_pandas = optional.have('pandas')
    written, codebook = [], []
    for key, table in built.items():
        names = safe_names(table.columns)
        target = out_dir / f'{stem}_{key}_full.csv'
        _write_csv(target, table, names)
        written.append(target)
        dta = target.with_suffix('.dta')
        if have_pandas:
            _write_dta(dta, table, names, f'{stem}: {key}')
            written.append(dta)
        else:
            # A .dta from an earlier build would now describe other data.
            dta.unlink(missing_ok=True)
        codebook += [{'table': target.stem, 'name': names[c], 'original': c,
                      'label': table.labels.get(c, c), 'source': _source(c)}
                     for c in table.columns]
    if not have_pandas:
        notes.append('No .dta written: it needs pandas. '
                     + optional.install_command('stata', ['pandas']))

    target = out_dir / f'{stem}_codebook.csv'
    # With a byte-order mark, unlike the tables: this one is opened in Excel.
    tables.write(target, codebook,
                 ['table', 'name', 'original', 'label', 'source'])
    written.append(target)
    return {'paths': written, 'notes': notes}


def _write_csv(path: Path, table: Table, names: dict) -> None:
    """Without a byte-order mark, which R's read.csv would take for part of
    the first column's name."""
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow([names[c] for c in table.columns])
        for row in table.rows:
            writer.writerow([row.get(c) or '' for c in table.columns])


def _as_number(values):
    """The column as numbers, or None if it should stay text.

    Text when anything in it is not a number, and also when converting would
    lose something: a code with a leading zero, or a run of digits too long
    for a double to hold exactly. A column with nothing in it stays text,
    because nothing says what it is.
    """
    import pandas as pd

    present = values[values != '']
    if present.empty:
        return None
    if (present.str.match(r'-?0\d').any()
            or present.str.fullmatch(r'-?\d{16,}').any()):
        return None
    number = pd.to_numeric(present, errors='coerce')
    if number.isna().any() or (number.abs() == float('inf')).any():
        return None
    return pd.to_numeric(values.replace('', float('nan')))


def _write_dta(path: Path, table: Table, names: dict, label: str) -> None:
    """Stata 14 and later (format 118): UTF-8, and strL for long text."""
    import pandas as pd

    frame = pd.DataFrame({names[c]: [row.get(c) or '' for row in table.rows]
                          for c in table.columns})
    strls = []
    for column in frame.columns:
        number = _as_number(frame[column])
        if number is not None:
            frame[column] = number
        elif frame[column].map(lambda v: len(v.encode('utf-8'))).max() \
                > STR_LIMIT:
            strls.append(column)
    labels = {names[c]: table.labels.get(c, c)[:LABEL_LIMIT]
              for c in table.columns}
    with warnings.catch_warnings():
        # pandas warns about every float it stores as a double; that is the
        # intent, and the warnings would bury anything worth reading.
        warnings.simplefilter('ignore')
        frame.to_stata(path, write_index=False, version=118,
                       variable_labels=labels, convert_strl=strls,
                       data_label=label[:LABEL_LIMIT])
