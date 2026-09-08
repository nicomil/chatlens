# API keys

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
  OK   OpenAI: key valid and in credit
```

If a key is wrong it says so unambiguously, and repeats the provider's own
explanation: `FAIL OpenAI: key rejected (HTTP 401): Incorrect API key provided`.

The check sends **one minimal completion**, costing a fraction of a cent, rather
than asking the provider to list its models. Listing is free, which is exactly
the problem: it answers successfully on a key with no credit left on it, so it
confirms the key exists and nothing about whether it can do any work. An analysis
would then start, spend what credit there was, and stop part-way through. A key
that is valid but out of credit is reported separately:
`FAIL OpenAI: no capacity — out of credit or rate limited (HTTP 429)`.

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
