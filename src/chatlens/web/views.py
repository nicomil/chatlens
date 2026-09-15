"""
HTML fragments of the dashboard.

No template engine: there are few pages and the content is almost all generated
from data, so f-strings and functions suffice and add no dependency.

Every fragment is a piece htmx swaps into the page: the whole page is built by
composing them, so the partial update and the initial load use the same code and
cannot drift apart.
"""

from __future__ import annotations

import itertools
import re
from pathlib import Path

from chatlens.web import ui
from chatlens.core import archive, config
from chatlens.web import active
from chatlens.web.runner import MODELS_RUBRIC, MODELS_TOPIC
from chatlens.web import runner as runner_module
from chatlens.web.runner import stages as runner_stages

LEVELS = ['group', 'dyad_directed', 'dyad', 'sender_group']

def _noun() -> str:
    """What this experiment calls a group. See core/experiment.py."""
    experiment = getattr(config, 'EXPERIMENT', None)
    return experiment.group_noun if experiment else 'group'


# What each unit of analysis means. These are the terms that appear everywhere
# in the data, and without an explanation at hand they cannot be chosen
# knowingly.
def level_labels() -> dict:
    return {
        'group': ('Group', f"the {_noun()}'s whole conversation"),
        'dyad_directed': ('Directed pair', 'who writes to whom, one direction'),
        'dyad': ('Pair', 'two people, both directions'),
        'sender_group': ('Person', 'everything one person wrote'),
    }


def level_help() -> dict:
    return {
        'group': f"The whole {_noun()}'s conversation: every message exchanged "
                 f'between its members. It is the unit with the most text.',
        'dyad_directed': 'The messages one person sends to another, in a '
                         'single direction. It is the unit of persuasion: who '
                         'speaks matters.',
        'dyad': 'The conversation between two people, in both directions.',
        'sender_group': f'Everything one person wrote in the {_noun()}, '
                        f'whoever it was addressed to.',
    }

OPTION_HELP = {
    'llm': 'Has a language model score the same conversations against an '
           'explicit rubric, to validate the measures computed from the '
           'dictionaries. Consumes paid calls.',
    'topics': "Extracts the conversations' themes with TopicGPT: it first "
              'induces them from the texts, then assigns them to the finer '
              'units. Consumes paid calls.',
    'replicates': 'How many times each text is scored. With more than one you '
                  'get the spread across ratings, that is an estimate of '
                  'measurement error. The cost grows in proportion.',
    'induction': 'The unit on which to discover which themes exist. It needs '
                 'text of some length: on short texts the model recognises '
                 'nothing.',
    'assignment': 'The unit the already discovered themes are attributed to. It '
                  'can be finer than the induction unit: recognising is easier '
                  'than discovering.',
}


PRESETS = [
    dict(id='base', name='Measures only',
         description='Volume, sentiment and the language indices. '
                     'No key, a few seconds.',
         cost='free'),
    dict(id='validation', name='Measures + validation',
         description='Adds the rubric that validates the indices by having a '
                     'model score them.',
         cost='paid'),
    dict(id='full', name='Full analysis',
         description="Also adds the conversations' themes with TopicGPT. This "
                     'is the run that produces everything.',
         cost='paid'),
]


def presets_panel(active='base') -> str:
    """The main choice: what you want to obtain.

    These are real radio inputs, not buttons: one at a time, reachable from the
    keyboard, with a visible state. The detail options mirror them and stay
    editable for anyone who needs to depart from a preset.
    """
    cards = ''.join(
        f'<label class="preset{" on" if p["id"] == active else ""}">'
        f'<input type="radio" name="preset" value="{_e(p["id"])}"'
        f'{" checked" if p["id"] == active else ""}>'
        f'<span class="nome">{_e(p["name"])}</span>'
        f'<span class="costo {"free" if p["cost"] == "free" else "paid"}">'
        f'{_e(p["cost"])}</span>'
        f'<span class="desc">{_e(p["description"])}</span></label>'
        for p in PRESETS
    )
    return f'<div class="presets">{cards}</div>'


def _unit_counts() -> dict:
    """How many units there are per level.

    It makes the choice concrete: "two replicates" says nothing, "about two
    hundred calls" does.

    From the last archived run where there is one, and otherwise counted from
    the merged messages — which is the case that matters, because the first run
    is the one nobody has a figure for and the paid presets are right there on
    the same screen. The page used to say "the estimate appears after the first
    run", so the one time it was most needed it said nothing.
    """
    for run in archive.list_runs(config.OUTPUT_DIR):
        levels = run.get('levels')
        if levels:
            return levels
    return _counts_from_merge()


def _counts_from_merge() -> dict:
    """The units the merge implies, counted without analysing anything.

    The same keys `core/aggregate.py` groups by, so the figure is the one a run
    would produce rather than an approximation of it.
    """
    from chatlens.core import aggregate, tables

    found = sorted(config.MERGED_DIR.glob('*_messages_long.csv'))
    if not found:
        return {}
    try:
        messages = tables.read(found[0])
    except (OSError, ValueError):
        return {}
    counts = {}
    for level, keys in aggregate.LEVEL_KEYS.items():
        counts[level] = len({tuple(str(message.get(key, '')) for key in keys)
                             for message in messages})
    return counts


def estimated_calls(form=None) -> tuple:
    """How many paid calls this configuration implies, and where they go.

    Its own function because two callers need the number rather than the
    sentence: the panel that shows it, and the guard that asks before spending
    it. Returns `(calls, parts)`; `calls` is 0 when there is nothing to go on,
    which is also what it is when nothing is paid for.
    """
    form = form or {}
    counts = _unit_counts()
    if not counts:
        return 0, []

    calls, parts = 0, []
    wanted = runner_stages(form)
    if wanted['llm']:
        levels = [v for v in form.get('llm_level', []) if v in counts]
        try:
            replicates = max(1, int((form.get('llm_replicates') or ['1'])[0] or 1))
        except (TypeError, ValueError):
            replicates = 1
        n = sum(counts[lv] for lv in levels) * replicates
        if n:
            calls += n
            parts.append(f'rubric {n}')
    if wanted['topics']:
        unit = (form.get('topicgpt_unit') or ['group'])[0]
        assign = (form.get('topicgpt_assign_unit') or ['dyad_directed'])[0]
        n = counts.get(unit, 0) + counts.get(assign, 0)
        if n:
            calls += n
            parts.append(f'topics ~{n}')
    return calls, parts


def confirm_panel(form, calls: int, parts) -> str:
    """Asked here, because the command line cannot ask from in here.

    `core/spend.py` stops and waits for a yes above its confirmation threshold —
    at a terminal. The dashboard runs the pipeline as a subprocess with no
    terminal attached, where `isatty()` is false and the guard's own comment says
    it proceeds with the figure printed. So every run the dashboard started under
    the hard ceiling spent whatever it spent, and the only warning was an
    estimate nobody had to read. This is the question, in the one place that can
    ask it.
    """
    from chatlens.core import spend

    detail = f' ({" + ".join(parts)})' if parts else ''
    hidden = ''.join(
        f'<input type="hidden" name="{_e(field)}" value="{_e(value)}">'
        for field, values in (form or {}).items() for value in values)
    return f'''<div id="logbody" class="logbody">
  {ui.notice(
      f'<b>This run makes about {calls} paid calls</b>{_e(detail)}. That is '
      f'above the {spend.CONFIRM_ABOVE} this asks about, and the run itself '
      f'cannot ask: it has no terminal. Ratings already in the cache are not '
      f'paid for twice, so a re-run of the same configuration costs less than '
      f'this.', 'warn')}
  <form hx-post="{active.base()}/run" hx-target="#logwrap"
        hx-swap="innerHTML">
    {hidden}
    <input type="hidden" name="confirmed" value="yes">
    <button type="submit" class="btn danger">Yes, spend it</button>
    <a class="btn quiet" href="{active.base()}/step/run">Go back</a>
  </form>
</div>'''


def estimate_panel(form=None) -> str:
    """Estimate of the calls the current configuration implies."""
    form = form or {}
    counts = _unit_counts()
    live = (f'hx-post="{active.base()}/estimate" '
            'hx-trigger="change from:#launch" '
            'hx-include="#launch" hx-target="this" hx-swap="outerHTML"')
    if not counts:
        return (f'<div id="estimate" class="estimate muted" {live}>The estimate '
                f'appears after the first run.</div>')

    calls = 0
    parts = []
    # The same function the runner uses, so the figure shown is the figure that
    # will be spent. Reading the checkboxes here while the runner read the
    # preset would be an estimate for a different run.
    wanted = runner_stages(form)

    if wanted['llm']:
        levels = [v for v in form.get('llm_level', []) if v in counts]
        # The runner validates this field; the estimate did not, and `int()`
        # on a value from the browser raised inside a handler with no try
        # around it. An unreadable figure means one rating, which is what the
        # form's own default says.
        try:
            replicates = max(1, int((form.get('llm_replicates') or ['1'])[0] or 1))
        except (TypeError, ValueError):
            replicates = 1
        n = sum(counts[lv] for lv in levels) * replicates
        if n:
            calls += n
            parts.append(f'rubric {n}')

    if wanted['topics']:
        unit = (form.get('topicgpt_unit') or ['group'])[0]
        assign = (form.get('topicgpt_assign_unit') or ['dyad_directed'])[0]
        n = counts.get(unit, 0) + counts.get(assign, 0)
        if n:
            calls += n
            parts.append(f'topics ~{n}')

    if not calls:
        return (f'<div id="estimate" class="estimate free" {live}>No paid '
                f'calls · a few seconds</div>')

    # About a second and a half per call, measured on real runs.
    minutes = max(1, round(calls * 1.5 / 60))
    detail = ' + '.join(parts)
    return (f'<div id="estimate" class="estimate paid" {live}>'
            f'<strong>~{calls} calls</strong> ({detail}) · '
            f'about {minutes} min</div>')


_HELP_IDS = itertools.count()


def _help(text: str) -> str:
    """A question mark carrying the explanation on hover — and to a reader.

    `data-tip` is a stylesheet trick and invisible to a screen reader, so the
    same words are in the document as well, referenced by `aria-describedby`.
    """
    marker = f'help-{next(_HELP_IDS)}'
    return (f'<span class="help" data-tip="{_e(text)}" tabindex="0" '
            f'aria-describedby="{marker}">?'
            f'<span id="{marker}" class="sronly">{_e(text)}</span></span>')


_e = ui.esc


# --- fragments -------------------------------------------------------------


def status_panel() -> str:
    rows = []
    for role, pattern in config.INPUT_PATTERNS.items():
        if pattern is None:
            continue            # optional input: nothing to be missing
        matches = sorted(config.INPUT_DIR.glob(pattern))
        if matches:
            for match in matches:
                rows.append(('ok', f'{match.name}',
                             f'{match.stat().st_size // 1024} KB'))
        else:
            rows.append(('ko', pattern, 'missing'))

    for name, purpose, present in config.key_status():
        if name == 'OPENAI_BASE_URL':
            continue
        rows.append(('ok' if present else 'off', name,
                     'configured' if present else 'absent'))

    body = ''.join(
        f'<tr><td><span class="dot {cls}"></span>{_e(label)}</td>'
        f'<td class="num muted">{_e(value)}</td></tr>'
        for cls, label, value in rows
    )
    return f'<table class="mini"><tbody>{body}</tbody></table>'


def _options(values, selected='') -> str:
    return ''.join(
        f'<option value="{_e(v)}"{" selected" if v == selected else ""}>'
        f'{_e(v or "automatic")}</option>' for v in values
    )


def _level_checkbox(level: str, checked: bool) -> str:
    name, subtitle = level_labels()[level]
    return (
        f'<label class="lev" data-tip="{_e(level_help()[level])}">'
        f'<input type="checkbox" name="llm_level" value="{level}"'
        f'{" checked" if checked else ""}>'
        f'<span class="lev-t"><b>{_e(name)}</b>'
        f'<i>{_e(subtitle)}</i></span></label>'
    )


def _level_options(selected: str) -> str:
    return ''.join(
        f'<option value="{lv}"{" selected" if lv == selected else ""}>'
        f'{_e(level_labels()[lv][0])} — {_e(level_labels()[lv][1])}</option>'
        for lv in LEVELS
    )


def form_panel() -> str:
    running = runner_module.current().running
    disabled = ' disabled' if running else ''

    return f'''
<form id="launch" hx-post="{active.base()}/run" hx-target="#logwrap" hx-swap="innerHTML">
  <fieldset{disabled}>
    {presets_panel()}
    {estimate_panel()}
    <button type="submit" class="btn primary wide">{'Running…' if running else 'Start run'}</button>

    <details class="advanced">
      <summary>Adjust the details</summary>

      <label class="field">
        <span>What to run</span>
        <select name="command">
          <option value="all">Everything — merges the data and analyses it</option>
          <option value="merge">Merge only — prepares the data, does not analyse it</option>
          <option value="analyze">Analysis only — reuses the data already merged</option>
        </select>
      </label>

      <div class="block">
        <p class="inline head">Validation rubric</p>
        <p class="why">Has a model score the conversations, to check that the
          indices computed from the dictionaries really measure what they claim
          to. It runs when the preset above includes it; these are its
          settings.</p>
        <div class="row">
          <label class="field"><span>Model</span>
            <select name="llm_model">{_options(MODELS_RUBRIC)}</select></label>
          <label class="field"><span>Replicates {_help(OPTION_HELP['replicates'])}</span>
            <select name="llm_replicates">
              <option>1</option><option>2</option><option>3</option>
            </select></label>
        </div>
        <div class="levels">
          <span class="lbl">Which units to score</span>
          {''.join(_level_checkbox(lv, lv == 'group') for lv in LEVELS)}
        </div>
      </div>

      <div class="block">
        <p class="inline head">Conversation themes</p>
        <p class="why">TopicGPT first <b>discovers</b> which themes exist by
          reading the longest texts, then <b>attributes</b> them to the finer
          units. It runs when the preset above includes it; these are its
          settings.</p>
        <div class="row">
          <label class="field"><span>Model</span>
            <select name="topicgpt_model">{_options(MODELS_TOPIC, 'gpt-4o')}</select></label>
        </div>
        <label class="field">
          <span>Discovers the themes by reading {_help(OPTION_HELP['induction'])}</span>
          <select name="topicgpt_unit">{_level_options('group')}</select></label>
        <label class="field">
          <span>Attributes them to {_help(OPTION_HELP['assignment'])}</span>
          <select name="topicgpt_assign_unit">{_level_options('dyad_directed')}</select></label>
      </div>
    </details>
  </fieldset>
</form>'''


# A run's phases, in the order they appear, with the text that announces them
# in the log. It shows how far along we are without having to read the log.
PHASES = [
    ('Merge', 'Input:'),
    ('Measures', 'Text measures'),
    ('Rubric', 'Validation rubric'),
    ('Topics', 'TopicGPT'),
    ('Report', 'Readable summary'),
]

BAR_RE = re.compile(r'(\d+)%\|')
KEYVALUE_RE = re.compile(r'^(\s*)([^:]{2,60}?)\s*:\s{1,}(.+)$')
PHASE_RE = re.compile(r'^\s*\[(\d)/(\d)\]\s*(.+)$')


def _phases(lines) -> str:
    """Phase bar: the ones already seen are done, the last is in progress."""
    text = '\n'.join(lines)
    seen = [name for name, marker in PHASES if marker in text]
    if not seen:
        return ''
    current = seen[-1]
    chips = []
    for name, _marker in PHASES:
        if name not in seen:
            state = 'todo'
        elif name == current:
            state = 'now'
        else:
            state = 'done'
        chips.append(f'<span class="phase {state}">{_e(name)}</span>')
    return f'<div class="phases">{"".join(chips)}</div>'


def _render_line(line: str) -> str:
    """A log line becomes an element with a shape of its own.

    Lines have recurring structures — bars, key/value pairs, paths, warnings —
    and rendering them all as raw text forces the reader to parse each one
    again to work out what it is.
    """
    stripped = line.strip()

    bar = BAR_RE.search(stripped)
    if bar and '|' in stripped:
        pct = min(100, int(bar.group(1)))
        tail = stripped.split('|')[-1].strip()
        return (f'<div class="l bar"><div class="track">'
                f'<div class="fill" style="width:{pct}%"></div></div>'
                f'<span class="pct">{pct}%</span>'
                f'<span class="tail">{_e(tail)}</span></div>')

    phase = PHASE_RE.match(line)
    if phase:
        return (f'<div class="l step"><span class="n">{_e(phase.group(1))}/'
                f'{_e(phase.group(2))}</span>{_e(phase.group(3))}</div>')

    low = stripped.lower()
    if low.startswith(('warning', 'error')):
        return f'<div class="l warn">{_e(stripped)}</div>'

    if stripped.startswith('/'):
        # Absolute paths fill the whole line and the useful part is at the
        # end: show the file name, with the full path available on demand.
        return (f'<div class="l path" title="{_e(stripped)}">'
                f'<span class="file">{_e(Path(stripped).name)}</span></div>')

    keyvalue = KEYVALUE_RE.match(line)
    if keyvalue:
        indent = ' indent' if keyvalue.group(1) else ''
        return (f'<div class="l kv{indent}"><span class="k">'
                f'{_e(keyvalue.group(2).strip())}</span>'
                f'<span class="v">{_e(keyvalue.group(3).strip())}</span></div>')

    return f'<div class="l">{_e(stripped)}</div>'


def log_body() -> str:
    """The log's content. It lives inside a container that is never swapped."""
    state = runner_module.current().snapshot()
    lines = state['lines']

    if not lines and not state['running']:
        return ('<div id="logbody" class="logbody empty">'
                'No run in this session. Choose the options and press '
                'Start run.</div>')

    if state['running']:
        # The content requests itself: the scrolling container stays put, so
        # the scroll position is not lost.
        attrs = (f'hx-get="{active.base()}/log" hx-trigger="load delay:1s" '
                 'hx-target="#logbody" hx-swap="outerHTML"')
    else:
        attrs = (f'hx-get="{active.base()}/done" hx-trigger="load" '
                 'hx-target="#after" '
                 'hx-swap="innerHTML"')

    rendered = ''.join(_render_line(line) for line in lines)
    return (f'<div id="logbody" class="logbody" {attrs}>'
            f'{_phases(lines)}{rendered}</div>')


# What a non-zero exit actually means, where we know. A run that ended badly
# used to be reported as `exit 3` and nothing else: the number is the one thing
# on the page that the reader can do nothing with.
EXIT_MEANING = {
    1: 'stopped with an error — the last lines of the log say which',
    2: 'the options were not understood',
    3: 'a file or a setting the run needed was missing',
    -15: 'stopped on request',
    -2: 'stopped on request',
    -9: 'killed',
}


def _stop_button() -> str:
    """Offered while something is running.

    `Runner.stop` has always existed and has always been tested; nothing in the
    interface called it. Someone who started a paid run with the wrong model
    had to go and kill the terminal.
    """
    return (f'<button class="btn quiet stop" hx-post="{active.base()}/stop"'
            f' hx-target="#loghead" hx-swap="outerHTML">Stop the run</button>')


def log_body_message(text: str) -> str:
    """A single line where the log would be. The router used to build this
    markup itself, in two places, with the wording different in each."""
    return f'<div class="logbody empty">{_e(text)}</div>'


def _other_studies_running() -> str:
    """Said, not refused: two workspaces write to two folders and do not
    collide. What they do share is the rate limit and the bill."""
    others = runner_module.elsewhere()
    if not others:
        return ''
    which = ', '.join(others)
    return ui.notice(
        f'A run is also in progress in {_e(which)}. They do not interfere — '
        f'each writes to its own folder — but the paid stages of two studies at '
        f'once cost twice as much and share one rate limit.', 'warn')


def log_head() -> str:
    state = runner_module.current().snapshot()
    control = ''
    if state['running']:
        badge = '<span class="badge run">running</span>'
        control = _stop_button()
    elif state['command']:
        code = state['returncode']
        ok = code == 0
        if ok:
            badge = '<span class="badge ok">completed</span>'
        else:
            meaning = EXIT_MEANING.get(code, 'stopped before it finished')
            badge = (f'<span class="badge ko">{_e(meaning)}</span>'
                     f'<span class="muted small">exit {_e(code)}</span>')
    else:
        return '<div id="loghead" class="loghead"></div>'

    finished = state['finished']
    when = _e(state['started'] or '') + (f' → {_e(finished)}' if finished else '')
    command = state['command']
    # The whole command is long and repeats options already chosen in the
    # form: show it compact, in full on hover. The workspace and the TopicGPT
    # repository are absolute paths that would take up most of the line and
    # say nothing the header does not already show.
    short = command.replace('python -m chatlens.cli ', 'chatlens ')
    short = re.sub(r' --workspace \S+', '', short)
    short = short.split(' --topicgpt-repo')[0]
    return (f'<div id="loghead" class="loghead">{badge}'
            f'<code title="{_e(command)}">{_e(short)}</code>'
            f'<span class="muted when">{when}</span>{control}</div>'
            f'{_other_studies_running()}')


def log_panel() -> str:
    """The content of #logwrap: head and body.

    The scrolling container is not part of what gets swapped: that is the only
    way for the scroll position to survive the automatic updates.
    """
    return log_head() + log_body()


def _run_time(stamp: str) -> str:
    """A readable instant: what matters is when, not the serial number."""
    from datetime import date, datetime, timedelta

    try:
        moment = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return stamp or '—'

    day = moment.date()
    if day == date.today():
        prefix = 'today'
    elif day == date.today() - timedelta(days=1):
        prefix = 'yesterday'
    else:
        prefix = moment.strftime('%d/%m')
    # With seconds: runs a few moments apart are common, and without them
    # they cannot be told apart.
    return f'{prefix} {moment.strftime("%H:%M:%S")}'


def _run_detail(run: dict) -> str:
    """What sets this run apart from the others.

    Among a dozen near-identical rows what is needed is the detail that
    changes: the model, the replicates, the unit the topics were induced on.
    The message count remains as a fallback when there is nothing else.
    """
    bits = []
    topics = run.get('topics') or {}
    if topics:
        model = topics.get('model') or '?'
        bits.append(f'{model} · {topics.get("unit")}→{topics.get("assign_unit")}')

    rubric = run.get('rubric') or {}
    if rubric:
        model = rubric.get('models')
        model = '' if model in (None, 'default') else f'{model} · '
        replicates = rubric.get('replicates', 1)
        label = '1 replicate' if replicates == 1 else f'{replicates} replicates'
        bits.append(f'{model}{label}')

    if not bits and run.get('n_messages') is not None:
        bits.append(f'{run["n_messages"]} messages')
    return ' · '.join(bits)


def _run_tooltip(run: dict) -> str:
    """The full parameters, for whoever wants to know exactly what ran."""
    lines = [f'Messages analysed: {run.get("n_messages", "?")}']
    levels = run.get('levels') or {}
    if levels:
        lines.append('Units: ' + ', '.join(f'{k} {v}' for k, v in levels.items()))
    rubric = run.get('rubric') or {}
    if rubric:
        n = rubric.get('replicates', 1)
        replicates = '1 replicate' if n == 1 else f'{n} replicates'
        lines.append(
            f'Rubric: {rubric.get("provider")}, model '
            f'{rubric.get("models")}, {replicates}, '
            f'levels {", ".join(rubric.get("levels") or [])}'
        )
    topics = run.get('topics') or {}
    if topics:
        lines.append(
            f'Topics: {topics.get("model")} via {topics.get("api")}, induction '
            f'on {topics.get("unit")}, assignment to '
            f'{topics.get("assign_unit")}, '
            + ('unsupervised' if topics.get('unsupervised')
               else f'seed {Path(topics.get("seed") or "").name}')
        )
    return ' — '.join(lines)


STAGE_LABELS = {'measures': 'measures', 'rubric': 'rubric', 'topics': 'topics'}


def runs_panel() -> str:
    runs = archive.list_runs(config.OUTPUT_DIR)
    if not runs:
        return ('<p class="muted">No archived run yet. Every run is saved '
                'here, so launching again does not erase the previous one.</p>')

    rows = []
    for index, run in enumerate(runs[:12]):
        stages = ''.join(
            f'<span class="chip {name}">{_e(STAGE_LABELS.get(name, name))}</span>'
            for name in (run.get('stages') or [])
        )

        if run.get('failed_stage'):
            note = (f'<span class="failed">{_e(run["failed_stage"])} '
                    f'not completed</span>')
        else:
            note = f'<span class="detail">{_e(_run_detail(run))}</span>'

        # The first one is also the one sitting in output/: it is the report
        # the dashboard shows, and unsaid it is hard to tell which.
        current = ('<span class="current">in output/</span>'
                   if index == 0 else '')

        name = run['path'].name
        # The whole row opens the run: it is the index of what was done, not
        # a list of links to a single file.
        # `role="button"` with `tabindex` puts the row in the tab order and
        # tells a screen reader it can be pressed; htmx, left alone, listens
        # for a click and nothing else, so the promise was not kept and the
        # row could be reached from the keyboard but never opened. Enter is
        # what the row now answers to as well.
        rows.append(
            f'<li hx-get="{active.base()}/run/{_e(name)}" hx-target="#report" '
            f'hx-swap="innerHTML" hx-trigger="click, keyup[key==\'Enter\']" '
            f'tabindex="0" role="button">'
            f'<span class="when">{_e(_run_time(run.get("timestamp", "")))}</span>'
            f'<span class="chips">{stages}{current}</span>'
            f'{note}<span class="go-arrow">›</span></li>'
        )
    return f'<ul class="runs">{"".join(rows)}</ul>'


def _human_size(n: int) -> str:
    return f'{n // 1024} KB' if n >= 1024 else f'{n} B'


def _run_files(run_dir: Path, name: str) -> str:
    """What that run produced, downloadable.

    Through `active.base()`, like every other address on this page. Written to
    the root, as these were, they name a route that only exists when the
    dashboard was pointed at a single workspace: in library mode `/runs/...`
    is served out of whichever folder the process was started in, which is not
    the study, so every file here answered 404.
    """
    items = []
    for path in sorted(run_dir.rglob('*')):
        if not path.is_file() or path.name == archive.RUN_INFO:
            continue
        rel = path.relative_to(run_dir).as_posix()
        items.append(
            f'<li><a href="{active.base()}/runs/{_e(name)}/{_e(rel)}" '
            f'target="_blank">'
            f'{_e(rel)}</a>'
            f'<span class="muted">{_e(_human_size(path.stat().st_size))}</span></li>'
        )
    if not items:
        return ''
    return f'<ul class="files">{"".join(items)}</ul>'


def _params_table(run: dict) -> str:
    rows = []

    def add(label, value):
        rows.append(f'<tr><td>{_e(label)}</td>'
                    f'<td class="num">{_e(value)}</td></tr>')

    add('Messages analysed', run.get('n_messages', '—'))
    for level, count in (run.get('levels') or {}).items():
        name = level_labels().get(level, (level, ''))[0]
        add(f'Units · {name}', count)

    rubric = run.get('rubric') or {}
    if rubric:
        n = rubric.get('replicates', 1)
        add('Rubric · provider', rubric.get('provider', '—'))
        add('Rubric · model', rubric.get('models', '—'))
        add('Rubric · replicates', '1 replicate' if n == 1 else f'{n} replicates')
        add('Rubric · levels', ', '.join(rubric.get('levels') or []))

    topics = run.get('topics') or {}
    if topics:
        add('Topics · model', topics.get('model', '—'))
        add('Topics · discovers by reading',
            level_labels().get(topics.get('unit'), (topics.get('unit'), ''))[0])
        add('Topics · attributes to',
            level_labels().get(topics.get('assign_unit'),
                             (topics.get('assign_unit'), ''))[0])
        # How the topics were induced, not merely which file was passed: a
        # reader six months on needs to know whether the list was steered.
        add('Topics · induction',
            'unsupervised (no starting list)' if topics.get('unsupervised')
            else f"seeded from {Path(topics.get('seed') or '—').name}")
        if topics.get('shuffle_seed') is not None:
            add('Topics · document order',
                f"shuffled, seed {topics['shuffle_seed']}"
                if topics.get('shuffle_seed') else 'as written')

    return f'<table class="mini params"><tbody>{"".join(rows)}</tbody></table>'


def run_detail(name: str) -> str:
    """Everything about an archived run."""
    run = next((r for r in archive.list_runs(config.OUTPUT_DIR)
                if r['path'].name == name), None)
    if run is None:
        return '<p class="muted">Run not found.</p>'

    stages = ' · '.join(run.get('stages') or ['?'])
    status = (f'<span class="badge ko">{_e(run["failed_stage"])} '
              f'not completed</span>' if run.get('failed_stage')
              else '<span class="badge ok">completed</span>')

    report = run['path'] / 'report.html'
    if report.is_file():
        base = active.base()
        viewer = (f'<div class="reportbar">'
                  f'<a href="{base}/runs/{_e(name)}/report.html" '
                  f'target="_blank">open full page</a></div>'
                  f'<iframe src="{base}/runs/{_e(name)}/report.html" '
                  f'title="Report"></iframe>')
    else:
        viewer = ('<p class="muted">This run produced no report: it was a data '
                  'merge only.</p>')

    return (
        f'<div class="detailhead">'
        f'<div><b>{_e(_run_time(run.get("timestamp", "")))}</b> '
        f'<span class="muted">{_e(stages)}</span></div>'
        f'{status}'
        f'<button class="btn quiet" hx-get="{active.base()}/report" hx-target="#report" '
        f'hx-swap="innerHTML">back to the latest</button></div>'
        f'{_params_table(run)}'
        f'{_run_files(run["path"], name)}'
        f'{viewer}'
    )


def report_panel() -> str:
    """The latest result: the one sitting at the fixed paths in output/."""
    reports = sorted(config.OUTPUT_DIR.glob('*_report.html'))
    if not reports:
        return ('<p class="muted">The report appears here after the first '
                'run with analysis.</p>')
    latest = reports[-1]
    return (f'<div class="reportbar">'
            f'<span class="badge ok">in output/</span>'
            f'<a href="{active.base()}/report.html" '
            f'target="_blank">open full page</a>'
            f'<span class="muted">{_e(latest.name)}</span></div>'
            f'<iframe src="{active.base()}/report.html" '
            f'title="Report"></iframe>')


def after_run() -> str:
    """What gets refreshed when a run ends."""
    return (f'<div hx-swap-oob="innerHTML:#loghead">{log_head()}</div>'
            f'<div hx-swap-oob="innerHTML:#status">{status_panel()}</div>'
            f'<div hx-swap-oob="innerHTML:#formbox">{form_panel()}</div>'
            f'<div hx-swap-oob="innerHTML:#runs">{runs_panel()}</div>'
            f'<div hx-swap-oob="innerHTML:#report">{report_panel()}</div>')


# --- page ------------------------------------------------------------------


def page(experiment_slug: str = '') -> str:
    # Whichever required input is there: the roles depend on the adapter, and
    # asking for 'wide' by name broke on every experiment that is not ours.
    dataset = '—'
    for role, pattern in config.INPUT_PATTERNS.items():
        if pattern is None:
            continue
        try:
            dataset = config.find_input(role).name
            break
        except config.InputError:
            continue

    # The experiment's name where it has one, and always the file: they answer
    # different questions, but printing the filename twice answers neither.
    experiment = getattr(config, 'EXPERIMENT', None)
    named = experiment.name if experiment and experiment.name else ''

    from chatlens.web import study as study_state

    lead = ('Everything the study can say comes out of one pass over the text. '
            'The free one takes seconds and needs no key; the other two send '
            'the conversations to a model and cost money, so the number of '
            'calls is shown before anything is sent.')

    body = f'''<div class="runlayout">
  <section class="runside">
    <h2>What is here</h2>
    <div id="status">{status_panel()}</div>
    <h2>What to run</h2>
    <div id="formbox">{form_panel()}</div>
  </section>
  <section class="runmain">
    <h2>Execution</h2>
    <div id="logwrap" class="log">{log_panel()}</div>
    <h2>Earlier runs</h2>
    <div id="runs">{runs_panel()}</div>
    <h2>Report</h2>
    <div id="report">{report_panel()}</div>
  </section>
</div>
<div id="after" hidden></div>'''

    numbers = {key: index for index, (key, _l, _h)
               in enumerate(ui.STEPS, start=1)}
    return ui.shell(
        f'{named or "Text analysis"} — run',
        ui.step_page(numbers['run'], 'Run it', lead, body,
                     next_label='See the findings',
                     next_href=f'/experiment/{ui.esc(experiment_slug)}/findings'
                     if experiment_slug else ''),
        slug=experiment_slug or '',
        study=named or dataset,
        steps=study_state.step_state(experiment) if experiment else {},
        step='run',
    )
