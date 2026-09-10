# chatlens

Text analysis of the conversations held during a behavioural experiment. It
turns a chat log into numbers you can take into Stata or R, and — this is the
part that makes it more than a measuring tool — it says **which of those numbers
is worth using**.

Six ways of reading the same conversations, each on its own page:

| Page | Question it answers | Needs |
|---|---|---|
| **Participation** | who spoke to whom, and who never did | nothing |
| **Words** | which terms go with the outcome | `words` extra |
| **Narratives** | who does what to whom, and which of it matters | `narratives` extra |
| **Emotions** | eight emotion categories, and how much of the corpus they reach | a lexicon |
| **Topics** | what the conversations were about | an API key |
| **Compare** | which of the above is worth building on | `words` extra |

Plus the deterministic language measures — volume, emotional tone, sentiment,
analytical thinking, Clout, Authenticity — computed at pair and group level and
grafted onto your choice datasets.

**One idea runs through all of it.** Longer messages contain more of everything,
so a text measure that looks impressive is often measuring how much somebody
typed. Every page that predicts anything shows length beside it, and says so when
length wins. On the experiment this was built for, that turned out to be the
answer twice.

The code is split where the reusable part ends and the experiment-specific part
begins. An **adapter** turns one experiment's export into the canonical message
tables; the **core** — measures, rubric, topics, aggregation, report — works from
those tables alone and never reads a raw export itself.

Two adapters ship with it. `generic_chat` needs no code at all where the export
is already one message per row: the column names go in a configuration file.
`otree_coalition` is the worked example of the other kind, written for a
three-player coalition game in oTree, where the groups, the channels and the
choices all have to be reconstructed. See [[§5](05-your-own-experiment.md)](05-your-own-experiment.md#your-own-experiment) for how to
run your own study.

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

```bash
uv tool install git+https://github.com/nicomil/chatlens.git
chatlens dashboard
```

That opens the library in your browser. Create an experiment, drop the CSVs in,
say which column is which, and press Start run — no editor, no paths, no
configuration file to write by hand.

Nothing to analyse yet? Try it on a synthetic study first — nobody's data,
generated on the spot:

```bash
chatlens demo
```

It writes a small four-player bargaining experiment with two treatments, runs
the whole pipeline over it and leaves you a report to read. It is the same
procedure you will run on your own data.

### From the terminal instead

```bash
cd my_experiment       # the folder holding input/
chatlens all           # merge + the automatic measures, a few seconds
```

`chatlens --help` lists every command. The main ones:

| Command | What it does | API key |
|---|---|---|
| `chatlens dashboard` | opens the library of experiments in the browser | — |
| `chatlens all` | merge + automatic measures, a few seconds | **no** |
| `chatlens merge` / `chatlens analyze` | the two steps separately | no |
| `chatlens keys` | configures the API keys, guided | — |
| `chatlens analyze --llm --llm-replicates 2` | measures + validation rubric | yes |
| `chatlens analyze --topics` | measures + topics with TopicGPT | yes |
| `chatlens subtopics` | subdivides the topics a run already found | yes |
| `chatlens all --llm --topics` | everything: rubric and topics included | yes |
| `chatlens experiments` | lists the experiments from the terminal | — |
| `chatlens report` | regenerates the readable summary | — |
| `chatlens runs` | lists the archived runs | — |
| `chatlens runs --prune 2` | keeps the last 2 and deletes the others | — |
| `chatlens status` | what is in input, in output and among the keys | — |
| `chatlens demo` | writes a synthetic study and analyses it | — |
| `chatlens install-topicgpt` | installs TopicGPT (only needed for the topics) | — |
| `chatlens install-relatio` | installs RELATIO (optional, for the narratives) | — |

**`all` is both *steps*, not everything.** It means merge plus analysis, as
opposed to `merge` and `analyze` taken singly: it runs only the automatic
measures, needs no key at all and takes a few seconds. Adding `--llm` and
`--topics` brings in the validation rubric and the topics, which need a key and
take far longer. You start from `chatlens all`; you add the rest once the keys
are there.

## Contents

**[The illustrated guide](guide.md)** — the whole tool,
step by step, with screenshots. Start there.

1. [What it does, in brief](01-what-it-does-in-brief.md#what-it-does-in-brief)
2. [Installation](02-installation.md#installation)
3. [API keys](03-api-keys.md#api-keys)
4. [Participant data](04-participant-data.md#participant-data)
5. [Your own experiment](05-your-own-experiment.md#your-own-experiment)
6. [The analysis procedure](06-the-analysis-procedure.md#the-analysis-procedure)
7. [The pages in the dashboard](07-the-pages-in-the-dashboard.md#the-pages-in-the-dashboard)
8. [The files produced](08-the-files-produced.md#the-files-produced)
9. [Before analysing: three filters](09-before-analysing-three-filters.md#before-analysing-three-filters)
10. [How the measures are built](10-how-the-measures-are-built.md#how-the-measures-are-built)
11. [TopicGPT](11-topicgpt.md#topicgpt)
12. [Costs and volumes](12-costs-and-volumes.md#costs-and-volumes)
13. [If something does not add up](13-if-something-does-not-add-up.md#if-something-does-not-add-up)
14. [Checking the tools](14-checking-the-tools.md#checking-the-tools)
15. [Results on the pilot](15-results-on-the-pilot.md#results-on-the-pilot)
