# Contributing

Bug reports, adapters for other experiments and corrections to the measures are
all welcome. What follows is what makes a change easy to accept.

## Getting set up

```bash
git clone https://github.com/nicomil/chatlens.git
cd chatlens
make setup      # editable install in .venv/, every extra included
make test
```

On Windows: `py -m venv .venv`, then
`.venv\Scripts\python -m pip install -e ".[llm,topics]"`.

The three suites need no network, no credentials and no data. If a change needs
any of those to be tested, that is usually a sign it belongs behind an
interface that can be tested without them.

## The one rule that matters

**The measures must not change by accident.** Published results rest on them.
Any change that touches the merge, the aggregation or the metrics has to say
what it does to the numbers — and if the answer is "nothing", show it:

```bash
chatlens --workspace <a workspace with real data> merge
shasum -a 256 output/merged/*.csv
```

against the same files before the change. Where the numbers *should* change,
say so in the commit message and in the changelog, plainly enough that someone
re-running an old analysis knows to expect it.

The rubric's system prompt is pinned by a test for the same reason: ratings are
cached under a signature that includes the prompt text, so an accidental
reword throws away every rating already paid for.

## Writing an adapter

An adapter is the only place that may know an experiment's column names, group
size, treatments or payoff rule. It needs `INPUTS`, `OPTIONS`, `run()` and
`print_summary()`, and `run()` must produce the three tables described in
`core/schema.py`. `adapters/generic_chat.py` is the short one to read first;
`adapters/otree_coalition.py` is the one that does real reconstruction.

Before writing one, check whether `generic_chat` plus an `experiment.toml`
already covers the case — it usually does.

## Style

Match what is there. Comments explain *why*, not what: the code says what.
Error messages name the thing that is wrong and what to do about it — every one
of them is read by somebody who does not know the codebase.

## What not to put in a commit

Participant data of any kind, API keys, and anything from an `input/` or
`output/` folder. They are gitignored; keep them that way.
