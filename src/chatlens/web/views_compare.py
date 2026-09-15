"""The comparison page: which representation of the text is worth using."""

from __future__ import annotations

from chatlens.web import active, pagecache, ui
from chatlens.core import compare, optional

# A few entries, keyed on the study among other things: see
# `web/pagecache.py` for why one was not enough.
_CACHE = pagecache.Cache()


_e = ui.esc


def _participation_line(name: str) -> str:
    """The strongest result is often not in the text, and belongs at the top.

    On a different sample from everything below — the whole grid rather than the
    rows that carry text — so it is a sentence and not a row in the table.
    Putting it in the table would invite a comparison that is not one.

    Only for an outcome declared per directed pair. The comparison holds a
    receiver fixed and asks which of the senders facing them was chosen, so it
    needs a value per direction; an outcome declared per person or per group has
    none. This used to pick the file by the outcome's unit and then index its
    rows by `partner_id_in_group` regardless — a column the participant table
    does not have — so an experiment with an outcome per person raised a
    KeyError from inside the page and the request died with a traceback on the
    server and nothing in the browser.
    """
    from chatlens.core import config, outcome as outcome_module, participation
    from chatlens.web import views_participation

    declared = config.EXPERIMENT.outcome
    if not declared or declared['kind'] != 'binary':
        return ''
    if declared['unit'] != 'dyad_directed':
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

    # `as_binary`, not a test against "0" and "1": every other page reads
    # yes/no/true/false through it, and a roster exported from a spreadsheet
    # usually holds words. Comparing strings here made this whole paragraph
    # disappear on such a study, with nothing said.
    values = {}
    for row in views_participation._read(pairs_path):
        found = outcome_module.as_binary(row.get(declared['column']))
        if found is not None:
            values[(row['group_uid'], row['focal_id_in_group'],
                    row['partner_id_in_group'])] = found
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
    path = views_participation._latest(active.datasets_dir(), suffix)
    if path is None:
        return None, 'no dataset'
    rows = views_participation._read(path)
    text_column = next((c for c in ('sent_transcript_text', 'text', 'body')
                        if rows and c in rows[0]), None)
    if text_column is None:
        return None, 'no text column'

    # The study is part of the key: see `active.scope()`.
    key = (active.scope(), declared['column'], declared['unit'],
           tuple(experiment.narrative_entities))
    remembered = _CACHE.get(key)
    if remembered is not None:
        return remembered, ''

    per_unit = terms = None
    key_of = None
    # Only RELATIO's own output — extracted here, or carried in by an imported
    # study: anything else would compare a representation nobody could
    # reproduce.
    if experiment.narrative_entities:
        messages_path = views_participation._latest(config.MERGED_DIR,
                                                    '_messages_long.csv')
        if messages_path is not None:
            messages = views_participation._read(messages_path)
            _message_key, key_of = narratives.keys_for(declared['unit'])
            per_unit = narratives.stored(
                messages, experiment.narrative_entities, declared['unit'],
                model=experiment.narrative_model)
            if per_unit is None and narratives.available()[0]:
                try:
                    # The same extraction the relations page makes, and the
                    # same call, so whichever page is opened first pays for
                    # both.
                    per_unit = narratives.extracted(
                        messages, experiment.narrative_entities,
                        declared['unit'], model=experiment.narrative_model)
                except ValueError:
                    # The comparison still stands without that row, and the
                    # narratives page explains why it is absent.
                    per_unit = None
            if per_unit is None:
                key_of = None
            else:
                # Narrowed to the chosen study before the threshold is applied:
                # which relations are frequent enough to test is a fact about
                # the sample, and `rows` below is that study's rows.
                per_unit = active.units_within(per_unit, messages)
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

    _CACHE.put(key, value)
    return value, ''



def panel(name: str) -> str:
    """The comparison itself."""
    scored, problem = _scored()

    if problem:
        return _cannot(name, problem)

    # Three words, because there are three answers. "no" on a difference whose
    # interval covers both nothing and something asserts more than the sample
    # carries, and that was the commonest row in the table.
    said = {compare.YES: 'adds something', compare.NO: 'adds nothing',
            compare.UNCLEAR: 'too close to call'}

    def cells(r):
        if r['auc'] is None:
            return (f'<tr class="absent"><td>{_e(r["name"])}</td>'
                    f'<td class="num">—</td><td class="num">—</td>'
                    f'<td class="num">—</td><td class="num">—</td>'
                    f'<td>{_e(r.get("why", ""))}</td></tr>')
        if r['kind'] == 'volume':
            return (f'<tr><td>{_e(r["name"])}</td>'
                    f'<td class="num">{r["features"]}</td>'
                    f'<td class="num">{r["auc"]:.3f}</td>'
                    f'<td class="num">—</td><td class="num">—</td>'
                    f'<td class="muted">the baseline</td></tr>')
        interval = ('—' if r.get('ci_low') is None else
                    f'{r["delta"]:+.3f} '
                    f'<span class="muted">[{r["ci_low"]:+.3f}, '
                    f'{r["ci_high"]:+.3f}]</span>')
        bar = ('—' if r.get('threshold') is None
               else f'{r["threshold"]:.3f}')
        return (f'<tr><td>{_e(r["name"])}</td>'
                f'<td class="num">{r.get("features", "—")}</td>'
                f'<td class="num">{r["auc"]:.3f}</td>'
                f'<td class="num">{interval}</td>'
                f'<td class="num">{bar}</td>'
                f'<td>{_e(said.get(r.get("verdict"), ""))}</td></tr>')

    rows = ''.join(cells(r) for r in scored['results'])
    table = f'''<div class="scroll"><table class="grid">
<thead><tr><th>Representation</th><th class="num">Variables</th>
<th class="num">With length, out of sample</th>
<th class="num">What it adds, and the interval</th>
<th class="num">Smallest it could show</th>
<th>Verdict</th></tr></thead>
<tbody>{rows}</tbody></table></div>'''

    floor = scored.get('min_effect', compare.MEANINGFUL)
    sample = (f'<p class="muted">{scored["rows"]} rows, {scored["folds"]} '
              f'folds, whole groups held out. Every block is fitted beside '
              f'length on the same training rows and scored on the same test '
              f'rows, and what is reported is the <b>difference</b> from length '
              f'alone, fold by fold — the two share their folds, so the paired '
              f'difference is what has an interval worth quoting. The interval '
              f'carries the Nadeau-Bengio correction for the overlap between '
              f'training sets. A block has to clear the larger of {floor:.2f} '
              f'and the smallest difference this design can observe — the '
              f'half-width of its interval, in its own column: an effect the '
              f'sample cannot tell from zero is not considered.</p>')

    volume = scored.get('volume')
    content = [r for r in scored['results']
               if r['kind'] != 'volume' and r.get('delta') is not None]
    winners = [r for r in content if r.get('verdict') == compare.YES]
    unsure = [r for r in content if r.get('verdict') == compare.UNCLEAR]
    if winners:
        best = max(winners, key=lambda r: r['delta'])
        answer = (f'<span class="with">{_e(best["name"])}</span>, adding '
                  f'<span class="figure">{best["delta"]:+.3f}</span> to the '
                  f'<span class="figure">{volume:.3f}</span> that length '
                  f'reaches on its own.')
        verdict = ui.YES
    elif unsure:
        answer = (f'Cannot be told from this sample. Length reaches '
                  f'<span class="figure">{volume:.3f}</span>, and '
                  f'{len(unsure)} of the blocks have an interval that covers '
                  f'both nothing and something.')
        verdict = ui.OPEN
    else:
        answer = ('Nothing. No representation of the content adds anything to '
                  f'how much was written, at '
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
    <p><b>The question is what a block adds to length, not how it scores on its
    own.</b> Longer documents contain more of everything, so a representation
    can score well by rediscovering who typed more. Each block is therefore put
    <i>beside</i> length in the same model and compared with length alone: the
    claim a paper can make is that the features of the message improve the
    prediction <i>after</i> accounting for the quantity of text.</p>
    <p>"With length, out of sample" is the area under the ROC curve of the
    block-plus-length model: 0.5 is a coin, 1.0 is perfect. Beside it is the
    difference from length alone with its 95% interval, computed on the paired
    per-fold differences — the two models share their folds, so their errors are
    correlated and differencing two separate intervals would throw away most of
    the precision the design has. The interval carries the correction of Nadeau
    and Bengio (2003) for the overlap between the training sets, which on five
    folds widens it by about half again.</p>
    <p><b>Three verdicts, not two.</b> A block adds something when its interval
    excludes zero and the improvement reaches the declared floor; it adds
    nothing when the interval rules that floor out; and it is too close to call
    when the interval covers both — which on a few hundred groups is the
    commonest answer, and the one a yes-or-no rule got wrong by picking a side.
    The p-values behind the verdicts carry a Holm correction across the blocks,
    because they all ask the same question of the same baseline.</p>'''
