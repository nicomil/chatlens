"""The shape of every screen: the spine, the register, the canvas.

A study has a life — files, columns, a question, a run, findings — and this
module makes that life the structure of the interface rather than something the
reader has to hold in their head while choosing between seven sibling pages.

Three zones, and every screen is made of them:

``spine``
    Always on top. The five steps with their real state, so "where am I and
    what is left" is answered without reading anything.

``register``
    On the findings screen only. One row per question the tool can answer, with
    its verdict. It is navigation made of content: `core/compare.py` already
    decides which representations beat length and which do not, and that
    decision belongs where the reader chooses what to look at.

``canvas``
    One thing at a time. A step, or a finding in the fixed shape
    question → answer → evidence → detail → how to read it.

Nothing here knows what a page *means*. The judgement about what to show stays
in the views; this is only about the form it takes once decided.
"""

from __future__ import annotations

import html
import json

# --- text ------------------------------------------------------------------


def esc(text) -> str:
    """The one escape. Every string that came from outside goes through it.

    Outside means: a name someone typed, a column read from their file, the
    body of a participant's message, a path, an error. Which is nearly
    everything, so the rule is to escape by default and to notice the
    exceptions.

    It takes anything, not just strings: `html.escape` calls `.replace` on what
    it is given, and `Path.replace` is a real method meaning something else
    entirely, so a Path used to raise from inside the escaper rather than being
    rejected at the door.
    """
    return html.escape(str(text if text is not None else ''))


def attr(value) -> str:
    """For an attribute, where a quote ends the attribute rather than the tag."""
    return html.escape(str(value if value is not None else ''), quote=True)


def hx_vals(**values) -> str:
    """A safe `hx-vals` attribute.

    Serialise first, escape second. HTML escaping is not JSON escaping: a
    filename containing a backslash produced an invalid escape sequence, htmx
    failed to parse it, and the request was dropped with nothing shown.
    """
    return f"hx-vals='{attr(json.dumps(values, ensure_ascii=False))}'"


# --- the spine -------------------------------------------------------------

# The five steps, in the order they happen. The first four are things the user
# does to the study; the fifth is what the study says back.
STEPS = (
    ('data', 'Data', 'the export, and what each file is'),
    ('columns', 'Columns', 'which column plays which part'),
    ('outcome', 'Outcome', 'what the analysis should explain'),
    ('run', 'Run', 'produce the measures'),
    ('findings', 'Findings', 'what the conversations say'),
)

DONE, CURRENT, TODO, BLOCKED = 'done', 'current', 'todo', 'blocked'


def spine(slug: str, state: dict, current: str = '') -> str:
    """The five steps, with the state each one is actually in.

    `state` maps a step key to one of DONE / TODO / BLOCKED, or to a tuple
    `(BLOCKED, reason)`. A blocked step stays visible and says why: a step that
    disappears until it is reachable teaches the reader that it does not exist.
    """
    if not slug:
        return ''
    base = f'/experiment/{esc(slug)}'
    items = []
    for index, (key, label, _hint) in enumerate(STEPS, start=1):
        raw = state.get(key, TODO)
        kind, reason = raw if isinstance(raw, tuple) else (raw, '')
        if key == current:
            kind = CURRENT
        classes = f'step {kind}'
        inner = (f'<span class="stepnum">{index}</span>'
                 f'<span class="steplabel">{esc(label)}</span>')
        if kind == BLOCKED:
            # The reason is in `data-tip`, which a stylesheet shows on hover and
            # a screen reader cannot see at all. `aria-describedby` points at the
            # same words in the document, so the step announces why it is
            # blocked rather than only looking greyed out.
            tip = f'why-{esc(key)}'
            items.append(
                f'<span class="{classes}" data-tip="{attr(reason)}" '
                f'tabindex="0" aria-describedby="{tip}">{inner}'
                f'<span id="{tip}" class="sronly">{esc(reason)}</span></span>')
        else:
            aria = ' aria-current="step"' if kind == CURRENT else ''
            href = base if key == 'findings' else f'{base}/step/{key}'
            if key == 'findings':
                href = f'{base}/findings'
            items.append(f'<a class="{classes}" href="{href}"{aria}>{inner}</a>')
    return f'<nav class="spine" aria-label="This study">{"".join(items)}</nav>'


# --- the register ----------------------------------------------------------

# What a finding's verdict can be. `NO` is deliberately not an error: on a
# corpus of short messages it is the commonest honest answer, and the tool's
# own prose says so. Colouring it like a failure teaches the reader that the
# analysis went wrong when what went wrong is nothing.
YES, NO, OPEN, UNAVAILABLE = 'yes', 'no', 'open', 'unavailable'

VERDICT_MARK = {
    YES: '✓',
    NO: '✗',
    OPEN: '·',
    UNAVAILABLE: '—',
}


def register(slug: str, findings, current: str = '', refresh: str = '') -> str:
    """One row per question, ordered so that answers come before obstacles.

    `refresh` is where the same list, with its verdicts worked out, will come
    from. The verdicts are the point of the register and they are expensive, so
    the list arrives at once and fills in rather than holding the page.

    A definite "no" sits with the still-open questions, not between "yes" and
    them. It used to come second, right after "yes" — which reads fine on a
    register that already has verdicts, but this one fills in *after* the
    page has painted: the reader loads a fresh study, sees "What was said"
    and "Who spoke to whom" first, and a second later two crossed-out entries
    — "adds nothing to length" — jump above both of them, because on this
    corpus two blocks came back negative. A definite no still belongs ahead of
    an unanswerable question, so it is not pushed to the very end; it is only
    no longer allowed to leapfrog the orientation pages a first-time reader
    has not gotten to yet.
    """
    order = {YES: 0, OPEN: 1, NO: 2, UNAVAILABLE: 3}
    rows = []
    for finding in sorted(findings, key=lambda f: (order.get(f['verdict'], 9),
                                                   f.get('order', 0))):
        active = ' on' if finding['id'] == current else ''
        mark = VERDICT_MARK.get(finding['verdict'], '·')
        # Built before the f-string: an escaped quote cannot live inside one on
        # the Python this supports.
        note = finding.get('note') or ''
        note_html = f'<span class="entrynote">{esc(note)}</span>' if note else ''
        rows.append(
            f'<a class="entry {esc(finding["verdict"])}{active}" '
            f'href="/experiment/{esc(slug)}/findings/{esc(finding["id"])}">'
            f'<span class="mark" aria-hidden="true">{mark}</span>'
            f'<span class="entrytext">'
            f'<span class="entryname">{esc(finding["name"])}</span>'
            f'{note_html}'
            f'</span></a>')
    arriving = (f' hx-get="{attr(refresh)}" hx-trigger="load"'
                f' hx-swap="outerHTML"' if refresh else '')
    # The end of the path: everything that has an answer, in one document.
    out = (f'<a class="entry export" '
           f'href="/experiment/{esc(slug)}/findings/export">'
           f'<span class="mark" aria-hidden="true">⤓</span>'
           f'<span class="entrytext"><span class="entryname">Put it '
           f'together</span><span class="entrynote">every finding, in one '
           f'page</span></span></a>') if slug else ''
    return (f'<aside class="register" aria-label="What this study can answer"'
            f'{arriving}>'
            f'<h2>Findings</h2>{"".join(rows)}{out}{_glossary(slug)}</aside>')


def _glossary(slug: str) -> str:
    """The technique's name, for a reader who arrived already knowing it.

    Every title in this register is a plain-English question — "Which words
    go with X?", never "run a bag-of-words model" — which is right for a
    reader who does not yet know what to call the thing they want, and wrong
    for one who does: nothing on this page contains the phrase "bag of
    words", or "RELATIO", or "NRC", so a search for any of them by name comes
    back empty even while standing on the right page. One static list, so a
    search finds it regardless of which page is open.

    Rubric and topics point at the run's static report rather than at an entry
    here: they have no page of their own in this register yet, and saying so
    plainly beats pretending the six entries above are the whole of what a
    paid run computed.
    """
    def link(href: str, label: str) -> str:
        return f'<a href="{href}">{esc(label)}</a>' if slug else esc(label)

    report_href = f'/experiment/{esc(slug)}/report.html'
    finding_href = lambda entry_id: f'/experiment/{esc(slug)}/findings/{entry_id}'

    rows = (
        ('Bag of words', link(finding_href('words'), 'The words')),
        ('RELATIO, relation extraction',
         link(finding_href('narratives'), 'The relations')),
        ('NRC Emotion Lexicon', link(finding_href('emotions'), 'The emotions')),
        ('Nested models, AUC comparison',
         link(finding_href('compare'), 'Which representation to trust')),
        ('Rubric (LLM judge)', link(report_href, "the run's report")),
        ('TopicGPT', link(report_href, "the run's report")),
    )
    items = ''.join(f'<li><b>{esc(term)}</b> — {dest}</li>'
                    for term, dest in rows)
    return disclosure(
        'Looking for a method by name',
        f'<ul class="glossary">{items}</ul>')


# --- the shell -------------------------------------------------------------

# Applied before the first paint, from a file rather than inline: the content
# security policy this server sends is `script-src 'self'`, so the inline
# version this replaces was refused by the browser and the reader's choice of
# theme was lost on every reload. See static/theme.js.
THEME_SCRIPT = '<script src="/static/theme.js"></script>'


def shell(title: str, canvas: str, *, slug: str = '', study: str = '',
          steps=None, step: str = '', aside: str = '', htmx: bool = True,
          selector: str = '') -> str:
    """The only page in the project.

    `aside` is the register, when there is one. Without it the canvas takes the
    whole width, which is what a step wants: one form, one decision.

    `selector` is which sample the findings are being read on, when the
    experiment declares more than one. It sits in the masthead rather than on
    each page because it applies to all of them at once, and because a reader
    who has forgotten which study a figure belongs to looks up, not down.
    """
    scripts = '<script src="/static/htmx.min.js"></script>' if htmx else ''
    bar = spine(slug, steps or {}, step) if slug else ''
    frame = 'frame with-aside' if aside else 'frame'

    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="stylesheet" href="/static/style.css">
{THEME_SCRIPT}
{scripts}
</head><body>
<header class="masthead">
  <a class="brand" href="/">chatlens</a>
  {f'<span class="study">{esc(study)}</span>' if study else ''}
  {selector}
  <a class="guidelink" href="https://nicomil.github.io/chatlens/guide/"
     target="_blank" rel="noopener">Guide</a>
  <button type="button" class="themetoggle" id="themetoggle"
          aria-label="Switch between the light and the dark theme"
          title="Light or dark">◐</button>
</header>
{bar}
<div class="{frame}">
{aside}
<main class="canvas">
{canvas}
</main>
</div>
<script src="/static/app.js"></script>
</body></html>'''


# --- the shape of a finding ------------------------------------------------


def finding(question: str, answer: str, *, evidence: str = '',
            detail: str = '', how_to_read: str = '', controls: str = '',
            verdict: str = OPEN, method: str = '') -> str:
    """Question, answer, evidence, detail, how to read it — in that order.

    The order is the argument. Every one of these screens used to open with a
    paragraph of reasoning, then the controls, then the numbers, and put the
    answer in a grey sentence halfway down. The answer is the largest text on
    the screen now, and the reasoning is one click away rather than in front of
    it.

    `method` is the technical name of what the page is actually doing — "bag
    of words", "RELATIO", "the NRC Emotion Lexicon" — printed once, small,
    under the question. Every title in this project is a plain-English
    question by design, on purpose, for a reader who does not yet know what to
    call the thing they want: nobody arrives asking for "a penalised logistic
    regression over unigrams and bigrams". But it means a reader who *does*
    already know the name — because a colleague used it, because a method
    section has to cite it — cannot find it anywhere on the page: the phrase
    "bag of words" appears in no title in this codebase. `method` is that
    bridge, and only that: it changes no computation and nothing below it.
    """
    parts = [
        f'<div class="finding {esc(verdict)}">',
        f'<h1 class="question">{esc(question)}</h1>',
    ]
    if method:
        parts.append(f'<p class="method-tag muted">{esc(method)}</p>')
    parts.append(f'<p class="answer">{answer}</p>')
    if controls:
        parts.append(f'<div class="controls">{controls}</div>')
    if evidence:
        parts.append(f'<section class="evidence">{evidence}</section>')
    if detail:
        parts.append(f'<section class="detail">{detail}</section>')
    if how_to_read:
        parts.append(disclosure('How to read this', how_to_read))
    parts.append('</div>')
    return '\n'.join(parts)


def step_page(number: int, title: str, lead: str, body: str,
              *, next_label: str = '', next_href: str = '') -> str:
    """One step of the setup: one decision, said plainly, with a way onward."""
    onward = ''
    if next_href:
        onward = (f'<p class="onward"><a class="btn primary" '
                  f'href="{attr(next_href)}">{esc(next_label or "Continue")}'
                  f'</a></p>')
    return f'''<div class="step-page">
  <p class="eyebrow">Step {number} of {len(STEPS)}</p>
  <h1 class="question">{esc(title)}</h1>
  <p class="lead">{lead}</p>
  {body}
  {onward}
</div>'''


# --- components ------------------------------------------------------------


def stat_tiles(items) -> str:
    """A row of headline figures: `(value, label)` pairs."""
    cells = ''.join(
        f'<div class="stat"><div class="v">{esc(value)}</div>'
        f'<div class="l">{esc(label)}</div></div>'
        for value, label in items
    )
    return f'<div class="stats">{cells}</div>'


def bar_cell(share: float, direction: str = '') -> str:
    """A magnitude drawn where the number is, not instead of it.

    `share` is 0..1 of the widest value in the column. `direction` is 'with' or
    'against' — this whole tool is directional, and a coefficient table where
    the sign is a word in another column makes the reader do the joining.
    """
    width = max(0.0, min(1.0, share)) * 100
    return (f'<span class="magnitude {esc(direction)}" '
            f'style="width:{width:.1f}%"></span>')


def table(headers, rows, *, numeric=(), empty_message='', caption='') -> str:
    """A data table, or the reason there is not one.

    There used to be a `sortable` flag here that added a class name. Nothing
    passed it, no script looked for it and no stylesheet styled it, so the only
    thing it could do was promise a reader that the headings were clickable.
    """
    if not rows:
        return empty(empty_message or 'Nothing to show here yet.')

    def cell(tag, index, content):
        # Written out rather than interpolated: an f-string cannot carry the
        # backslash an escaped quote would need on the Python this supports.
        css = ' class="num"' if index in numeric else ''
        return '<' + tag + css + '>' + content + '</' + tag + '>'

    head = ''.join(cell('th', index, esc(title))
                   for index, title in enumerate(headers))
    body = ''.join(
        '<tr>' + ''.join(cell('td', index, value)
                         for index, value in enumerate(row)) + '</tr>'
        for row in rows
    )
    legend = f'<caption>{esc(caption)}</caption>' if caption else ''
    return (f'<div class="scroll"><table class="grid">{legend}'
            f'<thead><tr>{head}</tr></thead><tbody>{body}</tbody>'
            f'</table></div>')


def empty(message: str, *, action: str = '') -> str:
    """What a screen shows when it has nothing to show."""
    link = f'<p class="emptyaction">{action}</p>' if action else ''
    return f'<div class="empty"><p>{message}</p>{link}</div>'


def blocked(what: str, why: str, commands=(), retry: str = '') -> str:
    """A question that cannot be answered yet, and exactly what unblocks it.

    On a fresh installation this is the state of four screens out of six, so it
    is the commonest thing the interface shows and it is designed rather than
    apologised for.
    """
    def one(label, command, size):
        weight = f'<span class="cmdsize">{esc(size)}</span>' if size else ''
        return (f'<li><span class="cmdwhat">{esc(label)}</span>'
                f'<pre class="cmd">{esc(command)}</pre>{weight}</li>')

    lines = ''.join(one(*command) for command in commands)
    again = (f'<p><a class="btn quiet" href="{attr(retry)}">Check again</a></p>'
             if retry else '')
    return f'''<div class="blocked">
  <h2>{esc(what)}</h2>
  <p>{why}</p>
  {f'<ul class="commands">{lines}</ul>' if lines else ''}
  {again}
</div>'''


def notice(text: str, kind: str = 'info') -> str:
    """A boxed remark. `kind` is info, good, warn or bad."""
    return f'<div class="notice {esc(kind)}">{text}</div>'


def disclosure(summary: str, body: str, *, open: bool = False) -> str:
    """The explanation, available but not in the way."""
    return (f'<details class="explain"{" open" if open else ""}>'
            f'<summary>{esc(summary)}</summary>'
            f'<div class="explainbody">{body}</div></details>')


def button(label: str, *, kind: str = 'primary', tag: str = 'button',
           href: str = '', **attrs) -> str:
    """One button, three intentions: primary, quiet, danger."""
    rendered = ' '.join(f'{key.replace("_", "-")}="{attr(value)}"'
                        for key, value in attrs.items())
    if tag == 'a' or href:
        return (f'<a class="btn {esc(kind)}" href="{attr(href)}" '
                f'{rendered}>{esc(label)}</a>')
    return (f'<button type="button" class="btn {esc(kind)}" {rendered}>'
            f'{esc(label)}</button>')


def spinner(label: str = 'Working…') -> str:
    """Shown while something slow is happening, which is often here."""
    return (f'<div class="working"><span class="dot"></span>'
            f'<span>{esc(label)}</span></div>')


def unavailable_reasons() -> dict:
    """Which findings cannot be computed here, and why, in one line each."""
    from chatlens.core import narratives, nrc, optional

    reasons = {}
    if not optional.have('sklearn'):
        needed = 'needs scikit-learn'
        reasons['words'] = needed
        reasons['lexical'] = needed
        reasons['volume'] = needed
    # An imported study can carry the relations already extracted, and the
    # page shows those without the package.
    if not optional.have('relatio') and not narratives.has_stored():
        reasons['narratives'] = 'needs spaCy and RELATIO'
    try:
        if not nrc.lexicon_path().is_file():
            reasons['emotions'] = 'needs the NRC lexicon'
    except Exception:  # noqa: BLE001 - a missing lexicon must not break the bar
        pass
    return reasons
