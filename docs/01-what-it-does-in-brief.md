# What it does, in brief

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
