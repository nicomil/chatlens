"""
Frammenti HTML della dashboard.

Nessun motore di template: le pagine sono poche e il contenuto e' quasi tutto
generato da dati, quindi f-string e funzioni bastano e non aggiungono una
dipendenza.

Ogni frammento e' un pezzo che htmx sostituisce nella pagina: la pagina intera
si costruisce componendoli, cosi' l'aggiornamento parziale e il caricamento
iniziale usano lo stesso codice e non possono divergere.
"""

from __future__ import annotations

import html
from pathlib import Path

from src import archive, config
from web.runner import runner

MODELS_RUBRICA = ['', 'gpt-4o', 'gpt-4.1', 'gpt-5.6-terra', 'gpt-5.6-luna',
                  'gpt-5.6-sol', 'claude-opus-5', 'llama3']
MODELS_TOPIC = ['gpt-4o', 'gpt-4.1']
LEVELS = ['group', 'dyad_directed', 'dyad', 'sender_group']


def _e(text) -> str:
    return html.escape(str(text))


# --- frammenti -------------------------------------------------------------


def status_panel() -> str:
    rows = []
    for kind, pattern in config.INPUT_PATTERNS.items():
        matches = sorted(config.INPUT_DIR.glob(pattern))
        if matches:
            for match in matches:
                rows.append(('ok', f'{match.name}',
                             f'{match.stat().st_size // 1024} KB'))
        else:
            rows.append(('ko', pattern, 'mancante'))

    for name, purpose, present in config.key_status():
        if name == 'OPENAI_BASE_URL':
            continue
        rows.append(('ok' if present else 'off', name,
                     'configurata' if present else 'assente'))

    body = ''.join(
        f'<tr><td><span class="dot {cls}"></span>{_e(label)}</td>'
        f'<td class="right muted">{_e(value)}</td></tr>'
        for cls, label, value in rows
    )
    return f'<table class="mini"><tbody>{body}</tbody></table>'


def _options(values, selected='') -> str:
    return ''.join(
        f'<option value="{_e(v)}"{" selected" if v == selected else ""}>'
        f'{_e(v or "automatico")}</option>' for v in values
    )


def form_panel() -> str:
    disabled = ' disabled' if runner.running else ''
    return f'''
<form id="launch" hx-post="/run" hx-target="#log" hx-swap="innerHTML">
  <fieldset{disabled}>
    <div class="row">
      <label class="grow">
        <span>Comando</span>
        <select name="command">
          <option value="all">all — unione + analisi</option>
          <option value="merge">merge — solo unione</option>
          <option value="analyze">analyze — solo analisi</option>
        </select>
      </label>
    </div>

    <details class="opt">
      <summary><label class="inline">
        <input type="checkbox" name="llm" value="1"> Rubrica di validazione
      </label><span class="tag">chiave</span></summary>
      <div class="row">
        <label><span>Modello</span>
          <select name="llm_model">{_options(MODELS_RUBRICA)}</select></label>
        <label><span>Repliche</span>
          <select name="llm_replicates">
            <option>1</option><option>2</option><option>3</option>
          </select></label>
      </div>
      <div class="row">
        <label class="grow"><span>Livelli</span>
          <span class="checks">{''.join(
            f'<label class="inline"><input type="checkbox" name="llm_level" '
            f'value="{lv}"{" checked" if lv == "group" else ""}> {lv}</label>'
            for lv in LEVELS)}</span></label>
      </div>
    </details>

    <details class="opt">
      <summary><label class="inline">
        <input type="checkbox" name="topics" value="1"> Topic con TopicGPT
      </label><span class="tag">chiave</span></summary>
      <div class="row">
        <label><span>Modello</span>
          <select name="topicgpt_model">{_options(MODELS_TOPIC, 'gpt-4o')}</select></label>
        <label><span>Induzione su</span>
          <select name="topicgpt_unit">{_options(LEVELS, 'group')}</select></label>
        <label><span>Assegna a</span>
          <select name="topicgpt_assign_unit">{_options(LEVELS, 'dyad_directed')}</select></label>
      </div>
    </details>

    <button type="submit" class="go">{'In corso…' if runner.running else 'Lancia'}</button>
  </fieldset>
</form>'''


def log_panel() -> str:
    state = runner.snapshot()
    lines = state['lines']

    if not lines and not state['running']:
        return ('<div id="log" class="log empty">Nessun run in questa sessione. '
                'Scegli le opzioni e premi Lancia.</div>')

    # Finché il run è in corso il pannello si richiede da solo ogni secondo;
    # quando finisce smette, e chiede l'aggiornamento del resto della pagina.
    if state['running']:
        attrs = ('hx-get="/log" hx-trigger="load delay:1s" '
                 'hx-target="#log" hx-swap="outerHTML"')
        badge = '<span class="badge run">in corso</span>'
    else:
        attrs = ('hx-get="/done" hx-trigger="load" hx-target="#after" '
                 'hx-swap="innerHTML"')
        code = state['returncode']
        ok = code == 0
        cls = 'ok' if ok else 'ko'
        label = 'completato' if ok else f'uscita {code}'
        badge = f'<span class="badge {cls}">{label}</span>' 

    finished = state['finished']
    when = _e(state['started'] or '') + (f' → {_e(finished)}' if finished else '')
    header = (f'<div class="loghead">{badge}'
              f'<code>{_e(state["command"])}</code>'
              f'<span class="muted">{when}</span></div>')
    body = '\n'.join(_e(line) for line in lines)
    return f'<div id="log" class="log" {attrs}>{header}<pre>{body}</pre></div>'


def runs_panel() -> str:
    runs = archive.list_runs(config.OUTPUT_DIR)
    if not runs:
        return '<p class="muted">Nessun run archiviato.</p>'

    items = []
    for run in runs[:12]:
        name = run['path'].name
        stages = ', '.join(run.get('stages') or ['?'])
        extra = ''
        if run.get('failed_stage'):
            extra = f'<span class="badge ko">{_e(run["failed_stage"])}</span>'
        report = run['path'] / 'report.html'
        link = (f'<a href="/runs/{_e(name)}/report.html" target="_blank">rapporto</a>'
                if report.is_file() else '')
        items.append(
            f'<li><code>{_e(name)}</code>'
            f'<span class="muted">{_e(stages)}</span>{extra}{link}</li>'
        )
    return f'<ul class="runs">{"".join(items)}</ul>'


def report_panel() -> str:
    reports = sorted(config.OUTPUT_DIR.glob('*_report.html'))
    if not reports:
        return ('<p class="muted">Il rapporto compare qui dopo il primo run '
                'con analisi.</p>')
    latest = reports[-1]
    return (f'<div class="reportbar">'
            f'<a href="/report.html" target="_blank">apri a tutta pagina</a>'
            f'<span class="muted">{_e(latest.name)}</span></div>'
            f'<iframe src="/report.html" title="Rapporto"></iframe>')


def after_run() -> str:
    """Cosa si aggiorna quando un run finisce."""
    return (f'<div hx-swap-oob="innerHTML:#status">{status_panel()}</div>'
            f'<div hx-swap-oob="innerHTML:#formbox">{form_panel()}</div>'
            f'<div hx-swap-oob="innerHTML:#runs">{runs_panel()}</div>'
            f'<div hx-swap-oob="innerHTML:#report">{report_panel()}</div>')


# --- pagina ----------------------------------------------------------------


def page() -> str:
    dataset = '—'
    try:
        dataset = config.find_input('wide').name
    except config.InputError:
        pass

    return f'''<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Analisi del testo</title>
<link rel="stylesheet" href="/static/style.css">
<script src="/static/htmx.min.js"></script>
</head><body>
<header>
  <h1>Analisi del testo</h1>
  <span class="muted">{_e(dataset)}</span>
</header>

<main>
  <section class="col left">
    <h2>Stato</h2>
    <div id="status">{status_panel()}</div>
    <h2>Lancia un run</h2>
    <div id="formbox">{form_panel()}</div>
    <h2>Archivio</h2>
    <div id="runs">{runs_panel()}</div>
  </section>

  <section class="col right">
    <h2>Esecuzione</h2>
    {log_panel()}
    <h2>Rapporto</h2>
    <div id="report">{report_panel()}</div>
  </section>
</main>

<div id="after" hidden></div>
</body></html>'''
