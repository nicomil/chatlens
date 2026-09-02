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


def _e(text) -> str:
    return html.escape(str(text if text is not None else ''))


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


def readiness(path: Path, adapter: str) -> tuple[bool, str]:
    """Whether it can be run, and what is missing when it cannot.

    Answered from the adapter's own declaration of what it needs, so a new
    adapter needs no change here.
    """
    try:
        patterns = adapters.inputs(adapter)
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
    ready, missing = readiness(entry['path'], entry['adapter'])
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


def library_list() -> str:
    entries = library.entries()
    if not entries:
        return ('<p class="muted empty-library">No experiments yet. '
                'Make one to get started, or press <b>Try an example</b> to see '
                'the whole procedure on data that belongs to nobody.</p>')
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
  <button type="submit" class="primary">Create</button>
</form>'''


def library_panel(error: str = '') -> str:
    """The whole middle of the library page, swapped as one piece."""
    return f'''<div id="library">
  <h2>Experiments</h2>
  {library_list()}
  <h2>New experiment</h2>
  {new_form(error)}
</div>'''


def library_page() -> str:
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>chatlens</title>
<link rel="stylesheet" href="/static/style.css">
<script src="/static/htmx.min.js"></script>
</head><body class="library">
<header>
  <h1>chatlens</h1>
  <span class="muted">text analysis of experiment conversations</span>
</header>

<main class="single">
  {library_panel()}

  <h2>Where these live</h2>
  <p class="muted path">{_e(library.ROOT)}</p>
  <p class="muted">Each experiment is an ordinary folder holding its files and
  its results, so one can be copied to a colleague or included in a backup.
  This folder is not somewhere you would come across by accident: if these are
  participant data, make sure your backup covers it.</p>
</main>
<script src="/static/app.js"></script>
</body></html>'''


# --- one experiment's settings ---------------------------------------------


def settings_page(name: str) -> str:
    """Everything about one experiment that is not running it."""
    from chatlens.core import config

    experiment = config.EXPERIMENT
    ready, missing = readiness(config.WORKSPACE, experiment.adapter)
    state = ('<span class="badge ok">ready to run</span>' if ready
             else f'<span class="badge warn">needs {_e(missing)}</span>')

    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(experiment.name)} — settings</title>
<link rel="stylesheet" href="/static/style.css">
<script src="/static/htmx.min.js"></script>
</head><body class="library">
<header>
  <a class="back-link" href="/experiment/{_e(name)}">&larr; {_e(experiment.name)}</a>
  <h1>Settings</h1>
  {state}
</header>

<main class="single">
  <h2>Files</h2>
  <div id="files">{files_panel(name)}</div>

  <h2>Where this experiment lives</h2>
  <p class="muted path">{_e(config.WORKSPACE)}</p>
</main>
<script src="/static/app.js"></script>
</body></html>'''


def files_panel(name: str, message: str = '', error: str = '',
                confirm_delete: str = '') -> str:
    """The input files: what is there, what it is taken for, and how to add."""
    from chatlens.core import config

    patterns = adapters.inputs(config.EXPERIMENT.adapter)
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
            label = (f'<span class="badge ok">{_e(role)}</span>' if role
                     else '<span class="badge warn">not recognised</span>')
            if confirm_delete == path.name:
                # Asked in the page rather than in a browser dialog: a native
                # confirm() blocks the page, and this can say what it is about
                # to remove.
                action = (
                    f'<span class="confirm">Remove it?'
                    f'<button class="danger" hx-post="{_base(name)}/files/delete"'
                    f' hx-vals=\'{{"file": "{_e(path.name)}"}}\''
                    f' hx-target="#files" hx-swap="innerHTML">Yes, remove</button>'
                    f'<button hx-get="{_base(name)}/files"'
                    f' hx-target="#files" hx-swap="innerHTML">Keep</button>'
                    f'</span>')
            else:
                action = (
                    f'<button class="linkish" hx-get="{_base(name)}/files"'
                    f' hx-vals=\'{{"confirm": "{_e(path.name)}"}}\''
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
    <span>Add CSV files &mdash; {wanted}</span>
    <input type="file" name="file" accept=".csv,text/csv" multiple required>
  </label>
  <button type="submit" class="primary">Upload</button>
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
        f'hx-vals=\'{{"adapter": "{_e(looks_like)}"}}\' '
        f'hx-target="#files" hx-swap="innerHTML">'
        f'Read them as {_e(title)} instead</button></p>')


# --- one experiment's settings ---------------------------------------------


def settings_page(name: str) -> str:
    """Everything about one experiment that is not running it."""
    from chatlens.core import config

    experiment = config.EXPERIMENT
    ready, missing = readiness(config.WORKSPACE, experiment.adapter)
    state = ('<span class="badge ok">ready to run</span>' if ready
             else f'<span class="badge warn">needs {_e(missing)}</span>')

    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(experiment.name)} — settings</title>
<link rel="stylesheet" href="/static/style.css">
<script src="/static/htmx.min.js"></script>
</head><body class="library">
<header>
  <a class="back-link" href="/experiment/{_e(name)}">&larr; {_e(experiment.name)}</a>
  <h1>Settings</h1>
  {state}
</header>

<main class="single">
  <h2>Files</h2>
  <div id="files">{files_panel(name)}</div>

  <h2>Where this experiment lives</h2>
  <p class="muted path">{_e(config.WORKSPACE)}</p>
</main>
<script src="/static/app.js"></script>
</body></html>'''
