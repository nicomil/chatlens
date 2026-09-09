"""The library: the experiments, and the settings of one of them.

`views.py` renders one experiment being run — the form, the log, the report.
This renders everything around that: what experiments exist, making one, the
files it holds and how its columns map.

No template engine here either, for the same reason as next door: the content
is almost all generated from data, so functions and f-strings do the job and
add no dependency.
"""

from __future__ import annotations

import html
from pathlib import Path

from chatlens import adapters
from chatlens.web import ui
from chatlens.core import library

ADAPTERS = ('generic_chat', 'otree_coalition')

# Per file. The real collection export is 16 MB, so this leaves ample room
# while still being a number rather than "as much as the disk holds".
MAX_UPLOAD = 500 * 1024 * 1024


def _base(name: str) -> str:
    return f'/experiment/{html.escape(str(name))}'

ADAPTER_HELP = {
    'generic_chat': ('One message per row',
                     'Your export already has a row per message, with a group, '
                     'a sender, a recipient and the text. Nothing to write: '
                     'you point at the columns below.'),
    'otree_coalition': ('oTree coalition game',
                        'An oTree export where the groups, the chat channels '
                        'and the choices have to be reconstructed. Written for '
                        'a three-player coalition game.'),
}


_e = ui.esc


def _size(n: int) -> str:
    if not n:
        return '—'
    if n < 1024:
        return f'{n} B'
    if n < 1024 * 1024:
        return f'{n // 1024} KB'
    return f'{n / (1024 * 1024):.1f} MB'


def _when(stamp: str) -> str:
    """A run folder's name, as something readable."""
    if not stamp:
        return 'never run'
    try:
        date, time = stamp.split('_')[:2]
        return f'{date[8:10]}/{date[5:7]} {time[:2]}:{time[2:4]}'
    except (ValueError, IndexError):
        return stamp


# --- what an experiment still needs ----------------------------------------


def input_patterns(adapter: str, overrides=None) -> dict:
    """What this experiment's files are called, role by role.

    The adapter says what it needs and the experiment may say what its own
    files are called — which it does as soon as somebody assigns a role in the
    interface. Reading the adapter alone means an assigned file still counts as
    missing, which is what happened.
    """
    patterns = adapters.inputs(adapter)
    for role, pattern in (overrides or {}).items():
        if role in patterns:
            patterns[role] = pattern
    return patterns


def readiness(path: Path, adapter: str, overrides=None) -> tuple[bool, str]:
    """Whether it can be run, and what is missing when it cannot.

    Answered from the adapter's declaration of what it needs, so a new adapter
    needs no change here.
    """
    try:
        patterns = input_patterns(adapter, overrides)
    except Exception:                    # noqa: BLE001 - unknown adapter
        return False, f'unknown adapter "{adapter}"'

    missing = []
    for role, pattern in patterns.items():
        if pattern is None:
            continue                     # optional
        if not sorted((path / 'input').glob(pattern)):
            missing.append(role)
    if missing:
        return False, ', '.join(missing)
    return True, ''


# --- the list --------------------------------------------------------------


def _card(entry: dict) -> str:
    ready, missing = readiness(entry['path'], entry['adapter'],
                               entry.get('input'))
    if entry['problem']:
        badge = '<span class="badge ko">configuration error</span>'
    elif ready:
        badge = '<span class="badge ok">ready</span>'
    else:
        badge = f'<span class="badge warn">needs {_e(missing)}</span>'

    return (
        f'<a class="card experiment" href="/experiment/{_e(entry["slug"])}">'
        f'<span class="title">{_e(entry["name"])}</span>'
        f'<span class="meta">{_e(entry["adapter"])} · '
        f'{entry["n_files"]} file{"s" if entry["n_files"] != 1 else ""}'
        f'{" · " + _size(entry["size"]) if entry["size"] else ""} · '
        f'{_e(_when(entry["last_run"]))}</span>'
        f'{badge}'
        f'</a>'
    )


EXAMPLE_BUTTON = (
    '<button class="btn quiet" hx-post="/experiments/example" '
    'hx-target="#library" hx-swap="innerHTML">Try an example</button>')


def library_list() -> str:
    entries = library.entries()
    if not entries:
        # The button this sentence names did not exist. It was the first thing
        # a new user read, and pressing what it told them to press was not
        # possible: the demo was a command line away, which is the one place
        # somebody opening a dashboard is not.
        return ui.empty(
            'No experiments yet. Make one from your own export, or try the '
            'example — a synthetic study that belongs to nobody, with the '
            'whole procedure already set up on it.',
            action=EXAMPLE_BUTTON)
    return '<div class="cards experiments">' + ''.join(
        _card(e) for e in entries) + '</div>'


def _adapter_choices(selected='generic_chat') -> str:
    out = []
    for name in ADAPTERS:
        title, description = ADAPTER_HELP[name]
        checked = ' checked' if name == selected else ''
        on = ' on' if name == selected else ''
        out.append(
            f'<label class="preset{on}">'
            f'<input type="radio" name="adapter" value="{_e(name)}"{checked}>'
            f'<span class="nome">{_e(title)}</span>'
            f'<span class="desc">{_e(description)}</span></label>'
        )
    return f'<div class="presets">{"".join(out)}</div>'


def new_form(error: str = '') -> str:
    problem = (f'<p class="formerror">{_e(error)}</p>') if error else ''
    return f'''<form id="newexp" hx-post="/experiments/new"
      hx-target="#library" hx-swap="innerHTML">
  {problem}
  <label class="field"><span>Name of the experiment</span>
    <input type="text" name="name" required maxlength="80" autocomplete="off"
           placeholder="Ultimatum with pre-play chat">
  </label>
  <p class="muted">What shape is your data in?</p>
  {_adapter_choices()}
  <button type="submit" class="btn primary">Create</button>
</form>'''


def library_panel(error: str = '', message: str = '') -> str:
    """The whole middle of the library page, swapped as one piece.

    The experiments come first and the form to make another is folded away.
    It used to be the other way round: a returning user, who wants to open one
    of the studies they already have, met a small card and then a form filling
    the screen for the thing they were not doing.
    """
    entries = library.entries()
    note = ui.notice(_e(message), 'good') if message else ''
    # Open when there is nothing to choose from instead, or when the last
    # attempt failed and the message is inside it.
    unfolded = ' open' if error or not entries else ''
    # "Another" is wrong when there is not a first one yet.
    summary = 'Add another experiment' if entries else 'New experiment'

    return f'''<div id="library">
  {note}
  <h2>Experiments</h2>
  {library_list()}
  <details class="explain newexp"{unfolded}>
    <summary>{summary}</summary>
    <div class="explainbody">{new_form(error)}</div>
  </details>
  {'' if not entries else '<p class="muted">' + EXAMPLE_BUTTON
   + ' &nbsp;a synthetic study, set up and ready to run.</p>'}
</div>'''


def library_page() -> str:
    where = ui.disclosure(
        'Where these live, and what to back up',
        f'''<p class="path">{_e(library.ROOT)}</p>
        <p>Each experiment is an ordinary folder holding its files and its
        results, so one can be copied to a colleague or included in a backup.
        This folder is not somewhere you would come across by accident: if
        these are participant data, make sure your backup covers it.</p>''',
    )
    # No spine here: choosing which study to open is not a step of a study.
    return ui.shell(
        'chatlens',
        f'''<p class="eyebrow">Your studies</p>
        <h1 class="question">Text analysis of experiment conversations</h1>
        <p class="lead">Each study is a folder of its own: its export, its
        settings and its results. Open one to carry on, or make another.</p>
        {library_panel()}
        {where}''',
    )


# --- the column mapping ----------------------------------------------------

ROLE_LABELS = {
    'group': ('Group', 'what puts participants in the same conversation'),
    'sender': ('Sender', 'who wrote the message'),
    'receiver': ('Recipient', 'who it was addressed to'),
    'body': ('Text', 'the message itself'),
    'timestamp': ('Time', 'when it was sent — epoch seconds or ISO 8601'),
    'treatment': ('Treatment', 'the experimental condition'),
}

REQUIRED_ROLES = ('group', 'sender', 'receiver', 'body')

# The adapters' input roles, said in words. The dropdown listed the raw keys —
# "wide", "chat", "participants" — which name the concept inside the code and
# not the file the person is looking at.
INPUT_LABELS = {
    'messages': 'the messages, one per row',
    'participants': 'the participants, one per row',
    'wide': "oTree's all-apps-wide export",
    'chat': "oTree's chat messages export",
}


def _input_label(role: str) -> str:
    return INPUT_LABELS.get(role, role)


def files_panel(name: str, message: str = '', error: str = '',
                confirm_delete: str = '') -> str:
    """The input files: what is there, what it is taken for, and how to add."""
    from chatlens.core import config

    # The effective patterns, not the adapter's: a file whose role was
    # assigned here is named in the experiment, and reading the adapter
    # alone showed it as unused right after it had been assigned.
    patterns = config.INPUT_PATTERNS
    wanted = ', '.join(f'<code>{_e(p)}</code>'
                       for p in patterns.values() if p)
    files = sorted((config.WORKSPACE / 'input').glob('*.csv'))

    notes = ''
    if error:
        notes += f'<p class="formerror">{_e(error)}</p>'
    if message:
        notes += f'<p class="formnote">{_e(message)}</p>'

    if not files:
        table = (f'<p class="muted">Nothing here yet. This adapter reads '
                 f'{wanted}.</p>')
    else:
        rows = []
        for path in files:
            role = next((r for r, pattern in patterns.items()
                         if pattern and path.match(pattern)), '')
            # A dropdown rather than a verdict: an export called
            # "chat_log.csv" is not "messages*.csv", and the answer to that
            # cannot be "rename your file" when the whole point is that nobody
            # has to touch a file manager.
            options = ['<option value="">not used</option>']
            for candidate in patterns:
                mark = ' selected' if candidate == role else ''
                options.append(f'<option value="{_e(candidate)}"{mark}>'
                               f'{_e(_input_label(candidate))}</option>')
            label = (
                f'<select name="role" hx-post="{_base(name)}/input"'
                f' {ui.hx_vals(file=path.name)}'
                f' hx-target="#files" hx-swap="innerHTML"'
                f' hx-trigger="change">{"".join(options)}</select>')
            if confirm_delete == path.name:
                # Asked in the page rather than in a browser dialog: a native
                # confirm() blocks the page, and this can say what it is about
                # to remove.
                action = (
                    f'<span class="confirm">Remove it?'
                    f'<button class="btn danger" hx-post="{_base(name)}/files/delete"'
                    f' {ui.hx_vals(file=path.name)}'
                    f' hx-target="#files" hx-swap="innerHTML">Yes, remove</button>'
                    f'<button class="btn quiet" hx-get="{_base(name)}/files"'
                    f' hx-target="#files" hx-swap="innerHTML">Keep</button>'
                    f'</span>')
            else:
                action = (
                    f'<button class="linkish" hx-get="{_base(name)}/files"'
                    f' {ui.hx_vals(confirm=path.name)}'
                    f' hx-target="#files" hx-swap="innerHTML">remove</button>')
            rows.append(
                f'<tr><td>{_e(path.name)}</td>'
                f'<td class="num muted">{_size(path.stat().st_size)}</td>'
                f'<td>{label}</td><td class="act">{action}</td></tr>')
        table = (f'<table class="mini files"><tbody>{"".join(rows)}</tbody>'
                 f'</table>')

    suggestion = _adapter_suggestion(name, files)

    return f'''{notes}{table}{suggestion}
<form class="upload" hx-post="{_base(name)}/upload" hx-encoding="multipart/form-data"
      hx-target="#files" hx-swap="innerHTML"
      hx-indicator="#uploading">
  <label class="field">
    <span>Add CSV files</span>
    <input type="file" name="file" accept=".csv,text/csv" multiple required>
    <span class="rolehint">This adapter reads {wanted}.</span>
  </label>
  <button type="submit" class="btn primary">Upload</button>
  <span id="uploading" class="htmx-indicator muted">uploading&hellip;</span>
</form>
<p class="muted small">Up to {MAX_UPLOAD // (1024 * 1024)} MB per file. A file
with the same name replaces the one that is there.</p>'''


def _adapter_suggestion(name: str, files) -> str:
    """Offer the adapter the files look like, where it is not the one set.

    Proposed, never applied on its own: which adapter reads an export is a
    decision about the data, and the files only hint at it.
    """
    from chatlens.core import config

    if not files:
        return ''
    names = [f.name for f in files]
    looks_like = None
    if any(n.startswith('all_apps_wide') for n in names) and any(
            n.startswith('ChatMessages') for n in names):
        looks_like = 'otree_coalition'
    if not looks_like or looks_like == config.EXPERIMENT.adapter:
        return ''
    title = ADAPTER_HELP[looks_like][0]
    return (
        f'<p class="formnote">These look like an oTree export, and this '
        f'experiment is set to read them as '
        f'<b>{_e(ADAPTER_HELP[config.EXPERIMENT.adapter][0])}</b>. '
        f'<button class="linkish" hx-post="{_base(name)}/adapter" '
        f'{ui.hx_vals(adapter=looks_like)} '
        f'hx-target="#files" hx-swap="innerHTML">'
        f'Read them as {_e(title)} instead</button></p>')




def _messages_file():
    """The file the column mapping is about, if it is there."""
    from chatlens.core import config

    pattern = config.INPUT_PATTERNS.get('messages')
    if not pattern:
        return None
    found = sorted((config.WORKSPACE / 'input').glob(pattern))
    return found[0] if found else None


def _select(role: str, columns, selected: str) -> str:
    label, hint = ROLE_LABELS[role]
    required = role in REQUIRED_ROLES
    options = ['<option value="">— not set —</option>']
    for column in columns:
        mark = ' selected' if column == selected else ''
        options.append(f'<option value="{_e(column)}"{mark}>{_e(column)}</option>')
    return (
        f'<label class="field maprow">'
        f'<span class="rolename">{_e(label)}'
        f'{"" if required else " <i>(optional)</i>"}</span>'
        f'<select name="col_{_e(role)}">{"".join(options)}</select>'
        f'<span class="rolehint">{_e(hint)}</span></label>'
    )


def columns_panel(name: str, message: str = '', error: str = '') -> str:
    """Point each role at a column, chosen from the ones the file has."""
    from chatlens.core import config, inspect

    experiment = config.EXPERIMENT
    notes = (f'<p class="formerror">{_e(error)}</p>' if error else '')
    notes += (f'<p class="formnote">{_e(message)}</p>' if message else '')

    if experiment.adapter != 'generic_chat':
        return (f'{notes}<p class="muted">The <b>'
                f'{_e(ADAPTER_HELP[experiment.adapter][0])}</b> adapter reads '
                f'the export directly and works out the groups, the senders '
                f'and the text itself. There is nothing to map.</p>')

    path = _messages_file()
    if path is None:
        return (f'{notes}<p class="muted">Upload the messages file first: the '
                f'columns are read from it, so there is nothing to choose '
                f'until it is here.</p>')

    try:
        columns = inspect.header_of(path)
    except inspect.ReadError as exc:
        return f'{notes}<p class="formerror">{_e(exc)}</p>'

    # What was saved, else a guess from the column names. The guess is right
    # often enough that the usual action is to confirm it.
    declared = experiment.declared.get('columns') or {}
    guessed = inspect.guess(columns)
    chosen = {role: declared.get(role) or guessed.get(role, '')
              for role in ROLE_LABELS}
    # A saved name that is no longer in the file would silently select nothing.
    stale = [f'{ROLE_LABELS[r][0]} → {v}' for r, v in declared.items()
             if r in ROLE_LABELS and v and v not in columns]
    if stale:
        notes += (f'<p class="formerror">These were set to columns the file no '
                  f'longer has: {_e(", ".join(stale))}. Choose again.</p>')

    rows = ''.join(_select(role, columns, chosen.get(role, ''))
                   for role in ROLE_LABELS)
    return f'''{notes}
<p class="muted">Read from <b>{_e(path.name)}</b>, {len(columns)} columns.</p>
<form hx-post="{_base(name)}/columns" hx-target="#columns" hx-swap="innerHTML">
  <div class="mapping">{rows}</div>
  <button type="submit" class="btn primary">Save</button>
</form>'''


def treatments_panel(name: str, message: str = '') -> str:
    """A label for each value the treatment column actually takes."""
    from chatlens.core import config, inspect

    experiment = config.EXPERIMENT
    notes = (f'<p class="formnote">{_e(message)}</p>' if message else '')

    column = (experiment.declared.get('columns') or {}).get('treatment')
    if experiment.adapter != 'generic_chat' or not column:
        saved = experiment.declared.get('treatments') or {}
        if not saved:
            return (f'{notes}<p class="muted">Set the treatment column above '
                    f'and its values will appear here, to be named.</p>')
        rows = ''.join(
            f'<tr><td><code>{_e(k)}</code></td><td>{_e(v)}</td></tr>'
            for k, v in saved.items())
        return (f'{notes}<table class="mini"><tbody>{rows}</tbody></table>'
                f'<p class="muted small">These come from the configuration '
                f'file.</p>')

    path = _messages_file()
    values = inspect.distinct(path, column) if path else []
    if not values:
        return (f'{notes}<p class="muted">No values found in '
                f'<code>{_e(column)}</code>, or too many for it to be a '
                f'treatment.</p>')

    saved = experiment.declared.get('treatments') or {}
    fields = ''.join(
        f'<label class="field maprow"><span class="rolename">'
        f'<code>{_e(value)}</code></span>'
        f'<input type="text" name="tr_{_e(value)}" maxlength="60" '
        f'value="{_e(saved.get(value, value))}"></label>'
        for value in values)
    return f'''{notes}
<p class="muted">Found in <code>{_e(column)}</code>. The name on the right is
what the report will print.</p>
<form hx-post="{_base(name)}/treatments" hx-target="#treatments"
      hx-swap="innerHTML">
  <div class="mapping">{fields}</div>
  <button type="submit" class="btn primary">Save</button>
</form>'''


# --- one experiment's settings ---------------------------------------------


def _outcome_columns(unit: str):
    """The columns of the built dataset for this unit, if it has been built.

    The outcome lives in the dataset the pipeline produces, not in the raw
    export, because that is where the adapter has already put one row per unit.
    Before the first run there is no such file, and the field falls back to
    typing the name — which is the honest option: we cannot offer a list we do
    not have.
    """
    from chatlens.core import config, inspect, outcome as outcome_module

    stem_files = sorted(config.DATASETS_DIR.glob(
        f'*_{outcome_module.DATASET_OF.get(unit, "chat_by_partner")}_nlp.csv'))
    if not stem_files:
        return None, None
    try:
        return inspect.header_of(stem_files[0]), stem_files[0]
    except inspect.ReadError:
        return None, stem_files[0]


def _outcome_summary(outcome) -> str:
    """What the chosen column holds, so a wrong choice shows up immediately."""
    import csv

    from chatlens.core import outcome as outcome_module

    columns, path = _outcome_columns(outcome['unit'])
    if path is None:
        return ('<p class="muted">No dataset has been built yet, so the column '
                'cannot be checked. Run the analysis once and this will fill '
                'in.</p>')
    if columns is not None and outcome['column'] not in columns:
        return (f'<p class="formerror">{_e(path.name)} has no column '
                f'<b>{_e(outcome["column"])}</b>. It may belong to a different '
                f'unit, or the name may have changed.</p>')
    try:
        with path.open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        return f'<p class="formerror">{_e(exc)}</p>'

    found = outcome_module.describe(rows, outcome)
    bits = [f'{found["set"]} of {found["rows"]} rows have a value']
    if found['kind'] == 'binary' and 'share' in found:
        bits.append(f'{found["positive"]} of them are 1 '
                    f'({100 * found["share"]:.0f}%)')
    elif found['kind'] == 'continuous' and 'median' in found:
        bits.append(f'median {found["median"]:g}, '
                    f'range {found["min"]:g} to {found["max"]:g}')
    note = (f'<p class="formerror">{_e(found["note"])}</p>' if found['note']
            else '')
    badge = ('<span class="badge ok">usable</span>' if found['usable']
             else '<span class="badge warn">not usable</span>')
    return (f'<p class="muted">{badge} {_e(" — ".join(bits))}, '
            f'in {_e(path.name)}.</p>{note}')


def outcome_panel(name: str, message: str = '', error: str = '') -> str:
    """What the experiment is trying to explain, if anything."""
    from chatlens.core import config, outcome as outcome_module

    experiment = config.EXPERIMENT
    notes = (f'<p class="formerror">{_e(error)}</p>' if error else '')
    notes += (f'<p class="formnote">{_e(message)}</p>' if message else '')

    current = experiment.outcome or {'column': '', 'kind': 'binary',
                                     'unit': 'dyad_directed', 'label': ''}
    columns, _path = _outcome_columns(current['unit'])

    if columns:
        options = ['<option value="">— none —</option>']
        for column in columns:
            mark = ' selected' if column == current['column'] else ''
            options.append(f'<option value="{_e(column)}"{mark}>'
                           f'{_e(column)}</option>')
        field = f'<select name="column">{"".join(options)}</select>'
    else:
        field = (f'<input type="text" name="column" '
                 f'value="{_e(current["column"])}" '
                 f'placeholder="column name">')

    kinds = ''.join(
        f'<option value="{k}"{" selected" if k == current["kind"] else ""}>'
        f'{k}</option>' for k in outcome_module.KINDS)
    units = ''.join(
        f'<option value="{u}"{" selected" if u == current["unit"] else ""}>'
        f'{_e(gloss)}</option>'
        for u, gloss in outcome_module.UNITS.items())

    summary = _outcome_summary(current) if current['column'] else (
        '<p class="muted">Nothing is set. Everything descriptive works without '
        'an outcome; the pages that predict one will say it is missing.</p>')

    return f'''{notes}
<p class="muted">The column holding what the analysis should explain — whether a
proposal was accepted, how much someone earned, whether a group agreed. It is
read from the dataset built for the unit you choose.</p>
<form hx-post="{_base(name)}/outcome" hx-target="#outcome" hx-swap="innerHTML">
  <div class="mapping">
    <label class="field maprow"><span class="rolename">Column</span>
      {field}
      <span class="rolehint">what to explain</span></label>
    <label class="field maprow"><span class="rolename">Kind</span>
      <select name="kind">{kinds}</select>
      <span class="rolehint">binary for yes/no, continuous for a number</span></label>
    <label class="field maprow"><span class="rolename">One row is</span>
      <select name="unit">{units}</select>
      <span class="rolehint">the unit the outcome belongs to</span></label>
    <label class="field maprow"><span class="rolename">Name</span>
      <input type="text" name="label" value="{_e(current.get("label") or "")}"
             placeholder="optional, for the report">
      <span class="rolehint">how it should read on a page</span></label>
  </div>
  <button type="submit" class="btn primary">Save</button>
</form>
{summary}'''


def _shell(name: str, step: str, title: str, lead: str, body: str,
           next_step: str = '', next_label: str = '') -> str:
    """One step of the study, on the spine.

    The four steps used to be four sections of one long page with three
    differently worded save buttons, and nothing said which of them still
    needed attention. Now each is a screen with one decision on it, and the
    spine above says where it sits in the whole.
    """
    from chatlens.core import config
    from chatlens.web import study as study_state

    experiment = config.EXPERIMENT
    numbers = {key: index for index, (key, _l, _h)
               in enumerate(ui.STEPS, start=1)}
    onward = f'{_base(name)}/step/{next_step}' if next_step else ''

    return ui.shell(
        f'{experiment.name} — {title.lower()}',
        ui.step_page(numbers[step], title, lead, body,
                     next_label=next_label, next_href=onward),
        slug=name,
        study=experiment.name,
        steps=study_state.step_state(experiment),
        step=step,
    )


def step_data(name: str) -> str:
    """Step 1: the export, and what each file is."""
    from chatlens.core import config

    experiment = config.EXPERIMENT
    ready, missing = readiness(config.WORKSPACE, experiment.adapter,
                               experiment.declared.get('input'))
    lead = ('The CSVs this study is built from. Each one has to be given a '
            'part to play — which file is the messages, which the '
            'participants — because the same export can be shaped in more '
            'than one way.')
    state = ('' if ready else
             ui.notice(f'Not ready yet: {_e(missing)} still missing.', 'warn'))
    where = ui.disclosure(
        'Where this study lives',
        f'<p class="path">{_e(config.WORKSPACE)}</p>')
    remove = ui.disclosure(
        'Take this study out of the list',
        f'''<p>Nothing is deleted. A marker file hides it from the library and
        the folder stays exactly where it is, with the data and the results in
        it — delete that file to bring it back.</p>
        <p><button class="btn danger" hx-post="{_base(name)}/archive"
           hx-target="body">Take it out of the list</button></p>''')

    body = (f'{state}<div id="files">{files_panel(name)}</div>'
            f'{where}{remove}')
    return _shell(name, 'data', 'The data', lead, body,
                  next_step='columns', next_label='Columns')


def step_columns(name: str) -> str:
    """Step 2: which column plays which part, and what to call each treatment."""
    lead = ('Four columns are needed — the group, the sender, the recipient '
            'and the text. Time and treatment are used if they are there. The '
            'names are read from the file itself, so nothing has to be typed.')
    body = (f'<div id="columns">{columns_panel(name)}</div>'
            f'<h2>Treatments</h2>'
            f'<div id="treatments">{treatments_panel(name)}</div>')
    return _shell(name, 'columns', 'Which column is which', lead, body,
                  next_step='outcome', next_label='Outcome')


def step_outcome(name: str) -> str:
    """Step 3: what the analysis is trying to explain."""
    lead = ('The column the analysis should explain — whether an offer was '
            'accepted, how much someone earned, whether a group agreed. '
            'Everything descriptive works without one; the four findings that '
            'explain something do not exist without it.')
    body = f'<div id="outcome">{outcome_panel(name)}</div>'
    return _shell(name, 'outcome', 'What to explain', lead, body,
                  next_step='run', next_label='Run it')
