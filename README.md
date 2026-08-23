# Chat text analysis

A self-contained project: it extracts from the experiment's conversations the
**topics** (with TopicGPT, Pham et al. 2024) and the **language measures** —
volume, emotional tone, sentiment, analytical thinking, Clout, Authenticity —
at the pair and group level, and grafts them onto the choice datasets.

It does not depend on the experiment's code: it can be copied elsewhere and
keeps working. Its only ties are the two CSVs in `input/`.

```
text_analysis/
├── Makefile          the main commands
├── run.py            the actual entry point
├── input/            the CSVs exported from oTree  ← put the data here
├── output/           everything that gets produced
├── src/              the code of the analysis steps
├── tests/            checks on the tools
├── .env              the API keys (never under version control)
└── requirements.txt
```

## The two things to know

**Input files are not passed on the command line.** You drop them in `input/`
and they are recognised by name. That is why the procedure comes down to a
single command.

**Everything needed lives in this folder**, keys included: `input/` and
`output/` are excluded from version control because they hold Prolific IDs and
chat texts.

On macOS and Linux:

```bash
make setup    # once only: creates the environment and installs the dependencies
make all      # merges the data and runs the analysis
```

On Windows, where `make` is not there, the same two steps are (PowerShell):

```powershell
py -m venv .venv                                   # once only
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\activate                             # once per terminal window
python run.py all
```

After `activate`, `python` is the project's one and every command below works as
written. Without activating, prefix them with `.venv\Scripts\` — for instance
`.venv\Scripts\python run.py all`.

`make` on its own lists every command. The main ones, with their Windows
equivalent:

| Command | Windows (activated venv) | What it does | API key |
|---|---|---|---|
| `make setup` | see the block above | prepares the project's virtual environment | — |
| `make keys` | `python run.py keys` | configures the API keys, guided | — |
| `make all` | `python run.py all` | merge + automatic measures, a few seconds | **no** |
| `make merge` / `make analyze` | `python run.py merge` / `python run.py analyze` | the two steps separately | no |
| `make llm` | `python run.py analyze --llm --llm-replicates 2` | measures + validation rubric | yes |
| `make topics` | `python run.py analyze --topics --topicgpt-repo <path>` | measures + topics with TopicGPT | yes |
| `make full` | `python run.py all --llm --llm-replicates 2 --topics --topicgpt-repo <path>` | like `all`, plus rubric and topics | yes |
| `make dashboard` | `python run.py dashboard` | opens the dashboard in the browser | — |
| `make report` | `python run.py report` | regenerates the readable summary and opens it | — |
| `make runs` | `python run.py runs` | lists the archived runs | — |
| `make prune` | `python run.py runs --prune 2` | keeps the last 2 and deletes the others (`KEEP=n`) | — |
| `make status` | `python run.py status` | what is in input, in output and among the keys | — |
| `make test` / `make check` | `python tests/test_merge.py` and the other two | checks the tools | — |
| `make clean` | see §5 | empties the latest result; archive and cache stay | — |

**`all` and `full` are not synonyms.** `all` means "both *steps*" — merge plus
analysis — as opposed to `merge` and `analyze` taken singly: it runs only the
automatic measures, needs no key at all and takes a few seconds. `full` does
the same and adds the validation rubric and the topics, so it needs a key and
takes far longer. You start from `all`; you move to `full` once the keys are
there.

For the less common options: `make analyze ARGS="--llm-replicates 3"`, which on
Windows is simply `python run.py analyze --llm-replicates 3`.

**The Makefile is a convenience, not a layer.** It does nothing but call
`python run.py <command>`, after making sure the environment exists. That is why
every command has a one-to-one Windows equivalent, and why the two roads cannot
produce different results.

## Contents

1. [What it does, in brief](#1-what-it-does-in-brief)
2. [Installation](#2-installation)
3. [API keys](#3-api-keys)
4. [The analysis procedure](#4-the-analysis-procedure)
5. [The files produced](#5-the-files-produced)
6. [Before analysing: three filters](#6-before-analysing-three-filters)
7. [How the measures are built](#7-how-the-measures-are-built)
8. [TopicGPT](#8-topicgpt)
9. [Costs and volumes](#9-costs-and-volumes)
10. [If something does not add up](#10-if-something-does-not-add-up)
11. [Checking the tools](#11-checking-the-tools)
12. [Results on the pilot](#12-results-on-the-pilot)

---

## 1. What it does, in brief

Three independent stages, each switchable on its own.

| Stage | Option | Does it need a credential? |
|---|---|---|
| Deterministic text measures | (always on) | **no** |
| Validation rubric | `--llm` | one of OpenAI, Anthropic or a local model |
| TopicGPT | `--topics` | depends on the backend |

The first stage runs on Python's standard library alone: it can be executed
straight away, with nothing to obtain first. The other two serve, respectively,
to validate the measures and to extract the topics.

**One key covers everything.** The validation rubric is not tied to a specific
provider: if OpenAI is already in use for TopicGPT, the same key covers that
stage too.

All the code of the analysis steps lives in `src/`; the entry point is `run.py`.

---

## 2. Installation

From the project folder, once only:

```bash
make setup
```

```powershell
py -m venv .venv                                   # Windows
.venv\Scripts\python -m pip install -r requirements.txt
```

It creates the virtual environment in `.venv/` and installs the dependencies. On
macOS and Linux there is no need to activate it: the Makefile takes care of
that. On Windows, activate it once per terminal window with
`.venv\Scripts\activate`, so that `python` is the project's one.

It installs what is needed for the sentiment and for the API clients. The
deterministic measures would work without them too, but the sentiment would
fall back on a poorer version, declaring it in the `sentiment_backend` column.

**Only if the topics are needed**, TopicGPT's repository has to be cloned as
well:

```bash
make topicgpt
```

```powershell
git clone https://github.com/chtmp223/topicGPT.git $HOME\src\topicGPT
python -m pip install $HOME\src\topicGPT
```

It clones the repository into `~/src/topicGPT` and installs it; with
`make topicgpt TOPICGPT_REPO=<path>` you choose where. On Windows the path is
whatever you cloned into, and it is the one to pass to `--topicgpt-repo`.

Two notes on why it is installed from the repository and not from PyPI: the
prompt files are part of the method and **are not inside the published
package**; and release 0.2.7 on PyPI imports vLLM at the top level, a dependency
that does not install on macOS without a GPU, whereas the `main` branch has
already made it optional.

---

## 3. API keys

| Key | What it is for | Required? |
|---|---|---|
| `OPENAI_API_KEY` | TopicGPT **and**, if you like, the validation rubric | only for the topics with OpenAI |
| `ANTHROPIC_API_KEY` | the validation rubric, as an alternative to OpenAI | **no, optional** |

### Configuring them

A single command, identical on macOS, Windows and Linux:

```bash
python run.py keys
```

It asks for the keys one at a time. While you paste them **the text does not
appear on screen**: that is normal, the terminal is not stuck. Press Enter after
each; an empty Enter skips that key or leaves the existing one unchanged.

When it is done the script does three things on its own:

1. it saves the keys in `.env` in the project folder;
2. it checks that git really is ignoring it, and if it is not, offers to fix
   `.gitignore` **before** writing anything;
3. it contacts the services to confirm the keys work, so a copy-and-paste
   mistake surfaces immediately and not three days later.

The correct outcome:

```
Saved to /.../.env
Permissions restricted to the owner (600).

Checking the keys:
  OK   OpenAI: key valid, 87 models available
```

If a key is wrong it says so unambiguously: `FAIL OpenAI: key rejected
(HTTP 401)`.

Once that is done nothing else is needed: the pipeline loads them on every run.

### Commands for checking

```bash
python run.py status        # what is configured, without touching anything
python run.py keys          # reconfigure or verify the keys
```

`run.py status` never prints the keys, only whether they are there.

### Which provider gets used

The pipeline chooses on its own from what it finds, and states it before
starting:

```
LLM rubric...
  provider: OpenAI
```

To force the choice: `--llm-provider openai|anthropic|ollama`.

### Two warnings

**`.env` must never be put under version control.** This project's repository is
public. The script checks before writing, but it is worth knowing: never add it
to a commit by hand, and never send the keys over chat or email.

**An environment variable already set always takes precedence over the file**,
for whoever prefers to manage them their own way. To remove everything just
delete `.env`: no system setting is touched.

### A free alternative

TopicGPT and the rubric also accept models run locally, which need no key at
all:

```bash
ollama pull llama3
```

Then add `--topicgpt-api ollama --topicgpt-model llama3` or
`--llm-provider ollama`. The flip side: TopicGPT lives off the quality of the
labels the model produces, and the paper uses GPT-4. With a small local model
the pipeline still runs, but the topics come out poorer. It is the right road
for a trial run, not for publishable results.

---

## 4. The analysis procedure

The `python run.py …` commands in this section are identical on macOS, Windows
and Linux. On macOS and Linux the shorter `make merge` / `make analyze` /
`make full` do the same thing.

### Step 1 — Download the exports from oTree

From the admin interface, **Data** section, two files are needed:

| Export | Typical name |
|---|---|
| All apps — wide | `all_apps_wide_<date>.csv` |
| Chat messages | `ChatMessages_<date>.csv` |

The two custom exports of the randomisation (**RCT slots** and **RCT
assignments**) should be downloaded too: they are not used by this procedure,
but they cannot be reconstructed afterwards and must be kept along with the
others.

### Step 2 — Merge choices and chat

```bash
python run.py merge
```

This is where the experiment's variables already get built: persuasion,
signal-choice consistency, strategic deception, group payoff and the triad
validity flags.

**Who enters the analysis.** The participants kept are those who satisfy two
conditions:

- they have a valid Prolific identifier in `participant.label`, which discards
  the internal test sessions;
- they were part of a triad, which keeps only those who could communicate.

Whoever was later **excluded for inactivity stays in the dataset**: they did
communicate, and their exclusion from the main analyses is governed with
`group_valid`, not by removing them from the data. With `--keep-all` nothing is
filtered, so the raw export can be inspected.

**What to check in the on-screen summary.** The command prints how many
participants were in the export, how many it excluded and for what reason, how
many triads it reconstructed and how many messages it analysed. The message
count must add up: those of excluded participants plus those analysed make the
export's total. If it does not, warning lines at the end explain which ones were
not traced back to a participant.

### Step 3 — Text analysis

**Automatic measures only** — no key needed, a few seconds:

```bash
python run.py analyze
```

**With the validation rubric:**

```bash
python run.py analyze --llm --llm-replicates 2
```

`--llm-replicates 2` has every text scored twice in independent calls, so the
spread between the two lands in the dataset as an estimate of measurement error.

**With the topics:**

```bash
python run.py analyze --topics --topicgpt-repo ~/src/topicGPT
```

On Windows the repository path is a Windows one, so
`python run.py analyze --topics --topicgpt-repo $HOME\src\topicGPT`.

**All together:** combine the options of the two commands above.

---

## 5. The files produced

Everything under `output/`.

### The dashboard

```bash
make dashboard          # macOS / Linux
python run.py dashboard # Windows, and anywhere else
```

It opens `http://127.0.0.1:8765` in the browser: from there you pick the
options, launch the run and watch the log advance live, with the report embedded
in the page and the list of archived runs.

It is the same `run.py` running underneath: the dashboard does nothing that
cannot be done from the command line, and the two paths cannot diverge.

Three choices worth knowing about:

- **It listens on `127.0.0.1` only.** This is a desktop tool, not a service: it
  executes processes, so it must not be reachable from the network.
- **The arguments come from a closed list.** The form offers dropdowns and
  checkboxes, and the server checks every value against the allowed ones before
  building the command. Nothing arriving from the browser ends up in a command
  line as it is.
- **No new dependency**: a standard-library-only server, with htmx shipped in
  the project. It works offline too.

One run at a time: two concurrent runs would write to the same files.

### What happens when you run again

`output/` always holds the **latest** run, at fixed paths: that is what you open
and what you take into Stata. Every run is however also copied into
`output/runs/<date_time>/`, with the two datasets, the report, the list of
topics used and a `run.json` with the parameters.

It is needed because two runs do not produce the same files: one without `--llm`
rewrites the datasets **without** the rubric's columns, and with no archive that
work would vanish from the final files while still sitting in the cache.

```bash
make runs            # lists the runs, with each one's stages and parameters
make prune KEEP=2    # keeps the 2 most recent and deletes the others
make clean           # empties the latest result; archive and cache stay
make clean-runs      # deletes the whole archive
```

The same on Windows (PowerShell). The first two are run.py commands; the last
two only delete files, so they are plain PowerShell:

```powershell
python run.py runs
python run.py runs --prune 2
Get-ChildItem output -Exclude runs,cache,.gitkeep | Remove-Item -Recurse -Force
Remove-Item -Recurse -Force output\runs
```

A session of trials leaves a long tail of near-identical runs: `make prune`
(`python run.py runs --prune 2`) shortens it while keeping the ones that matter.
Each run takes about 800 KB.

The intermediate measures are not archived: they are regenerated.

### The run's summary

Every run produces `output/<name>_report.md` and `<name>_report.html`: a single
page with sample coverage, game outcomes, behavioural variables, language
measures and — when those stages were run — rubric and topics. It is there to
show how it went without opening CSVs three hundred columns wide. The HTML is
self-contained: it opens on a double click and can be sent to someone.

The sections of the stages not run do not appear. The comparisons between
treatments are descriptive by choice: on numbers like the pilot's they serve to
check that the pipeline produces sensible results, not to draw conclusions from.
To regenerate it without redoing the analysis: `make report`, or
`python run.py report` on Windows — then open the `.html` in `output/` with a
double click.

### To take into Stata

| File | Unit of observation |
|---|---|
| `..._chat_by_partner_nlp.csv` | the directed pair i→j, six per triad |
| `..._chat_aggregated_nlp.csv` | the participant |

The text measures carry a prefix saying which conversation they refer to:

| Prefix | Content |
|---|---|
| `nlp_sent_*` | the messages **sent** by the subject (to the partner in the per-pair file, to the whole group in the per-participant file) |
| `nlp_recv_*` | those **received** |
| `nlp_dyad_*` | the pair's whole conversation |
| `nlp_group_*` | the triad's whole conversation |

The distinction between sent and received is not cosmetic: in persuasion what
counts is the speaker's language, so regressions on persuasion must use the
`nlp_sent_*` columns.

Main columns of each block: `n_messages`, `wc`, `mean_words_per_message`,
`type_token_ratio`, `duration_seconds`, `median_gap_seconds`, the triples
`analytic_cdi` / `analytic_z` / `analytic_100` and their equivalents for
`clout`, `authenticity`, `tone`, plus `sentiment_compound_mean` and the category
percentages (`pct_i`, `pct_we`, `pct_you`, `pct_negate`, `pct_posemo`,
`pct_negemo`, `pct_commitment`, `pct_exclusive`, `pct_social`).

With stages 2 and 3 active you also get `llm_analytic`, `llm_clout`,
`llm_authenticity`, `llm_tone` with their `_sd` counterparts, the flags
`llm_contains_support_commitment` and `llm_contains_support_request`, and
`nlp_*_topics` / `nlp_*_topic_primary` / `nlp_*_n_topics`.

### The experiment's variables, built at step 2

| Variable | Definition |
|---|---|
| `persuasion_ij` | i promises support to j **and** j actually chooses i. Six observations per game |
| `C_ij`, `cc_i` | consistency between final signal and choice, per pair and on average: 1, 0.5 or 0 |
| `strategic_deception` | promises support to both, then supports no one |
| `group_valid` | 0 if the triad was interrupted or if even a single member let a timer expire |
| `group_total_payoff` | the basis for Efficiency, in the theoretical version and in the paid one |

### Intermediate files

`..._messages_long.csv` (one message per row), `..._messages_nlp.csv` (the same
with counts and sentiment) and `..._features_<level>.csv` for the four
aggregation levels. They serve the checks and analyses at different levels; they
are not needed for Stata.

---

## 6. Before analysing: three filters

**`group_valid == 1`** — excludes the interrupted triads and those where at
least one member let a timer expire, as agreed. The full sample stays available
for robustness checks. The column has the same name in both files.

**`low_language_flag == 0`** — excludes text that is not language. It is needed
because keyboard mashing comes out paradoxically *maximally analytic*: the index
subtracts the function words, and a text containing none suffers no subtraction
at all. On the pilot, groups made only of test strings scored a median of 93
against 43 for the real groups.

The flag carries the prefix of the block it refers to, so use the one consistent
with the measures being analysed: `nlp_sent_low_language_flag`,
`nlp_dyad_low_language_flag`, `nlp_group_low_language_flag`. On very short units
the threshold does not trip, so at the dyadic level it must be read together
with `nlp_sent_wc`.

**`nlp_sent_wc > 0`** (or the `wc` of the block in use) — units with no text
have **blank** indices by construction, not zeros: without this filter they
would enter the means as missing values rather than as an absence of
conversation.

---

## 7. How the measures are built

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

---

## 8. TopicGPT

The adapter **does not rewrite the algorithm**: it prepares the input in the
expected format, invokes the official functions in the order the paper
prescribes — generation of the first-level topics, refinement, assignment,
correction — and recomposes the output onto the experiment's keys.

**Unit of analysis: two, not one.** The topics are **induced** on the whole
triad's conversation (`--topicgpt-unit group`), which has enough text for the
model to recognise something, and are **assigned** to the directed pairs
(`--topicgpt-assign-unit dyad_directed`), which are the unit where persuasion
plays out. They are then aggregated to participant and group by taking the union
of the topics of the component units.

The separation is not a detail: inducing directly on the directed pairs makes
the model answer "None" on every document, because the paper's prompt explicitly
instructs it to do so when the document contains no recognisable topic, and a
two-line exchange contains none.

**The seed is a research choice.** TopicGPT starts from a list of initial
topics, which in the official repository concerns the paper's demonstration
corpus — US legislation, with `[1] Trade` and examples about tariffs and
agricultural policy. With that seed, on chat conversations the model recognises
nothing. The project therefore uses `prompts/seed_coalition_formation.md`, with
three topics pertinent to the game. Supplying the seed is a **parameter of the
method**, not a modification of the authors' code: `seed_file` is an argument of
`generate_topic_lvl1`.

A caveat, though: the seed conditions the resulting ontology. On the pilot, with
18 conversations, no new topics emerged beyond the three starting ones — which
is the behaviour the prompt prescribes, reusing existing topics when they are
pertinent. On a large corpus others are expected to emerge. The seed's content
must be reviewed and approved by whoever runs the study before the topics are
used in an analysis.

**Models: TopicGPT and the rubric do not accept the same ones.** TopicGPT fixes
`temperature` and `top_p` in every phase, inside the authors' code. Recent
models that allow only the default temperature — verified on `gpt-5.6-luna`,
`gpt-5.6-terra`, `gpt-5.6-sol` — reject them with a 400 error, and the library
reacts by retrying three times a minute apart: unchecked, the incompatibility
would surface after two minutes for every document. The preflight check
intercepts it with a minimal call and stops immediately.

For the topics it is therefore best to stay on `gpt-4o`, which is also the
paper's model. The rubric does not send `temperature` and works with all of
them: it is chosen with `--llm-models`.

**Backends.** TopicGPT talks to OpenAI, Azure, Vertex, Gemini, Ollama or vLLM.
The paper uses OpenAI and that is the most faithful choice. To use Claude there
are two roads that require no change to the authors' code: the `vertex` backend,
which in the repository builds an `AnthropicVertex` client, or `openai` pointed
at a compatible gateway through `OPENAI_BASE_URL`.

---

## 9. Costs and volumes

On the final dataset (~1,557 participants, ~519 triads) the directed pairs will
be about 3,100 and the groups 519.

**TopicGPT** queries the model once per document, in two phases: in the order of
6,500 calls on short texts.

**The rubric** with two replicates comes to about 7,200 calls. Two devices keep
the count down: the system prompt, identical on every call, is marked for the
cache, and `--llm-batch` uses the Batches API at half price (asynchronous
outcome, batch id to be kept; available only with the Anthropic provider).

These are modest but not negligible figures: it is worth setting a spending cap
on the provider's dashboard before launching.

---

## 10. If something does not add up

**"Missing file: ..._messages_long.csv"** — the merge was not run:
`python run.py merge`, or directly `python run.py all`.

**"No all_apps_wide*.csv file in input/"** — the export was not put in `input/`,
or it has a different name from the one oTree produces.

**"More than one ChatMessages*.csv file in input/"** — `input/` must contain a
single export per kind, otherwise it is unclear which one to analyse: keep only
the one you need, or point at it with `--chat <path>`.

**"Missing OPENAI_API_KEY"** — see §3. With `--topicgpt-api ollama` the topics
run locally without any key.

**"The topicgpt_python package is not installed"** — see §2, second part.

**On Windows, `.venv\Scripts\activate` is refused** with a message about the
execution policy — that is PowerShell blocking scripts, not a problem with the
project. Either allow them for your own user, once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or skip activation
entirely and prefix each command with `.venv\Scripts\`, as in
`.venv\Scripts\python run.py all`.

**"No credentials available" for the rubric** — the message lists the three
roads: OpenAI, Anthropic or a local model.

**I want to see what would be sent, without spending.** `--llm-dry-run` shows
the rubric's request; `--topicgpt-dry-run` only writes TopicGPT's input file.
Neither contacts any service.

**I want to check that the keys work.** `python run.py keys` verifies them again
by contacting the services; `python run.py status` says only which ones are
present, without going out to the network.

---

## 11. Checking the tools

```bash
make test
```

```powershell
python tests/test_merge.py      # Windows
python tests/test_analysis.py
python tests/test_dashboard.py
```

They run with no network and no credentials. If they all end with `OK`, the
tools are in order and any problem lies in the input data.

The most stringent check of the first is not an example but a property: for
**all 27 possible choice profiles**, under both payoff rules, the variables
built must come out consistent with the game's payoff function. If the mapping
between `decision_choice` — which is relative to the circular topology — and the
absolute players were wrong by even a single rotation, the test would fail.

The second covers tokenisation of contracted forms, the heuristic on *-ly*
adverbs, the CDI formula recomputed by hand, the expected direction of the
composites, standardisation, the preservation of words and messages across the
aggregation levels, the asymmetry of directed pairs, the grafting onto the
datasets, parsing of TopicGPT's response format, recognition of text that is not
language, key loading and provider selection.

---

## 12. Results on the pilot

Stage 1 was run on all 311 messages of the pilot of 18 August 2026.

| Level | Units |
|---|---|
| directed pair (i→j) | 91 |
| pair | 48 |
| participant within group | 50 |
| group | 18 |

That is **18 triads and 54 participants**: six per treatment, from the three
real Prolific sessions. The other seven triads present in the export came from
internal test sessions and were excluded by the filter on the Prolific
identifier. Of the export's 311 messages, 28 belonged to those sessions and 283
enter the analysis. The distributions are not degenerate — at the group level
`analytic_cdi` runs from −30 to +49 with 21 distinct values over 24 units — and
the z-scores have mean 0 and standard deviation 1 by construction.

**On the content**: 241 messages out of 311 contain recognisable English, spread
over 20 groups; the rest are test strings typed during the internal tests. There
is genuinely strategic material — "*If you want to do that, we can support each
other. Unfortunately one person must be left out…*" — enough to check that the
pipeline works end to end, not enough for a stable topic ontology. That is the
intended purpose: run it in now, produce results on the final dataset.
