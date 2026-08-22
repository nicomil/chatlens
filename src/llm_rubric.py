"""
Seconda misura, indipendente, dei costrutti in stile LIWC: una rubrica valutata
da un modello linguistico.

Serve a validare le misure dizionario-based di `text_metrics`. Le due strade
sono metodologicamente diverse — una conta function words, l'altra legge il
testo — quindi una correlazione alta fra loro è un'evidenza di validità
convergente; una correlazione bassa è un segnale da riportare, non da
nascondere.

Perché si valuta il testo aggregato e non il singolo messaggio
--------------------------------------------------------------
Vale lo stesso argomento delle misure automatiche: un turno di chat di cinque
parole non contiene abbastanza segnale per una scala 0-100. La rubrica gira
quindi sulle trascrizioni già aggregate — coppia ordinata, coppia, gruppo — che
sono anche le unità richieste dall'analisi.

Affidabilità
------------
Con `--llm-replicates 2` la stessa trascrizione viene valutata più volte in
chiamate indipendenti: la dispersione fra repliche è la stima test-retest
dell'errore di misura, e finisce nel dataset come `*_sd`. Si possono anche
indicare più modelli giudici (`--llm-models`), ottenendo un accordo fra
valutatori diversi anziché fra repliche dello stesso.

Costo
-----
Per grandi volumi conviene `--llm-batch`, che usa la Batches API a metà prezzo (solo
con il fornitore Anthropic). Sul
pilota (25 gruppi, 311 messaggi) le chiamate sono poche centinaia e la modalità
sincrona basta.
"""

from __future__ import annotations

import functools
import json
import os
import statistics
import time
from dataclasses import dataclass

# La rubrica non dipende da un fornitore specifico: quello che serve è un modello
# che segua istruzioni e restituisca JSON. Sono quindi supportati tre backend, e
# quello da usare si sceglie in base alle credenziali disponibili.
#
# `openai` serve anche a chi non vuole una seconda chiave: se si usa già OpenAI
# per TopicGPT, la stessa chiave copre anche questo stadio. `ollama` gira in
# locale e non richiede alcuna credenziale.
PROVIDERS = {
    'anthropic': dict(
        default_model='claude-opus-5',
        env_key='ANTHROPIC_API_KEY',
        label='Anthropic',
    ),
    'openai': dict(
        default_model='gpt-4o',
        env_key='OPENAI_API_KEY',
        label='OpenAI',
    ),
    'ollama': dict(
        default_model='llama3',
        env_key=None,  # locale: nessuna chiave
        label='Ollama (locale)',
    ),
}

# Ordine di preferenza quando il fornitore non è indicato esplicitamente.
PROVIDER_PRIORITY = ('anthropic', 'openai', 'ollama')

OLLAMA_BASE_URL = 'http://localhost:11434/v1'

DEFAULT_MODEL = PROVIDERS['anthropic']['default_model']

SYSTEM_PROMPT = """You are a research assistant coding transcripts for a \
behavioural economics experiment. Three participants play a coalition-formation \
game and exchange short private chat messages before deciding whom to support.

You rate a transcript on four constructs, each on a 0-100 scale. Use the full \
range: 50 is the midpoint for an unremarkable transcript of this kind, not a \
default answer. Rate only what the text shows; never infer from what you \
imagine happened outside the transcript.

ANALYTICAL THINKING (analytic)
Formal, logical, hierarchical reasoning versus narrative, here-and-now, \
informal language. High: reasoning about payoffs, conditions, consequences, \
structured argument. Low: greetings, reactions, unstructured chatter.

CLOUT (clout)
The confidence and social status the writer projects. High: speaks with \
authority, focuses on the other person and on the group, makes offers and \
proposals, appears to lead the exchange. Low: tentative, self-focused, \
anxious, deferential, hedging.

AUTHENTICITY (authenticity)
How spontaneous and personally honest the language reads. High: unguarded, \
self-disclosing, admits uncertainty or self-interest openly. Low: guarded, \
strategic, distanced, impression-managing, evasive.

EMOTIONAL TONE (tone)
Emotional valence. Above 50: positive, warm, friendly. Below 50: negative, \
hostile, anxious. Exactly 50: neutral or no emotional content.

Also record whether the transcript contains an explicit commitment to support \
someone, and whether it contains an explicit request for support.

If the transcript is empty or contains no usable language, return 50 for every \
scale and set insufficient_text to true."""

USER_TEMPLATE = """Transcript ({unit}), {n_messages} message(s), \
treatment "{treatment}":

<transcript>
{transcript}
</transcript>

Rate the language of {target} in this transcript."""


@functools.lru_cache(maxsize=1)
def rubric_model():
    """Schema di output della rubrica.

    Costruito su richiesta perché pydantic serve solo a questo stadio: le
    misure deterministiche di `text_metrics` devono restare eseguibili senza
    alcuna dipendenza esterna.
    """
    try:
        from pydantic import BaseModel, Field
    except ImportError as exc:  # pragma: no cover - dipende dall'ambiente
        raise RuntimeError(
            'La rubrica richiede pydantic e il client del fornitore scelto.\n'
            '  pip install -r requirements.txt'
        ) from exc

    class RubricScores(BaseModel):
        """Punteggi della rubrica per una singola trascrizione."""

        analytic: int = Field(ge=0, le=100, description='Analytical thinking, 0-100')
        clout: int = Field(ge=0, le=100, description='Confidence and social status, 0-100')
        authenticity: int = Field(ge=0, le=100, description='Spontaneous honesty, 0-100')
        tone: int = Field(ge=0, le=100, description='Emotional tone, 50 = neutral')
        contains_support_commitment: bool = Field(
            description='The text explicitly promises support to someone'
        )
        contains_support_request: bool = Field(
            description='The text explicitly asks someone for support'
        )
        insufficient_text: bool = Field(
            description='True when the transcript carries too little language to rate'
        )
        rationale: str = Field(
            description='One sentence, at most 25 words, justifying the ratings'
        )

    return RubricScores


SCALE_FIELDS = ('analytic', 'clout', 'authenticity', 'tone')
FLAG_FIELDS = (
    'contains_support_commitment', 'contains_support_request', 'insufficient_text',
)


@dataclass
class RubricUnit:
    """Una trascrizione da valutare, con la sua chiave di ricongiungimento."""

    key: tuple
    unit: str
    transcript: str
    n_messages: int
    treatment: str
    target: str


def build_units(features_rows, level: str, transcript_lookup) -> list[RubricUnit]:
    """Costruisce le unità da valutare a partire dalle righe aggregate."""
    from .aggregate import LEVEL_KEYS

    keys = LEVEL_KEYS[level]
    targets = {
        'dyad_directed': 'the sender',
        'dyad': 'both participants',
        'sender_group': 'the sender',
        'group': 'all three participants',
    }
    units = []
    for row in features_rows:
        key = tuple(str(row.get(k, '')) for k in keys)
        transcript = transcript_lookup.get(key, '')
        if not transcript.strip():
            continue
        units.append(
            RubricUnit(
                key=key,
                unit=level,
                transcript=transcript,
                n_messages=int(row.get('n_messages', 0) or 0),
                treatment=row.get('treatment', ''),
                target=targets.get(level, 'the participants'),
            )
        )
    return units


def _user_message(unit: RubricUnit) -> str:
    return USER_TEMPLATE.format(
        unit=unit.unit,
        n_messages=unit.n_messages,
        treatment=unit.treatment or 'unknown',
        transcript=unit.transcript,
        target=unit.target,
    )


def _request_params(unit: RubricUnit, model: str) -> dict:
    return dict(
        model=model,
        max_tokens=8000,
        # Il prompt di sistema è identico per ogni chiamata: metterlo in cache
        # abbatte il costo dell'input su corpus grandi.
        system=[{
            'type': 'text',
            'text': SYSTEM_PROMPT,
            'cache_control': {'type': 'ephemeral'},
        }],
        thinking={'type': 'adaptive'},
        output_config={'effort': 'medium'},
        messages=[{'role': 'user', 'content': _user_message(unit)}],
    )


def _empty_scores() -> dict:
    scores = {field: None for field in SCALE_FIELDS}
    scores.update({field: None for field in FLAG_FIELDS})
    scores['rationale'] = ''
    return scores


def _scores_from_parsed(parsed, model: str) -> dict:
    result = {field: getattr(parsed, field) for field in SCALE_FIELDS}
    result.update({field: int(getattr(parsed, field)) for field in FLAG_FIELDS})
    result['rationale'] = parsed.rationale
    result['error'] = ''
    result['model'] = model
    return result


# --- Fornitori ------------------------------------------------------------


def available_providers() -> list[str]:
    """Fornitori utilizzabili con le credenziali presenti nell'ambiente.

    Ollama è elencato solo se risponde davvero: dichiararlo disponibile perché
    "tanto è locale" porterebbe a fallire a metà esecuzione.
    """
    usable = []
    for name in PROVIDER_PRIORITY:
        env_key = PROVIDERS[name]['env_key']
        if env_key is None:
            if _ollama_is_running():
                usable.append(name)
        elif os.environ.get(env_key, '').strip():
            usable.append(name)
    return usable


def ollama_models() -> list[str]:
    """Modelli effettivamente installati in Ollama; lista vuota se non risponde."""
    import json
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen('http://localhost:11434/api/tags', timeout=2) as r:
            payload = json.loads(r.read().decode('utf-8'))
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return []
    return [m.get('name', '') for m in payload.get('models') or []]


def _ollama_is_running() -> bool:
    """Ollama è utilizzabile solo se ha almeno un modello installato.

    Il server risponde anche a installazione vuota. Considerarlo disponibile in
    quel caso porta a un fallimento lento e incomprensibile: ogni valutazione
    fallisce e viene ritentata, e su centinaia di unità la pipeline sembra
    bloccata invece che mal configurata.
    """
    return bool(ollama_models())


def resolve_provider(preferred: str | None = None) -> str:
    """Sceglie il fornitore, o spiega come renderne disponibile uno."""
    if preferred:
        if preferred not in PROVIDERS:
            raise SystemExit(f'Fornitore sconosciuto: {preferred}')
        env_key = PROVIDERS[preferred]['env_key']
        if env_key and not os.environ.get(env_key, '').strip():
            raise SystemExit(
                f"\nIl fornitore '{preferred}' richiede {env_key}, che non è "
                f'impostata.\n  python run.py keys\n'
            )
        return preferred

    usable = available_providers()
    if usable:
        return usable[0]

    raise SystemExit(
        '\nLa rubrica di validazione richiede un modello linguistico. Opzioni:\n'
        '  - imposta OPENAI_API_KEY (la stessa chiave che usa TopicGPT), oppure\n'
        '  - imposta ANTHROPIC_API_KEY, oppure\n'
        '  - avvia un modello in locale: ollama pull llama3\n\n'
        '  python run.py keys\n'
    )


def default_model_for(provider: str) -> str:
    return PROVIDERS[provider]['default_model']


def check_models_available(provider: str, models) -> None:
    """Verifica prima di partire che i modelli richiesti esistano.

    Si controlla solo dove è possibile e istantaneo, cioè in locale: scoprire a
    metà di centinaia di chiamate che il modello non c'è è il modo peggiore di
    accorgersene.
    """
    if provider != 'ollama':
        return
    installed = ollama_models()
    # Ollama accetta sia "llama3" sia "llama3:latest": si confronta il nome base.
    base = {name.split(':')[0] for name in installed}
    missing = [m for m in models if m.split(':')[0] not in base]
    if missing:
        elenco = ', '.join(installed) if installed else 'nessuno'
        raise SystemExit(
            f"\nModelli non installati in Ollama: {', '.join(missing)}\n"
            f'  installati: {elenco}\n'
            f"  scaricali con:  ollama pull {missing[0]}\n"
        )


def make_client(provider: str):
    if provider == 'anthropic':
        import anthropic
        return anthropic.Anthropic()

    from openai import OpenAI
    if provider == 'ollama':
        # La chiave è richiesta dalla libreria ma ignorata dal server locale.
        return OpenAI(base_url=OLLAMA_BASE_URL, api_key='ollama')
    return OpenAI(api_key=os.environ['OPENAI_API_KEY'],
                  base_url=os.environ.get('OPENAI_BASE_URL') or None)


# --- Valutazione ----------------------------------------------------------


def score_unit(client, unit: RubricUnit, model: str = DEFAULT_MODEL,
               provider: str = 'anthropic') -> dict:
    """Valuta una trascrizione. Restituisce i punteggi o l'errore incontrato."""
    if provider == 'anthropic':
        return _score_anthropic(client, unit, model)
    return _score_openai_compatible(client, unit, model)


def _score_anthropic(client, unit: RubricUnit, model: str, attempt: int = 0) -> dict:
    import anthropic

    try:
        response = client.messages.parse(
            output_format=rubric_model(),
            **_request_params(unit, model),
        )
    except anthropic.NotFoundError as exc:
        raise RuntimeError(f'modello non disponibile: {model}') from exc
    except anthropic.RateLimitError as exc:
        if attempt >= 4:
            return dict(_empty_scores(), error='rate_limit')
        retry_after = int(exc.response.headers.get('retry-after', '30'))
        time.sleep(retry_after)
        return _score_anthropic(client, unit, model, attempt + 1)
    except anthropic.APIStatusError as exc:
        if exc.status_code >= 500 and attempt < 4:
            time.sleep(5 * (attempt + 1))
            return _score_anthropic(client, unit, model, attempt + 1)
        return dict(_empty_scores(), error=f'api_status_{exc.status_code}')
    except anthropic.APIConnectionError:
        if attempt >= 4:
            return dict(_empty_scores(), error='connection')
        time.sleep(5 * (attempt + 1))
        return _score_anthropic(client, unit, model, attempt + 1)

    if response.stop_reason == 'refusal':
        category = getattr(response.stop_details, 'category', None)
        return dict(_empty_scores(), error=f'refusal:{category}')

    return _scores_from_parsed(response.parsed_output, model)


def _json_instruction() -> str:
    """Schema descritto nel prompt.

    Si usa la modalità JSON generica anziché lo schema vincolato: quest'ultima
    non è supportata allo stesso modo da tutti gli endpoint compatibili — in
    particolare da Ollama — e la validazione avviene comunque in locale con
    pydantic, che è il controllo che conta.
    """
    fields = ', '.join(f'"{f}": integer 0-100' for f in SCALE_FIELDS)
    flags = ', '.join(f'"{f}": true/false' for f in FLAG_FIELDS)
    return (
        '\n\nRespond with a single JSON object and nothing else, with exactly '
        f'these keys: {fields}, {flags}, "rationale": string of at most 25 words.'
    )


def _score_openai_compatible(client, unit: RubricUnit, model: str,
                             attempt: int = 0) -> dict:
    """Percorso per OpenAI e per qualunque endpoint compatibile, Ollama incluso."""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT + _json_instruction()},
                {'role': 'user', 'content': _user_message(unit)},
            ],
            response_format={'type': 'json_object'},
        )
    except Exception as exc:  # noqa: BLE001 - le eccezioni variano per endpoint
        if attempt >= 4:
            return dict(_empty_scores(), error=f'api_error:{type(exc).__name__}')
        time.sleep(5 * (attempt + 1))
        return _score_openai_compatible(client, unit, model, attempt + 1)

    text = (response.choices[0].message.content or '').strip()
    try:
        parsed = rubric_model().model_validate_json(text)
    except Exception:  # noqa: BLE001 - risposta non conforme allo schema
        # Una risposta malformata è spesso transitoria: si riprova, e solo dopo
        # si registra l'errore, così il dato mancante resta tracciato.
        if attempt < 2:
            return _score_openai_compatible(client, unit, model, attempt + 1)
        return dict(_empty_scores(), error='unparseable')

    return _scores_from_parsed(parsed, model)


def score_units(units, models=None, replicates=1, progress=None, provider=None):
    """Valuta tutte le unità, con repliche e/o più giudici.

    Restituisce una riga per unità: media fra tutte le valutazioni, deviazione
    standard come stima dell'errore di misura, e i punteggi grezzi di ciascuna
    valutazione per gli usi di controllo.
    """
    provider = resolve_provider(provider)
    models = list(models) if models else [default_model_for(provider)]
    check_models_available(provider, models)

    client = make_client(provider)
    rows = []
    total = len(units) * len(models) * replicates
    done = 0

    for unit in units:
        judgements = []
        for model in models:
            for _ in range(replicates):
                judgements.append(score_unit(client, unit, model, provider))
                done += 1
                if progress:
                    progress(done, total)

        rows.append(_summarize(unit, judgements))
    return rows


def _summarize(unit: RubricUnit, judgements) -> dict:
    from .aggregate import LEVEL_KEYS

    row = dict(zip(LEVEL_KEYS[unit.unit], unit.key))
    valid = [j for j in judgements if not j.get('error')]

    for field in SCALE_FIELDS:
        values = [j[field] for j in valid if j.get(field) is not None]
        row[f'llm_{field}'] = round(statistics.mean(values), 3) if values else ''
        row[f'llm_{field}_sd'] = (
            round(statistics.stdev(values), 3) if len(values) > 1 else ''
        )
    for field in FLAG_FIELDS:
        values = [j[field] for j in valid if j.get(field) is not None]
        # Maggioranza fra le valutazioni; a parità si sceglie 0.
        row[f'llm_{field}'] = int(sum(values) * 2 > len(values)) if values else ''

    row['llm_n_judgements'] = len(valid)
    row['llm_n_errors'] = len(judgements) - len(valid)
    row['llm_errors'] = ';'.join(sorted({j['error'] for j in judgements if j.get('error')}))
    row['llm_rationale'] = valid[0]['rationale'] if valid else ''
    row['llm_models'] = ','.join(sorted({j.get('model', '') for j in valid if j.get('model')}))
    return row


# --- Modalità batch, per il dataset finale ---------------------------------


def submit_batch(units, model: str = DEFAULT_MODEL, replicates: int = 1):
    """Invia le valutazioni alla Batches API (metà prezzo, esito asincrono).

    Disponibile solo con il fornitore Anthropic. Con gli altri backend si usa
    la modalità sincrona, che sul volume di questo studio resta praticabile.

    Restituisce l'id del batch: va conservato, perché i risultati si ritirano
    con `collect_batch` anche in una sessione successiva.
    """
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    client = anthropic.Anthropic()
    requests = []
    for index, unit in enumerate(units):
        for replicate in range(replicates):
            params = _request_params(unit, model)
            params['output_config'] = dict(
                params['output_config'],
                format={
                    'type': 'json_schema',
                    'schema': rubric_model().model_json_schema(),
                },
            )
            requests.append(
                Request(
                    custom_id=f'{index}-{replicate}',
                    params=MessageCreateParamsNonStreaming(**params),
                )
            )

    batch = client.messages.batches.create(requests=requests)
    return batch.id


def collect_batch(batch_id: str, units, poll_seconds: int = 60, progress=None):
    """Attende la fine del batch e ricompone le righe nell'ordine delle unità."""
    import anthropic

    client = anthropic.Anthropic()
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == 'ended':
            break
        if progress:
            progress(batch.request_counts.processing)
        time.sleep(poll_seconds)

    # I risultati arrivano in ordine arbitrario: si indicizza per custom_id.
    by_unit = {index: [] for index in range(len(units))}
    for result in client.messages.batches.results(batch_id):
        index = int(result.custom_id.split('-')[0])
        if result.result.type != 'succeeded':
            by_unit[index].append(dict(_empty_scores(), error=result.result.type))
            continue
        message = result.result.message
        if message.stop_reason == 'refusal':
            by_unit[index].append(dict(_empty_scores(), error='refusal'))
            continue
        text = next((b.text for b in message.content if b.type == 'text'), '')
        try:
            payload = rubric_model().model_validate_json(text)
        except Exception:  # noqa: BLE001 - risposta non conforme allo schema
            by_unit[index].append(dict(_empty_scores(), error='unparseable'))
            continue
        row = {field: getattr(payload, field) for field in SCALE_FIELDS}
        row.update({field: int(getattr(payload, field)) for field in FLAG_FIELDS})
        row['rationale'] = payload.rationale
        row['error'] = ''
        row['model'] = message.model
        by_unit[index].append(row)

    return [_summarize(unit, by_unit[i]) for i, unit in enumerate(units)]


def has_credentials() -> bool:
    """True se almeno un fornitore è utilizzabile."""
    return bool(available_providers())


def dry_run_payload(units, model: str = DEFAULT_MODEL) -> str:
    """Anteprima della prima richiesta, per ispezione senza spendere token."""
    if not units:
        return '(nessuna unità da valutare)'
    params = _request_params(units[0], model)
    preview = dict(
        model=params['model'],
        effort=params['output_config']['effort'],
        system=params['system'][0]['text'][:400] + '...',
        user=params['messages'][0]['content'],
    )
    try:
        preview['output_format'] = rubric_model().model_json_schema()
    except RuntimeError as exc:
        # L'anteprima deve restare utile anche senza le dipendenze opzionali.
        preview['output_format'] = f'(schema non disponibile: {exc})'
    return json.dumps(preview, indent=2, ensure_ascii=False)
