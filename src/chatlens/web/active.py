"""Which experiment a request is about.

The dashboard used to serve one workspace, fixed when the process started, and
`config` could keep it in module attributes without anybody minding. Now the
same window reaches several experiments, and which one a request concerns comes
from its URL.

That makes those module attributes shared mutable state under a threading
server — and the requests really are concurrent, because the execution log
polls itself once a second while the rest of the page is being used. Setting
the workspace per request without holding anything would let a log poll for one
experiment interleave with a settings page for another, and each would read the
other's paths.

So a guard, held for the length of the part that reads or writes that state.
It is not a plain mutex, and the reason is what that assumption cost. Rendering
a page is usually quick, but three of them are not: the words page fits a
model, the narratives page parses every message with spaCy, the comparison page
cross-validates. Under one mutex those minutes stopped the whole dashboard,
including the log poll that is supposed to show a run progressing.

The observation that fixes it is that requests for the **same** experiment do
not conflict at all: the state they share is already set to what they both
want. Only a switch between experiments needs exclusivity. So this counts the
requests in flight and lets any number of them through as long as they concern
the same experiment; one for a different experiment waits until the last of
them has left.

In the ordinary case — one person, one experiment open, the log polling while
something computes — nothing waits for anything.
"""

from __future__ import annotations

import contextlib
import threading
import time
from pathlib import Path

from chatlens.core import config, experiment as experiment_module, library

# The condition guards `_active` and `_depth`; waiting on it is how a request
# for another experiment stays out of the way.
_LOCK = threading.Condition()

# The experiment every request in flight is about, and how many of them there
# are. `None` means nobody holds it and the next arrival may take it.
_active = None
_depth = 0

# The URL every fragment of the current page hangs off. Empty in
# single-workspace mode, where the endpoints sit at the root as they always
# have; `/experiment/<name>` when the library is in use, so that a log poll or
# a report request says which experiment it is about instead of relying on
# whatever the server happened to have active when it arrived.
BASE = ''


def base() -> str:
    return BASE


# Which declared study each workspace is currently being read through, by
# workspace path. Server-side rather than in the URL, and the reason is that
# every findings page, every fragment it pulls and every download link would
# otherwise have to carry the slug: one forgotten place and a figure drawn on
# one sample sits beside a table computed on another. One dictionary, keyed the
# way the runner registry is keyed, and every page asks the same question.
#
# An empty string means the pooled sample — every treatment together — which is
# what an experiment with no `[[studies]]` has and the only thing it can have.
_CHOSEN: dict = {}


def studies() -> tuple:
    """The studies this experiment declares, or an empty tuple."""
    from chatlens.core import config

    experiment = getattr(config, 'EXPERIMENT', None)
    return tuple(getattr(experiment, 'studies', ()) or ())


def chosen() -> str:
    """The slug being read, or an empty string for the pooled sample.

    Validated on the way out rather than on the way in: an experiment can be
    edited while the dashboard is open, and a slug that has since been renamed
    or removed must not silently filter a page to nothing.
    """
    from chatlens.core import config

    slug = _CHOSEN.get(str(config.WORKSPACE), '')
    if slug and slug not in {s.slug for s in studies()}:
        return ''
    return slug


def study():
    """The chosen `Study` object, or None for the pooled sample."""
    slug = chosen()
    for candidate in studies():
        if candidate.slug == slug:
            return candidate
    return None


def choose(slug: str) -> str:
    """Read this workspace through one declared study from now on.

    Anything unrecognised means the pooled sample, deliberately: the value comes
    from a browser, and a page that renders the whole sample and says so is
    better than one that refuses.
    """
    from chatlens.core import config

    slug = str(slug or '').strip()
    if slug not in {s.slug for s in studies()}:
        slug = ''
    _CHOSEN[str(config.WORKSPACE)] = slug
    return slug


def forget_choices() -> None:
    """Back to the pooled sample everywhere. For tests."""
    _CHOSEN.clear()


def datasets_dir():
    """Where the findings pages read their built tables from.

    A study's own folder when `chatlens studies` has written one, and the pooled
    folder otherwise. This is the whole point of the selector: the per-study
    tables are not the pooled ones filtered — the standardised columns are
    recomputed on that sample, so `clout_100` for the same participant differs
    between the two — and a page that filtered rows itself would show pooled
    z-scores under a study's name.
    """
    from chatlens.core import config, perstudy

    picked = study()
    if picked is None:
        return config.DATASETS_DIR
    folder = perstudy.directory(picked) / 'datasets'
    if folder.is_dir() and any(folder.glob('*_nlp.csv')):
        return folder
    return config.DATASETS_DIR


def missing_datasets() -> str:
    """Why a chosen study is showing the pooled tables, in one sentence.

    Empty when there is nothing to say. The selector is allowed to point at a
    study that has never been built; what is not allowed is showing that study's
    name over the pooled sample without a word.
    """
    from chatlens.core import config

    picked = study()
    if picked is None:
        return ''
    if datasets_dir() != config.DATASETS_DIR:
        return ''
    return (f'{picked.name} has no tables of its own yet, so what is shown '
            f'below is the whole sample. Build them with `chatlens studies` — '
            f'it costs nothing and no paid call — and the standardised columns '
            f'will be recomputed on this study\'s participants.')


def within(rows):
    """Keep only the rows belonging to the chosen study.

    For the tables that are not built per study — the merged messages the
    participation page counts, above all. Rows with no `treatment` column are
    left alone: the column is how a study is defined, and a table without it is
    not something this can filter.
    """
    picked = study()
    if picked is None or not rows:
        return rows
    if 'treatment' not in rows[0]:
        return rows
    return [row for row in rows if picked.holds(row.get('treatment'))]


def units_within(per_unit, messages):
    """An extraction restricted to the groups of the chosen study.

    The relations are extracted once on the whole corpus and narrowed here,
    rather than extracted per study: a relation comes out of a single sentence,
    so the two give the same relations for the same messages, and parsing eight
    thousand messages takes two minutes. What must be narrowed is the result —
    the frequencies shown beside the table, and the threshold a relation has to
    reach before it is tested, are properties of the sample under analysis.

    Every unit key in this project begins with the group, whichever unit the
    outcome is declared at, so one rule covers all four shapes.
    """
    if study() is None:
        return per_unit
    groups = {row.get('group_uid') for row in within(messages)}
    return {key: value for key, value in per_unit.items()
            if (key[0] if isinstance(key, tuple) else key) in groups}


def scope() -> str:
    """Which study a page's remembered answer belongs to.

    Three pages keep their last result in memory, because fitting a model or
    parsing eight thousand messages is not something to repay on every request.
    Each keyed that result by what the analysis depends on — the outcome
    column, the unit, the entities, the knobs — and by nothing that says *which
    study* it came from. Two experiments configured alike therefore shared one
    entry, and the second one opened was served the first one's model, figures
    and verdicts, with no sign that anything was wrong.

    That is not a corner case in a library of studies: copying a study to try a
    variation on it produces exactly two experiments configured alike. So the
    workspace goes in the key. It is the identity the rest of the request
    already turns on, and `active.experiment()` has set it before any view
    runs.

    The chosen sample is in the key for the same reason. The words page fitted
    on study 1 and the same page fitted on study 2 are different answers to the
    same question, and one of them would otherwise be served for the other.
    """
    from chatlens.core import config

    slug = chosen()
    return f'{config.WORKSPACE}#{slug}' if slug else str(config.WORKSPACE)


class Unknown(LookupError):
    """No such experiment, said in terms the page can show."""


class Busy(RuntimeError):
    """Another experiment holds the shared state, and waiting timed out."""


# How long a request for a different experiment waits before saying so. Long
# enough for an ordinary page to finish, short enough that nobody concludes the
# dashboard has died: the words page fits a model, the relations page parses
# every message, and those take minutes.
WAIT_SECONDS = 10.0


@contextlib.contextmanager
def experiment(name: str):
    """Make `name` the active experiment for the body of the block.

    The previous state is put back on the way out, so single-workspace mode —
    `chatlens --workspace X dashboard`, where there is no library at all — is
    unaffected by a page that happened to look at something else.
    """
    try:
        path = library.path_for(name)
    except library.LibraryError as exc:
        raise Unknown(str(exc)) from None
    if not path.is_dir():
        raise Unknown(f'There is no experiment called "{name}".')

    global BASE, _active, _depth

    with _LOCK:
        # Anyone asking for the experiment already loaded joins it; anyone
        # asking for a different one waits for the last of them to leave.
        #
        # Bounded, because the wait used to have no end. The log of the other
        # study polls itself once a second and a page that computes holds this
        # for minutes, so a second study opened in a second tab sat there with
        # no page, no message and nothing to suggest it was waiting rather than
        # broken. Now it says so, and the reader can try again.
        deadline = time.monotonic() + WAIT_SECONDS
        while _active is not None and _active != name:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Busy(
                    f'The study "{_active}" is using the analysis right now — '
                    f'a page that fits a model holds it for as long as it '
                    f'takes. Nothing is lost: wait for it to finish and open '
                    f'this one again.')
            _LOCK.wait(remaining)
        first = _depth == 0
        if first:
            _saved['workspace'] = config.WORKSPACE
            _saved['experiment'] = config.EXPERIMENT
            _saved['base'] = BASE
            config.use_workspace(path)
            config.use_experiment(experiment_module.load(path))
            BASE = f'/experiment/{name}'
        _active = name
        _depth += 1

    try:
        yield path
    finally:
        with _LOCK:
            _depth -= 1
            if _depth == 0:
                _active = None
                BASE = _saved['base']
                config.use_workspace(_saved['workspace'])
                if _saved['experiment'] is not None:
                    # Restores the input patterns along with the object: they
                    # are the adapter's, and the adapter belongs to the
                    # experiment.
                    config.use_experiment(_saved['experiment'])
                else:
                    config.EXPERIMENT = None
                _LOCK.notify_all()


# What to put back when the last request for an experiment leaves. One dict
# rather than three globals, because the three are only ever set and restored
# together.
_saved = {'workspace': None, 'experiment': None, 'base': ''}


@contextlib.contextmanager
def held():
    """Just the guard, for a view that reads the current state without
    changing it."""
    with _LOCK:
        yield


def load(name: str):
    """The experiment's own object, without making it active."""
    try:
        path = library.path_for(name)
    except library.LibraryError as exc:
        raise Unknown(str(exc)) from None
    if not path.is_dir():
        raise Unknown(f'There is no experiment called "{name}".')
    return experiment_module.load(path), Path(path)
