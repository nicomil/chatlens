# If something does not add up

**"Missing file: ..._messages_long.csv"** — the merge was not run:
`chatlens merge`, or directly `chatlens all`.

**"No all_apps_wide*.csv file in input/"** — the export was not put in `input/`,
or it has a different name from the one oTree produces.

**"More than one ChatMessages*.csv file in input/"** — `input/` must contain a
single export per kind, otherwise it is unclear which one to analyse: keep only
the one you need, or point at it with `--chat <path>`.

**"Missing OPENAI_API_KEY"** — see [§3](03-api-keys.md). With `--topicgpt-api ollama` the topics
run locally without any key.

**"The topicgpt_python package is not installed"** — see [§2](02-installation.md), second part.

**"... is missing columns the analysis cannot do without"** — the adapter did
not produce one of the columns the core needs. The message names it, says what
it is for and lists what is present; [§5](05-your-own-experiment.md) and `core/schema.py` have the full
contract.

**"does not have the columns the configuration names"** — with `generic_chat`,
the names under `[columns]` in `experiment.toml` do not match the export's
header. The message lists the header, so it is usually a matter of copying the
right name across.

**Every language measure is near zero** — the dictionaries are English only.
See the end of [§5](05-your-own-experiment.md).

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
