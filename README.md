# chatlens

Text analysis of the conversations held during a behavioural experiment. It
extracts the **topics** (with TopicGPT, Pham et al. 2024) and the **language
measures** — volume, emotional tone, sentiment, analytical thinking, Clout,
Authenticity — at the pair and group level, and grafts them onto the choice
datasets, ready for Stata or R.

The code is split where the reusable part ends and the experiment-specific part
begins. An **adapter** turns one experiment's export into the canonical message
tables; the **core** — measures, rubric, topics, aggregation, report — works
from those tables alone and never reads a raw export itself.

Two adapters ship with it. `generic_chat` needs no code at all where the
export is already one message per row: the column names go in a configuration
file. `otree_coalition` is the worked example of the other kind, written for a
three-player coalition game in oTree, where the groups, the channels and the
choices all have to be reconstructed. See §5 for how to run your own study.

## The three things to know

**Everything happens in a workspace**: an ordinary folder of yours holding
`input/` and `output/`. Commands act on the current directory unless
`--workspace` says otherwise, so the usual way to work is to change into the
experiment's folder and run the command there. Two experiments are two folders,
and they never touch each other's results.

```
my_experiment/          <- the workspace
├── input/              the CSVs exported from oTree  ← put the data here
└── output/             everything that gets produced
```

**Input files are not passed on the command line.** You drop them in `input/`
and they are recognised by name. That is why the procedure comes down to a
single command, and also why `input/` must hold nothing else.

**Nothing sensitive leaves your machine, and nothing sensitive is kept next to
the code.** `input/` and `output/` hold participant identifiers and chat texts;
the API keys live in this machine's configuration directory, outside any
repository, so they cannot be committed by mistake.

## Quick start

The same three lines on macOS, Windows and Linux:

```bash
uv tool install chatlens        # once only
cd my_experiment                # the folder holding input/
chatlens all                    # merge + automatic measures
```

`chatlens --help` lists every command. The main ones:

| Command | What it does | API key |
|---|---|---|
| `chatlens all` | merge + automatic measures, a few seconds | **no** |
| `chatlens merge` / `chatlens analyze` | the two steps separately | no |
| `chatlens keys` | configures the API keys, guided | — |
| `chatlens analyze --llm --llm-replicates 2` | measures + validation rubric | yes |
| `chatlens analyze --topics` | measures + topics with TopicGPT | yes |
| `chatlens all --llm --topics` | everything: rubric and topics included | yes |
| `chatlens dashboard` | opens the dashboard in the browser | — |
| `chatlens report` | regenerates the readable summary | — |
| `chatlens runs` | lists the archived runs | — |
| `chatlens runs --prune 2` | keeps the last 2 and deletes the others | — |
| `chatlens status` | what is in input, in output and among the keys | — |
| `chatlens install-topicgpt` | installs TopicGPT (only needed for the topics) | — |

**`all` is both *steps*, not everything.** It means merge plus analysis, as
opposed to `merge` and `analyze` taken singly: it runs only the automatic
measures, needs no key at all and takes a few seconds. Adding `--llm` and
`--topics` brings in the validation rubric and the topics, which need a key and
take far longer. You start from `chatlens all`; you add the rest once the keys
are there.

## Contents

1. [What it does, in brief](#1-what-it-does-in-brief)
2. [Installation](#2-installation)
3. [API keys](#3-api-keys)
4. [Participant data](#4-participant-data)
5. [Your own experiment](#5-your-own-experiment)
6. [The analysis procedure](#6-the-analysis-procedure)
7. [The files produced](#7-the-files-produced)
8. [Before analysing: three filters](#8-before-analysing-three-filters)
9. [How the measures are built](#9-how-the-measures-are-built)
10. [TopicGPT](#10-topicgpt)
11. [Costs and volumes](#11-costs-and-volumes)
12. [If something does not add up](#12-if-something-does-not-add-up)
13. [Checking the tools](#13-checking-the-tools)
14. [Results on the pilot](#14-results-on-the-pilot)

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

The code lives in `src/chatlens/`: `core/` for the analysis steps, `adapters/`
for the experiment-specific part, `web/` for the dashboard.

---

## 2. Installation

One command, the same on macOS, Windows and Linux:

```bash
uv tool install chatlens
```

[uv](https://docs.astral.sh/uv/) is a single binary and installs Python itself
if the machine has none, which is why this works on a Windows laptop with
nothing set up. If uv is not there yet:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell
# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

`pipx install chatlens` works just as well if you already use pipx, and so does
`pip install chatlens` inside a virtual environment of your own.

This installs what the deterministic measures and the dashboard need. The
optional stages ask for more:

```bash
uv tool install "chatlens[llm]"      # + the validation rubric
uv tool install "chatlens[all]"      # + everything
```

Check it arrived:

```bash
chatlens --help
chatlens status        # run inside the folder holding your data
```

### Only if you need the topics

TopicGPT is installed separately, because the prompt files are part of the
method and **are not inside the published package**; release 0.2.7 on PyPI also
imports vLLM at the top level, a dependency that does not install on macOS
without a GPU, whereas the `main` branch has already made it optional.

```bash
chatlens install-topicgpt
```

It clones the official repository into this machine's application data
directory and installs it, then checks that the prompt files really arrived.
With `--repo <path>` you choose where it goes; to point the analysis at a copy
you already have, set `CHATLENS_TOPICGPT_REPO=<path>` or pass
`--topicgpt-repo <path>`.

### Working on the code rather than using it

```bash
git clone https://github.com/nicomil/chatlens.git
cd chatlens
make setup      # editable install in .venv/, every extra included
make test
```

On Windows, where `make` is absent:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -e ".[llm,topics]"
.venv\Scripts\python tests\test_merge.py
```

## 3. API keys

| Key | What it is for | Required? |
|---|---|---|
| `OPENAI_API_KEY` | TopicGPT **and**, if you like, the validation rubric | only for the topics with OpenAI |
| `ANTHROPIC_API_KEY` | the validation rubric, as an alternative to OpenAI | **no, optional** |

### Configuring them

A single command, identical on macOS, Windows and Linux:

```bash
chatlens keys
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
chatlens status        # what is configured, without touching anything
chatlens keys          # reconfigure or verify the keys
```

`chatlens status` never prints the keys, only whether they are there.

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

## 4. Participant data

The files this produces are **personal data**, and treating them as anything
else is the mistake worth avoiding at the start rather than explaining later.
Two things are in them.

**Identifiers.** The oTree export carries the recruitment platform's
participant id — on Prolific, a value that follows the same person across every
study they have ever taken part in — and it passes straight through into the
output. The analysis never uses it: what it needs is to tell participants
apart, not to know who they are.

```bash
chatlens merge --pseudonymise
```

replaces every identifier with a keyed hash. The pseudonyms are stable within a
workspace, so the same person is the same code across the three tables and
across a re-run months later; they are not reversible without the key, which
lives in `output/.pseudonym_key` and must never travel with the data. Delete
the key and the link is gone for good — which is the point, and also the thing
to be sure about before you delete it. The flag changes nothing else: every
number is identical either way.

**The conversations themselves.** These are untouched, and no option changes
that: they are the object of the analysis. People write their names, their
towns and their jobs into chat windows, so a pseudonymised dataset is
pseudonymised, not anonymous. What follows from that:

- `input/` and `output/` are excluded from version control, and should stay so
  in any workspace you create;
- the paid stages send the conversations to a third party — OpenAI or Anthropic
  — which is a disclosure your ethics approval and your participant information
  sheet have to cover. `--topicgpt-api ollama` runs the topics on a local model
  instead, and the rubric takes `--llm-provider ollama` for the same reason;
- the API keys are kept in this machine's configuration directory rather than
  beside the code, so a key cannot be committed by accident;
- the dashboard listens on 127.0.0.1 and refuses anything else. It executes
  processes and has no user accounts: anyone who could reach it could spend
  your API credit. To drive it from another machine, forward the port over SSH
  rather than opening it up.

None of this is legal advice, and the obligations depend on where you and your
participants are. It is the list of what the tool does with the data, so that
the assessment can be made on facts.

---

## 5. Your own experiment

The project is split where the reusable part ends and the experiment-specific
part begins.

```
your export
     │
     ▼
  ADAPTER          knows your columns, your group size, your game
     │
     ▼
  THREE TABLES     messages_long · chat_by_partner · chat_aggregated
     │             the contract, written down in core/schema.py
     ▼
  CORE             measures · rubric · topics · aggregation · report
```

The core never reads a raw export. It reads the three tables and nothing else,
which is what lets it run on a study it has never seen.

### The usual case: a configuration file

If your export is already one message per row — a group, a sender, a recipient,
a text — no code is needed. Put an `experiment.toml` at the root of the
workspace:

```toml
[experiment]
name       = "Ultimatum with pre-play chat"
adapter    = "generic_chat"
group_noun = "team"          # what the report calls a group; default "group"

[input]
messages     = "chat_log*.csv"
participants = "roster*.csv"       # optional: joined onto the participant table

[columns]
group     = "team"
sender    = "from_seat"
receiver  = "to_seat"
body      = "text"
timestamp = "sent_at"              # epoch seconds or ISO 8601, either works
treatment = "condition"

[treatments]                       # how the report names them, and their order
anonymous = "Anonymous offers"
named     = "Named offers"
```

Then the usual `chatlens all`. `chatlens status` shows which adapter is active
and which files it is looking for.

Group size is whatever your data says: nothing in the core counts the members,
so three or nine aggregate the same way. The one real assumption is that a
message has **one sender and one recipient** — a message to the whole group has
no directed pair to belong to. Those rows are counted and reported rather than
attributed to somebody; if your chat is group-wide, write one row per recipient
before running.

### Measuring something else

The rubric's dimensions are declared, not hard-coded, and the prompt, the
output schema and the column names are all generated from that one declaration.
To measure something your experiment cares about:

```toml
[rubric]
context = "Two participants bargain over how to divide a sum of money."

[[rubric.dimensions]]
name    = "aggression"
label   = "AGGRESSIVENESS"
kind    = "scale"                  # 0-100; "flag" for true/false
summary = "How forcefully the writer pushes their own claim, 0-100"
high    = "ultimatums, threats to walk away, refusal to move"
low     = "concessions, hedging, invitations to find a middle ground"
```

Declaring any dimension replaces the default four, so list every one you want.
`insufficient_text` is always added: without it an empty transcript scores 50
across the board and reads like a real measurement.

One dictionary can be replaced the same way — `commitment`, the only word list
in the project that belongs to a particular game rather than to English:

```toml
[lexicons]
commitment = ["offer", "accept", "reject", "deadline", "final"]
```

### When the export is not that shape

Some exports need real reconstruction — who was in which group, what a channel
name means, what a choice was relative to a seating order. That is a Python
module in `adapters/`, and `adapters/otree_coalition.py` is the worked example:
it does all of the above for a three-player coalition game in oTree. An adapter
needs `INPUTS`, `OPTIONS`, `run()` and `print_summary()`; `core/schema.py`
states exactly what `run()` has to produce, and says so in an error message
naming the missing column if it does not.

### A limitation worth knowing before you start

The dictionary-based measures are **English only**. The tokeniser matches a-z
and the word lists are English. On a conversation in another language the
volume measures still mean something, while analytic, clout, authenticity and
tone read near zero and mean nothing at all. There is no partial credit: another
language needs its own lexicons. The rubric and the topics, being model-based,
do not have this limitation.

---

## 6. The analysis procedure

The commands in this section are identical on macOS, Windows and Linux, and
they all act on the current folder unless `--workspace` names another one.

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
chatlens merge
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
chatlens analyze
```

**With the validation rubric:**

```bash
chatlens analyze --llm --llm-replicates 2
```

`--llm-replicates 2` has every text scored twice in independent calls, so the
spread between the two lands in the dataset as an estimate of measurement error.

**With the topics:**

```bash
chatlens analyze --topics
```

On Windows the repository path is a Windows one, so
`chatlens analyze --topics --topicgpt-repo <path>` if it lives somewhere
unusual.

**All together:** combine the options of the two commands above.

---

## 7. The files produced

Everything under `output/`.

### The dashboard

```bash
chatlens dashboard
```

It opens `http://127.0.0.1:8765` in the browser: from there you pick the
options, launch the run and watch the log advance live, with the report embedded
in the page and the list of archived runs.

It is the same command running underneath: the dashboard does nothing that
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
chatlens runs             # lists the runs, with each one's stages and parameters
chatlens runs --prune 2   # keeps the 2 most recent and deletes the others
```

To clear results by hand, delete `output/` — or the single dataset's folder
inside it. Nothing there is needed to run again: it is all regenerated from
`input/`.

```powershell
chatlens runs
chatlens runs --prune 2
Get-ChildItem output -Exclude runs,cache,.gitkeep | Remove-Item -Recurse -Force
Remove-Item -Recurse -Force output\runs
```

A session of trials leaves a long tail of near-identical runs:
`chatlens runs --prune 2` shortens it while keeping the ones that matter.
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
To regenerate it without redoing the analysis: `chatlens report` — then open
the `.html` in `output/` with a
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
| `group_outcome_recomputed` | the outcome the stored decisions imply, under the game's rule |
| `payoff_decision_mismatch` | 1 when the recorded outcome is not reconstructable from those decisions |

**On `payoff_decision_mismatch`.** Normally it is 0. It turns 1 when a
participant let the Decision page time out *after* someone else had already
reached the final page: the payoff is computed from a random choice drawn on
their behalf, and the timeout then overwrites the stored decision with a
second, independent random draw. The row ends up carrying an outcome its own
decisions do not produce.

Nothing is corrected, because nothing can be: the replaced choice is not in the
export. The flag exists so the contradiction is visible in the data instead of
being found months later and mistaken for corruption. It is empty when the
triad is incomplete or the outcome has not been computed yet — "not checkable"
must not read as "checked and fine". On the three collection days it was 1 on a
single triad out of 262, already excluded by `group_valid == 0`.

### Analysis in Stata

`examples/coalition_formation/stata/` holds seven do-files that read
`output/datasets/` and produce the tables: preparation and labelling,
descriptives, treatment effects, the language-and-persuasion regressions, the
1–4 conversation profiles, the non-parametric tests and the optional
rubric/topics sections. They were written for the coalition-formation
experiment, and are as good a starting point as any for another one.

```
cd examples/coalition_formation/stata
do 00_master.do
```

They are documented in that folder's `README.md`, which also records the choices behind
them — clustering on the triad, the main-sample flag, the reference category —
and states plainly that the language regressions are associations, since the
treatment is assigned but the language is chosen.

### Intermediate files

`..._messages_long.csv` (one message per row), `..._messages_nlp.csv` (the same
with counts and sentiment) and `..._features_<level>.csv` for the four
aggregation levels. They serve the checks and analyses at different levels; they
are not needed for Stata.

---

## 8. Before analysing: three filters

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

## 9. How the measures are built

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

## 10. TopicGPT

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

## 11. Costs and volumes

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

The tool has a cap of its own, because the call count is the product of four
choices — levels, replicates, models, units — and none of them looks expensive
on its own. Above a thousand calls a run says what it is about to do and, at a
terminal, waits for a yes; above twenty thousand it stops, since nothing
legitimate reaches that figure and what does is a typo. `--max-calls N` raises
the limit when you mean it, `--yes` skips the question. Away from a terminal —
the dashboard's subprocess, a scheduled job — there is nobody to answer, so a
run under the limit proceeds with the figure printed and one above it is
refused.

---

## 12. If something does not add up

**"Missing file: ..._messages_long.csv"** — the merge was not run:
`chatlens merge`, or directly `chatlens all`.

**"No all_apps_wide*.csv file in input/"** — the export was not put in `input/`,
or it has a different name from the one oTree produces.

**"More than one ChatMessages*.csv file in input/"** — `input/` must contain a
single export per kind, otherwise it is unclear which one to analyse: keep only
the one you need, or point at it with `--chat <path>`.

**"Missing OPENAI_API_KEY"** — see §3. With `--topicgpt-api ollama` the topics
run locally without any key.

**"The topicgpt_python package is not installed"** — see §2, second part.

**"... is missing columns the analysis cannot do without"** — the adapter did
not produce one of the columns the core needs. The message names it, says what
it is for and lists what is present; §5 and `core/schema.py` have the full
contract.

**"does not have the columns the configuration names"** — with `generic_chat`,
the names under `[columns]` in `experiment.toml` do not match the export's
header. The message lists the header, so it is usually a matter of copying the
right name across.

**Every language measure is near zero** — the dictionaries are English only.
See the end of §5.

**On Windows, `chatlens` is not found after installing** — the folder uv puts
its tools in is not on `PATH` yet. `uv tool update-shell` adds it; open a new
terminal afterwards. Working from a source checkout instead, PowerShell may
refuse `.venv\Scripts\activate` over its execution policy: either allow scripts
for your own user once with
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or skip activation and
prefix each command with `.venv\Scripts\`.

**"No credentials available" for the rubric** — the message lists the three
roads: OpenAI, Anthropic or a local model.

**I want to see what would be sent, without spending.** `--llm-dry-run` shows
the rubric's request; `--topicgpt-dry-run` only writes TopicGPT's input file.
Neither contacts any service.

**I want to check that the keys work.** `chatlens keys` verifies them again
by contacting the services; `chatlens status` says only which ones are
present, without going out to the network.

---

## 13. Checking the tools

From a source checkout:

```bash
make test
```

```powershell
.venv\Scripts\python tests\test_merge.py      # Windows
.venv\Scripts\python tests\test_analysis.py
.venv\Scripts\python tests\test_dashboard.py
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

## 14. Results on the pilot

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
