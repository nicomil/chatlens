# TopicGPT

The adapter **does not rewrite the algorithm**: it prepares the input in the
expected format, invokes the official functions in the order the paper
prescribes — generation of the first-level topics, refinement, assignment,
correction — and recomposes the output onto the experiment's keys.

**Unit of analysis: two, not one.** The topics are **induced** on the whole
triad's conversation (`--topicgpt-unit group`), which has enough text for the
model to recognise something, and are **assigned** to the directed pairs
(`--topicgpt-assign-unit dyad_directed`), which are the unit where persuasion
plays out. They are then aggregated to participant and group by taking the union
of the topics of the component units.

The separation is not a detail: inducing directly on the directed pairs makes
the model answer "None" on every document, because the paper's prompt explicitly
instructs it to do so when the document contains no recognisable topic, and a
two-line exchange contains none.

### The seed, and doing without one

TopicGPT does not start from a fixed taxonomy. It keeps a list that **grows as
it reads**: each document is shown the list so far and asked to reuse a topic or
add one. The seed is only that list's initial state, and supplying it is a
parameter of the method rather than a change to the authors' code — `seed_file`
is an argument of `generate_topic_lvl1`.

There are three ways to run it.

```bash
chatlens analyze --topics --topicgpt-unsupervised   # nothing to start from
chatlens analyze --topics                           # the game's three topics
chatlens analyze --topics --topicgpt-seed mine.md   # your own list
```

**Unsupervised** is the method's own mode: every topic comes from the
documents. Nothing steers what the model may find, which is the point when the
topics are meant to be a finding rather than a coding scheme. The cost is that
the ontology is then a function of the model, of the temperature and of the
order the documents were read in, so the induced list has to be reported as a
result — it is archived as `topics.md` with each run, and the run's parameters
record that no seed was used.

**Seeded** steers the induction. The project ships
`prompts/seed_coalition_formation.md`, three topics pertinent to the game. On
the pilot's 18 conversations nothing emerged beyond those three, which is what
the prompt prescribes when existing topics fit; on a larger corpus more appear.
A seed's content is a research choice and should be approved before the topics
are used in an analysis.

**Neither** falls back to the repository's own seed, which concerns the paper's
demonstration corpus — US legislation, `[1] Trade`, examples about tariffs. On
chat conversations that seed makes the model recognise nothing. Avoid it.

### Document order is part of the method

Induction is order-dependent by construction — the list accumulates, and
generation stops early once a hundred consecutive documents add nothing — so
whatever comes first decides the taxonomy. Left in their natural order the
documents arrive sorted by `group_uid`, which begins with the session code, and
each session is one treatment. On the coalition data the third treatment did
not appear until document 104, past the early-stop threshold: the topics could
have been induced from two conditions out of three.

The documents are therefore shuffled before induction, with a seed
(`--topicgpt-shuffle-seed`, default 1) so that a run stays reproducible and the
seed can be reported. `--topicgpt-shuffle-seed 0` keeps the file order. This
matters most without a seed, where there is no starting list to cover the gap,
but it applies either way.

**Models: TopicGPT and the rubric do not accept the same ones.** TopicGPT fixes
`temperature` and `top_p` in every phase, inside the authors' code. Recent
models that allow only the default temperature — verified on `gpt-5.6-luna`,
`gpt-5.6-terra`, `gpt-5.6-sol` — reject them with a 400 error, and the library
reacts by retrying three times a minute apart: unchecked, the incompatibility
would surface after two minutes for every document. The preflight check
intercepts it with a minimal call and stops immediately.

For the topics it is therefore best to stay on `gpt-4o`, which is also the
paper's model. The rubric does not send `temperature` and works with all of
them: it is chosen with `--llm-models`.

**Backends.** TopicGPT talks to OpenAI, Azure, Vertex, Gemini, Ollama or vLLM.
The paper uses OpenAI and that is the most faithful choice. To use Claude there
are two roads that require no change to the authors' code: the `vertex` backend,
which in the repository builds an `AnthropicVertex` client, or `openai` pointed
at a compatible gateway through `OPENAI_BASE_URL`.
