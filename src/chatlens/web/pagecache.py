"""What a slow page remembers, and for how many studies at a time.

Three pages cost from seconds to minutes — the words page fits a model, the
relations page parses every message, the comparison cross-validates every block
— so each kept its last answer. One answer: a dictionary holding a single key
and a single value.

That was enough for one experiment and is not enough for two. With a library of
studies the reader moves between them, and a cache of one entry is evicted by
every move: open study 1, open study 2, come back to study 1, and the model is
fitted a third time. Worse, the register on every page reads the comparison, so
the eviction happens on page loads that are not even about the analysis.

So: a few entries, oldest evicted first. Small on purpose — these values hold
fitted models and matrices, and a cache that grows without limit in a
long-running process is a leak with a friendly name.
"""

from __future__ import annotations

import threading
from collections import OrderedDict

# Enough for two studies with a couple of settings each, which is the shape of
# the work this is for. Not a tuning parameter anybody should need to touch.
KEEP = 6


class Cache:
    """Keyed on whatever the caller decides identifies an answer.

    The key is the caller's business — it is the thing that has to include the
    study, and `active.scope()` is how it does — and this only remembers.
    """

    def __init__(self, keep: int = KEEP):
        self._keep = keep
        self._lock = threading.Lock()
        self._entries: OrderedDict = OrderedDict()

    def get(self, key, default=None):
        with self._lock:
            if key not in self._entries:
                return default
            # Touched, so the least recently *used* is the one evicted rather
            # than the least recently written.
            self._entries.move_to_end(key)
            return self._entries[key]

    def put(self, key, value) -> None:
        with self._lock:
            self._entries[key] = value
            self._entries.move_to_end(key)
            while len(self._entries) > self._keep:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def __contains__(self, key) -> bool:
        with self._lock:
            return key in self._entries
