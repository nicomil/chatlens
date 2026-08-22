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
import re
from pathlib import Path

from src import archive, config
from web.runner import runner

MODELS_RUBRICA = ['', 'gpt-4o', 'gpt-4.1', 'gpt-5.6-terra', 'gpt-5.6-luna',
                  'gpt-5.6-sol', 'claude-opus-5', 'llama3']
MODELS_TOPIC = ['gpt-4o', 'gpt-4.1']
LEVELS = ['group', 'dyad_directed', 'dyad', 'sender_group']

# Cosa significa ciascuna unità di analisi. Sono i termini che compaiono ovunque
# nei dati, e senza una spiegazione a portata di mano non si scelgono a ragion
# veduta.
LEVEL_LABELS = {
    'group': ('Gruppo', "l'intera conversazione della triade"),
    'dyad_directed': ('Coppia orientata', 'chi scrive a chi, una direzione'),
    'dyad': ('Coppia', 'due persone, entrambe le direzioni'),
    'sender_group': ('Persona', 'tutto cio\' che uno ha scritto'),
}

LEVEL_HELP = {
    'group': 'La conversazione dell\'intera triade: tutti i messaggi scambiati '
             'fra i tre partecipanti. È l\'unità con più testo.',
    'dyad_directed': 'I messaggi che una persona manda a un\'altra, in una sola '
                     'direzione. È l\'unità della persuasione: conta chi parla.',
    'dyad': 'La conversazione fra due persone, in entrambe le direzioni.',
    'sender_group': 'Tutto ciò che una persona ha scritto nel gruppo, a '
                    'chiunque fosse rivolto.',
}

OPTION_HELP = {
    'llm': 'Fa valutare le stesse conversazioni a un modello linguistico con una '
           'rubrica esplicita, per validare le misure calcolate dai dizionari. '
           'Consuma chiamate a pagamento.',
    'topics': 'Estrae i temi delle conversazioni con TopicGPT: prima li induce '
              'dai testi, poi li assegna alle unità più fini. Consuma chiamate '
              'a pagamento.',
    'replicates': 'Quante volte valutare ogni testo. Con più di una si ottiene '
                  'la dispersione fra valutazioni, cioè una stima dell\'errore '
                  'di misura. Il costo cresce in proporzione.',
    'induzione': 'Su quale unità scoprire quali temi esistono. Serve testo '
                 'abbastanza lungo: su testi brevi il modello non riconosce '
                 'nulla.',
    'assegnazione': 'A quale unità attribuire i temi già scoperti. Può essere '
                    'più fine dell\'induzione: riconoscere è più facile che '
                    'scoprire.',
}


PRESETS = [
    dict(id='base', nome='Solo misure',
         descrizione='Volume, sentiment e indici del linguaggio. '
                     'Nessuna chiave, pochi secondi.',
         costo='gratis'),
    dict(id='validazione', nome='Misure + validazione',
         descrizione='Aggiunge la rubrica che convalida gli indici '
                     'facendoli valutare a un modello.',
         costo='a pagamento'),
    dict(id='completa', nome='Analisi completa',
         descrizione='Aggiunge anche i temi delle conversazioni con TopicGPT. '
                     'È il run che produce tutto.',
         costo='a pagamento'),
]


def presets_panel() -> str:
    cards = ''.join(
        f'<button type="button" class="preset" data-preset="{_e(p["id"])}">'
        f'<span class="nome">{_e(p["nome"])}</span>'
        f'<span class="desc">{_e(p["descrizione"])}</span>'
        f'<span class="costo {"free" if p["costo"] == "gratis" else "paid"}">'
        f'{_e(p["costo"])}</span></button>'
        for p in PRESETS
    )
    return f'<div class="presets">{cards}</div>'


def _unit_counts() -> dict:
    """Quante unita' ci sono per livello, dall'ultimo run archiviato.

    Serve a rendere concreta la scelta: "due repliche" non dice nulla, "circa
    duecento chiamate" si.
    """
    for run in archive.list_runs(config.OUTPUT_DIR):
        levels = run.get('levels')
        if levels:
            return levels
    return {}


def estimate_panel(form=None) -> str:
    """Stima delle chiamate che la configurazione corrente comporta."""
    form = form or {}
    counts = _unit_counts()
    if not counts:
        return ('<div id="estimate" class="estimate muted">La stima compare '
                'dopo il primo run.</div>')

    calls = 0
    parts = []

    if form.get('llm'):
        levels = [v for v in form.get('llm_level', []) if v in counts]
        replicates = int((form.get('llm_replicates') or ['1'])[0] or 1)
        n = sum(counts[lv] for lv in levels) * replicates
        if n:
            calls += n
            parts.append(f'rubrica {n}')

    if form.get('topics'):
        unit = (form.get('topicgpt_unit') or ['group'])[0]
        assign = (form.get('topicgpt_assign_unit') or ['dyad_directed'])[0]
        n = counts.get(unit, 0) + counts.get(assign, 0)
        if n:
            calls += n
            parts.append(f'topic ~{n}')

    if not calls:
        return ('<div id="estimate" class="estimate free">Nessuna chiamata a '
                'pagamento · pochi secondi</div>')

    # Circa un secondo e mezzo per chiamata, misurato sui run veri.
    minuti = max(1, round(calls * 1.5 / 60))
    dettaglio = ' + '.join(parts)
    return (f'<div id="estimate" class="estimate paid">'
            f'<strong>~{calls} chiamate</strong> ({dettaglio}) · '
            f'circa {minuti} min</div>')


def _help(text: str) -> str:
    """Punto interrogativo con la spiegazione al passaggio del mouse."""
    return f'<span class="help" data-tip="{_e(text)}">?</span>' 


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
        f'<td class="num muted">{_e(value)}</td></tr>'
        for cls, label, value in rows
    )
    return f'<table class="mini"><tbody>{body}</tbody></table>'


def _options(values, selected='') -> str:
    return ''.join(
        f'<option value="{_e(v)}"{" selected" if v == selected else ""}>'
        f'{_e(v or "automatico")}</option>' for v in values
    )


def _level_checkbox(level: str, checked: bool) -> str:
    nome, sotto = LEVEL_LABELS[level]
    return (
        f'<label class="lev" data-tip="{_e(LEVEL_HELP[level])}">'
        f'<input type="checkbox" name="llm_level" value="{level}"'
        f'{" checked" if checked else ""}>'
        f'<span class="lev-t"><b>{_e(nome)}</b>'
        f'<i>{_e(sotto)}</i></span></label>'
    )


def _level_options(selected: str) -> str:
    return ''.join(
        f'<option value="{lv}"{" selected" if lv == selected else ""}>'
        f'{_e(LEVEL_LABELS[lv][0])} — {_e(LEVEL_LABELS[lv][1])}</option>'
        for lv in LEVELS
    )


def form_panel() -> str:
    disabled = ' disabled' if runner.running else ''
    # Ogni cambiamento nel modulo aggiorna la stima: e' cio' che rende
    # concreta una scelta altrimenti astratta.
    live = ('hx-post="/estimate" hx-trigger="change" '
            'hx-target="#estimate" hx-swap="outerHTML"')

    return f'''
{presets_panel()}
<form id="launch" hx-post="/run" hx-target="#logwrap" hx-swap="innerHTML" {live}>
  <fieldset{disabled}>
    <label class="field">
      <span>Cosa eseguire</span>
      <select name="command">
        <option value="all">Tutto — unisce i dati e li analizza</option>
        <option value="merge">Solo unione — prepara i dati, non li analizza</option>
        <option value="analyze">Solo analisi — riusa i dati gia uniti</option>
      </select>
    </label>

    <details class="opt" id="opt-llm">
      <summary>
        <label class="inline">
          <input type="checkbox" name="llm" value="1"> Rubrica di validazione
        </label>{_help(OPTION_HELP['llm'])}<span class="tag">a pagamento</span>
      </summary>
      <p class="why">Fa valutare le conversazioni a un modello, per verificare
        che gli indici calcolati dai dizionari misurino davvero quello che
        dicono.</p>
      <div class="row">
        <label class="field"><span>Modello</span>
          <select name="llm_model">{_options(MODELS_RUBRICA)}</select></label>
        <label class="field"><span>Repliche {_help(OPTION_HELP['replicates'])}</span>
          <select name="llm_replicates">
            <option>1</option><option>2</option><option>3</option>
          </select></label>
      </div>
      <div class="levels">
        <span class="lbl">Su quali unità valutare</span>
        {''.join(_level_checkbox(lv, lv == 'group') for lv in LEVELS)}
      </div>
    </details>

    <details class="opt" id="opt-topics">
      <summary>
        <label class="inline">
          <input type="checkbox" name="topics" value="1"> Temi delle conversazioni
        </label>{_help(OPTION_HELP['topics'])}<span class="tag">a pagamento</span>
      </summary>
      <p class="why">TopicGPT prima <b>scopre</b> quali temi esistono leggendo i
        testi più lunghi, poi li <b>attribuisce</b> alle unità più fini.</p>
      <div class="row">
        <label class="field"><span>Modello</span>
          <select name="topicgpt_model">{_options(MODELS_TOPIC, 'gpt-4o')}</select></label>
      </div>
      <div class="row">
        <label class="field grow">
          <span>Scopre i temi leggendo {_help(OPTION_HELP['induzione'])}</span>
          <select name="topicgpt_unit">{_level_options('group')}</select></label>
      </div>
      <div class="row">
        <label class="field grow">
          <span>Li attribuisce a {_help(OPTION_HELP['assegnazione'])}</span>
          <select name="topicgpt_assign_unit">{_level_options('dyad_directed')}</select></label>
      </div>
    </details>

    {estimate_panel()}
    <button type="submit" class="go">{'In corso…' if runner.running else 'Lancia'}</button>
  </fieldset>
</form>'''


# Fasi di un run, nell'ordine in cui compaiono, con il testo che le annuncia
# nel log. Serve a mostrare a che punto siamo senza dover leggere il log.
PHASES = [
    ('Unione', 'Input:'),
    ('Misure', 'Misure testuali'),
    ('Rubrica', 'Rubrica di validazione'),
    ('Topic', 'TopicGPT'),
    ('Rapporto', 'Riassunto leggibile'),
]

BAR_RE = re.compile(r'(\d+)%\|')
KEYVALUE_RE = re.compile(r'^(\s*)([^:]{2,60}?)\s*:\s{1,}(.+)$')
PHASE_RE = re.compile(r'^\s*\[(\d)/(\d)\]\s*(.+)$')


def _phases(lines) -> str:
    """Barra delle fasi: quelle gia' viste sono fatte, l'ultima e' in corso."""
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
    """Una riga di log diventa un elemento con la sua forma.

    Le righe hanno strutture ricorrenti — barre, coppie chiave/valore, percorsi,
    avvisi — e renderle tutte come testo grezzo costringe a rileggerle ogni
    volta per capire cosa siano.
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
    if low.startswith(('attenzione', 'errore', 'error')):
        return f'<div class="l warn">{_e(stripped)}</div>'

    if stripped.startswith('/'):
        # I percorsi assoluti occupano tutta la riga e la parte utile e' in
        # fondo: si mostra il nome del file, con il percorso intero a richiesta.
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
    """Contenuto del log. Vive dentro un contenitore che non viene sostituito."""
    state = runner.snapshot()
    lines = state['lines']

    if not lines and not state['running']:
        return ('<div id="logbody" class="logbody empty">'
                'Nessun run in questa sessione. Scegli le opzioni e premi '
                'Lancia.</div>')

    if state['running']:
        # Il contenuto si richiede da solo: il contenitore che scorre resta al
        # suo posto, quindi la posizione dello scroll non viene persa.
        attrs = ('hx-get="/log" hx-trigger="load delay:1s" '
                 'hx-target="#logbody" hx-swap="outerHTML"')
    else:
        attrs = ('hx-get="/done" hx-trigger="load" hx-target="#after" '
                 'hx-swap="innerHTML"')

    rendered = ''.join(_render_line(line) for line in lines)
    return (f'<div id="logbody" class="logbody" {attrs}>'
            f'{_phases(lines)}{rendered}</div>')


def log_head() -> str:
    state = runner.snapshot()
    if state['running']:
        badge = '<span class="badge run">in corso</span>'
    elif state['command']:
        code = state['returncode']
        ok = code == 0
        badge = (f'<span class="badge {"ok" if ok else "ko"}">'
                 f'{"completato" if ok else f"uscita {code}"}</span>')
    else:
        return '<div id="loghead" class="loghead"></div>'

    finished = state['finished']
    when = _e(state['started'] or '') + (f' → {_e(finished)}' if finished else '')
    command = state['command']
    # Il comando intero e' lungo e ripete opzioni gia' scelte nel modulo: si
    # mostra compatto, per intero al passaggio del mouse.
    short = command.replace('python run.py ', '').split(' --topicgpt-repo')[0]
    return (f'<div id="loghead" class="loghead">{badge}'
            f'<code title="{_e(command)}">{_e(short)}</code>'
            f'<span class="muted when">{when}</span></div>')


def log_panel() -> str:
    """Contenuto di #logwrap: intestazione e corpo.

    Il contenitore che scorre non fa parte di quello che viene sostituito:
    e' l'unico modo perche' la posizione dello scroll sopravviva agli
    aggiornamenti automatici.
    """
    return log_head() + log_body()


def _run_time(stamp: str) -> str:
    """Istante leggibile: quello che serve e' quando, non il numero seriale."""
    from datetime import date, datetime, timedelta

    try:
        moment = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return stamp or '—'

    day = moment.date()
    if day == date.today():
        prefix = 'oggi'
    elif day == date.today() - timedelta(days=1):
        prefix = 'ieri'
    else:
        prefix = moment.strftime('%d/%m')
    return f'{prefix} {moment.strftime("%H:%M")}'


def _run_detail(run: dict) -> str:
    """Cosa distingue questo run dagli altri.

    Fra dodici righe quasi uguali serve il dettaglio che cambia: il modello, le
    repliche, l'unita' su cui sono stati indotti i topic. Il conteggio dei
    messaggi resta come ripiego quando non c'e' altro.
    """
    bits = []
    topic = run.get('topic') or {}
    if topic:
        model = topic.get('model') or '?'
        bits.append(f'{model} · {topic.get("unit")}→{topic.get("assign_unit")}')

    rubrica = run.get('rubrica') or {}
    if rubrica:
        model = rubrica.get('models')
        model = '' if model in (None, 'predefinito') else f'{model} · '
        repliche = rubrica.get('replicates', 1)
        etichetta = '1 replica' if repliche == 1 else f'{repliche} repliche'
        bits.append(f'{model}{etichetta}')

    if not bits and run.get('n_messages') is not None:
        bits.append(f'{run["n_messages"]} messaggi')
    return ' · '.join(bits)


def _run_tooltip(run: dict) -> str:
    """Parametri completi, per chi vuole sapere esattamente cosa girava."""
    lines = [f'Messaggi analizzati: {run.get("n_messages", "?")}']
    levels = run.get('levels') or {}
    if levels:
        lines.append('Unita: ' + ', '.join(f'{k} {v}' for k, v in levels.items()))
    rubrica = run.get('rubrica') or {}
    if rubrica:
        n = rubrica.get('replicates', 1)
        repliche = '1 replica' if n == 1 else f'{n} repliche'
        lines.append(
            f'Rubrica: {rubrica.get("provider")}, modello '
            f'{rubrica.get("models")}, {repliche}, '
            f'livelli {", ".join(rubrica.get("levels") or [])}'
        )
    topic = run.get('topic') or {}
    if topic:
        lines.append(
            f'Topic: {topic.get("model")} via {topic.get("api")}, induzione su '
            f'{topic.get("unit")}, assegnazione a {topic.get("assign_unit")}, '
            f'seed {Path(topic.get("seed") or "").name}'
        )
    return ' — '.join(lines)


STAGE_LABELS = {'misure': 'misure', 'rubrica': 'rubrica', 'topic': 'topic'}


def runs_panel() -> str:
    runs = archive.list_runs(config.OUTPUT_DIR)
    if not runs:
        return ('<p class="muted">Nessun run archiviato. Ogni esecuzione viene '
                'salvata qui, cosi\' rilanciare non cancella la precedente.</p>')

    rows = []
    for index, run in enumerate(runs[:12]):
        stages = ''.join(
            f'<span class="chip {name}">{_e(STAGE_LABELS.get(name, name))}</span>'
            for name in (run.get('stages') or [])
        )

        if run.get('failed_stage'):
            note = (f'<span class="failed">{_e(run["failed_stage"])} '
                    f'non completato</span>')
        else:
            note = f'<span class="detail">{_e(_run_detail(run))}</span>'

        # Il primo e' anche quello che si trova in output/: e' il rapporto che
        # la dashboard mostra, e senza dirlo si cerca di capire quale sia.
        current = ('<span class="current">in output/</span>'
                   if index == 0 else '')

        name = run['path'].name
        link = ('<a href="/runs/{n}/report.html" target="_blank">rapporto</a>'
                .format(n=_e(name))
                if (run['path'] / 'report.html').is_file() else '<span></span>')

        rows.append(
            f'<li data-tip="{_e(_run_tooltip(run))}">'
            f'<span class="when">{_e(_run_time(run.get("timestamp", "")))}</span>'
            f'<span class="chips">{stages}{current}</span>'
            f'{note}{link}</li>'
        )
    return f'<ul class="runs">{"".join(rows)}</ul>'


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
    return (f'<div hx-swap-oob="innerHTML:#loghead">{log_head()}</div>'
            f'<div hx-swap-oob="innerHTML:#status">{status_panel()}</div>'
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
  <section class="col col-side">
    <h2>Stato</h2>
    <div id="status">{status_panel()}</div>
    <h2>Lancia un run</h2>
    <div id="formbox">{form_panel()}</div>
    <h2>Archivio</h2>
    <div id="runs">{runs_panel()}</div>
  </section>

  <section class="col col-main">
    <h2>Esecuzione</h2>
    <div id="logwrap" class="log">{log_panel()}</div>
    <h2>Rapporto</h2>
    <div id="report">{report_panel()}</div>
  </section>
</main>

<div id="after" hidden></div>
<script src="/static/app.js"></script>
</body></html>'''
