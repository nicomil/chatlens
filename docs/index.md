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
choices all have to be reconstructed. See [§5](05-your-own-experiment.md) for how to run your own study.

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

Nothing to analyse yet? Try it on a synthetic study first — no data of anyone's,
generated on the spot:

```bash
chatlens demo
```

It writes a small four-player bargaining experiment with two treatments, runs
the whole pipeline over it and leaves you a report to read. It is the same
procedure you will run on your own data.

`chatlens --help` lists every command. The main ones:

| Command | What it does | API key |
|---|---|---|
| `chatlens all` | merge + automatic measures, a few seconds | **no** |
| `chatlens merge` / `chatlens analyze` | the two steps separately | no |
| `chatlens keys` | configures the API keys, guided | — |
| `chatlens analyze --llm --llm-replicates 2` | measures + validation rubric | yes |
| `chatlens analyze --topics` | measures + topics with TopicGPT | yes |
| `chatlens all --llm --topics` | everything: rubric and topics included | yes |
| `chatlens dashboard` | opens the library of experiments in the browser | — |
| `chatlens experiments` | lists them from the terminal | — |
| `chatlens report` | regenerates the readable summary | — |
| `chatlens runs` | lists the archived runs | — |
| `chatlens runs --prune 2` | keeps the last 2 and deletes the others | — |
| `chatlens status` | what is in input, in output and among the keys | — |
| `chatlens demo` | writes a synthetic study and analyses it | — |
| `chatlens install-topicgpt` | installs TopicGPT (only needed for the topics) | — |

**`all` is both *steps*, not everything.** It means merge plus analysis, as
opposed to `merge` and `analyze` taken singly: it runs only the automatic
measures, needs no key at all and takes a few seconds. Adding `--llm` and
`--topics` brings in the validation rubric and the topics, which need a key and
take far longer. You start from `chatlens all`; you add the rest once the keys
are there.

Full documentation, the same text split into pages:
<https://nicomil.github.io/chatlens>
