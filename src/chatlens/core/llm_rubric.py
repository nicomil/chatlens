"""
A second, independent measurement of the LIWC-style constructs: a rubric scored
by a language model.

Its job is to validate the dictionary-based measures in `text_metrics`. The two
routes are methodologically different — one counts function words, the other
reads the text — so a high correlation between them is evidence of convergent
validity; a low correlation is a finding to report, not to hide.

Why the aggregated text is scored, not the single message
---------------------------------------------------------
The same argument as for the automatic measures: a five-word chat turn does not
carry enough signal for a 0-100 scale. The rubric therefore runs on already
aggregated transcripts — directed dyad, dyad, group — which are also the units
the analysis requires.

Reliability
-----------
With `--llm-replicates 2` the same transcript is scored several times in
independent calls: the spread across replicates is the test-retest estimate of
measurement error, and lands in the dataset as `*_sd`. Several judge models can
also be named (`--llm-models`), giving agreement between different raters
rather than between replicates of the same one.

Cost
----
For large volumes use `--llm-batch`, which uses the Batches API at half price
(Anthropic provider only). On the pilot (25 groups, 311 messages) the calls
number a few hundred and the synchronous mode is enough.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from dataclasses import dataclass

from . import rubric_spec

# The rubric does not depend on a specific provider: what it needs is a model
# that follows instructions and returns JSON. Three backends are therefore
# supported, and the one to use is chosen from the credentials available.
#
# `openai` also serves anyone who does not want a second key: if OpenAI is
# already used for TopicGPT, the same key covers this stage. `ollama` runs
# locally and needs no credential at all.
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
        env_key=None,  # local: no key
        label='Ollama (local)',
    ),
}

# Order of preference when no provider is named explicitly.
PROVIDER_PRIORITY = ('anthropic', 'openai', 'ollama')

OLLAMA_BASE_URL = 'http://localhost:11434/v1'

DEFAULT_MODEL = PROVIDERS['anthropic']['default_model']

def dimensions() -> tuple:
    """What this workspace's rubric measures.

    Declared once in rubric_spec and, where a workspace says otherwise, in its
    experiment.toml. Everything the rubric needs — the prompt, the schema, the
    column names — is generated from this one list, so the three cannot drift
    apart the way they used to.
    """
    from . import config

    experiment = config.EXPERIMENT
    if experiment is None:
        return rubric_spec.DEFAULT_DIMENSIONS
    try:
        return rubric_spec.from_config(experiment.rubric_dimensions)
    except ValueError as exc:
        raise SystemExit(f'\nIn experiment.toml: {exc}\n') from None


def rubric_context() -> str:
    from . import config

    experiment = config.EXPERIMENT
    if experiment is not None and experiment.rubric_context:
        return experiment.rubric_context
    return rubric_spec.DEFAULT_CONTEXT


def system_prompt() -> str:
    return rubric_spec.build_system_prompt(dimensions(), rubric_context())


def scale_fields() -> tuple:
    return rubric_spec.scales(dimensions())


def flag_fields() -> tuple:
    return rubric_spec.flags(dimensions())


USER_TEMPLATE = """Transcript ({unit}), {n_messages} message(s), \
treatment "{treatment}":

<transcript>
{transcript}
</transcript>

Rate the language of {target} in this transcript."""


def rubric_model():
    """Output schema of the rubric, built from the declared dimensions.

    Built on demand because pydantic is needed only at this stage: the
    deterministic measures in `text_metrics` must stay runnable with no
    external dependency at all.
    """
    return rubric_spec.build_model(dimensions())


@dataclass
class RubricUnit:
    """A transcript to score, with the key that rejoins it to the data."""

    key: tuple
    unit: str
    transcript: str
    n_messages: int
    treatment: str
    target: str


def build_units(features_rows, level: str, transcript_lookup) -> list[RubricUnit]:
    """Build the units to score from the aggregated rows."""
    from .aggregate import LEVEL_KEYS

    keys = LEVEL_KEYS[level]
    # What the prompt calls the people being rated. The group level is the
    # only one that depends on how many there are, so the experiment says it;
    # the coalition adapter keeps "all three participants", which is what the
    # cached ratings were produced against.
    from . import config

    experiment = config.EXPERIMENT
    everyone = (experiment.group_target if experiment
                else 'all three participants')
    targets = {
        'dyad_directed': 'the sender',
        'dyad': 'both participants',
        'sender_group': 'the sender',
        'group': everyone,
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
        # The system prompt is identical on every call: caching it cuts the
        # input cost on large corpora.
        system=[{
            'type': 'text',
            'text': system_prompt(),
            'cache_control': {'type': 'ephemeral'},
        }],
        thinking={'type': 'adaptive'},
        output_config={'effort': 'medium'},
        messages=[{'role': 'user', 'content': _user_message(unit)}],
    )


def _empty_scores() -> dict:
    scores = {field: None for field in scale_fields()}
    scores.update({field: None for field in flag_fields()})
    scores['rationale'] = ''
    return scores


def _scores_from_parsed(parsed, model: str) -> dict:
    result = {field: getattr(parsed, field) for field in scale_fields()}
    result.update({field: int(getattr(parsed, field)) for field in flag_fields()})
    result['rationale'] = parsed.rationale
    result['error'] = ''
    result['model'] = model
    return result


# --- Fornitori ------------------------------------------------------------


def available_providers() -> list[str]:
    """Providers usable with the credentials present in the environment.

    Ollama is listed only if it actually answers: calling it available because
    "it is local anyway" would lead to failing halfway through a run.
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
    """Models actually installed in Ollama; empty list if it does not answer."""
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
    """Ollama is usable only if it has at least one model installed.

    The server answers even on an empty installation. Treating it as available
    in that case leads to a slow, incomprehensible failure: every rating fails
    and is retried, and across hundreds of units the pipeline looks stuck rather
    than misconfigured.
    """
    return bool(ollama_models())


def resolve_provider(preferred: str | None = None) -> str:
    """Pick the provider, or explain how to make one available."""
    if preferred:
        if preferred not in PROVIDERS:
            raise SystemExit(f'Unknown provider: {preferred}')
        env_key = PROVIDERS[preferred]['env_key']
        if env_key and not os.environ.get(env_key, '').strip():
            raise SystemExit(
                f"\nProvider '{preferred}' requires {env_key}, which is not "
                f'set.\n  chatlens keys\n'
            )
        return preferred

    usable = available_providers()
    if usable:
        return usable[0]

    raise SystemExit(
        '\nThe validation rubric needs a language model. Options:\n'
        '  - set OPENAI_API_KEY (the same key TopicGPT uses), or\n'
        '  - set ANTHROPIC_API_KEY, or\n'
        '  - start a local model: ollama pull llama3\n\n'
        '  chatlens keys\n'
    )


def default_model_for(provider: str) -> str:
    return PROVIDERS[provider]['default_model']


def check_models_available(provider: str, models) -> None:
    """Check before starting that the requested models exist.

    Checked only where it is possible and instant, that is locally: finding out
    halfway through hundreds of calls that the model is missing is the worst way
    to learn it.
    """
    if provider != 'ollama':
        return
    installed = ollama_models()
    # Ollama accepts both "llama3" and "llama3:latest": compare the base name.
    base = {name.split(':')[0] for name in installed}
    missing = [m for m in models if m.split(':')[0] not in base]
    if missing:
        listing = ', '.join(installed) if installed else 'none'
        raise SystemExit(
            f"\nModels not installed in Ollama: {', '.join(missing)}\n"
            f'  installed: {listing}\n'
            f'  pull them with:  ollama pull {missing[0]}\n'
        )


def make_client(provider: str):
    if provider == 'anthropic':
        import anthropic
        return anthropic.Anthropic()

    from openai import OpenAI
    if provider == 'ollama':
        # The library demands a key; the local server ignores it.
        return OpenAI(base_url=OLLAMA_BASE_URL, api_key='ollama')
    return OpenAI(api_key=os.environ['OPENAI_API_KEY'],
                  base_url=os.environ.get('OPENAI_BASE_URL') or None)


# --- Scoring ---------------------------------------------------------------

# Longer than this is not a pause between attempts, it is a hung run.
MAX_RETRY_SLEEP = 300


def _retry_after(exc, default: int = 30) -> float:
    """How long the server asked us to wait, bounded and tolerant.

    The header is not always an integer — the specification allows an HTTP date
    — so parsing it strictly turns a rate limit into a crash halfway through a
    paid run. And the value is not always small, so an unbounded sleep parks the
    process for hours.
    """
    response = getattr(exc, 'response', None)
    headers = getattr(response, 'headers', None) or {}
    try:
        seconds = float(headers.get('retry-after', ''))
    except (TypeError, ValueError):
        seconds = float(default)
    return max(0.0, min(seconds, MAX_RETRY_SLEEP))


def _is_terminal(exc) -> bool:
    """True for an error that another attempt cannot fix.

    A wrong key, a model that does not exist, a malformed request: each fails
    the same way every time. Retrying them five times with a growing pause turns
    a mistake that should surface in a second into fifty seconds of silence per
    unit — fourteen hours over a thousand units, and empty scores at the end.
    Rate limits are excluded: 429 is the one 4xx that waiting does fix.
    """
    status = getattr(exc, 'status_code', None)
    if status is None:
        status = getattr(getattr(exc, 'response', None), 'status_code', None)
    if status is None:
        return False
    try:
        status = int(status)
    except (TypeError, ValueError):
        return False
    return 400 <= status < 500 and status != 429


def score_unit(client, unit: RubricUnit, model: str = DEFAULT_MODEL,
               provider: str = 'anthropic') -> dict:
    """Score one transcript. Returns the scores or the error encountered."""
    if provider == 'anthropic':
        return _score_anthropic(client, unit, model)
    return _score_openai_compatible(client, unit, model,
                                    extra=_extra_params(provider))


def _score_anthropic(client, unit: RubricUnit, model: str, attempt: int = 0) -> dict:
    import anthropic

    try:
        response = client.messages.parse(
            output_format=rubric_model(),
            **_request_params(unit, model),
        )
    except anthropic.NotFoundError as exc:
        raise RuntimeError(f'model not available: {model}') from exc
    except anthropic.RateLimitError as exc:
        if attempt >= 4:
            return dict(_empty_scores(), error='rate_limit')
        time.sleep(_retry_after(exc))
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
    """Schema described in the prompt.

    Generic JSON mode is used rather than constrained schema: the latter is not
    supported uniformly across compatible endpoints — Ollama in particular — and
    validation happens locally with pydantic anyway, which is the check that
    matters.
    """
    fields = ', '.join(f'"{f}": integer 0-100' for f in scale_fields())
    flags = ', '.join(f'"{f}": true/false' for f in flag_fields())
    return (
        '\n\nRespond with a single JSON object and nothing else, with exactly '
        f'these keys: {fields}, {flags}, "rationale": string of at most 25 words.'
    )


def _extra_params(provider: str) -> dict:
    """Parameters that only one endpoint understands.

    Local reasoning models spend most of their time on a chain of thought this
    rubric throws away. `gemma4:e4b` on the study this was written for emitted
    794 tokens of *Thinking Process* before the 72 tokens of JSON — 92% of the
    generation, and the difference between 63 seconds a call and 9. Ollama
    turns it off through `reasoning_effort`, which is the only one of the three
    ways that reaches it: `think` in the body is dropped by the
    OpenAI-compatible endpoint, and `PARAMETER think false` in a Modelfile is
    not a parameter Ollama knows.

    Only for Ollama. On OpenAI the same field is a real one, meaningful to the
    reasoning models and an error on the rest, so sending it there would break
    the ordinary case to speed up a local one.
    """
    return {'reasoning_effort': 'none'} if provider == 'ollama' else {}


def _score_openai_compatible(client, unit: RubricUnit, model: str,
                             attempt: int = 0, extra=None) -> dict:
    """Path for OpenAI and any compatible endpoint, Ollama included."""
    extra = extra or {}
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': system_prompt() + _json_instruction()},
                {'role': 'user', 'content': _user_message(unit)},
            ],
            response_format={'type': 'json_object'},
            **extra,
        )
    except Exception as exc:  # noqa: BLE001 - exceptions vary by endpoint
        if _is_terminal(exc) or attempt >= 4:
            return dict(_empty_scores(), error=f'api_error:{type(exc).__name__}')
        time.sleep(min(5 * (attempt + 1), MAX_RETRY_SLEEP))
        return _score_openai_compatible(client, unit, model, attempt + 1, extra)

    text = (response.choices[0].message.content or '').strip()
    try:
        parsed = rubric_model().model_validate_json(text)
    except Exception:  # noqa: BLE001 - response does not match the schema
        # A malformed answer is often transient: retry first, and only then
        # record the error, so the missing datum stays traceable.
        if attempt < 2:
            return _score_openai_compatible(client, unit, model, attempt + 1,
                                            extra)
        return dict(_empty_scores(), error='unparseable')

    return _scores_from_parsed(parsed, model)


def unit_signature(unit: RubricUnit, models, replicates: int) -> str:
    """Fingerprint of a rating: if it changes, the result is not reusable.

    It covers the text, the prompt and the judges' configuration: changing the
    rubric or the model invalidates the cache automatically, while re-running
    the same analysis reuses it.
    """
    import hashlib

    material = '\x00'.join([
        unit.unit, unit.transcript, unit.treatment, unit.target,
        ','.join(sorted(models)), str(replicates), system_prompt(),
    ])
    return hashlib.sha256(material.encode('utf-8')).hexdigest()[:32]


def load_cache(path) -> dict:
    """Ratings already paid for in earlier runs, keyed by fingerprint."""
    if path is None or not path.is_file():
        return {}
    entries = {}
    with path.open(encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue  # line truncated by an interruption: ignore it
            if 'signature' in record and 'row' in record:
                entries[record['signature']] = record['row']
    return entries


def _append_cache(path, signature: str, row: dict) -> None:
    """Save the single rating immediately.

    One line at a time rather than all at the end: if the run is interrupted
    halfway, what has already been paid for stays available.
    """
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps({'signature': signature, 'row': row},
                                ensure_ascii=False) + '\n')


def cache_split(units, models, replicates: int, cache_path):
    """Separate the units already paid for from the ones still to pay.

    Returns `(reused, pending)`: `reused` maps a unit's position to the row
    read from the cache, `pending` is the list of `(position, unit)` still to be
    sent. Both paths use it, and so does the spending guard — asking about calls
    the cache will serve for nothing is how a free re-run gets refused.
    """
    cached = load_cache(cache_path)
    reused, pending = {}, []
    for index, unit in enumerate(units):
        row = cached.get(unit_signature(unit, models, replicates))
        if row is None:
            pending.append((index, unit))
        else:
            reused[index] = row
    return reused, pending


def score_units(units, models=None, replicates=1, progress=None, provider=None,
                cache_path=None):
    """Score every unit, with replicates and/or several judges.

    Returns one row per unit: the mean across all ratings, the standard
    deviation as an estimate of measurement error, and the raw scores of each
    rating for checking.

    Successful ratings are cached: re-running on the same data does not pay for
    them again. Failed ratings are not cached, so a transient problem is retried
    instead of being frozen in place.
    """
    if replicates < 1:
        raise ValueError(
            f'replicates must be at least 1, not {replicates}: with none, every '
            f'unit is rated by nobody and the run reports a success it did not '
            f'have.'
        )

    provider = resolve_provider(provider)
    models = list(models) if models else [default_model_for(provider)]
    check_models_available(provider, models)

    cached = load_cache(cache_path)
    client = None
    rows = []
    total = len(units) * len(models) * replicates
    done = 0
    reused = 0

    for unit in units:
        signature = unit_signature(unit, models, replicates)
        if signature in cached:
            rows.append(cached[signature])
            done += len(models) * replicates
            reused += 1
            if progress:
                progress(done, total)
            continue

        if client is None:
            client = make_client(provider)

        judgements = []
        for model in models:
            for _ in range(replicates):
                judgements.append(score_unit(client, unit, model, provider))
                done += 1
                if progress:
                    progress(done, total)

        row = _summarize(unit, judgements)
        rows.append(row)
        if judgements and not row.get('llm_n_errors'):
            _append_cache(cache_path, signature, row)
            # And in memory, not only on disk. Two units with the same
            # transcript have the same signature and the second was being paid
            # for again, because the dictionary consulted above was loaded once
            # before the loop and never learned anything the loop produced. On
            # the study this was written for that is 52 ratings of 2 963.
            cached[signature] = row

    if reused and progress:
        progress(total, total)
    return rows, reused


def _summarize(unit: RubricUnit, judgements) -> dict:
    from .aggregate import LEVEL_KEYS

    row = dict(zip(LEVEL_KEYS[unit.unit], unit.key))
    valid = [j for j in judgements if not j.get('error')]

    for field in scale_fields():
        values = [j[field] for j in valid if j.get(field) is not None]
        row[f'llm_{field}'] = round(statistics.mean(values), 3) if values else ''
        row[f'llm_{field}_sd'] = (
            round(statistics.stdev(values), 3) if len(values) > 1 else ''
        )
    for field in flag_fields():
        values = [j[field] for j in valid if j.get(field) is not None]
        # Majority across ratings; ties resolve to 0.
        row[f'llm_{field}'] = int(sum(values) * 2 > len(values)) if values else ''

    row['llm_n_judgements'] = len(valid)
    row['llm_n_errors'] = len(judgements) - len(valid)
    row['llm_errors'] = ';'.join(sorted({j['error'] for j in judgements if j.get('error')}))
    row['llm_rationale'] = valid[0]['rationale'] if valid else ''
    row['llm_models'] = ','.join(sorted({j.get('model', '') for j in valid if j.get('model')}))
    return row


# --- Batch mode, for the final dataset ------------------------------------


def submit_batch(units, model: str = DEFAULT_MODEL, replicates: int = 1):
    """Send the ratings to the Batches API (half price, asynchronous result).

    Available with the Anthropic provider only. With the other backends the
    synchronous mode is used, which at this study's volume stays practical.

    Returns the batch id: keep it, because the results are collected with
    `collect_batch`, possibly in a later session.
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


class BatchNotReady(RuntimeError):
    """The batch did not end within the time we were prepared to wait."""


# The provider undertakes to end a batch within 24 hours. Waiting appreciably
# longer than that is not patience, it is a process nobody will ever reclaim.
BATCH_DEADLINE = 26 * 60 * 60


def collect_batch(batch_id: str, units, poll_seconds: int = 60, progress=None,
                  deadline_seconds: float = BATCH_DEADLINE):
    """Wait for the batch to end and rebuild the rows in unit order.

    Waiting is bounded. A batch that has not ended by the deadline is not lost:
    it is still on the provider's side under the id in the message, and
    collecting it later costs nothing more.
    """
    import anthropic

    client = anthropic.Anthropic()
    started = time.monotonic()
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == 'ended':
            break
        if time.monotonic() - started > deadline_seconds:
            raise BatchNotReady(
                f'batch {batch_id} has not ended after '
                f'{deadline_seconds / 3600:.0f} hours (status: '
                f'{batch.processing_status}).\n'
                f'  Nothing is lost: the results stay on the provider\'s side '
                f'under that id, and what has already been paid for is paid '
                f'for. Collect them later with the same id.'
            )
        if progress:
            progress(batch.request_counts.processing)
        time.sleep(poll_seconds)

    # Results arrive in arbitrary order: index them by custom_id.
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
        except Exception:  # noqa: BLE001 - response does not match the schema
            by_unit[index].append(dict(_empty_scores(), error='unparseable'))
            continue
        row = {field: getattr(payload, field) for field in scale_fields()}
        row.update({field: int(getattr(payload, field)) for field in flag_fields()})
        row['rationale'] = payload.rationale
        row['error'] = ''
        row['model'] = message.model
        by_unit[index].append(row)

    return [_summarize(unit, by_unit[i]) for i, unit in enumerate(units)]


def score_units_batch(units, model: str = DEFAULT_MODEL, replicates: int = 1,
                      cache_path=None, on_submit=None, progress=None,
                      deadline_seconds: float = BATCH_DEADLINE):
    """The batch path, with the cache the synchronous path already had.

    Returns `(rows, reused)` like `score_units`. Without this, a batch run
    re-sent and re-paid for every unit it had already rated, and a batch that
    never ended left nothing at all on disk.
    """
    if replicates < 1:
        raise ValueError(f'replicates must be at least 1, not {replicates}')

    reused, pending = cache_split(units, [model], replicates, cache_path)
    rows = [None] * len(units)
    for index, row in reused.items():
        rows[index] = row

    if pending:
        pending_units = [unit for _, unit in pending]
        batch_id = submit_batch(pending_units, model, replicates)
        if on_submit:
            on_submit(batch_id)
        scored = collect_batch(batch_id, pending_units, progress=progress,
                               deadline_seconds=deadline_seconds)
        for (index, unit), row in zip(pending, scored):
            rows[index] = row
            if not row.get('llm_n_errors'):
                _append_cache(
                    cache_path,
                    unit_signature(unit, [model], replicates),
                    row,
                )

    return rows, len(reused)


def has_credentials() -> bool:
    """True if at least one provider is usable."""
    return bool(available_providers())


def dry_run_payload(units, model: str = DEFAULT_MODEL) -> str:
    """Preview of the first request, to inspect without spending tokens."""
    if not units:
        return '(no units to score)'
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
        # The preview must stay useful even without the optional dependencies.
        preview['output_format'] = f'(schema unavailable: {exc})'
    return json.dumps(preview, indent=2, ensure_ascii=False)
