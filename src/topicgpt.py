"""
Adattatore per TopicGPT (Pham et al., NAACL 2024).

Lo sperimentatore ha chiesto di usare rigorosamente il codice del paper: questo
modulo **non riscrive** l'algoritmo. Prepara l'input nel formato che TopicGPT si
aspetta, invoca le funzioni ufficiali del pacchetto nell'ordine previsto e
ricompone l'output sulle chiavi dell'esperimento. La generazione, il
raffinamento, l'assegnazione e la correzione dei topic restano interamente
codice degli autori.

Repository ufficiale: https://github.com/chtmp223/topicGPT

Installazione
-------------
Il pacchetto su PyPI (0.2.7) importa vLLM al primo livello, dipendenza pesante e
non installabile su macOS senza GPU; il ramo ``main`` su GitHub l'ha già resa un
extra opzionale. Conviene quindi installare dal repository, che serve comunque
perché **i file di prompt non sono dentro il pacchetto**: vivono in `prompt/`
nel repository e sono parte integrante del metodo.

    git clone https://github.com/chtmp223/topicGPT.git
    pip install ./topicGPT           # senza l'extra [vllm]

Unità di analisi
----------------
TopicGPT induce i topic da documenti, e un turno di chat di poche parole non è
un documento. Il default qui è la **coppia ordinata**: tutto ciò che i ha
scritto a j, che è anche l'unità in cui si gioca la persuasione. I topic
ottenuti si aggregano poi a livello di partecipante e di gruppo.

Backend
-------
TopicGPT parla con OpenAI, Azure, Vertex, Gemini, Ollama o vLLM. Il paper usa
OpenAI, che resta la scelta più fedele. Per usare Claude ci sono due strade
supportate dal codice degli autori senza modificarlo: il backend ``vertex``, che
nel repository costruisce un client ``AnthropicVertex``, oppure il backend
``openai`` puntato a un gateway compatibile tramite ``OPENAI_BASE_URL``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Il formato di risposta di TopicGPT per l'assegnazione: "[1] Nome: descrizione".
TOPIC_RE = re.compile(r"\[(\d)\]\s*([\w\s\-'\&]+)")

PROMPT_FILES = {
    'generation': 'prompt/generation_1.txt',
    'seed': 'prompt/seed_1.md',
    'refinement': 'prompt/refinement.txt',
    'assignment': 'prompt/assignment.txt',
    'correction': 'prompt/correction.txt',
}

UNIT_KEYS = {
    'dyad_directed': ('group_uid', 'sender_id_in_group', 'receiver_id_in_group'),
    'dyad': ('group_uid', 'dyad_key'),
    'sender_group': ('group_uid', 'sender_id_in_group'),
    'group': ('group_uid',),
}


class TopicGPTUnavailable(RuntimeError):
    """TopicGPT o i suoi file di prompt non sono disponibili."""


def check_installation(repo_path: Path) -> None:
    """Verifica pacchetto e file di prompt, con messaggi azionabili."""
    # Si verifica che il pacchetto esista senza importarlo: l'import trascina
    # torch e transformers e costa parecchi secondi, che in un controllo
    # preliminare — eseguito a ogni avvio — non hanno senso di spendersi.
    import importlib.util

    if importlib.util.find_spec('topicgpt_python') is None:
        raise TopicGPTUnavailable(
            'Il pacchetto topicgpt_python non è installato.\n'
            '  git clone https://github.com/chtmp223/topicGPT.git\n'
            '  pip install ./topicGPT'
        )

    missing = [name for name in PROMPT_FILES.values() if not (repo_path / name).is_file()]
    if missing:
        raise TopicGPTUnavailable(
            f'File di prompt mancanti sotto {repo_path}: {", ".join(missing)}.\n'
            'I prompt fanno parte del metodo e stanno nel repository, non nel '
            'pacchetto installato: clona il repository e passa --topicgpt-repo.'
        )


def build_documents(messages, unit: str = 'dyad_directed') -> list[dict]:
    """Compone i documenti per TopicGPT a partire dai messaggi.

    Ogni documento porta con sé un ``id`` che permette di ricongiungere i topic
    assegnati alle unità dell'esperimento: TopicGPT conserva le colonne extra
    del JSONL nel file di output.
    """
    from collections import defaultdict

    keys = UNIT_KEYS[unit]
    buckets = defaultdict(list)
    for message in messages:
        buckets[tuple(str(message.get(k, '')) for k in keys)].append(message)

    documents = []
    for key, bucket in sorted(buckets.items()):
        bucket.sort(key=lambda m: float(m.get('timestamp') or 0))
        lines = [
            f"{m.get('sender_color', '?')} to {m.get('receiver_color', '?')}: "
            f"{m.get('body', '')}"
            for m in bucket
        ]
        text = '\n'.join(lines).strip()
        if not text:
            continue
        documents.append(
            dict(
                id='|'.join(key),
                text=text,
                unit=unit,
                treatment=bucket[0].get('treatment', ''),
                n_messages=len(bucket),
            )
        )
    return documents


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def run_topicgpt(
    documents,
    outdir: Path,
    repo_path: Path,
    api: str = 'openai',
    model: str = 'gpt-4o',
    refine: bool = True,
    verbose: bool = True,
) -> Path:
    """Esegue la pipeline ufficiale e restituisce il file delle assegnazioni.

    Le quattro fasi sono quelle del paper: generazione dei topic di primo
    livello, raffinamento (fusione dei topic simili e rimozione di quelli rari),
    assegnazione ai documenti, correzione delle assegnazioni non valide.
    """
    check_installation(repo_path)
    from topicgpt_python import (
        assign_topics,
        correct_topics,
        generate_topic_lvl1,
        refine_topics,
    )

    outdir.mkdir(parents=True, exist_ok=True)
    data_file = outdir / 'topicgpt_input.jsonl'
    write_jsonl(data_file, documents)

    generation_out = outdir / 'generation_1.jsonl'
    topics_lvl1 = outdir / 'generation_1.md'

    generate_topic_lvl1(
        api=api,
        model=model,
        data=str(data_file),
        prompt_file=str(repo_path / PROMPT_FILES['generation']),
        seed_file=str(repo_path / PROMPT_FILES['seed']),
        out_file=str(generation_out),
        topic_file=str(topics_lvl1),
        verbose=verbose,
    )

    topics_for_assignment = topics_lvl1
    data_for_assignment = data_file
    if refine:
        refined_topics = outdir / 'generation_1_refined.md'
        refined_generation = outdir / 'generation_1_updated.jsonl'
        refine_topics(
            api=api,
            model=model,
            prompt_file=str(repo_path / PROMPT_FILES['refinement']),
            generation_file=str(generation_out),
            topic_file=str(topics_lvl1),
            out_file=str(refined_topics),
            updated_file=str(refined_generation),
            verbose=verbose,
            remove=True,
            mapping_file=str(outdir / 'refiner_mapping.json'),
        )
        topics_for_assignment = refined_topics

    assignment_out = outdir / 'assignment.jsonl'
    assign_topics(
        api=api,
        model=model,
        data=str(data_for_assignment),
        prompt_file=str(repo_path / PROMPT_FILES['assignment']),
        out_file=str(assignment_out),
        topic_file=str(topics_for_assignment),
        verbose=verbose,
    )

    corrected_out = outdir / 'assignment_corrected.jsonl'
    correct_topics(
        api=api,
        model=model,
        data_path=str(assignment_out),
        prompt_path=str(repo_path / PROMPT_FILES['correction']),
        topic_path=str(topics_for_assignment),
        output_path=str(corrected_out),
        verbose=verbose,
    )
    return corrected_out


def parse_assignments(path: Path) -> dict:
    """Estrae i topic assegnati, indicizzati per ``id`` del documento."""
    result = {}
    for row in read_jsonl(path):
        response = row.get('responses') or ''
        topics = []
        for _level, name in TOPIC_RE.findall(response):
            cleaned = name.strip()
            if cleaned and cleaned not in topics:
                topics.append(cleaned)
        result[row.get('id', '')] = dict(
            topics='|'.join(topics),
            topic_primary=topics[0] if topics else '',
            n_topics=len(topics),
        )
    return result


def topics_by_key(assignments: dict, unit: str) -> dict:
    """Riporta le assegnazioni sulle chiavi tuple usate dal merge."""
    return {tuple(doc_id.split('|')): value for doc_id, value in assignments.items()}


def rollup_topics(assignments: dict, unit: str, target: str) -> dict:
    """Aggrega i topic da un'unità fine a una più grossa.

    Serve quando i topic sono indotti sulle coppie ordinate ma servono anche a
    livello di partecipante o di gruppo: l'insieme dei topic dell'unità
    superiore è l'unione di quelli delle unità che la compongono.
    """
    from collections import defaultdict

    source_keys = UNIT_KEYS[unit]
    target_keys = UNIT_KEYS[target]
    positions = [source_keys.index(k) for k in target_keys if k in source_keys]
    if len(positions) != len(target_keys):
        raise ValueError(f'{target} non è aggregabile a partire da {unit}')

    buckets = defaultdict(list)
    for doc_id, value in assignments.items():
        parts = doc_id.split('|')
        key = tuple(parts[p] for p in positions)
        buckets[key].extend(t for t in value['topics'].split('|') if t)

    rolled = {}
    for key, topics in buckets.items():
        unique = []
        for topic in topics:
            if topic not in unique:
                unique.append(topic)
        rolled[key] = dict(
            topics='|'.join(unique),
            topic_primary=unique[0] if unique else '',
            n_topics=len(unique),
        )
    return rolled
