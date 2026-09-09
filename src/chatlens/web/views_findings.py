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
    'participation': ('views_participation', 'body'),
    'compare': ('views_compare', 'panel'),
    'words': ('views_words', 'body'),
    'narratives': ('views_narratives', 'panel'),
    'emotions': ('views_emotions', 'panel'),
}


def _body(entry: str, name: str, query) -> str:
    import importlib

    if entry not in BODIES:
        return ui.empty(
            'Reading the conversations themselves is not built yet. Until it '
            'is, the messages are in the merged table in this study\'s '
            'output folder.')
    module_name, function = BODIES[entry]
    module = importlib.import_module(f'chatlens.web.{module_name}')
    render = getattr(module, function)
    try:
        return render(name, query)
    except TypeError:
        # The panels that take no query, and the one that takes only a name.
        try:
            return render(name)
        except TypeError:
            return render()


def page(name: str, entry: str = '', query=None) -> str:
    """The register, and whichever finding was asked for."""
    from chatlens.core import config

    experiment = config.EXPERIMENT
    entries = study_state.findings(experiment)
    known = {item['id'] for item in entries}
    if entry not in known:
        entry = entries[0]['id'] if entries else ''

    canvas = _body(entry, name, query or {})
    return ui.shell(
        f'{experiment.name} — {study_state.entry_name(entry).lower()}',
        canvas,
        slug=name,
        study=experiment.name,
        steps=study_state.step_state(experiment),
        step='findings',
        aside=ui.register(name, entries, entry),
    )
