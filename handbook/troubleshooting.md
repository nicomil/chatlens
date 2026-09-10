# When something does not add up

**"Missing file: ..._messages_long.csv"** — the merge was not run:
`chatlens merge`, or directly `chatlens all`.

**"No all_apps_wide*.csv file in input/"** — the export was not put in `input/`,
or it has a different name from the one oTree produces.

**"More than one ChatMessages*.csv file in input/"** — `input/` must contain a
single export per kind, otherwise it is unclear which one to analyse: keep only
the one you need, or point at it with `--chat <path>`.

**"Missing OPENAI_API_KEY"** — see [api keys, and what they cost](keys-and-costs.md). With `--topicgpt-api ollama` the topics
run locally without any key.

**"The topicgpt_python package is not installed"** — see [installation](installation.md), second part.

**"... is missing columns the analysis cannot do without"** — the adapter did
not produce one of the columns the core needs. The message names it, says what
it is for and lists what is present; [your own experiment](your-experiment.md) and `core/schema.py` have the full
contract.

**"does not have the columns the configuration names"** — with `generic_chat`,
the names under `[columns]` in `experiment.toml` do not match the export's
header. The message lists the header, so it is usually a matter of copying the
right name across.

**Every language measure is near zero** — the dictionaries are English only.
See the end of [your own experiment](your-experiment.md).

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

## Checking the tools


From a source checkout:

```bash
make test
```

```powershell
# Windows, where make is absent: one command per file, in tests\
.venv\Scripts\python tests\test_golden_merge.py
.venv\Scripts\python tests\test_merge.py
.venv\Scripts\python tests\test_analysis.py
.venv\Scripts\python tests\test_dashboard.py
.venv\Scripts\python tests\test_library.py
.venv\Scripts\python tests\test_views.py
.venv\Scripts\python tests\test_participation.py
.venv\Scripts\python tests\test_words.py
.venv\Scripts\python tests\test_narratives.py
.venv\Scripts\python tests\test_emotions.py
.venv\Scripts\python tests\test_compare.py
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
