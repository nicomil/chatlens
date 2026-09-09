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


class Unknown(LookupError):
    """No such experiment, said in terms the page can show."""


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
        while _active is not None and _active != name:
            _LOCK.wait()
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
