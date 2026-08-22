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

import contextlib
import io
import json
import re
import sys
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

# TopicGPT commenta ogni documento con print() su stdout, mentre la barra di
# avanzamento vive su stderr: ogni messaggio manda la barra a capo, e al posto
# di una riga che avanza si ottengono centinaia di righe. I messaggi ripetitivi
# vengono quindi raccolti e riassunti a fine fase; quelli non previsti passano
# invariati, perche' nascondere un messaggio sconosciuto e' peggio del disordine.
NOISY_LINES = [
    ('Invalid topic format', 'documenti senza topic riconosciuto'),
    ('Lower level topics are not allowed', 'topic di livello inferiore scartati'),
    ('Error: Row', 'righe senza topic'),
    ('Hallucinated:', 'topic inventati dal modello'),
    ('Document is too long', 'documenti troncati'),
    ('Too many topics', 'elenchi di topic potati'),
]

# Righe di intestazione che ripetono parametri gia' noti a chi ha lanciato.
BANNER_LINES = (
    '---', 'Initializing', 'Model:', 'Data file:', 'Prompt file:',
    'Seed file:', 'Output file:', 'Topic file:', 'Generation file:',
    'Refined file:', 'Updated file:', 'Mapping file:', 'Prompt token usage',
    'Response token usage',
)


class _Digest(io.TextIOBase):
    """Raccoglie stdout di TopicGPT contando i messaggi ripetitivi."""

    def __init__(self):
        self.counts = {}
        self.passthrough = []
        self._partial = ''

    def write(self, text):
        self._partial += text
        while '\n' in self._partial:
            line, self._partial = self._partial.split('\n', 1)
            self._handle(line.strip())
        return len(text)

    def _handle(self, line):
        if not line or line.startswith(BANNER_LINES):
            return
        for needle, label in NOISY_LINES:
            if needle in line:
                self.counts[label] = self.counts.get(label, 0) + 1
                return
        self.passthrough.append(line)

    def flush(self):
        if self._partial.strip():
            self._handle(self._partial.strip())
            self._partial = ''

    def report(self, prefix='    '):
        """Stampa il riassunto: prima i messaggi non previsti, poi i conteggi."""
        self.flush()
        for line in self.passthrough:
            print(f'{prefix}{line}')
        for label, count in sorted(self.counts.items(), key=lambda kv: -kv[1]):
            print(f'{prefix}{count} {label}')


@contextlib.contextmanager
def _quiet(verbose: bool):
    """Silenzia lo stdout di TopicGPT lasciando intatta la barra su stderr."""
    if verbose:
        yield None
        return
    digest = _Digest()
    try:
        with contextlib.redirect_stdout(digest):
            yield digest
    finally:
        sys.stdout.flush()


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


def check_model_compatibility(api: str, model: str) -> None:
    """Verifica che il modello accetti i parametri che TopicGPT invia.

    TopicGPT fissa `temperature` e `top_p` in tutte le fasi. Alcuni modelli
    recenti li rifiutano con un 400, e la libreria reagisce riprovando tre
    volte con sessanta secondi di attesa fra un tentativo e l'altro: senza
    questo controllo l'incompatibilita' emergerebbe dopo due minuti di nulla,
    e su ogni documento.

    Si prova con una chiamata minima invece di tenere un elenco di modelli
    incompatibili, che sarebbe vecchio il mese prossimo.
    """
    if api != 'openai':
        return
    try:
        from openai import OpenAI
    except ImportError:
        return

    try:
        OpenAI().chat.completions.create(
            model=model,
            messages=[{'role': 'user', 'content': 'ok'}],
            temperature=0.0,
            top_p=1.0,
            max_completion_tokens=5,
        )
    except Exception as exc:  # noqa: BLE001 - qualunque rifiuto e' informativo
        message = str(exc)
        if 'temperature' in message or 'top_p' in message:
            raise TopicGPTUnavailable(
                f"Il modello {model} non accetta i parametri che TopicGPT "
                f"invia (temperature e top_p sono fissati nel codice degli "
                f"autori).\n"
                f"  Usa un modello che li supporta, per esempio gpt-4o, che e' "
                f"anche quello del paper.\n"
                f"  I modelli recenti restano utilizzabili per la rubrica: "
                f"--llm-models {model}"
            ) from None
        # Qualunque altro errore (chiave, rete, modello inesistente) viene
        # riportato tale e quale: non e' un problema di compatibilita'.
        raise TopicGPTUnavailable(
            f'Il modello {model} non risponde: {message[:200]}'
        ) from None


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
    seed_file: Path | None = None,
    assignment_documents=None,
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

    # Il seed e' un parametro del metodo, non codice: il repository ne fornisce
    # uno di esempio per il proprio corpus dimostrativo (legislazione USA), e il
    # prompt del paper istruisce il modello a rispondere "None" quando il
    # documento non contiene alcun topic riconoscibile. Con il seed sbagliato,
    # su conversazioni di chat quella e' la risposta per ogni documento.
    seed_path = Path(seed_file) if seed_file else (repo_path / PROMPT_FILES['seed'])
    if not seed_path.is_file():
        raise TopicGPTUnavailable(f'File seed non trovato: {seed_path}')

    generation_out = outdir / 'generation_1.jsonl'
    topics_lvl1 = outdir / 'generation_1.md'

    print('  [1/4] generazione dei topic', flush=True)
    with _quiet(verbose) as digest:
        generate_topic_lvl1(
            api=api,
            model=model,
            data=str(data_file),
            prompt_file=str(repo_path / PROMPT_FILES['generation']),
            seed_file=str(seed_path),
            out_file=str(generation_out),
            topic_file=str(topics_lvl1),
            verbose=verbose,
        )
    if digest:
        digest.report()

    topics_for_assignment = topics_lvl1
    # I topic si possono indurre su un'unita' ampia e assegnare a una piu' fine:
    # l'induzione ha bisogno di documenti sostanziosi, l'assegnazione no.
    if assignment_documents is not None:
        data_for_assignment = outdir / 'topicgpt_assignment_input.jsonl'
        write_jsonl(data_for_assignment, assignment_documents)
    else:
        data_for_assignment = data_file

    if refine:
        refined_topics = outdir / 'generation_1_refined.md'
        refined_generation = outdir / 'generation_1_updated.jsonl'
        print('  [2/4] raffinamento', flush=True)
        with _quiet(verbose) as digest:
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
        if digest:
            digest.report()
        topics_for_assignment = refined_topics

    assignment_out = outdir / 'assignment.jsonl'
    print('  [3/4] assegnazione ai documenti', flush=True)
    with _quiet(verbose) as digest:
        assign_topics(
            api=api,
            model=model,
            data=str(data_for_assignment),
            prompt_file=str(repo_path / PROMPT_FILES['assignment']),
            out_file=str(assignment_out),
            topic_file=str(topics_for_assignment),
            verbose=verbose,
        )
    if digest:
        digest.report()

    corrected_out = outdir / 'assignment_corrected.jsonl'
    print('  [4/4] correzione delle assegnazioni', flush=True)
    with _quiet(verbose) as digest:
        correct_topics(
            api=api,
            model=model,
            data_path=str(assignment_out),
            prompt_path=str(repo_path / PROMPT_FILES['correction']),
            topic_path=str(topics_for_assignment),
            output_path=str(corrected_out),
            verbose=verbose,
        )
    if digest:
        digest.report()

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
