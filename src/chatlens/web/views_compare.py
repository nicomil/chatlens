"""The comparison page: which representation of the text is worth using."""

from __future__ import annotations

import threading

from chatlens.web import ui
from chatlens.core import compare, optional

_CACHE = {}
_LOCK = threading.Lock()


_e = ui.esc


def _participation_line(name: str) -> str:
    """The strongest result is often not in the text, and belongs at the top.

    On a different sample from everything below — the whole grid rather than the
    rows that carry text — so it is a sentence and not a row in the table.
    Putting it in the table would invite a comparison that is not one.
    """
    from chatlens.core import config, outcome as outcome_module, participation
    from chatlens.web import views_participation

    declared = config.EXPERIMENT.outcome
    if not declared or declared['kind'] != 'binary':
        return ''
    messages_path = views_participation._latest(config.MERGED_DIR,
                                                '_messages_long.csv')
    roster_path = views_participation._latest(config.MERGED_DIR,
                                              '_chat_aggregated.csv')
    suffix = f'_{outcome_module.DATASET_OF[declared["unit"]]}.csv'
    pairs_path = views_participation._latest(config.MERGED_DIR, suffix)
    if messages_path is None or pairs_path is None:
        return ''

    messages = views_participation._read(messages_path)
    roster = views_participation._read(roster_path) if roster_path else None
    members, _source = participation.membership(messages, roster=roster)
    cells = participation.grid(messages, members)

    values = {}
    for row in views_participation._read(pairs_path):
        raw = str(row.get(declared['column'], '')).strip()
        if raw in ('0', '1'):
            values[(row['group_uid'], row['focal_id_in_group'],
                    row['partner_id_in_group'])] = int(raw)
    within = participation.within_receiver(cells, values)
    if not within or not within['decided']:
        return ''

    return f'''<div class="verdictbox">
  <p><b>Before any of this: whether anything was written at all.</b> Holding the
  receiver fixed, where exactly one of the possible senders wrote to them, the
  outcome went to the one who wrote {within["chose_writer"]} times against
  {within["chose_silent"]} — {100 * within["share"]:.0f}%.</p>
  <p class="note">On a different sample from the table below, which can only see
  the rows that carry text, so it is not a row in it. See
  <a href="/experiment/{_e(name)}/findings/participation">Participation</a>.</p>
</div>'''


def _scored():
    from chatlens.core import config, narratives, outcome as outcome_module
    from chatlens.web import views_participation

    experiment = config.EXPERIMENT
    declared = experiment.outcome
    if not declared:
        return None, 'no outcome'
    if declared['kind'] != 'binary':
        return None, 'not binary'
    if not optional.have('sklearn'):
        return None, 'no sklearn'

    suffix = f'_{outcome_module.DATASET_OF[declared["unit"]]}_nlp.csv'
    path = views_participation._latest(config.DATASETS_DIR, suffix)
    if path is None:
        return None, 'no dataset'
    rows = views_participation._read(path)
    text_column = next((c for c in ('sent_transcript_text', 'text', 'body')
                        if rows and c in rows[0]), None)
    if text_column is None:
        return None, 'no text column'

    key = (declared['column'], declared['unit'],
           tuple(experiment.narrative_entities))
    with _LOCK:
        if _CACHE.get('key') == key:
            return _CACHE['value'], ''

    per_unit = terms = None
    key_of = None
    # Only with the package: the relations are RELATIO's method, and this table
    # would otherwise compare a representation nobody could reproduce.
    if experiment.narrative_entities and narratives.available()[0]:
        messages_path = views_participation._latest(config.MERGED_DIR,
                                                    '_messages_long.csv')
        if messages_path is not None:
            message_key, key_of = narratives.keys_for(declared['unit'])
            try:
                per_unit = narratives.extract_with_relatio(
                    views_participation._read(messages_path),
                    experiment.narrative_entities, unit_key=message_key)
            except ValueError:
                # The comparison still stands without that row, and the
                # narratives page explains why it is absent.
                per_unit = None
            counts = narratives.frequencies(per_unit)
            terms = [n for n, c in counts.items()
                     if c >= narratives.MIN_DOCUMENTS]


    try:
        assembled = compare.build(rows, declared['column'], text_column,
                                  per_unit=per_unit, key_of=key_of,
                                  narrative_terms=terms)
        value = compare.score(assembled)
    except ValueError as exc:
        return None, str(exc)

    with _LOCK:
        _CACHE.clear()
        _CACHE.update(key=key, value=value)
    return value, ''



def _how_to_read(name: str) -> str:
    base = f'/experiment/{_e(name)}'
    return ui.disclosure(
        'How to read this table, and where to go next',
        f'''<p><b>Predicting well and mattering are different questions, and
        this table answers the first.</b> A relation can carry a large and
        reliable effect and still predict poorly, because it appears in a
        fraction of the rows and brings a handful of variables where a bag of
        words brings a thousand.</p>
        <p>Length is first because it is the null hypothesis of text analysis:
        longer documents contain more of everything, and a representation that
        does not beat "how much was written" has not yet shown that content
        matters.</p>
        <p>"How well it separates" is the area under the ROC curve: 0.5 is a
        coin, 1.0 is perfect. The spread beside it is how much that figure
        moved between folds — a large one means the number is not to be read
        closely.</p>
        <p>From here: <a href="{base}/findings/words">the words</a> for which terms were
        selected, <a href="{base}/findings/narratives">the narratives</a> for what is
        true rather than what predicts, <a href="{base}/findings/participation">
        participation</a> for who spoke at all.</p>''')


def panel(name: str) -> str:
    """The comparison itself."""
    scored, problem = _scored()

    if problem == 'no outcome':
        body = ('<p class="muted">Nothing to compare against. Declare an '
                f'outcome under <a href="/experiment/{_e(name)}/step/outcome">'
                'Settings</a>.</p>')
    elif problem == 'not binary':
        body = ('<p class="muted">This page compares how well each '
                'representation separates a yes/no outcome. The declared one is '
                'continuous.</p>')
    elif problem == 'no sklearn':
        command = optional.install_command(
            'words', ['scikit-learn', 'matplotlib', 'wordcloud'])
        body = (f'<div class="panel"><h3>Needs scikit-learn</h3>'
                f'<pre class="cmd">{_e(command)}</pre></div>')
    elif problem == 'no dataset':
        body = ('<p class="muted">Run the analysis once so there is a dataset '
                'to read.</p>')
    elif problem:
        body = f'<p class="formerror">{_e(problem)}</p>'
    else:
        rows = ''.join(
            (f'<tr><td>{_e(r["name"])}</td>'
             f'<td class="num">{r["features"]}</td>'
             f'<td class="num">{r["auc"]:.3f}</td>'
             f'<td class="num">{r["spread"]:.3f}</td>'
             f'<td>{"" if r["beats_volume"] is None else ("yes" if r["beats_volume"] else "no")}</td></tr>'
             if r['auc'] is not None else
             f'<tr class="absent"><td>{_e(r["name"])}</td>'
             f'<td class="num">—</td><td class="num">—</td>'
             f'<td class="num">—</td><td>{_e(r.get("why", ""))}</td></tr>')
            for r in scored['results'])
        body = f'''{_participation_line(name)}
<p class="muted">{scored["rows"]} rows, {scored["folds"]} folds, whole groups
held out. Every representation is fitted on the same training rows and scored on
the same test rows — a feature set scored on a different split is not being
compared to anything.</p>
<div class="scroll"><table class="grid">
<thead><tr><th>Representation</th><th class="num">Variables</th>
<th class="num">How well it separates</th>
<th class="num">Spread across folds</th>
<th>Beats length alone</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<div class="verdictbox"><p>{_e(compare.verdict(scored))}</p></div>
{_how_to_read(name)}'''

    return body
