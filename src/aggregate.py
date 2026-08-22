"""
Aggregazione delle misure testuali e innesto sui dataset dell'esperimento.

Parte da `..._messages_long.csv` (prodotto da `src/merge.py`)
e produce le misure a quattro livelli:

``message``       il singolo messaggio (solo conteggi e sentiment)
``dyad_directed`` i messaggi che i manda a j — l'unità della persuasione
``dyad``          l'intera conversazione della coppia, nei due sensi
``sender_group``  tutto ciò che i ha scritto nel gruppo
``group``         l'intera conversazione della triade

Gli indici compositi (analytic, clout, authenticity, tone) vengono calcolati
sui conteggi *sommati* dell'unità, non come media di valori per messaggio: su
testi di poche parole la seconda strada produrrebbe rumore. La
standardizzazione avviene separatamente dentro ciascun livello, perché unità di
lunghezza molto diversa non sono confrontabili sulla stessa scala.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from .text_metrics import (
    COUNT_KEYS,
    analyze_message,
    score_counts,
    standardize,
    sum_counts,
)

LEVELS = ('dyad_directed', 'dyad', 'sender_group', 'group')

# Chiavi identificative per ciascun livello di aggregazione.
LEVEL_KEYS = {
    'dyad_directed': ('group_uid', 'sender_id_in_group', 'receiver_id_in_group'),
    'dyad': ('group_uid', 'dyad_key'),
    'sender_group': ('group_uid', 'sender_id_in_group'),
    'group': ('group_uid',),
}


def read_messages(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def analyze_messages(messages: list[dict]) -> list[dict]:
    """Aggiunge conteggi e sentiment a ogni messaggio."""
    enriched = []
    for message in messages:
        row = dict(message)
        row.update(analyze_message(message.get('body', '')))
        enriched.append(row)
    return enriched


def _group_by(messages, keys):
    buckets = defaultdict(list)
    for message in messages:
        buckets[tuple(message.get(k, '') for k in keys)].append(message)
    return buckets


def aggregate_level(messages: list[dict], level: str) -> list[dict]:
    """Aggrega i messaggi a un livello e calcola gli indici."""
    keys = LEVEL_KEYS[level]
    rows = []
    for key_values, bucket in _group_by(messages, keys).items():
        counts = sum_counts(
            {k: int(m.get(k, 0) or 0) for k in COUNT_KEYS + ['wc', 'char_count',
                                                            'sixltr', 'qmark',
                                                            'exclam', 'unique_wc']}
            for m in bucket
        )
        row = dict(zip(keys, key_values))
        row.update(score_counts(counts))
        row['n_messages'] = len(bucket)
        row['mean_words_per_message'] = counts['wc'] / len(bucket) if bucket else 0.0

        timestamps = sorted(float(m['timestamp']) for m in bucket if m.get('timestamp'))
        row['first_timestamp'] = timestamps[0] if timestamps else ''
        row['last_timestamp'] = timestamps[-1] if timestamps else ''
        row['duration_seconds'] = (
            round(timestamps[-1] - timestamps[0], 3) if len(timestamps) > 1 else 0.0
        )
        # Ritmo dello scambio: intervallo mediano fra turni consecutivi.
        gaps = [b - a for a, b in zip(timestamps, timestamps[1:])]
        row['median_gap_seconds'] = round(sorted(gaps)[len(gaps) // 2], 3) if gaps else ''

        compounds = [
            float(m['sentiment_compound']) for m in bucket
            if m.get('sentiment_compound') not in (None, '')
        ]
        row['sentiment_compound_mean'] = (
            round(sum(compounds) / len(compounds), 6) if compounds else ''
        )
        backends = {m.get('sentiment_backend') for m in bucket}
        row['sentiment_backend'] = '/'.join(sorted(b for b in backends if b))
        row['treatment'] = bucket[0].get('treatment', '')
        rows.append(row)

    standardize(rows)
    return rows


def aggregate_all(messages: list[dict]) -> dict:
    return {level: aggregate_level(messages, level) for level in LEVELS}


# --- Innesto sui dataset dell'esperimento ----------------------------------

# Colonne portate dentro i dataset finali. Le altre restano nei file di
# feature, per non gonfiare oltre misura i CSV principali.
MERGE_COLUMNS = [
    'n_messages', 'wc', 'mean_words_per_message', 'type_token_ratio',
    'duration_seconds', 'median_gap_seconds',
    'analytic_cdi', 'analytic_z', 'analytic_100',
    'clout_raw', 'clout_z', 'clout_100',
    'authenticity_raw', 'authenticity_z', 'authenticity_100',
    'tone_raw', 'tone_z', 'tone_100',
    'sentiment_compound_mean', 'sentiment_backend',
    'pct_funcwords', 'low_language_flag',
    'pct_i', 'pct_we', 'pct_you', 'pct_negate', 'pct_posemo', 'pct_negemo',
    'pct_commitment', 'pct_exclusive', 'pct_social',
]


def _index(rows, keys):
    return {tuple(str(r.get(k, '')) for k in keys): r for r in rows}


def _prefixed(row, prefix, columns=MERGE_COLUMNS):
    if row is None:
        return {f'{prefix}{c}': '' for c in columns}
    return {f'{prefix}{c}': row.get(c, '') for c in columns}


def merge_into_by_partner(by_partner_rows, features, topics_by_directed=None):
    """Aggiunge a ogni coppia ordinata le misure inviate, ricevute e diadiche."""
    directed = _index(features['dyad_directed'], LEVEL_KEYS['dyad_directed'])
    dyads = _index(features['dyad'], LEVEL_KEYS['dyad'])

    for row in by_partner_rows:
        uid = str(row.get('group_uid', ''))
        focal = str(row.get('focal_id_in_group', ''))
        partner = str(row.get('partner_id_in_group', ''))
        row.update(_prefixed(directed.get((uid, focal, partner)), 'nlp_sent_'))
        row.update(_prefixed(directed.get((uid, partner, focal)), 'nlp_recv_'))
        row.update(_prefixed(dyads.get((uid, str(row.get('dyad_key', '')))), 'nlp_dyad_'))
        if topics_by_directed is not None:
            topics = topics_by_directed.get((uid, focal, partner), {})
            row['nlp_sent_topics'] = topics.get('topics', '')
            row['nlp_sent_topic_primary'] = topics.get('topic_primary', '')
            row['nlp_sent_n_topics'] = topics.get('n_topics', '')
    return by_partner_rows


def merge_into_aggregated(aggregated_rows, features, topics_by_sender=None,
                          topics_by_group=None):
    """Aggiunge a ogni partecipante le misure individuali e di gruppo."""
    senders = _index(features['sender_group'], LEVEL_KEYS['sender_group'])
    groups = _index(features['group'], LEVEL_KEYS['group'])

    for row in aggregated_rows:
        uid = str(row.get('group_uid', ''))
        focal = str(row.get('focal_id_in_group', ''))
        row.update(_prefixed(senders.get((uid, focal)), 'nlp_sent_'))
        row.update(_prefixed(groups.get((uid,)), 'nlp_group_'))
        if topics_by_sender is not None:
            topics = topics_by_sender.get((uid, focal), {})
            row['nlp_sent_topics'] = topics.get('topics', '')
            row['nlp_sent_topic_primary'] = topics.get('topic_primary', '')
            row['nlp_sent_n_topics'] = topics.get('n_topics', '')
        if topics_by_group is not None:
            topics = topics_by_group.get((uid,), {})
            row['nlp_group_topics'] = topics.get('topics', '')
            row['nlp_group_topic_primary'] = topics.get('topic_primary', '')
            row['nlp_group_n_topics'] = topics.get('n_topics', '')
    return aggregated_rows


def write_csv(path: Path, rows):
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    fieldnames, seen = [], set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
