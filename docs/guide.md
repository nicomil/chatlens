# chatlens — a guide

Text analysis of the conversations held during a behavioural experiment: what
was said, by whom, to whom, and which of it is worth building a result on.

Every figure here is a screenshot of the tool running on a synthetic study that
`chatlens demo` generates from a fixed seed — forty-eight groups of four, two
treatments, nobody real. You can reproduce every step.

## Contents

1. [What this is for](#1-what-this-is-for)
2. [What it can do](#2-what-it-can-do)
3. [Installing it](#3-installing-it)
4. [Setting up a study](#4-setting-up-a-study)
5. [Running the analysis](#5-running-the-analysis)
6. [The pages, one at a time](#6-the-pages-one-at-a-time)
7. [A complete session](#7-a-complete-session)
8. [Where things live](#8-where-things-live)

---

## 1. What this is for

An experiment with a chat produces two kinds of data. The choices — who offered
what, who accepted — are already numbers. The conversations are not, and turning
them into numbers is where the difficulty is, because there are many ways to do
it and they do not agree.

chatlens does that turning, six different ways, and then does something less
usual: it puts them side by side against the same outcome and tells you which
one is actually carrying anything.

**One idea runs through the whole tool.** Longer messages contain more of
everything — more positive words, more relations, more of any term you care to
count. So a text measure that looks impressive is often measuring how much
somebody typed. Every page that predicts anything shows message length beside
the model, and says plainly when length wins.

On the experiment this tool was built for, that turned out to be the answer
twice, and the strongest result in the dataset was not in the text at all: it
was in who never wrote to whom.

## 2. What it can do

| Page | The question it answers | What it needs |
|---|---|---|
| **Participation** | who spoke to whom, and who never did | nothing |
| **Words** | which terms go with the outcome | `words` extra |
| **Narratives** | who does what to whom, and which of it matters | `narratives` extra |
| **Emotions** | eight emotion categories, and how much of the corpus they reach | a lexicon you request |
| **Topics** | what the conversations were about | an API key — the only paid part |
| **Compare** | which of the above is worth building on | `words` extra |

Underneath all of them, always on and needing nothing: the deterministic
measures — how much was written, sentiment, and LIWC-style indices for
analytical thinking, Clout and Authenticity — computed at pair and group level
and grafted onto your choice data, ready for Stata or R.

**Two units of work, four units of analysis.** Every measure can be computed per
directed pair (what i wrote to j), per pair, per person, or per group. Which one
is right is a question about your design, and the tool makes you answer it
rather than choosing for you.

**Nothing is our own invention where somebody has published the method.** Topics
are TopicGPT's, called through the authors' own functions. Relations are
RELATIO's. Sentiment is VADER. The lexical indices are ours and are labelled
LIWC-*style*, because LIWC itself is proprietary and we do not have it.

## 3. Installing it

```bash
uv tool install git+https://github.com/nicomil/chatlens.git
```

[uv](https://docs.astral.sh/uv/) is a single binary and installs Python itself
if the machine has none. `pipx` and a plain `pip install` into a virtual
environment work the same way with the same URL.

That gives you about four megabytes and one dependency: the deterministic
measures, the dashboard, Participation. Everything heavier is an extra, so that
nothing large arrives because you opened a page.

| Extra | Adds | Roughly |
|---|---|---|
| `words` | word clouds, coefficient tables, the comparison page | 150 MB |
| `narratives` | the relational analysis | 500 MB with the language model |
| `llm` | the validation rubric | small |
| `topics` | TopicGPT | small |

```bash
uv tool install --reinstall "git+https://github.com/nicomil/chatlens.git#egg=chatlens[all]"
python -m spacy download en_core_web_md    # for the narratives
chatlens install-relatio                   # for the narratives
chatlens install-topicgpt                  # for the topics
```

**`--reinstall`, not `--force`.** Adding an extra to an existing installation
needs the environment rebuilt, and `--force` alone will not rebuild one that uv
considers current.

Every page that needs something missing says so, with the command already
written out for the interpreter chatlens is running under. That last detail
matters more than it sounds: chatlens lives in an environment of its own, so a
`pip install` typed into a shell installs somewhere else and the page goes on
reporting the same thing missing.

## 4. Setting up a study

```bash
chatlens dashboard
```

![The library, empty](images/01-library-empty.png)

The library is empty on a first run. Everything happens here — there is no
configuration file to write by hand, and no paths to type.

### 4.1 Make an experiment

Give the study a name and say what shape the data is in.

**One message per row** is the general case: your export already has a row per
message with a group, a sender, a recipient and the text. You point at the
columns; no code is involved.

**oTree coalition game** is a worked example of the other kind, where the
groups, the chat channels and the choices all have to be reconstructed from a
raw oTree export. It is specific to a three-player coalition game and is there
as a model for writing an adapter of your own.

![The experiment created](images/02-library-created.png)

The card says what is still missing — here, the files. That badge is the tool's
running answer to "can this be analysed yet", and it stays wrong-looking until
it can.

### 4.2 Upload the files

![Files and their roles](images/03-settings-files.png)

Under **Settings**, drop the CSVs in. Up to 500 MB each; a file with the same
name replaces the one that is there.

Each file gets a **role** from the dropdown beside it — which is the messages,
which is the roster of participants. This is what lets the tool work with an
export whose filename is not one it expected: you say what a file *is* rather
than renaming it to suit.

The roster is optional and worth having. It is the only source that can see a
participant who never wrote and was never written to — someone invisible in a
chat log by construction, and precisely the kind of person the Participation
page is about.

### 4.3 Say which column is which

![The column mapping](images/04-settings-columns.png)

The dropdowns are built from the header of the file you just uploaded, so you
are choosing among your own column names rather than typing them.

They arrive **already guessed**. `group`, `sender`, `receiver`, `text`,
`sent_at` are recognised, and so are `teamId`, `fromSeat`, `sentAt` — the
matching understands snake_case, kebab-case and camelCase as one convention. In
the ordinary case the whole step is confirming what is already selected.

Where nothing is recognised, nothing is selected. That is deliberate: a blank
field costs you a minute, and a wrong guess sitting there waiting to be
confirmed costs you a dataset.

Four columns are required — group, sender, receiver, text — and the rest change
what can be computed rather than whether anything can:

| Column | Without it |
|---|---|
| `timestamp` | no durations, no ordering by time |
| `treatment` | the report does not break down by condition |
| colours or role names | transcripts do not read as the participants saw them |

One thing to get right: **the group identifier must be unique across the whole
dataset**, not just within a session. If two sessions both have a "group 1",
distinguish them (`sess3-g1`), or two different conversations will be merged.

### 4.4 Name the treatments

![The treatments](images/05-settings-treatments.png)

The values the treatment column actually takes are read from the file and listed
for naming. `restricted` becomes *Restricted chat*, and that is what the report
prints — you are not editing a lookup table somewhere, you are labelling what is
in your data.

### 4.5 Say what the analysis should explain

![The outcome](images/06-settings-outcome.png)

This is the setting the rest of the tool depends on. Without it chatlens
describes text; with it, the same pages answer questions about it.

Three things to set:

**The column.** What the analysis should explain — whether an offer was
accepted, how much someone earned, whether a group reached agreement. Read from
the dataset the pipeline builds, so it appears after the first run.

**The kind.** Binary or continuous. Binary reads `1`, `yes`, `true`, `y`, `t`
and their opposites, so a column exported from a spreadsheet works as it is.

**The unit.** Which of the four an outcome row belongs to. This is not a
formality: fit a model at the wrong unit and each group's value is silently
repeated across its members, and the result reports a precision it has not got.

Underneath, the page reads the column and says what it found — *191 of 191 rows
have a value, 133 of them are 1 (70%)*. A column that turns out to be a
participant code looks obviously wrong the moment its distribution is shown, and
looks like nothing at all until then.

## 5. Running the analysis

![The run](images/11-run-done.png)

Three presets, and the page says which costs money before you press anything.

| Preset | What it adds | Key | Time |
|---|---|---|---|
| **Measures only** | volume, sentiment, the language indices | no | seconds |
| **Measures + validation** | a model scores the same texts, to check the indices | yes | minutes |
| **Full analysis** | also the topics, with TopicGPT | yes | longer, and the expensive one |

Start with the first. It needs nothing, it is free, and it produces the datasets
every page here reads.

Every run is **archived**, so running again does not erase the last one, and the
log stays on screen while it works rather than leaving you watching a spinner.

![The report](images/12-report.png)

The run writes a readable summary as well as the datasets: how many groups and
messages survived the filters, the measures broken down by treatment, and a
section of things worth knowing about the data that the tool noticed on the way
past.

## 6. The pages, one at a time

### 6.1 Participation — who spoke to whom

![Participation](images/20-participation.png)

Start here. It needs no extra, no key and no waiting, and on the study this tool
was built for it held the strongest result in the dataset.

Every other page measures text, so it can only see the pairs that produced some.
This one shows the **whole grid**: for every group, every ordered pair of its
members, whether or not anything passed between them. Here that is 48 groups,
570 possible directed pairs, and **257 that stayed empty**.

Those are not missing data. Somebody chose not to write, and in a design where
speaking is a choice that is a finding rather than a gap. It also means every
other page in this tool is computed on a sample **conditional on having
spoken** — a selection that is easy to forget precisely because it never appears
anywhere.

The bars show how many of the possible directions each group actually used. The
shape of that is usually more interesting than its average.

With a binary outcome per directed pair, the page adds two comparisons. The raw
one — the outcome where somebody wrote against where they did not — comes with a
warning that it cannot be read as it stands, because a receiver who can choose
only one partner bounds the rate mechanically and people who write a lot may
simply be different people. The second holds the **receiver fixed**: among
receivers where exactly one of the possible senders wrote to them, the two
candidates face the same person, in the same group, under the same treatment,
and differ in whether they spoke.

Where the design cannot support that comparison, the page says so instead of
producing a number.

### 6.2 Words — the look before the statistics

![Words](images/30-words.png)

A penalised regression over unigrams and bigrams against the outcome, drawn as
two clouds — the terms that go with it, and the terms that go against — and
listed underneath with their coefficients. Downloads as PNG, SVG and CSV.

This is deliberately the crude analysis. A term being kept says it carries
signal; its size says how much the penalty let it keep. **None of it is an
estimate**: a lasso picks and shrinks, so what survives is biased by having been
picked.

Above the clouds, always, sits length alone:

> *Out-of-sample, whole groups held out. The words beat length, so this is not
> simply a count of who typed more.*

And where they do not beat it, the page says that is the finding rather than
something to tune away.

The control worth moving is the **penalty**. Tighten it and the model keeps only
what it is most sure of:

![A tight penalty](images/31-words-strict.png)

Loosen it and it keeps hundreds of terms:

![A loose penalty](images/32-words-loose.png)

Watching them appear and disappear is the quickest way to see how fragile the
selection is, which a single static table hides completely. Terms and minimum
frequency work the same way, and every value is pulled into a known range rather
than trusted, since it arrives from a browser.

### 6.3 Narratives — who does what to whom

![Narratives](images/40-narratives.png)

The same text read as (agent, verb, patient) relations rather than as words,
using RELATIO. Two properties make that worth having.

A relation comes out of a **sentence**, so nothing has to be generalisable at
the level of a whole document — which is exactly where topic modelling gives up
on short conversations. And a relation has a **direction**, which a word count
cannot represent: in a study of who supports whom, "I support you" and "I
support the other one" are opposite moves made of the same words, and any model
built on word counts scores them identically.

**The page will not run until you name the entities**, and that is deliberate.
Left to be grouped by similarity, `i` and `you` fall together — they sit in the
same positions and mean the same kind of thing — and the speaker stops being
distinguishable from the person being spoken to. Nothing but the experiment can
know which of its words are its participants.

Every relation appearing in twenty-five or more units is tested, with length in
the model and standard errors clustered by group, and the reported **q** carries
a correction across the whole family tested. Reporting the one that came out
significant, out of dozens tried, is how a list of nothing becomes a finding.

### 6.4 Emotions — eight categories from a word list

![Emotions](images/50-emotions.png)

Counts from the NRC Emotion Lexicon: eight emotions and two sentiments, about
fourteen thousand English words. It is free for research and distributed through
a form, so it is not shipped — the page says where to request it, where to put
it, and that `tidytext::get_sentiments("nrc")` is quicker if you have R. All
three file shapes in circulation are read without conversion.

*(The figure above uses a stand-in word list, so the page has something to draw.
The real lexicon is larger and its numbers will differ.)*

Half the page is about coverage, and that is the point of it rather than a
caveat. **A zero is a real value**: a message with no frightening word in it did
not frighten anyone, and that row belongs in the analysis.

The care is needed elsewhere. A document containing *no listed word at all*
scores zero on every category at once, and on short messages that happens
constantly. Those all-zero rows are not spread at random — they are the short
ones. So the emotion columns carry a signal about length mixed into the one
about emotion, and the same rule applies as everywhere else in this tool: keep
the zeros, and put length in the model.

Category shares are reported over the documents that could be measured, not over
all of them. Over everything, each category is divided by the same inflated
denominator and a corpus of very short messages comes out looking uniformly
unemotional rather than unmeasured.

### 6.5 Compare — which representation to use

![Compare](images/60-compare.png)

All of them against the same outcome, on the same rows and the same folds, with
whole groups held out. A feature set scored on a different split is not being
compared to anything.

Length is always the first row, because it is the null hypothesis of text
analysis. The bar is the higher of length and chance — length can score below
chance, and beating *that* would be no achievement at all.

A representation that could not be built appears **with its reason** rather than
being quietly dropped. Comparing three things while the reader believes they are
seeing five is the worse failure.

One distinction the page states in words, because a table cannot: **predicting
well and mattering are different questions, and this table answers the first.**
A relation can carry a large and reliable effect and still predict poorly,
because it appears in a fraction of the rows and brings a handful of variables
where a bag of words brings a thousand. Read this page to choose what to build
on, and the Narratives page to decide what is true.

## 7. A complete session

Start to finish on the demo study, using every feature. About ten minutes, of
which most is the narratives parsing.

```bash
uv tool install --reinstall "git+https://github.com/nicomil/chatlens.git#egg=chatlens[all]"
python -m spacy download en_core_web_md
chatlens install-relatio
chatlens demo /tmp/study            # writes the synthetic study
chatlens dashboard
```

Then, in the browser:

1. **Create** — *Ultimatum with pre-play chat*, one message per row.
2. **Settings → Files** — upload `messages.csv` and `roster.csv` from
   `/tmp/study/input`, and set their roles to *messages* and *participants*.
3. **Settings → Which column is which** — confirm the guess: `group`, `sender`,
   `receiver`, `text`, `sent_at`, `treatment`.
4. **Settings → Treatments** — name `open` and `restricted`.
5. **Settings → What to explain** — column `accepted`, binary, one row per
   person. Check the line underneath: *191 of 191 rows have a value*.
6. **Start run**, preset *Measures only*. A few seconds.
7. **Participation** — 570 possible pairs, 257 empty. Note how much of the
   design never happened.
8. **Words** — move the penalty from 0.02 to 1.0 and watch the term list grow
   from a handful to hundreds. Check whether the words beat length.
9. **Narratives** — set the entities to `i, you, we`, save, and wait. Read the
   table of what was said before the table of what mattered.
10. **Emotions** — the lexicon notice. Follow it if you want the page; the rest
    of the guide works without it.
11. **Compare** — the answer to what all of this was for.

Then read the report, and take
`output/datasets/*_nlp.csv` into Stata or R.

## 8. Where things live

An experiment is an ordinary folder:

```
<library>/my-experiment/
├── experiment.toml     name, adapter, columns, treatments, outcome, entities
├── input/              the CSVs you uploaded
└── output/
    ├── merged/         the canonical message tables
    ├── datasets/       the tables with the measures, for Stata or R
    ├── runs/           every run, archived
    └── *_report.html   the readable summary
```

Everything about one study is in its own folder, so it can be copied to a
colleague or included in a backup complete.

What is *not* in it, deliberately: the API keys, the TopicGPT and RELATIO
clones, and the NRC lexicon. Those belong to the machine rather than to a study,
and copying keys into a folder you then send someone is a mistake worth making
structurally impossible.

The library lives in this machine's application data directory —
`~/Library/Application Support/chatlens/experiments` on macOS,
`%LOCALAPPDATA%\chatlens\experiments` on Windows,
`~/.local/share/chatlens/experiments` on Linux. The dashboard prints the path.
It is a folder your backups may not cover by default, and if these are
participant data, that is worth checking.
