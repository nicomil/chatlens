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

So a lock, held for the length of the part that reads or writes that state.
Rendering a page is quick — it reads a few files and formats HTML — so
serialising it costs nothing anyone can perceive. What must **not** be done
inside the lock is anything slow: an upload streams to disk first and only then
takes it to record the result.
"""

from __future__ import annotations

import contextlib
import threading
from pathlib import Path

from chatlens.core import config, experiment as experiment_module, library

# Re-entrant: a view that activates an experiment may call another that does
# the same, and the second must not deadlock on the first.
_LOCK = threading.RLock()

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

    global BASE
    with _LOCK:
        previous_workspace = config.WORKSPACE
        previous_experiment = config.EXPERIMENT
        previous_base = BASE
        try:
            config.use_workspace(path)
            config.use_experiment(experiment_module.load(path))
            BASE = f'/experiment/{name}'
            yield path
        finally:
            BASE = previous_base
            config.use_workspace(previous_workspace)
            if previous_experiment is not None:
                # Restores the input patterns along with the object: they are
                # the adapter's, and the adapter belongs to the experiment.
                config.use_experiment(previous_experiment)
            else:
                config.EXPERIMENT = None


@contextlib.contextmanager
def held():
    """Just the lock, for a view that reads the current state without changing
    it."""
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
