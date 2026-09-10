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
            _message_key, key_of = narratives.keys_for(declared['unit'])
            try:
                # The same extraction the relations page makes, and the same
                # call, so whichever page is opened first pays for both.
                per_unit = narratives.extracted(
                    views_participation._read(messages_path),
                    experiment.narrative_entities, declared['unit'],
                    model=experiment.narrative_model)
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



def panel(name: str) -> str:
    """The comparison itself."""
    scored, problem = _scored()

    if problem:
        return _cannot(name, problem)

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
    table = f'''<div class="scroll"><table class="grid">
<thead><tr><th>Representation</th><th class="num">Variables</th>
<th class="num">How well it separates</th>
<th class="num">Spread across folds</th>
<th>Beats length alone</th></tr></thead>
<tbody>{rows}</tbody></table></div>'''

    sample = (f'<p class="muted">{scored["rows"]} rows, {scored["folds"]} '
              f'folds, whole groups held out. Every representation is '
              f'fitted on the same training rows and scored on the same '
              f'test rows — a feature set scored on a different split is '
              f'not being compared to anything.</p>')

    volume = scored.get('volume')
    scorable = [r for r in scored['results'] if r['auc'] is not None]
    winners = [r for r in scorable
               if r['kind'] != 'volume' and r.get('beats_volume')]
    if winners:
        best = max(winners, key=lambda r: r['auc'])
        answer = (f'<span class="with">{_e(best["name"])}</span>, at '
                  f'<span class="figure">{best["auc"]:.3f}</span> against '
                  f'<span class="figure">{volume:.3f}</span> for length '
                  f'alone.')
        verdict = ui.YES
    else:
        answer = ('Nothing. No representation of the content beats how '
                  f'much was written, at '
                  f'<span class="figure">{volume:.3f}</span>.')
        verdict = ui.NO

    return ui.finding(
        'Which representation of the text is worth using?',
        answer,
        verdict=verdict,
        evidence=_participation_line(name) + sample + table,
        detail=f'<p>{_e(compare.verdict(scored))}</p>',
        how_to_read=_reading())


def _cannot(name: str, problem: str) -> str:
    """The question, and why it cannot be answered here yet."""
    question = 'Which representation of the text is worth using?'
    if problem == 'no outcome':
        return ui.finding(
            question, 'Not yet: nothing has been declared to explain.',
            evidence=ui.blocked(
                'This finding needs an outcome',
                'Every representation here is scored on how well it separates '
                'one column. Until a column is named there is nothing to score '
                'against.',
                retry=f'/experiment/{_e(name)}/step/outcome'))
    if problem == 'not binary':
        return ui.finding(
            question, 'Not with this outcome.',
            evidence=ui.blocked(
                'This finding needs a yes/no outcome',
                'It compares how well each representation separates two '
                'groups. The declared outcome is continuous.',
                retry=f'/experiment/{_e(name)}/step/outcome'))
    if problem == 'no sklearn':
        command = optional.install_command(
            'words', ['scikit-learn', 'matplotlib', 'wordcloud'])
        return ui.finding(
            question, 'Not on this machine yet.',
            evidence=ui.blocked(
                'This finding needs scikit-learn',
                'The models are fitted with it. Nothing is installed on your '
                'behalf: chatlens is four megabytes and this is the part that '
                'is not.',
                commands=[('scikit-learn, matplotlib, wordcloud', command,
                           'about 150 MB')]))
    if problem == 'no dataset':
        return ui.finding(
            question, 'Not yet: nothing has been measured.',
            evidence=ui.blocked(
                'This finding needs a run',
                'It reads the dataset the measures stage writes. Run the '
                'analysis once — the free preset is enough.',
                retry=f'/experiment/{_e(name)}/step/run'))
    return ui.finding(question, 'Something is in the way.',
                      evidence=ui.notice(_e(problem), 'bad'))


def _reading() -> str:
    return '''<p><b>Predicting well and mattering are different questions, and
    this table answers the first.</b> A relation can carry a large and reliable
    effect and still predict poorly, because it appears in a fraction of the
    rows and brings a handful of variables where a bag of words brings a
    thousand.</p>
    <p>Length is first because it is the null hypothesis of text analysis:
    longer documents contain more of everything, and a representation that does
    not beat "how much was written" has not yet shown that content
    matters.</p>
    <p>"How well it separates" is the area under the ROC curve: 0.5 is a coin,
    1.0 is perfect. The spread beside it is how much that figure moved between
    folds — a large one means the number is not to be read closely.</p>'''
