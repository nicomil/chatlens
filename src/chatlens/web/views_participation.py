"""The participation page: who spoke to whom, and who did not.

Every other page in this tool measures text, and can therefore only see the
pairs that produced some. This one shows the whole grid, which is where the
strongest result on the experiment it was built for turned out to be.
"""

from __future__ import annotations

import csv
from pathlib import Path

from chatlens.core import tables

from chatlens.web import ui

csv.field_size_limit(10 ** 7)


_e = ui.esc


def _read(path: Path):
    return tables.read(path)


def _latest(directory: Path, suffix: str):
    """The table this workspace is currently working on.

    A workspace accumulates tables — a pilot merged in August sits beside the
    full collection merged in September, both matching the same glob. Sorting by
    name picks whichever happens to sort first, which on real filenames is the
    dated pilot, and the page would then describe the wrong study without
    saying so. The stem of the declared input is the authority; failing that,
    the most recently written file.
    """
    from chatlens.core import config

    found = list(directory.glob(f'*{suffix}'))
    if not found:
        return None
    try:
        stem = config.dataset_stem(config.find_input('wide'))
    except Exception:            # no input declared, or none on disk yet
        stem = None
    if stem:
        exact = [p for p in found if p.name == f'{stem}{suffix}']
        if exact:
            return exact[0]
    return max(found, key=lambda p: p.stat().st_mtime)


def _sources():
    """The three files this page can use, whichever of them exist."""
    from chatlens.core import config

    merged = config.MERGED_DIR
    return (_latest(merged, '_messages_long.csv'),
            _latest(merged, '_chat_aggregated.csv'),
            _latest(merged, '_chat_by_partner.csv'))


def _outcomes(by_partner_path, outcome):
    """The declared outcome, keyed by directed pair, if there is one."""
    from chatlens.core import outcome as outcome_module

    if by_partner_path is None or not outcome:
        return {}, ''
    if outcome['unit'] != 'dyad_directed':
        return {}, (f'The outcome is declared per '
                    f'{outcome["unit"].replace("_", " ")}, and this page '
                    f'compares directed pairs. Only the grid is shown.')
    if outcome['kind'] != 'binary':
        return {}, ('The outcome is continuous; the comparisons below need a '
                    'yes/no one. Only the grid is shown.')

    rows = _read(by_partner_path)
    column = outcome['column']
    if rows and column not in rows[0]:
        return {}, (f'{_e(by_partner_path.name)} has no column '
                    f'"{_e(column)}".')
    values = {}
    for row in rows:
        found = outcome_module.as_binary(row.get(column))
        if found is not None:
            values[(row['group_uid'], row['focal_id_in_group'],
                    row['partner_id_in_group'])] = found
    return values, ''


def _matrix(grid: dict) -> str:
    """The grid itself, which this page was named after and never showed.

    Rows are who wrote, columns are who was written to, and the number in each
    cell is the share of groups in which anything at all went that way. A cell
    at zero is the finding: it is a direction nobody used, and it is invisible
    in every other page here because those pages can only measure text that
    exists.
    """
    if not grid['seats']:
        return ui.empty('No pairs to lay out yet.')
    if not grid['comparable']:
        return ui.empty(
            f'This design has {len(grid["seats"])} seats, too many to lay out '
            f'as a readable grid. The distribution below still holds.')

    seats = grid['seats']
    head = ''.join(f'<th class="num">to {_e(s)}</th>' for s in seats)
    rows = []
    for sender in seats:
        cells = []
        for receiver in seats:
            if sender == receiver:
                cells.append('<td class="num diag">·</td>')
                continue
            entry = grid['cells'].get((sender, receiver))
            if not entry or not entry['possible']:
                cells.append('<td class="num">—</td>')
                continue
            share = entry['groups'] / entry['possible']
            classes = 'num' + (' silent' if not entry['groups'] else '')
            cells.append(
                f'<td class="{classes}" '
                f'title="{entry["groups"]} of {entry["possible"]} groups, '
                f'{entry["messages"]} messages">{100 * share:.0f}%</td>')
        rows.append(f'<tr><th>from {_e(sender)}</th>{"".join(cells)}</tr>')

    sizes = grid.get('sizes') or []
    mixed = ('' if len(sizes) < 2 else
             f' — the groups here are not all the same size ('
             f'{", ".join(str(s) for s in sizes)} people)')
    return (f'<div class="scroll"><table class="grid matrix">'
            f'<thead><tr><th></th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>'
            f'<p class="muted">The share of groups in which that direction '
            f'carried at least one message, counted against the groups that '
            f'had both seats{mixed}. A zero is a direction nobody used.</p>')


def _histogram(pairs, total_label) -> str:
    """A bar per count, because the shape is the point and a list hides it."""
    if not pairs:
        return ''
    biggest = max(n for _k, n in pairs)
    rows = []
    for used, groups in pairs:
        width = 100 * groups / biggest
        rows.append(
            f'<tr><td class="num">{used}</td>'
            f'<td class="barcell"><span class="bar" style="width:{width:.1f}%">'
            f'</span></td><td class="num">{groups}</td></tr>')
    return (f'<table class="hist"><thead><tr><th class="num">Directions used'
            f'</th><th>{_e(total_label)}</th><th class="num">Groups</th></tr>'
            f'</thead><tbody>{"".join(rows)}</tbody></table>')


def page(name: str) -> str:
    from chatlens.core import config, participation

    experiment = config.EXPERIMENT
    messages_path, roster_path, by_partner_path = _sources()

    if messages_path is None:
        body = ('<p class="muted">No messages table yet. Run the analysis once '
                'and this page fills in — it reads what the merge produces, '
                'and costs nothing.</p>')
        return _shell(name, experiment, body)

    messages = _read(messages_path)
    roster = _read(roster_path) if roster_path else None
    members, source = participation.membership(messages, roster=roster)
    cells = participation.grid(messages, members)
    cover = participation.coverage(cells, members)

    warning = ''
    if source == 'the messages':
        warning = (
            '<p class="formerror">Membership was taken from the messages, '
            'because no roster was available. Anyone who never wrote and was '
            'never written to is invisible, and that is not a small or random '
            'omission — it removes exactly the people this page is about. '
            'Run the analysis to build the aggregated table, or declare a '
            'participants file.</p>')

    stats = f'''<div class="stats">
  <div class="stat"><div class="v">{cover["groups"]}</div>
    <div class="l">groups</div></div>
  <div class="stat"><div class="v">{cover["cells"]}</div>
    <div class="l">possible directed pairs</div></div>
  <div class="stat"><div class="v">{cover["used"]}</div>
    <div class="l">carried at least one message</div></div>
  <div class="stat"><div class="v">{cover["empty"]}</div>
    <div class="l">stayed empty
      ({100 * (1 - cover["share_used"]):.0f}%)</div></div>
</div>'''

    sizes = ', '.join(f'{n} of {count}' for n, count in cover['group_sizes'])
    grid_note = (f'<p class="muted">Membership from <b>{_e(source)}</b>. '
                 f'Group sizes: {_e(sizes)}.</p>')

    outcome = experiment.outcome
    values, note = _outcomes(by_partner_path, outcome)
    sections = ''

    if not outcome:
        sections = ('<h2>What it means for the outcome</h2>'
                    '<p class="muted">No outcome is declared, so there is '
                    'nothing to compare the grid against. Set one under '
                    '<a href="/experiment/' + _e(name) + '/settings">'
                    'Settings</a>.</p>')
    elif note:
        sections = f'<h2>What it means for the outcome</h2><p class="muted">{note}</p>'
    elif values:
        label = _e(outcome['label'] or outcome['column'])
        contrast = participation.contrast(cells, values)
        within = participation.within_receiver(cells, values)

        if contrast:
            sections += f'''<h2>{label}, by whether anything was written</h2>
<div class="scroll"><table class="grid">
<thead><tr><th></th><th class="num">Pairs</th><th class="num">Positive</th>
<th class="num">Share</th></tr></thead>
<tbody>
<tr><td>i wrote to j</td><td class="num">{contrast["wrote"]["n"]}</td>
  <td class="num">{contrast["wrote"]["positive"]}</td>
  <td class="num">{100 * contrast["wrote"]["share"]:.0f}%</td></tr>
<tr><td>i never wrote to j</td><td class="num">{contrast["silent"]["n"]}</td>
  <td class="num">{contrast["silent"]["positive"]}</td>
  <td class="num">{100 * contrast["silent"]["share"]:.0f}%</td></tr>
</tbody></table></div>
<p class="muted">This is the obvious comparison and it should not be read as it
stands. A receiver who can choose only one partner bounds the rate mechanically,
and people who write a lot may simply be different people. The comparison below
removes both.</p>'''

        if within and within['decided']:
            sections += f'''<h2>The same, with the receiver held fixed</h2>
<p class="muted">Among receivers where exactly one of the possible senders wrote
to them, the two candidates face the same person, in the same group, under the
same treatment, and differ in whether they spoke.</p>
<div class="stats">
  <div class="stat"><div class="v">{within["chose_writer"]}</div>
    <div class="l">chose the one who wrote</div></div>
  <div class="stat"><div class="v">{within["chose_silent"]}</div>
    <div class="l">chose the one who stayed silent</div></div>
  <div class="stat"><div class="v">{100 * within["share"]:.0f}%</div>
    <div class="l">n = {within["decided"]}, p = {within["p"]:.1g}</div></div>
</div>
<p class="muted">{within["both_wrote"]} receivers had every possible sender write
to them, and {within["none_wrote"]} had none; those carry no comparison and are
excluded.</p>'''
        elif within is None:
            sections += ('<h2>The same, with the receiver held fixed</h2>'
                         '<p class="muted">Not computable on this design: it '
                         'needs receivers with at least two possible senders, '
                         'so that two candidates can be compared against the '
                         'same person.</p>')

    matrix = _matrix(participation.seat_matrix(cells))
    body = f'''{warning}
<h2>The grid</h2>
{stats}
{matrix}
{grid_note}
{_histogram(cover["directions_histogram"], "How many groups used that many")}
{sections}'''
    return _shell(name, experiment, body)


def _shell(name: str, experiment, body: str) -> str:
    from chatlens.core import config

    # The reasoning is kept and moved: the grid is the page's whole argument,
    # and it used to sit under three lines explaining it.
    why = ui.disclosure(
        'What this page is for',
        '''<p>Every other page measures text, so it can only see the pairs
        that produced some. This one shows the whole grid, including the
        pairs where nothing was said — which is not missing data when
        speaking is a choice.</p>''',
    )
    where = (f'<h2>Where this experiment lives</h2>'
             f'<p class="muted path">{ui.esc(config.WORKSPACE)}</p>')

    return ui.shell(
        f'{experiment.name} — participation',
        f'{why}\n{body}\n{where}',
        heading='Participation',
        slug=name,
        experiment_name=experiment.name,
        current='participation',
        htmx=False,
    )
