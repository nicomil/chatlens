# API keys, and what they cost

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

## Which stages cost anything

Three independent stages, each switchable on its own.

| Stage | Where | Does it need a credential? |
|---|---|---|
| Deterministic text measures | always on | **no** |
| Participation — who spoke to whom | a page | **no** |
| Words, and the comparison | a page, `words` extra | **no** |
| Narratives | a page, `narratives` extra | **no** |
| Emotions | a page, plus a lexicon you request | **no** |
| Validation rubric | `--llm` | one of OpenAI, Anthropic or a local model |
| TopicGPT | `--topics` | depends on the backend |

Only the last two cost anything. Everything else runs on your machine, on data
that never leaves it.

The first stage runs on Python's standard library alone: it can be executed
straight away, with nothing to obtain first. The other two serve, respectively,
to validate the measures and to extract the topics.

**One key covers everything.** The validation rubric is not tied to a specific
provider: if OpenAI is already in use for TopicGPT, the same key covers that
stage too.

## What a run costs

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
