"""One module per experiment: raw export in, canonical tables out.

An adapter is the only place that may know an experiment's column names, its
group size, its treatments or its payoff rule. Everything downstream works from
the canonical tables of `core/schema.py` alone, which is what lets the same
analysis run on a different study.

Each adapter declares two things and provides two functions:

``INPUTS``
    The files it needs, as role → filename pattern. A role whose pattern is
    ``None`` is optional. These are what `chatlens status` reports on and what
    the workspace's ``[input]`` block overrides.

``OPTIONS``
    The names of the keyword arguments its ``run`` accepts beyond the common
    ones, so the command line can pass along only what the adapter understands.

``run(**paths, outdir, stem, ...)``
    Writes the three tables and returns a summary.

``print_summary(summary)``
    Puts that summary on screen, in the terms of its own experiment.

Adding one means writing a module here and naming it in ``experiment.toml``.
`otree_coalition` is the reference implementation, written for a three-player
coalition-formation experiment in oTree; `generic_chat` needs no code at all
when the export is already one message per row.
"""

from __future__ import annotations

import importlib

BUILTIN = ('otree_coalition', 'generic_chat')


def available() -> set[str]:
    return set(BUILTIN)


def load(name: str):
    """Import an adapter by name."""
    if name not in BUILTIN:
        raise ValueError(
            f'Unknown adapter "{name}". Available: {", ".join(sorted(BUILTIN))}'
        )
    return importlib.import_module(f'{__name__}.{name}')


def inputs(name: str) -> dict:
    """The files an adapter needs, as role → pattern."""
    return dict(load(name).INPUTS)
