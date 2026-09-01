"""A guard between a mistyped option and a three-figure bill.

The paid stages charge per call, and the number of calls is the product of four
choices — levels, replicates, models, units — each of which looks harmless on
its own. `--llm-replicates 3` across all four levels is not obviously thirteen
times `--llm-replicates 1` on one level, but that is what it is.

Two thresholds, because one would be either useless or in the way:

- above `confirm_above` the run says what it is about to do and, at a terminal,
  waits for a yes. Real workloads land here — the rubric on the full dataset
  with two replicates was about 7,200 calls — so this is a checkpoint, not an
  obstacle;
- above `refuse_above` it stops. Nothing legitimate reaches that figure; what
  reaches it is a typo, and by then the money would already be gone.

Away from a terminal — the dashboard's subprocess, a CI job, a batch script —
there is nobody to answer, so a run under the hard limit proceeds with the
figure printed, and one above it is refused. Refusing something recoverable is
cheaper than spending something that is not.
"""

from __future__ import annotations

import sys

# Deliberately far apart. See the module docstring for where they come from.
CONFIRM_ABOVE = 1_000
REFUSE_ABOVE = 20_000


class SpendRefused(SystemExit):
    """The run was stopped before any call was paid for."""


def _thousands(n: int) -> str:
    return f'{n:,}'.replace(',', ' ')


def check(calls: int, what: str, *, confirm_above=None, refuse_above=None,
          assume_yes=False, breakdown='') -> None:
    """Let `calls` paid calls through, ask about them, or refuse them."""
    confirm_above = CONFIRM_ABOVE if confirm_above is None else confirm_above
    refuse_above = REFUSE_ABOVE if refuse_above is None else refuse_above

    if calls <= confirm_above or assume_yes:
        return

    detail = f' ({breakdown})' if breakdown else ''
    headline = f'{what}: {_thousands(calls)} paid calls{detail}'

    if calls > refuse_above:
        raise SpendRefused(
            f'\n{headline}\n\n'
            f'  That is above the limit of {_thousands(refuse_above)} calls,'
            f' and it is\n'
            f'  usually a mistyped option rather than an intention. Check the\n'
            f'  levels, the replicates and the models.\n\n'
            f'  If you did mean it:  --max-calls {calls}\n'
        )

    if not sys.stdin.isatty():
        # Nobody to ask: under the hard limit, say the figure and go on.
        print(f'  {headline} — proceeding', flush=True)
        return

    print(f'\n{headline}')
    answer = input('  Proceed? [y/N] ').strip().lower()
    if answer not in ('y', 'yes'):
        raise SpendRefused('\nStopped: nothing was called, nothing was paid.\n')
