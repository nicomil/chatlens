"""
Misure testuali deterministiche in stile LIWC-22, più volume e sentiment.

Copre le grandezze chieste dallo sperimentatore — volume, tono emotivo,
sentiment, pensiero analitico, Clout, Authenticity — senza dipendere dal
software LIWC, che è a licenza commerciale.

Cosa è replica e cosa è approssimazione
---------------------------------------
- **Analytic** si basa sul Categorical-Dynamic Index, la cui formula è
  *pubblicata* per esteso in Pennebaker et al. (2014):

      CDI = 30 + article + prep − ppron − ipron − auxverb − conj − adverb − negate

  con ogni termine espresso in percentuale sul totale delle parole. Qui è
  riprodotta alla lettera: `analytic_cdi` è quindi una replica, non un
  surrogato. `analytic_pct` è la stessa quantità riscalata sul campione.

- **Clout** e **Authenticity** poggiano su costrutti pubblicati (rispettivamente
  Kacewicz et al. 2014 e Newman et al. 2003), ma i pesi esatti usati da LIWC-22
  non sono di dominio pubblico. Qui sono composti standardizzati a pesi uguali,
  con i segni presi dalla letteratura, e vanno letti come **indici in stile
  LIWC**, non come punteggi LIWC. Il modulo `llm_rubric` fornisce una seconda
  misura indipendente degli stessi costrutti, così da poterne verificare la
  convergenza.

Perché i conteggi si aggregano prima di calcolare gli indici
------------------------------------------------------------
I messaggi di chat sono cortissimi: sul pilota la mediana è di poche parole. Una
percentuale calcolata su cinque parole assume pochi valori distinti ed è
dominata dal rumore, e la media di tali percentuali non è la percentuale del
testo complessivo. Per questo `score_counts` lavora su conteggi *sommati*: al
livello di messaggio si estraggono conteggi, e gli indici si calcolano
sull'unità di analisi vera (coppia ordinata, coppia, gruppo).
"""

from __future__ import annotations

import math
import re
from collections import Counter

from .lexicons import CATEGORIES, is_adverb

# Tokenizzazione: parole con apostrofi interni (don't, i'm) tenute intere,
# così le forme contratte restano riconoscibili dai dizionari.
TOKEN_RE = re.compile(r"[a-z]+(?:'[a-z]+)*", re.IGNORECASE)

COUNT_KEYS = sorted(set(CATEGORIES) | {'adverb'})


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text or '')]


def count_categories(text: str) -> dict:
    """Conteggi grezzi per un singolo testo.

    Restituisce il numero di parole e, per ogni categoria, quante ne cadono
    dentro. Le categorie non sono mutuamente esclusive: una negazione come
    "don't" conta sia fra gli ausiliari sia fra le negazioni, esattamente come
    in LIWC.
    """
    tokens = tokenize(text)
    counts = {key: 0 for key in COUNT_KEYS}
    for token in tokens:
        for name, vocabulary in CATEGORIES.items():
            if token in vocabulary:
                counts[name] += 1
        if is_adverb(token):
            counts['adverb'] += 1

    counts['wc'] = len(tokens)
    counts['unique_wc'] = len(set(tokens))
    counts['char_count'] = len(text or '')
    # Parole lunghe: proxy di densità lessicale usato da LIWC come "sixltr".
    counts['sixltr'] = sum(1 for t in tokens if len(t) > 6)
    counts['qmark'] = (text or '').count('?')
    counts['exclam'] = (text or '').count('!')
    return counts


def sum_counts(count_dicts) -> dict:
    """Somma conteggi di più messaggi: è il passo che precede gli indici."""
    total = Counter()
    for counts in count_dicts:
        total.update(counts)
    merged = {key: int(total.get(key, 0)) for key in COUNT_KEYS}
    for key in ('wc', 'char_count', 'sixltr', 'qmark', 'exclam', 'unique_wc'):
        merged[key] = int(total.get(key, 0))
    return merged


def _pct(count: int, total: int) -> float:
    return 100.0 * count / total if total else 0.0


def score_counts(counts: dict) -> dict:
    """Calcola gli indici a partire da conteggi già sommati.

    Restituisce le percentuali di categoria, il CDI e le componenti grezze di
    Clout e Authenticity. Gli indici standardizzati veri e propri richiedono il
    campione intero e si ottengono con `standardize`.
    """
    wc = counts.get('wc', 0)
    pct = {f'pct_{key}': _pct(counts.get(key, 0), wc) for key in COUNT_KEYS}
    pct['pct_sixltr'] = _pct(counts.get('sixltr', 0), wc)

    # Categorical-Dynamic Index, formula pubblicata.
    cdi = (
        30.0
        + pct['pct_article']
        + pct['pct_prep']
        - pct['pct_ppron']
        - pct['pct_ipron']
        - pct['pct_auxverb']
        - pct['pct_conj']
        - pct['pct_adverb']
        - pct['pct_negate']
    )

    # Componenti dei due compositi: segni dalla letteratura, pesi uguali.
    # Clout alto = molti riferimenti agli altri, pochi a sé, poche negazioni.
    clout_raw = (
        pct['pct_we'] + pct['pct_you'] + pct['pct_social']
        - pct['pct_i'] - pct['pct_negate'] - pct['pct_swear']
    )
    # Authenticity alto = molti "io", molta differenziazione, poca emozione
    # negativa, pochi verbi di movimento (Newman et al. 2003).
    authenticity_raw = (
        pct['pct_i'] + pct['pct_exclusive']
        - pct['pct_negemo'] - pct['pct_motion']
    )
    # Tono emotivo. Si usa la differenza fra le percentuali sul totale delle
    # parole, non il rapporto interno alle sole parole emotive: quest'ultimo
    # satura a +/-100 non appena il testo contiene una sola parola emotiva, e su
    # messaggi di chat lo farebbe quasi sempre. Il rapporto resta disponibile
    # come `tone_balance`, da leggere solo dove `has_emotion_words` vale 1.
    emo_total = counts.get('posemo', 0) + counts.get('negemo', 0)
    tone_raw = pct['pct_posemo'] - pct['pct_negemo']
    tone_balance = (
        100.0 * (counts['posemo'] - counts['negemo']) / emo_total if emo_total else ''
    )

    # Densità di function words. Serve a riconoscere il testo che *non* è
    # lingua: una stringa di tastiera non contiene articoli, pronomi né
    # ausiliari, quindi il CDI non subisce alcuna sottrazione e il testo risulta
    # paradossalmente "massimamente analitico". Sul pilota i gruppi con sole
    # stringhe di prova avevano analytic_100 mediano 93, contro 37 dei gruppi
    # con conversazione reale: senza questo indicatore l'artefatto passerebbe
    # per segnale.
    funcword_pct = (
        pct['pct_article'] + pct['pct_prep'] + pct['pct_ppron']
        + pct['pct_ipron'] + pct['pct_auxverb'] + pct['pct_conj']
        + pct['pct_negate'] + pct['pct_adverb']
    )

    scores = dict(pct)
    scores.update(
        pct_funcwords=funcword_pct,
        # Soglia prudenziale: sotto il 15% di function words su almeno cinque
        # parole, il testo quasi certamente non è inglese conversazionale.
        # Da usare come filtro, non come esclusione automatica.
        low_language_flag=int(wc >= 5 and funcword_pct < 15.0),
        wc=wc,
        unique_wc=counts.get('unique_wc', 0),
        char_count=counts.get('char_count', 0),
        type_token_ratio=(counts.get('unique_wc', 0) / wc) if wc else 0.0,
        qmark=counts.get('qmark', 0),
        exclam=counts.get('exclam', 0),
        analytic_cdi=cdi,
        clout_raw=clout_raw,
        authenticity_raw=authenticity_raw,
        tone_raw=tone_raw,
        tone_balance=tone_balance,
        has_emotion_words=int(emo_total > 0),
    )
    return scores


# Indici che vengono standardizzati sul campione.
STANDARDIZED = ('analytic_cdi', 'clout_raw', 'authenticity_raw', 'tone_raw')

STANDARDIZED_NAMES = {
    'analytic_cdi': 'analytic',
    'clout_raw': 'clout',
    'authenticity_raw': 'authenticity',
    'tone_raw': 'tone',
}


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def standardize(rows, keys=STANDARDIZED):
    """Aggiunge z-score e scala 0-100 calcolati sul campione fornito.

    LIWC restituisce le tre misure composite su scala 0-100 perché le
    standardizza rispetto a un corpus di riferimento proprietario. Qui la
    standardizzazione avviene sul campione in analisi: i valori sono quindi
    confrontabili *fra* unità dello stesso studio, non con i punteggi LIWC
    pubblicati altrove. È la scelta corretta per un confronto fra trattamenti,
    che è esattamente l'uso previsto.

    Modifica `rows` sul posto e restituisce le medie e deviazioni usate.
    """
    stats = {}
    for key in keys:
        values = [r[key] for r in rows if r.get('wc', 0) > 0 and key in r]
        n = len(values)
        if n < 2:
            stats[key] = dict(mean=0.0, sd=0.0, n=n)
            continue
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / (n - 1)
        stats[key] = dict(mean=mean, sd=math.sqrt(variance), n=n)

    for row in rows:
        for key in keys:
            name = STANDARDIZED_NAMES[key]
            if row.get('wc', 0) <= 0 or key not in row:
                row[f'{name}_z'] = ''
                row[f'{name}_100'] = ''
                continue
            sd = stats[key]['sd']
            if sd <= 0:
                row[f'{name}_z'] = 0.0
                row[f'{name}_100'] = 50.0
                continue
            z = (row[key] - stats[key]['mean']) / sd
            row[f'{name}_z'] = round(z, 6)
            row[f'{name}_100'] = round(100.0 * _normal_cdf(z), 4)
    return stats


# --- Sentiment -------------------------------------------------------------

_VADER = None
_VADER_TRIED = False


def _vader():
    """Analizzatore VADER, se la libreria è installata."""
    global _VADER, _VADER_TRIED
    if not _VADER_TRIED:
        _VADER_TRIED = True
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            _VADER = SentimentIntensityAnalyzer()
        except ImportError:
            _VADER = None
    return _VADER


def sentiment(text: str) -> dict:
    """Sentiment con VADER; senza la libreria, ripiega sui dizionari di semi.

    Il campo `sentiment_backend` dice quale dei due ha prodotto il valore, così
    la provenienza resta tracciata nel dataset finale.
    """
    analyzer = _vader()
    if analyzer is not None:
        scores = analyzer.polarity_scores(text or '')
        return dict(
            sentiment_compound=scores['compound'],
            sentiment_pos=scores['pos'],
            sentiment_neg=scores['neg'],
            sentiment_neu=scores['neu'],
            sentiment_backend='vader',
        )

    counts = count_categories(text)
    total = counts['posemo'] + counts['negemo']
    compound = (counts['posemo'] - counts['negemo']) / total if total else 0.0
    wc = counts['wc'] or 1
    return dict(
        sentiment_compound=compound,
        sentiment_pos=counts['posemo'] / wc,
        sentiment_neg=counts['negemo'] / wc,
        sentiment_neu=max(0.0, 1.0 - (total / wc)),
        sentiment_backend='lexicon_fallback',
    )


def analyze_message(text: str) -> dict:
    """Conteggi e sentiment di un singolo messaggio.

    Gli indici compositi NON vengono calcolati qui: su testi di poche parole
    sarebbero rumore. Si ottengono aggregando i conteggi e passandoli a
    `score_counts`.
    """
    counts = count_categories(text)
    result = dict(counts)
    result.update(sentiment(text))
    return result
