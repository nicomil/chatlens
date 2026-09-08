"""The thing an analysis is trying to explain.

Until now this tool described text: how much of it, how positive, which topics.
Describing is where it stops — nothing in it knows what the text was *for*. The
analyses worth having all predict something: which words go with being supported,
which relations matter, whether speaking at all is what counts.

So an experiment may declare an outcome:

    [outcome]
    column = "persuasion_ij"
    kind   = "binary"
    unit   = "dyad_directed"
    label  = "j chose i"

**The unit is the point of the declaration.** The same experiment can carry an
outcome per directed pair (did j choose i), per person (how much i earned) or per
group (did they reach agreement), and these are not interchangeable: a model
fitted at the wrong one silently repeats each group's value across its members
and reports a precision it has not got.

The column is looked for in the dataset built for that unit, which is what the
pipeline already produces. Nothing here computes an outcome — the adapter carries
it through from the experiment's own export, because what counts as success is a
fact about the experiment and not something a text tool can work out.

An experiment with no `[outcome]` keeps working. Everything descriptive is
unaffected; only the predictive pages are unavailable, and they say so rather
than guessing.
"""

from __future__ import annotations

from collections import Counter

KINDS = ('binary', 'continuous')

# The four the aggregation already knows, with a plain-English gloss: the TOML
# names are ours and mean nothing to someone meeting them for the first time.
UNITS = {
    'dyad_directed': 'one directed pair — what i wrote to j',
    'dyad': 'one pair, both directions',
    'sender_group': 'one person, everything they wrote',
    'group': 'one whole group',
}

# Which built dataset holds each unit. The two finer units live in the same
# file, one row per directed pair; the coarser ones are rolled up into the
# aggregated file.
DATASET_OF = {
    'dyad_directed': 'chat_by_partner',
    'dyad': 'chat_by_partner',
    'sender_group': 'chat_aggregated',
    'group': 'chat_aggregated',
}


class OutcomeError(ValueError):
    """The declaration cannot be used as it stands."""


def parse(block) -> dict | None:
    """Read the `[outcome]` table, or None if the experiment declared none."""
    block = dict(block or {})
    if not block:
        return None
    outcome = {
        'column': str(block.get('column') or '').strip(),
        'kind': str(block.get('kind') or 'binary').strip().lower(),
        'unit': str(block.get('unit') or 'dyad_directed').strip(),
        'label': str(block.get('label') or '').strip(),
    }
    if not outcome['label']:
        outcome['label'] = outcome['column']
    return outcome


def problems(outcome) -> list[str]:
    """Everything wrong with the declaration, in words the interface can show.

    Returned rather than raised: the configuration page wants to show all of
    them at once, not the first one and then another after the next save.
    """
    if not outcome:
        return []
    found = []
    if not outcome.get('column'):
        found.append('No column is set: choose the one holding the outcome.')
    if outcome.get('kind') not in KINDS:
        found.append(f'Kind must be one of {", ".join(KINDS)}, '
                     f'not "{outcome.get("kind")}".')
    if outcome.get('unit') not in UNITS:
        found.append(f'Unit must be one of {", ".join(UNITS)}, '
                     f'not "{outcome.get("unit")}".')
    return found


def check(outcome) -> None:
    """As `problems`, but for callers that cannot show a list."""
    found = problems(outcome)
    if found:
        raise OutcomeError(' '.join(found))


def describe(rows, outcome) -> dict:
    """What the column actually contains, so a wrong choice is visible at once.

    A column that turns out to be a participant code or a timestamp looks
    obviously wrong the moment its distribution is shown, and looks like nothing
    at all until then.
    """
    column = outcome['column']
    present = [r.get(column) for r in rows if r.get(column) not in (None, '')]
    summary = {'rows': len(rows), 'set': len(present),
               'empty': len(rows) - len(present), 'kind': outcome['kind'],
               'usable': False, 'note': ''}

    if not present:
        summary['note'] = ('The column is empty in every row, or is not in this '
                           'dataset.')
        return summary

    if outcome['kind'] == 'binary':
        counts = Counter(str(v).strip() for v in present)
        summary['values'] = counts.most_common(6)
        binary = set(counts) <= {'0', '1', 'True', 'False', 'true', 'false'}
        if not binary:
            summary['note'] = (f'{len(counts)} distinct values, which is not '
                               f'binary. Change the kind, or the column.')
            return summary
        ones = sum(n for v, n in counts.items() if v in ('1', 'True', 'true'))
        summary['positive'] = ones
        summary['share'] = ones / len(present)
        # An outcome that almost never happens cannot be predicted from a few
        # hundred rows, and saying so now is cheaper than a page of empty models.
        if summary['share'] in (0.0, 1.0):
            summary['note'] = 'Every row has the same value: nothing to explain.'
            return summary
        if min(summary['share'], 1 - summary['share']) < 0.02:
            summary['note'] = ('Fewer than 2% of rows are in the smaller class. '
                               'Models on this will be unstable.')
    else:
        numbers = []
        for value in present:
            try:
                numbers.append(float(value))
            except (TypeError, ValueError):
                pass
        if len(numbers) < len(present) * 0.9:
            summary['note'] = ('Most values are not numbers. Change the kind, '
                               'or the column.')
            return summary
        numbers.sort()
        summary['min'] = numbers[0]
        summary['max'] = numbers[-1]
        summary['median'] = numbers[len(numbers) // 2]
        summary['mean'] = sum(numbers) / len(numbers)
        if summary['min'] == summary['max']:
            summary['note'] = 'Every row has the same value: nothing to explain.'
            return summary

    summary['usable'] = True
    return summary
