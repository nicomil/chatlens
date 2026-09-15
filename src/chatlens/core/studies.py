"""The samples an experiment is analysed as, when it is more than one.

One collection of sessions can be the material of two papers. The experiment
this tool grew out of is a 2x2 with one cell not run, and the two comparisons it
supports are:

    baseline vs public            communication becomes observable
    baseline vs private_no_dwl    the payoff rule changes

Those are two studies and not one. They share the baseline arm, they differ on
different dimensions, and nothing is learnt by putting a number from the first
beside a number from the second — the two conditions being compared differ in
two respects at once. So they are written up separately, with a replication
package each.

**Why the tool has to know.** Three kinds of number here are computed over "the
sample", and the sample is exactly what a study declares:

- the standardised language indices. `text_metrics.standardize` takes the mean
  and the standard deviation of the units it is given, by design — the indices
  are relative to the study, not to an external corpus — so `clout_100` on the
  baseline-plus-public sample is a different number from `clout_100` on the
  baseline-plus-slacker sample, for the same participant;
- the lasso's vocabulary, its penalty path and every AUC, all of which are
  properties of the rows they were fitted on;
- the multiple-testing corrections, whose family is the tests of one paper.

Declared in the experiment's own file, as an array of tables:

    [[studies]]
    slug       = "study1"
    name       = "Study 1 — public communication"
    treatments = ["private", "public"]
    baseline   = "private"

    [[studies]]
    slug       = "study2"
    name       = "Study 2 — slacker (no deadweight loss)"
    treatments = ["private", "private_no_dwl"]
    baseline   = "private"

An experiment that declares none keeps behaving exactly as before: one sample,
everything pooled. That is the right default — most experiments are one study —
and it is what every test written before this module assumes.

Nothing here computes a measure. It says which rows belong to which study, and
the callers do their own work on the subset.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# What a slug may contain. It becomes a folder name under `output/studies/`, so
# the same rule as everywhere else in this project: no separators, nothing a
# shell or a path would read as structure.
SLUG = re.compile(r'^[a-z0-9][a-z0-9_-]{0,30}$')

KEYS = {'slug', 'name', 'treatments', 'baseline'}


class StudyError(ValueError):
    """A declaration that cannot be used as it stands."""


@dataclass(frozen=True)
class Study:
    """One sample, and what it is called in the paper it belongs to."""

    slug: str
    name: str
    treatments: tuple
    baseline: str

    def holds(self, treatment) -> bool:
        """Is a row with this treatment part of this study's sample?"""
        return str(treatment or '').strip() in self.treatments

    @property
    def others(self) -> tuple:
        """The arms compared against the baseline, in declared order."""
        return tuple(t for t in self.treatments if t != self.baseline)

    def describe(self) -> str:
        against = ' + '.join(self.others) or '(nothing to compare)'
        return f'{self.name}: {self.baseline} vs {against}'


def parse(block) -> tuple:
    """Read `[[studies]]`, or return () when the experiment declares none.

    Raises `StudyError` rather than dropping a malformed entry: a study that is
    silently absent means a paper's tables are quietly the pooled ones.
    """
    if not block:
        return ()
    if isinstance(block, dict):
        # A single `[studies]` table instead of `[[studies]]`. Easy to write by
        # mistake and unambiguous to read, so it is accepted as one entry.
        block = [block]

    studies, seen = [], set()
    for index, entry in enumerate(block, start=1):
        if not isinstance(entry, dict):
            raise StudyError(
                f'[[studies]] entry {index} is not a table. Each study is a '
                f'[[studies]] block with slug, name and treatments.')
        strays = sorted(set(entry) - KEYS)
        if strays:
            raise StudyError(
                f'[[studies]] entry {index} has no "{strays[0]}" setting. '
                f'It takes: {", ".join(sorted(KEYS))}.')

        slug = str(entry.get('slug') or '').strip().lower()
        if not SLUG.match(slug):
            raise StudyError(
                f'[[studies]] entry {index}: "{slug}" is not a usable slug. '
                f'It names a folder, so: lower case, digits, dash and '
                f'underscore, starting with a letter or a digit.')
        if slug in seen:
            raise StudyError(f'Two studies are both called "{slug}".')
        seen.add(slug)

        treatments = tuple(str(t).strip() for t in (entry.get('treatments') or [])
                           if str(t).strip())
        if len(treatments) < 2:
            raise StudyError(
                f'Study "{slug}" names {len(treatments)} treatment(s). A study '
                f'is a comparison, so it needs at least two — the baseline and '
                f'what it is compared against.')
        if len(set(treatments)) != len(treatments):
            raise StudyError(f'Study "{slug}" names the same treatment twice.')

        baseline = str(entry.get('baseline') or treatments[0]).strip()
        if baseline not in treatments:
            raise StudyError(
                f'Study "{slug}" has baseline "{baseline}", which is not among '
                f'its treatments ({", ".join(treatments)}).')

        studies.append(Study(slug=slug, name=str(entry.get('name') or slug).strip(),
                             treatments=treatments, baseline=baseline))
    return tuple(studies)


def problems(block) -> list:
    """Everything wrong with the declaration, for a page that shows a list.

    The same shape as `outcome.problems`: returned rather than raised, so the
    interface can show every fault at once instead of one per save.
    """
    try:
        parse(block)
    except StudyError as exc:
        return [str(exc)]
    return []


def to_config(studies) -> list:
    """Back to the plain tables `tomlwrite` writes."""
    return [{'slug': s.slug, 'name': s.name,
             'treatments': list(s.treatments), 'baseline': s.baseline}
            for s in studies]


def find(studies, slug: str):
    """One study by slug, or None."""
    wanted = str(slug or '').strip().lower()
    return next((s for s in studies if s.slug == wanted), None)


# --- selecting a study's rows ----------------------------------------------


def rows_for(study, rows, column: str = 'treatment') -> list:
    """The rows of `rows` that belong to `study`.

    `column` because the treatment is called `treatment` in every table this
    project writes, and naming it here anyway keeps the function usable on a
    table where it is not.
    """
    if study is None:
        return list(rows)
    return [row for row in rows if study.holds(row.get(column))]


def groups_in(rows, column: str = 'group_uid') -> set:
    """The groups present in a set of rows, to carry a selection across tables.

    Selecting the two grafting tables by treatment directly would work, but the
    message table is the authority on which group belongs to which arm — a
    never-grouped row carries no treatment at all, and a row whose treatment is
    blank would silently fall out of both studies. So the groups are taken from
    the messages once and the other tables follow them.
    """
    return {str(row.get(column) or '') for row in rows
            if str(row.get(column) or '')}


def rows_in_groups(rows, groups, column: str = 'group_uid') -> list:
    return [row for row in rows if str(row.get(column) or '') in groups]


def census(study, messages) -> dict:
    """What this study's sample actually holds, for the record it travels with.

    Written beside the data because a reader six months on needs to know the
    sample was 361 groups and not 538, and because the smallest difference the
    design can resolve follows from that count.
    """
    from collections import Counter

    mine = rows_for(study, messages)
    per_arm = Counter(str(m.get('treatment') or '') for m in mine)
    groups = {}
    for message in mine:
        uid = str(message.get('group_uid') or '')
        if uid:
            groups.setdefault(str(message.get('treatment') or ''), set()).add(uid)
    return {
        'slug': None if study is None else study.slug,
        'name': None if study is None else study.name,
        'baseline': None if study is None else study.baseline,
        'treatments': [] if study is None else list(study.treatments),
        'n_messages': len(mine),
        'messages_per_treatment': dict(sorted(per_arm.items())),
        'groups_per_treatment': {k: len(v) for k, v in sorted(groups.items())},
        'n_groups': len(set().union(*groups.values())) if groups else 0,
    }
