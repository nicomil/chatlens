"""The findings area: the register on the left, one answer on the right.

There were five sibling pages here, each answering a version of the same
question — *does the content of these conversations explain anything?* — and no
way to know which of them had something to say without opening all five.
`core/compare.py` already decides that. This module puts the decision where the
reader chooses.
"""

from __future__ import annotations

from chatlens.web import active, ui
from chatlens.web import study as study_state

# Which module draws which entry. `corpus` has no module yet: the reader is
# told so rather than shown a page that pretends otherwise.
BODIES = {
    'corpus': ('views_corpus', 'body'),
    'participation': ('views_participation', 'body'),
    'compare': ('views_compare', 'panel'),
    'words': ('views_words', 'body'),
    'narratives': ('views_narratives', 'panel'),
    'emotions': ('views_emotions', 'panel'),
}


# On screen the words finding answers at once and fills in when the model has
# been fitted. A document cannot wait: printed before the fill-in it would say
# "Working it out…" where the answer belongs.
SETTLED = {'words': ('views_words', 'panel')}


def _body(entry: str, name: str, query, settled: bool = False) -> str:
    import importlib

    if entry not in BODIES:
        return ui.empty('There is nothing under that name.')
    module_name, function = (SETTLED.get(entry) if settled else None) \
        or BODIES[entry]
    module = importlib.import_module(f'chatlens.web.{module_name}')
    render = getattr(module, function)

    # These renderers take a name and a query, a name alone, or neither. Asking
    # the signature is the only honest way to tell: catching `TypeError` around
    # the call, as this did, cannot distinguish "wrong number of arguments"
    # from a `TypeError` raised inside the function, and quietly retried with
    # the query dropped.
    import inspect

    wanted = len(inspect.signature(render).parameters)
    if wanted >= 2:
        return render(name, query)
    if wanted == 1:
        return render(name)
    return render()


class Unknown(LookupError):
    """No finding under that name."""


def panel(name: str, entry: str, query=None) -> str:
    """The computed body of one finding, without the page around it.

    A panel request is the fill-in: it asks for the thing that was being worked
    out, so it takes the settled renderer. Answering it with the same
    placeholder the page already showed leaves the screen saying "Working it
    out…" for ever, which is what it did.
    """
    if entry not in BODIES:
        raise Unknown(f'No finding called "{entry}".')
    return _body(entry, name, query or {}, settled=True)


def register(name: str, entry: str = '') -> str:
    """The register with the verdicts worked out.

    Asked for separately so that the page does not wait on it: the comparison
    behind these verdicts cross-validates every representation, and the reader
    should be looking at the finding they opened while that happens.
    """
    from chatlens.core import config

    experiment = config.EXPERIMENT
    entries = study_state.findings(experiment, study_state.verdicts())
    return ui.register(name, entries, entry)


# The order the findings read in when they are put together as a document:
# the ground first, then who spoke, then the four ways of turning it into
# numbers.
EXPORT_ORDER = ('corpus', 'participation', 'compare', 'words', 'narratives',
                'emotions')


def sample_picker(name: str, back: str) -> str:
    """Which declared sample the findings are read on.

    Nothing at all when the experiment declares no studies, which is every
    experiment until somebody writes a `[[studies]]` block: a control offering
    one choice is furniture.

    The whole sample stays an option and stays first. Two treatments varying two
    things at once is not a comparison anybody should make by accident, but
    "everything together" is the right sample for describing a corpus, and it is
    what every figure in this tool meant before studies existed.
    """
    declared = active.studies()
    if not declared:
        return ''
    current = active.chosen()
    options = ['<option value=""'
               + (' selected' if not current else '')
               + '>The whole sample</option>']
    for item in declared:
        options.append(
            f'<option value="{ui.attr(item.slug)}"'
            + (' selected' if item.slug == current else '')
            + f'>{ui.esc(item.name)}</option>')
    return (
        f'<form class="samplepick" method="post" '
        f'action="/experiment/{ui.attr(name)}/sample">'
        f'<input type="hidden" name="back" value="{ui.attr(back)}">'
        f'<label class="offscreen" for="samplepick">'
        f'Which sample these findings are computed on</label>'
        # No inline handler: the content security policy this server sends is
        # `script-src \'self\'`, which blocks one silently, and the control
        # would look broken. `app.js` submits on change; the button beside it is
        # what works when scripting is off altogether.
        f'<select id="samplepick" name="slug" data-submit-on-change="1">'
        + ''.join(options) +
        '</select>'
        # For a browser with scripting off, and for a keyboard user who has
        # changed the value without leaving the control.
        '<button type="submit" class="samplego">Use</button>'
        '</form>')


def sample_notice() -> str:
    """A word when the chosen study has no tables of its own yet."""
    problem = active.missing_datasets()
    # Escaped: the sentence is prose, and `ui.notice` takes markup.
    return ui.notice(f'<p>{ui.esc(problem)}</p>', 'warn') if problem else ''


def export(name: str, query=None) -> str:
    """Every finding that has an answer, in one document.

    The end of the path should be something to send to somebody. This is the
    register read out in order, with what could not be computed said plainly
    rather than left out — a summary that quietly omits the four findings that
    were blocked is a summary that misleads.
    """
    from chatlens.core import config

    experiment = config.EXPERIMENT
    entries = {item['id']: item
               for item in study_state.findings(experiment,
                                                study_state.verdicts())}

    parts, missing = [], []
    for key in EXPORT_ORDER:
        item = entries.get(key)
        if item is None:
            continue
        if item['verdict'] == ui.UNAVAILABLE:
            missing.append(item)
            continue
        parts.append(f'<section class="exported">'
                     f'{_body(key, name, query or {}, settled=True)}'
                     f'</section>')

    if missing:
        rows = ''.join(
            f'<li><b>{ui.esc(item["name"])}</b> — {ui.esc(item["note"])}</li>'
            for item in missing)
        parts.append(
            f'<section class="exported"><h2>Not answered here</h2>'
            f'<p>These questions were not computed on this machine. Left out '
            f'silently they would make the rest read as the whole of what this '
            f'study has to say.</p><ul>{rows}</ul></section>')

    return ui.shell(
        f'{experiment.name} — findings',
        f'<p class="eyebrow">{ui.esc(experiment.name)}</p>'
        f'<h1 class="question">What these conversations say</h1>'
        f'<p class="lead">Every finding this study can answer, in order. '
        f'Print this page to keep it, or send the link to someone who has the '
        f'dashboard open.</p>'
        + sample_notice()
        + _what_was_analysed()
        + '\n'.join(parts)
        + _take_the_data(name)
        + _send_to_a_colleague(name),
        slug=name,
        study=experiment.name,
        steps=study_state.step_state(experiment),
        step='findings',
        selector=sample_picker(name, f'/experiment/{name}/findings/export'),
    )


def _what_was_analysed() -> str:
    """The sample, and what to keep in mind about it.

    This document and `core/report.py` used to describe the same run and share
    nothing: the report knew the coverage, the treatments and the data-quality
    notes and none of the findings; this knew the findings and not what they were
    computed on. A reader who had only one of them was missing half, and the
    missing half was never named. The report's two sections that are about the
    *sample* rather than about a stage now open this page as well.
    """
    from chatlens.core import archive, config, report

    found = sorted(config.MERGED_DIR.glob('*_messages_long.csv'))
    if not found:
        return ''
    suffix = '_messages_long.csv'
    stem = found[0].name[:-len(suffix)]
    try:
        data = report.collect(config.OUTPUT_DIR, stem)
    except (OSError, ValueError, KeyError):
        return ''

    cover = data['coverage']
    tiles = ui.stat_tiles([
        (cover['n_triads'], 'groups'),
        (cover['n_participants'], 'participants'),
        (cover['n_pairs'], 'directed pairs'),
        (cover.get('n_messages') or '—', 'messages'),
    ])

    # Which sample this is, where the experiment declares more than one. Without
    # it two printed documents from two studies are indistinguishable.
    experiment = config.EXPERIMENT
    which = ''
    if getattr(experiment, 'studies', ()):
        which = ui.notice(
            'This experiment declares more than one study, and this page is '
            'the pooled sample. The per-study datasets are written by '
            '<code>chatlens studies</code>; the standardised measures differ '
            'between them, so a figure here is not a figure from either.',
            'warn')

    runs = archive.list_runs(config.OUTPUT_DIR)
    failed = str(runs[0].get('failed_stage') or '') if runs else ''
    incomplete = ui.notice(
        f'The last run did not finish: the <b>{ui.esc(failed)}</b> stage '
        f'stopped, so the columns it produces are missing from everything '
        f'below.', 'bad') if failed else ''

    notes = data['quality']['notes']
    caveats = ''
    if notes:
        caveats = ('<h2>Worth keeping in mind</h2><ul>'
                   + ''.join(f'<li>{ui.esc(note)}</li>' for note in notes)
                   + '</ul>')

    per_arm = ''
    if cover['per_treatment']:
        per_arm = ui.table(
            ['Treatment', 'Groups', 'Participants'],
            [(ui.esc(row['label']), str(row['n_triads']),
              str(row['n_participants'])) for row in cover['per_treatment']],
            numeric={1, 2})

    return (f'<section class="exported"><h2>What was analysed</h2>'
            f'{which}{incomplete}{tiles}{per_arm}{caveats}</section>')


def _take_the_data(name: str) -> str:
    """Every measure, one table per unit, for somebody who analyses elsewhere.

    `output/datasets/` lacks what the pages compute after a run — the
    relations and the emotions — and not all of its column names are ones
    Stata accepts. This is those two tables again with both added and every
    name fixed, with a codebook saying what each column was called and where
    it came from.
    """
    href = f'/experiment/{ui.esc(name)}/tables.zip'
    return f'''<section class="exported">
  <h2>Take the data into Stata or R</h2>
  <p>Two tables, one per unit of observation — the directed pair and the
  participant — each with the experiment's variables and every measure this
  study has: the text measures, the rubric, the topics, the relations and the
  emotions. As CSV and as a Stata <code>.dta</code>, with names both programs
  accept and a codebook that maps each back to its original.</p>
  <p><a class="btn primary" href="{href}">Download the tables</a></p>
  <p class="muted small">The relations are included once the relations page
  has extracted them, and the emotions once the word list is installed.
  Whatever is missing is listed in <code>NOTES.txt</code> inside the file.</p>
</section>'''


def _send_to_a_colleague(name: str) -> str:
    """The page above is a document. This is the study itself.

    Kept next to it because they answer the same wish and differ in one way
    that matters: a printed page is read, while this one is opened, and
    whoever opens it can turn the controls and see the messages behind a
    number. What it costs is that the participants' words travel with it.
    """
    base = f'/experiment/{ui.esc(name)}/bundle'
    return f'''<section class="exported">
  <h2>Send the study itself</h2>
  <p>The page above is something to read. This is something to open: the
  configuration, the data and everything already computed, in one file. They
  import it and every finding here is there, with nothing to run again — the
  paid stages included, so nobody pays twice for the same answers.</p>
  <p><a class="btn primary" href="{base}">Download the study</a>
     <a class="btn quiet" href="{base}?pseudonymise=1">Download without the
     participant identifiers</a></p>
  <p class="muted small">The chat texts travel either way, and people write
  their names in them. The API keys and the pseudonym key never travel.</p>
</section>'''


def page(name: str, entry: str = '', query=None) -> str:
    """The register, and whichever finding was asked for."""
    from chatlens.core import config

    experiment = config.EXPERIMENT
    entries = study_state.findings(experiment)
    known = {item['id'] for item in entries}
    if entry and entry not in known:
        raise Unknown(f'No finding called "{entry}".')
    if not entry:
        entry = entries[0]['id'] if entries else ''

    # One place for the inspector on every finding: a term or a relation is
    # clicked here and the messages behind it arrive without leaving the page.
    canvas = (sample_notice()
              + _body(entry, name, query or {})
              + '<div id="inspector" class="inspectorslot"></div>')
    return ui.shell(
        f'{experiment.name} — {study_state.entry_name(entry).lower()}',
        canvas,
        slug=name,
        study=experiment.name,
        steps=study_state.step_state(experiment),
        step='findings',
        aside=ui.register(name, entries, entry, refresh=(
            f'/experiment/{ui.esc(name)}/findings/register?on={ui.esc(entry)}')),
        selector=sample_picker(
            name, f'/experiment/{name}/findings/{entry}'),
    )
