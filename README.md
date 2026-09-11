# chatlens

Text analysis of the conversations held during a behavioural experiment. It
turns a chat log into numbers you can take into Stata or R, and — this is the
part that makes it more than a measuring tool — it says **which of those numbers
is worth using**.

```bash
uv tool install git+https://github.com/nicomil/chatlens.git
chatlens dashboard
```

That opens the library in your browser and walks you through five steps — the
data, the columns, what to explain, the run, and then the findings. No editor,
no paths, no configuration file to write by hand. Nothing to analyse yet?
`chatlens demo` writes a synthetic four-player bargaining study, belonging to
nobody, and runs the whole procedure over it.

## What it will tell you

Six readings of the same conversations, each answering one question:

| Finding | Question | Needs |
|---|---|---|
| **Who spoke to whom** | who wrote to whom, and who never wrote at all | nothing |
| **The words** | which terms go with the outcome | `words` extra |
| **The relations** | who does what to whom, and which of it matters | `narratives` extra |
| **The emotions** | eight categories, and how much of the corpus they reach | a lexicon |
| **The topics** | what the conversations were about | an API key |
| **Which to trust** | which of the above is worth building on | `words` extra |

Plus the deterministic language measures — volume, emotional tone, sentiment,
analytical thinking, Clout, Authenticity — computed at pair and group level and
grafted onto your choice datasets. Only the topics and the validation rubric
cost anything; everything else runs on your machine, on data that never leaves
it. `chatlens tables` then puts all of it — the experiment's variables and
every measure, the relations and emotions included — into one table per unit,
as CSV for R and `.dta` for Stata, with a codebook.

**One idea runs through all of it.** Longer messages contain more of
everything, so a text measure that looks impressive is often measuring how much
somebody typed. Every finding that predicts anything shows length beside it,
and says so when length wins. On the experiment this was built for, that turned
out to be the answer twice.

## Where things live

Everything happens in a **workspace**: an ordinary folder of yours holding
`input/` and `output/`. Two experiments are two folders, and they never touch
each other's results.

```
my_experiment/          <- the workspace
├── input/              the CSVs exported from oTree  ← put the data here
└── output/             everything that gets produced
```

Input files are not passed on the command line: you drop them in `input/` and
they are recognised by name. That is why the procedure comes down to a single
command, and also why `input/` must hold nothing else. The dashboard keeps its
studies in the application data directory instead, so neither command above
cares which folder you run it from — see
[installation](handbook/installation.md).

From a terminal rather than the browser:

```bash
cd my_experiment       # the folder holding input/
chatlens all           # merge + the automatic measures, a few seconds
```

`all` is both *steps*, not everything: merge plus the automatic measures, no key
and a few seconds. `--llm` and `--topics` add the paid stages. The full list is
in [commands](handbook/commands.md).

## Participant data

The files this produces are **personal data**. The chat texts are the object of
the analysis and are never altered; the recruitment platform's participant id
passes straight through unless you ask for it not to, and `chatlens merge
--pseudonymise` replaces every identifier with a keyed hash. The paid stages
send the conversations to a third party, which is a disclosure your ethics
approval has to cover. The API keys are kept in this machine's configuration
directory, outside any repository, so they cannot be committed by mistake.

That paragraph is a summary and not the whole of it:
[participant data](handbook/participant-data.md) is the page to read before
running this on a real study.

## The rest of the documentation

**[The illustrated guide](GUIDE.md)** is the place to start: the whole tool,
step by step, with screenshots of every screen.

| | |
|---|---|
| [Installation](handbook/installation.md) | the two commands, the three add-ons, the emotion lexicon, where files end up on each operating system |
| [Commands](handbook/commands.md) | everything the terminal can be asked to do |
| [Your own experiment](handbook/your-experiment.md) | the configuration file, the two adapters, and how to write one for an export nothing else understands |
| [The analysis procedure](handbook/procedure.md) | what each stage does, in the order it happens, and the three filters applied before anything is measured |
| [The pages in the dashboard](handbook/dashboard.md) | what each finding shows and how to read it |
| [The files produced](handbook/files.md) | every output column, and how to send a whole study to a colleague |
| [How the measures are built](handbook/measures.md) | the formulas, the dictionaries and the choices behind them |
| [API keys, and what they cost](handbook/keys-and-costs.md) | which key each stage wants, and the price of a run |
| [TopicGPT](handbook/topics.md) | the method, its backends, and what it does badly on short messages |
| [Participant data](handbook/participant-data.md) | identifiers, pseudonymisation, and what leaves the machine |
| [When something does not add up](handbook/troubleshooting.md) | the errors worth recognising, and how to check the tools are doing what they claim |
| [Results on the pilot](handbook/pilot.md) | a worked output, to see what the numbers look like |

## Design

An **adapter** turns one experiment's export into the canonical message tables;
the **core** — measures, rubric, topics, aggregation, report — works from those
tables alone and never reads a raw export itself. That line is where the
reusable part ends and the experiment-specific part begins.

Two adapters ship with it. `generic_chat` needs no code at all where the export
is already one message per row: the column names go in a configuration file.
`otree_coalition` is the worked example of the other kind, written for a
three-player coalition game in oTree, where the groups, the channels and the
choices all have to be reconstructed.

The code is in `src/chatlens/`: `core/` for the analysis steps, `adapters/` for
the experiment-specific part, `web/` for the dashboard. The development setup is
in [CONTRIBUTING.md](CONTRIBUTING.md).

## Citing it

The methods are other people's and are cited where they are used: RELATIO (Ash,
Gauthier and Widmer 2024), the NRC Emotion Lexicon (Mohammad and Turney 2013),
TopicGPT (Pham et al. 2024), VADER (Hutto and Gilbert 2014). `CITATION.cff` has
the full list and the entry for this tool.

MIT licensed. See [LICENSE](LICENSE).
