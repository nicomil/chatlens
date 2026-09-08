# How the measures are built

This section is for whoever writes the paper: it says what is an exact
replication and what is an approximation.

### The LIWC measures without LIWC

The point that makes this possible: **Analytic, Clout and Authenticity do not
depend on proprietary content dictionaries.** They rest on *function words* —
articles, prepositions, pronouns, auxiliaries, conjunctions, negations — which
in English are closed classes and in the public domain. What LIWC sells is the
software and the calibration, not the English language.

**Analytic is a replication.** The Categorical-Dynamic Index is published in
full in Pennebaker, Chung, Frazee, Lavergne & Beaver (2014), *PLOS ONE*:

```
CDI = 30 + article + prep − ppron − ipron − auxverb − conj − adverb − negate
```

with every term as a percentage of total words. It is implemented to the letter,
and a test recomputes its value by hand.

**Clout and Authenticity are LIWC-*style* indices.** The constructs are
published — Clout in Kacewicz, Pennebaker, Davis, Jeon & Graesser (2014),
Authenticity in the deception index of Newman, Pennebaker, Berry & Richards
(2003) — but LIWC-22's exact weights are not. Here they are composed with equal
weights, with the signs taken from the literature:

- Clout ↑ with `we`, `you` and social references; ↓ with `I`, negations,
  swearing;
- Authenticity ↑ with `I` and differentiation words (*but*, *except*,
  *without*); ↓ with negative emotion and motion verbs.

In the dataset they are called `clout_raw` / `clout_z` / `clout_100`, **never**
"LIWC Clout". In a pre-registration they should be declared as *LIWC-style
measures computed from published formulas*.

**The convergent validation.** Stage 2 has a language model score the same
transcripts against an explicit rubric, on a 0-100 scale for the same four
constructs. The two roads are methodologically independent — one counts function
words, the other reads the text — so the correlation between `clout_100` and
`llm_clout` is evidence of convergent validity. If they diverge, that must be
reported: it is a result, not a fault.

**Sentiment.** VADER, open source and validated, is the primary measure
(`sentiment_compound`). Without the library the code falls back on dictionary
counts and declares it in `sentiment_backend`, so the provenance stays traceable
row by row.

### Three decisions that change the numbers

**The indices are computed on the summed counts**, not as a mean of per-message
percentages. Chat turns are very short: a percentage computed on five words
takes few distinct values and is dominated by noise, and the mean of those
percentages is not the percentage of the overall text. The pipeline extracts
*counts* at the message level and computes the *indices* only on the real unit
of analysis. A test checks that a group's CDI matches that of the joined text of
its messages.

**The emotional tone uses the difference between percentages**, not the ratio
internal to emotion words. The ratio formulation — `(pos − neg) / (pos + neg)` —
jumps to ±100 as soon as the text contains a single emotion word, which on chat
messages happens almost always; in the first draft the median group value was
exactly 100, that is degeneration and not signal. The measure used is
`pct_posemo − pct_negemo`; the ratio remains available as `tone_balance`, to be
read only where `has_emotion_words` is 1.

**Standardisation is within the sample.** LIWC returns its measures on a 0-100
scale because it standardises them against a proprietary reference corpus. Here
standardisation happens within the sample under analysis: the values are
comparable *between units of the same study* — that is between treatments, which
is the intended use — but not with LIWC scores published elsewhere.

## Emotions, and what a zero means

The Emotions page counts words from the NRC Emotion Lexicon: eight emotions and
two sentiments, about fourteen thousand English words. It is free for research
and distributed through a form, so it is not shipped — the page says where to
request it and where to put it.

**A zero is two different things and the column cannot tell them apart.** A
document scores by containing words that are on the list; one containing none
scores zero on every category, which is an absence of measurement rather than an
absence of feeling. Anything built on these columns should carry the unmeasured
rows as missing, not as zeros, or the model will read "we could not tell" as
"calm".

The page therefore always shows how much of the corpus could be measured at all,
by document length, because the shape says where the limit is:

- **Falling with length** — the documents are the constraint. No word list finds
  emotion in "ok" or "sure", and a larger one will not change that. On the corpus
  this tool was built for, 73% of documents of seven words or fewer contained no
  listed word, against 8% of those over thirty.
- **High everywhere** — the word list is the constraint: a vocabulary it does not
  cover.

Category shares are computed over the documents that could be measured, not over
all of them. Dividing by everything puts every category over the same inflated
denominator, and an unmeasurable corpus comes out looking uniformly unemotional
rather than unmeasured.
