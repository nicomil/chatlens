# Costs and volumes

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
