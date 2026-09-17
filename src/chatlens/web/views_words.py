"""The words page: which terms go with the outcome, as a picture and a table."""

from __future__ import annotations

from chatlens.web import active, pagecache, ui
from chatlens.core import optional, words

REQUIREMENTS = [
    optional.Requirement('sklearn', 'scikit-learn',
                         optional.install_command(
                             'words', ['scikit-learn', 'matplotlib',
                                       'wordcloud']),
                         size='about 150 MB',
                         note='fits the model and scores it out of sample'),
    optional.Requirement('matplotlib', 'matplotlib',
                         optional.install_command(
                             'words', ['scikit-learn', 'matplotlib',
                                       'wordcloud']),
                         size='included above',
                         note='draws the figures'),
    optional.Requirement('wordcloud', 'wordcloud',
                         optional.install_command(
                             'words', ['scikit-learn', 'matplotlib',
                                       'wordcloud']),
                         size='included above',
                         note='lays the terms out'),
]

# One fit serves the page and both images, which otherwise arrive as three
# separate requests and pay for the same model three times. Keyed on everything
# that changes the answer — the study included, see `active.scope()` — and
# holding a few entries rather than one, so moving between two studies does not
# refit both on every move.
_CACHE = pagecache.Cache()


_e = ui.esc

# The name a reader already knows this by, printed once under the question:
# see `ui.finding`'s `method` parameter for why.
METHOD = 'Bag of words: unigrams and bigrams, penalised logistic regression'


def _params(query) -> dict:
    """The knobs, taken from the query string and forced into range.

    They arrive from a browser, so nothing is trusted: an unknown value becomes
    the default rather than an error, because a page that refuses to render
    teaches less than one that renders the default and shows what it used.
    """
    def one(key, default=''):
        return (query.get(key) or [default])[0]

    ngrams = one('ngrams', 'both')
    if ngrams not in words.NGRAMS:
        ngrams = 'both'
    try:
        penalty = float(one('penalty', '0.1'))
    except ValueError:
        penalty = 0.1
    if penalty not in words.PENALTIES:
        penalty = min(words.PENALTIES, key=lambda p: abs(p - penalty))
    try:
        min_df = int(one('min_df', '10'))
    except ValueError:
        min_df = 10
    if min_df not in words.MIN_DF:
        min_df = min(words.MIN_DF, key=lambda m: abs(m - min_df))
    return {'ngrams': ngrams, 'penalty': penalty, 'min_df': min_df}


def _text_column(rows) -> str | None:
    for candidate in ('sent_transcript_text', 'transcript_text', 'text',
                      'body'):
        if rows and candidate in rows[0]:
            return candidate
    return None


def _dataset():
    """The built dataset for the outcome's unit, and the outcome itself."""
    from chatlens.core import config, outcome as outcome_module
    from chatlens.web import views_participation

    experiment = config.EXPERIMENT
    declared = experiment.outcome
    if not declared:
        return None, None, 'no outcome'
    suffix = f'_{outcome_module.DATASET_OF[declared["unit"]]}_nlp.csv'
    path = views_participation._latest(active.datasets_dir(), suffix)
    if path is None:
        return None, declared, 'no dataset'
    return views_participation._read(path), declared, ''


def result(query):
    """The fit for these parameters, from the cache when it is the same one."""
    params = _params(query)
    rows, declared, problem = _dataset()
    if problem:
        return None, declared, problem, params

    text_column = _text_column(rows)
    if text_column is None:
        return None, declared, 'no text column', params

    # The study is part of the key, not only the settings: see
    # `active.scope()` for what sharing an entry between two experiments did.
    key = (active.scope(), tuple(sorted(params.items())), declared['column'],
           declared['unit'])
    remembered = _CACHE.get(key)
    if remembered is not None:
        return remembered, declared, '', params
    try:
        value = words.fit(rows, text_column, declared['column'], **params)
    except ValueError as exc:
        return None, declared, str(exc), params
    _CACHE.put(key, value)
    return value, declared, '', params


def _requirements_panel() -> str:
    state = optional.report(REQUIREMENTS)
    if state['ready']:
        return ''
    rows = []
    seen = set()
    for requirement in state['missing']:
        if requirement.command in seen:
            continue
        seen.add(requirement.command)
        rows.append(
            f'<p class="muted">{_e(requirement.note)} — '
            f'{_e(requirement.size)}</p>'
            f'<pre class="cmd">{_e(requirement.command)}</pre>')
    names = ', '.join(r.label for r in state['missing'])
    return f'''<div class="panel">
  <h3>This page needs something that is not installed</h3>
  <p>Missing: <b>{_e(names)}</b>. chatlens itself is four megabytes and does not
  carry these, so nothing was downloaded on your behalf. Run the command below,
  then reload.</p>
  {"".join(rows)}
  <p class="muted">The command names this installation's own interpreter. A
  <code>pip install</code> typed into a shell usually reaches a different Python
  and leaves this page saying the same thing.</p>
</div>'''


def _controls(name: str, params: dict) -> str:
    def options(values, chosen, labels=None):
        out = []
        for value in values:
            label = labels.get(value, value) if labels else value
            mark = ' selected' if value == chosen else ''
            out.append(f'<option value="{_e(value)}"{mark}>{_e(label)}</option>')
        return ''.join(out)

    return f'''<form class="wordform" hx-get="/experiment/{_e(name)}/findings/words/panel"
      hx-target="#wordpanel" hx-swap="innerHTML" hx-trigger="change">
  <label class="field"><span class="rolename">Terms</span>
    <select name="ngrams">{options(list(words.NGRAMS), params["ngrams"])}</select>
  </label>
  <label class="field"><span class="rolename">Present in at least</span>
    <select name="min_df">{options([str(m) for m in words.MIN_DF],
                                   str(params["min_df"]))}</select>
    <span class="rolehint">documents — rarer terms are dropped before
      fitting</span>
  </label>
  <label class="field"><span class="rolename">How selective</span>
    <select name="penalty">{options([str(p) for p in words.PENALTIES],
                                    str(params["penalty"]))}</select>
    <span class="rolehint">lower keeps fewer terms; watching them appear and
      disappear says how fragile the selection is</span>
  </label>
</form>'''


def panel(name: str, query) -> str:
    """Everything that changes when a knob moves."""
    found, declared, problem, params = result(query)

    if problem:
        return _cannot(name, problem)

    label = _e(declared['label'] or declared['column'])
    query_string = (f'ngrams={params["ngrams"]}&min_df={params["min_df"]}'
                    f'&penalty={params["penalty"]}')
    base = f'/experiment/{_e(name)}/findings/words'

    # The answer is the comparison with length, because on a corpus of short
    # messages that is what the selection is usually measuring.
    baseline = ''
    answer = f'{len(found["kept"])} terms survive the penalty.'
    verdict = ui.OPEN
    if found['auc_words'] is not None and found['auc_length'] is not None:
        beaten = found['auc_words'] > found['auc_length'] + 0.02
        verdict = ui.YES if beaten else ui.NO
        answer = (
            f'{"Yes" if beaten else "No"}. The words score '
            f'<span class="figure">{found["auc_words"]:.3f}</span> against '
            f'<span class="figure">{found["auc_length"]:.3f}</span> for '
            f'length alone.')
        baseline = ui.stat_tiles([
            (f'{found["auc_length"]:.3f}', 'length alone'),
            (f'{found["auc_words"]:.3f}', 'the words'),
        ]) + (
            '<p class="muted">Out-of-sample, whole groups held out. ' + (
                'The words beat length, so this is not simply a count of who '
                'typed more.' if beaten else
                'What looks like content here is mostly how much was written, '
                'and that is the finding rather than a problem to tune '
                'away.') + '</p>')

    warning = ''
    if found['penalty_did_nothing']:
        warning = ui.notice(
            'Every term survived, so the penalty is not selecting anything. '
            'Lower it.', 'warn')

    kept = found['kept']
    shown = kept[:TABLE_ROWS]
    # The magnitude is drawn where the number is, and the sign is the colour
    # rather than a word in the next column: this whole tool is directional and
    # the reader should not have to join two cells to see which way a term
    # points.
    widest = max((abs(t['coef']) for t in shown), default=1.0) or 1.0
    rows = []
    for term in shown:
        with_it = term['coef'] > 0
        direction = 'with' if with_it else 'against'
        # Clicking a term opens the messages it came from. Until now there was
        # no path at all from a coefficient back to the sentences behind it.
        look = (f'<button class="termlink" '
                f'hx-get="/experiment/{_e(name)}/inspect" '
                f'{ui.hx_vals(term=term["term"], unit=declared["unit"])} '
                f'hx-target="#inspector" hx-swap="innerHTML">'
                f'<code>{_e(term["term"])}</code></button>')
        rows.append((
            look,
            f'{term["coef"]:+.3f}',
            ui.bar_cell(abs(term['coef']) / widest, direction),
            f'{term["documents"]}',
        ))
    caption = ''
    if len(kept) > len(shown):
        # It used to cut at forty and say nothing, so a reader had no way of
        # knowing whether they were looking at the whole selection.
        caption = (f'The {len(shown)} largest of {len(kept)} terms. '
                   f'The full list is in the CSV below.')

    # The column says what it counts. "Documents" is the model's word, and the
    # documents are units of the outcome's level — which is the number most
    # easily misread as a count of messages.
    unit_heading = declared['unit'].replace('_', ' ') + ' units'
    clouds = _clouds(found, label, base, query_string)

    summary = (f'{found["rows"]} rows across {found["groups"]} groups, '
               f'{100 * found["share"]:.0f}% positive. {found["vocabulary"]} '
               f'terms appear in at least {found["min_df"]} documents; '
               f'<b>{len(kept)}</b> survive the penalty.')

    table = ui.table(
        ['Term', 'Coefficient', '', unit_heading], rows,
        numeric={1, 3}, caption=caption,
        empty_message='No term survived the penalty, so there is nothing to '
                      'list. Raise the penalty to keep more of them.')

    return ui.finding(
        f'Which words go with {label}?',
        answer,
        verdict=verdict,
        method=METHOD,
        controls=_controls(name, params),
        evidence=f'{warning}<p class="muted">{summary}</p>{baseline}{clouds}',
        detail=f'<h2>The terms</h2>{table}',
        how_to_read='''<p>A penalised regression picks the terms, so a term
        being here says it carries signal and its size says how much the
        penalty let it keep — none of it is an estimate of an effect.</p>
        <p>The penalty is the control worth moving. Watching terms appear and
        disappear as it changes says how fragile the selection is, which a
        single table hides.</p>
        <p>Click a term to read the messages it came from. The count beside it
        is units at the outcome's level, not messages: one unit can hold
        several.</p>''')


def _cannot(name: str, problem: str) -> str:
    """The question, and why it cannot be answered here yet."""
    question = 'Which words go with the outcome?'
    if problem == 'no outcome':
        return ui.finding(
            question, 'Not yet: nothing has been declared to explain.',
            method=METHOD,
            evidence=ui.blocked(
                'This finding needs an outcome',
                'The terms are chosen by how well they separate one column. '
                'Until a column is named there is nothing to separate.',
                retry=f'/experiment/{_e(name)}/step/outcome'))
    if problem == 'no dataset':
        return ui.finding(
            question, 'Not yet: nothing has been measured.',
            method=METHOD,
            evidence=ui.blocked(
                'This finding needs a run',
                'It reads the dataset built for the outcome\'s unit. Run the '
                'analysis once — the free preset is enough.',
                retry=f'/experiment/{_e(name)}/step/run'))
    if problem == 'no text column':
        return ui.finding(
            question, 'Not on this dataset.',
            method=METHOD,
            evidence=ui.blocked(
                'This finding needs a column of text',
                'The dataset built for that unit carries no transcript to '
                'read.',
                retry=f'/experiment/{_e(name)}/step/outcome'))
    return ui.finding(question, 'Something is in the way.', method=METHOD,
                      evidence=ui.notice(_e(problem), 'bad'))


# Enough to see the shape of the selection without turning the page into a
# spreadsheet; the CSV below the table holds all of it.
TABLE_ROWS = 40


def _clouds(found, label: str, base: str, query_string: str) -> str:
    """The two figures, or the reason there are none.

    They used to be emitted whatever happened: with nothing surviving the
    penalty the page still wrote two `<img>` tags, the requests behind them
    answered 403, and the reader was left looking at two broken-image icons
    with no explanation. That state is in the documentation's own screenshots.
    """
    from chatlens.core import words as words_core

    figures = []
    for positive, caption, ink in (
            (True, f'Goes with {label}', 'var(--with)'),
            (False, 'Goes against it', 'var(--against)')):
        try:
            svg = words_core.cloud_svg(found['kept'], positive)
        except ValueError:
            continue
        except Exception as exc:  # noqa: BLE001 - a figure is not the page
            figures.append(
                f'<figure><div class="empty"><p>This figure could not be '
                f'drawn: {_e(exc)}</p></div>'
                f'<figcaption>{caption}</figcaption></figure>')
            continue
        figures.append(
            f'<figure style="--cloud-ink: {ink}" '
            f'aria-label="terms that {_e(caption.lower())}">{svg}'
            f'<figcaption>{_e(caption)}</figcaption></figure>')

    if not figures:
        return ui.empty(
            'No term survived the penalty in either direction, so there is '
            'nothing to draw. Raise the penalty above and the figures come '
            'back.')

    downloads = (
        f'<p class="muted">Each word is sized by the size of its coefficient. '
        f'Downloads: '
        f'<a href="{base}/cloud.svg?direction=positive&amp;{query_string}">'
        f'SVG, with</a> · '
        f'<a href="{base}/cloud.svg?direction=negative&amp;{query_string}">'
        f'SVG, against</a> · '
        f'<a href="{base}/terms.csv?{query_string}">the coefficients as CSV</a>'
        f'</p>')
    return f'<div class="clouds">{"".join(figures)}</div>{downloads}'


def body(name: str, query=None) -> str:
    """The controls, and a panel that arrives when the model has been fitted."""
    query = query or {}
    needs = _requirements_panel()
    if needs:
        return needs
    params = _params(query)
    query_string = (f'ngrams={params["ngrams"]}&min_df={params["min_df"]}'
                    f'&penalty={params["penalty"]}')
    # The question is there from the first byte. It used to be inside the
    # panel, so the screen opened on a spinner with nothing saying what was
    # being worked out.
    from chatlens.core import config

    declared = config.EXPERIMENT.outcome or {}
    label = _e(declared.get('label') or declared.get('column') or 'the outcome')
    waiting = ui.finding(
        f'Which words go with {label}?',
        'Working it out…',
        method=METHOD,
        evidence=ui.spinner('Fitting the model and drawing the figures…'))
    return (f'<div id="wordpanel"'
            f' hx-get="/experiment/{_e(name)}/findings/words/panel'
            f'?{query_string}"'
            f' hx-trigger="load" hx-swap="innerHTML">{waiting}</div>')


