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

**The seed is a research choice.** TopicGPT starts from a list of initial
topics, which in the official repository concerns the paper's demonstration
corpus — US legislation, with `[1] Trade` and examples about tariffs and
agricultural policy. With that seed, on chat conversations the model recognises
nothing. The project therefore uses `prompts/seed_coalition_formation.md`, with
three topics pertinent to the game. Supplying the seed is a **parameter of the
method**, not a modification of the authors' code: `seed_file` is an argument of
`generate_topic_lvl1`.

A caveat, though: the seed conditions the resulting ontology. On the pilot, with
18 conversations, no new topics emerged beyond the three starting ones — which
is the behaviour the prompt prescribes, reusing existing topics when they are
pertinent. On a large corpus others are expected to emerge. The seed's content
must be reviewed and approved by whoever runs the study before the topics are
used in an analysis.

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
