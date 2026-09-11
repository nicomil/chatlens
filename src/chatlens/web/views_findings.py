"""The findings area: the register on the left, one answer on the right.

There were five sibling pages here, each answering a version of the same
question — *does the content of these conversations explain anything?* — and no
way to know which of them had something to say without opening all five.
`core/compare.py` already decides that. This module puts the decision where the
reader chooses.
"""

from __future__ import annotations

from chatlens.web import ui
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
        + '\n'.join(parts)
        + _take_the_data(name)
        + _send_to_a_colleague(name),
        slug=name,
        study=experiment.name,
        steps=study_state.step_state(experiment),
        step='findings',
    )


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
    canvas = (_body(entry, name, query or {})
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
    )
