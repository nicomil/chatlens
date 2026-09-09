"""One page shell, one set of components, one way to escape text.

The interface grew a page at a time, and each page brought its own `<!doctype>`,
its own header and its own copy of `html.escape`. Seven shells is seven places
to change a stylesheet link, seven headers that drifted apart, and — because one
of those copies is in the router rather than a view — one place where text from
the URL reached the browser unescaped.

This module is the single place. A view returns its body; `shell` puts the page
around it. A view needs a table, a figure, an empty state; it asks for one here
rather than writing the markup again slightly differently.

Nothing in here knows what a page means. The judgement about *what* to show
stays in the view; this is only about how it looks once decided.
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

    It used to be built by interpolating HTML-escaped text into hand-written
    JSON. HTML escaping is not JSON escaping: a filename containing a backslash
    produced an invalid escape sequence, htmx failed to parse it and dropped the
    request with nothing shown to anyone. Serialise first, escape second.
    """
    return f"hx-vals='{attr(json.dumps(values, ensure_ascii=False))}'"


# --- navigation ------------------------------------------------------------

# The destinations inside one experiment, in the order they are useful. The
# analysis pages sit together because they answer the same kind of question,
# and because four of the five are unavailable on a fresh install: grouping
# them is what lets the bar say so once instead of five times.
OVERVIEW = ('', 'Overview')
ANALYSIS = (
    ('participation', 'Participation'),
    ('words', 'Words'),
    ('narratives', 'Narratives'),
    ('emotions', 'Emotions'),
    ('compare', 'Compare'),
)
SETTINGS = ('settings', 'Settings')


def nav(slug: str, current: str = '', unavailable=None) -> str:
    """The bar that is on every page of an experiment.

    `current` is the action part of the path — '' for the hub, 'words', and so
    on. `unavailable` maps an action to the reason it cannot be opened; those
    entries stay visible and become inert, because a destination that vanishes
    when a dependency is missing teaches the user that the feature does not
    exist.
    """
    unavailable = unavailable or {}
    base = f'/experiment/{esc(slug)}'

    def item(action, label):
        classes = ['navlink']
        if action == current:
            classes.append('on')
        reason = unavailable.get(action)
        if reason:
            return (f'<span class="navlink off" data-tip="{attr(reason)}" '
                    f'tabindex="0">{esc(label)}</span>')
        href = f'{base}/{action}' if action else base
        aria = ' aria-current="page"' if action == current else ''
        return (f'<a class="{" ".join(classes)}" href="{href}"{aria}>'
                f'{esc(label)}</a>')

    analysis = ''.join(item(action, label) for action, label in ANALYSIS)
    return f'''<nav class="nav" aria-label="This experiment">
  {item(*OVERVIEW)}
  <span class="navgroup">{analysis}</span>
  {item(*SETTINGS)}
</nav>'''


# --- the shell -------------------------------------------------------------

THEME_SCRIPT = (
    '<script>(function(){try{var t=localStorage.getItem("chatlens-theme");'
    'if(t){document.documentElement.setAttribute("data-theme",t);}}'
    'catch(e){}})();</script>'
)


def unavailable_reasons() -> dict:
    """Which analysis pages cannot open, and why, in one line each.

    The bar asks this so that a destination needing a 1.6 GB download says so
    where the reader is choosing, rather than after they have clicked and are
    looking at install instructions where they expected results. The page
    itself still explains it in full — this is the label on the door.
    """
    from chatlens.core import nrc, optional

    reasons = {}
    if not optional.have('sklearn'):
        needed = 'needs scikit-learn — see the page for the command'
        reasons['words'] = needed
        reasons['compare'] = needed
    if not optional.have('relatio'):
        reasons['narratives'] = ('needs spaCy and RELATIO — see the page for '
                                 'the commands')
    try:
        if not nrc.lexicon_path().is_file():
            reasons['emotions'] = ('needs the NRC lexicon — see the page for '
                                   'where to get it')
    except Exception:  # noqa: BLE001 - a missing lexicon must not break the bar
        pass
    return reasons


def shell(title: str, body: str, *, heading: str = '', slug: str = '',
          experiment_name: str = '', current: str = '', subtitle: str = '',
          unavailable=None, wide: bool = False, htmx: bool = True) -> str:
    """The only page in the project.

    `heading` is what the page is called; `experiment_name` is what it is about.
    Both are shown, because a page that says only "Words" leaves the reader to
    remember which experiment they are looking at, and one that says only the
    experiment's name leaves them to work out which page they are on.
    """
    scripts = '<script src="/static/htmx.min.js"></script>' if htmx else ''
    # The trail is the ancestors, never the page itself: with the current page
    # in it too, the library read "chatlens chatlens" and the hub repeated the
    # experiment's name twice across three centimetres.
    crumb = ''
    if slug and current:
        crumb = (f'<a class="crumb" href="/">chatlens</a>'
                 f'<span class="crumbsep">/</span>'
                 f'<a class="crumb" href="/experiment/{esc(slug)}">'
                 f'{esc(experiment_name or slug)}</a>')
    elif slug:
        crumb = '<a class="crumb" href="/">chatlens</a>'

    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="stylesheet" href="/static/style.css">
{THEME_SCRIPT}
{scripts}
</head><body>
<header class="topbar">
  <div class="crumbs">{crumb}</div>
  <h1>{esc(heading or title)}</h1>
  {f'<span class="subtitle">{esc(subtitle)}</span>' if subtitle else ''}
  <button type="button" class="themetoggle" id="themetoggle"
          aria-label="Switch between the light and the dark theme"
          title="Light or dark">◐</button>
</header>
{nav(slug, current, unavailable if unavailable is not None else unavailable_reasons()) if slug else ''}
<main class="{'wide' if wide else 'single'}">
{body}
</main>
<script src="/static/app.js"></script>
</body></html>'''


# --- components ------------------------------------------------------------


def stat_tiles(items) -> str:
    """A row of headline figures: `(value, label)` pairs.

    One implementation, because there were two — `.stats/.stat` in the
    dashboard and `.cards/.card` in the report — differing in font size, in
    layout and in nothing that mattered.
    """
    cells = ''.join(
        f'<div class="stat"><div class="v">{esc(value)}</div>'
        f'<div class="l">{esc(label)}</div></div>'
        for value, label in items
    )
    return f'<div class="stats">{cells}</div>'


def table(headers, rows, *, numeric=(), empty_message='', caption='') -> str:
    """A data table, or the reason there is not one.

    `headers` are the column titles, `rows` the cells already rendered.
    `numeric` holds the indices to align right. An empty `rows` renders
    `empty_message` instead of a header over nothing, which is what every one
    of these tables used to do.
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
    """What a page shows when it has nothing to show.

    A designed state rather than a paragraph, because the two are read
    differently: a paragraph in the flow of the page looks like commentary on
    results that are further down, and there are none.
    """
    link = f'<p class="emptyaction">{action}</p>' if action else ''
    return f'<div class="empty"><p>{message}</p>{link}</div>'


def notice(text: str, kind: str = 'info') -> str:
    """A boxed remark. `kind` is info, good, warn or bad."""
    return f'<div class="notice {esc(kind)}">{text}</div>'


def disclosure(summary: str, body: str, *, open: bool = False) -> str:
    """The explanation, available but not in the way.

    These pages carry a lot of prose, and it is there for a reason: a number
    from a penalised regression means something different from a mean, and the
    difference has to be readable somewhere. But it was above the figures, so
    the figures started below the fold. This puts the reasoning one click away
    and the result first.
    """
    return (f'<details class="explain"{" open" if open else ""}>'
            f'<summary>{esc(summary)}</summary>'
            f'<div class="explainbody">{body}</div></details>')


def button(label: str, *, kind: str = 'primary', **attrs) -> str:
    """One button, three intentions: primary, quiet, danger."""
    rendered = ' '.join(f'{key.replace("_", "-")}="{attr(value)}"'
                        for key, value in attrs.items())
    return (f'<button type="button" class="btn {esc(kind)}" {rendered}>'
            f'{esc(label)}</button>')


def spinner(label: str = 'Working…') -> str:
    """Shown while something slow is happening, which is often here."""
    return (f'<div class="working"><span class="dot"></span>'
            f'<span>{esc(label)}</span></div>')
