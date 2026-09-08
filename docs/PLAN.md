# Plan — bringing the new analysis into chatlens

Work done on the coalition-formation experiment produced several things this
tool does not have: a check that stops a run which lost documents, a bag-of-words
layer with word clouds, a relational analysis that is the only content measure to
survive the volume control, and a diagnostic that explains why topic induction
returns so little on a repetitive corpus. This plan brings them across.

## Decisions already taken

- **Heavy dependencies are optional extras**, detected at runtime, with a notice
  on the page rather than a crash. `chatlens[narratives]` is roughly 500 MB for
  the spaCy route; `chatlens[relatio]` roughly 1.6 GB for the full package. The
  `llm` extra already works this way.
- **Every command shown is built from `sys.executable`**, never written by hand.
  chatlens installs as a uv tool, so its environment is not the one a `pip
  install` in the user's shell would reach; a hand-written command sends the
  install to the wrong place and the page keeps saying the dependency is missing.
- **`known_entities` and the outcome column live in the TOML** and are set from
  the interface. They are the two lines the results depend on, and they change
  from experiment to experiment.
- **Volume is a mandatory comparison, not an option.** Every predictive page
  shows length alone beside the model. Longer messages contain more of every
  word, and both of this project's early findings dissolved once length was held
  constant.

---

## Phase 0 — The two shipped defects

Not features. Anyone holding the current build has both.

**`core/topicgpt.py`**: port `verify_phase()`, `TopicGPTIncomplete`, and the
count of API failures in the stdout digest. The four phases fail differently —
generation truncates its output file, assignment and correction write `"Error"`
into otherwise normal rows, refinement leaves no trace and only prints a line.
Early stopping in generation stays distinct from a failure: it is the method
converging.

**`core/setup_keys.py`**: replace `GET /v1/models` with one minimal completion.
Listing models answers 200 on a key with no credit left, so today the check
confirms the key exists and nothing about whether it can do any work.

**Done when**: the tests written for the experiment repo pass here, and the real
truncated file — 806 responses for 1,333 documents — is rejected with a message
saying how many answers are already on disk.

## Phase 1 — The concept of an outcome

Prerequisite for phases 3, 4, 6 and 7. Today chatlens describes text; from here
it answers questions about it.

**`core/experiment.py`**: an `[outcome]` section — column, kind (binary or
continuous), and the unit it belongs to. **`core/schema.py`**: validation, reusing
the messages it already produces.

**`web/views_library.py`**: the dropdown is filled by reading the file's header,
reusing the column mapping that already exists. For a binary outcome, show the
distribution immediately — it is the fastest way to notice the wrong column.

**Done when**: the TOML round-trip holds, and an experiment with no `[outcome]`
still runs everything descriptive.

## Phase 2 — Participation page

The strongest finding on this project lives in the empty cells, and they are
invisible today.

The full sender × receiver matrix including the silent directions; how many of
the possible directions are used; the distribution across groups. With an
outcome present, the contrast between those who wrote and those who did not.

**The within-receiver comparison** where the structure allows it — a receiver
with at least two senders and an outcome per directed pair. On the triad design
it gives 357 against 35. On another design it may not be computable, and the page
must say so rather than produce a meaningless number.

Needs no extra. The best value-to-effort ratio in the plan.

## Phase 3 — Words page

Lasso over unigrams and bigrams, clouds and tables.

**Interactivity, server-side via htmx** as everything else: outcome, unit,
unigrams/bigrams/both, minimum frequency, and the **penalty**. The penalty
control is the one that matters — watching terms appear and disappear says how
fragile the selection is, which a static table hides.

**Downloads**: PNG, SVG and CSV. The SVG is the one that ends up in a paper.

**The volume baseline is always on the page**, beside the model.

## Phase 4 — Narratives page

**Three-state detection**, reusing the `check_installation()` pattern: spaCy
missing, language model missing, relatio missing. Three different commands, each
complete with its interpreter, each with its download size written beside it and
a button to copy it. Plus a **check again** control that re-runs detection
without a restart, and a start button disabled with the reason beside it rather
than left live to fail mid-run.

**Light mode** (spaCy only): subject-verb-object triples, entities from the TOML,
narratives per unit. **Full mode** (relatio): adds automatic selection of k and
the two-tier entity system.

With an outcome: which narratives matter, volume in the model, Benjamini-Hochberg
across the whole family tested. Never one narrative reported because it was the
one that came out significant.

## Phase 5 — Topics, finished

Independent of phase 1, so it can sit anywhere.

**The "None" rate by document length.** This is what showed the problem was
neither the seed nor the unit, and anyone running chatlens on a repetitive corpus
will hit the same wall. They should see it before spending, not after five
thousand calls.

**Second-level subtopics**, with the grounding warning: on this corpus the model
cited documents 1-10 out of the 1,383 it was given.

## Phase 6 — NRC emotions

The lexicon is free but behind a request form: treat its absence like a missing
dependency, same notice.

**Always with the coverage diagnostic beside it.** 77% of our 1-5 word messages
contain no emotion word at all, and no lexicon can invent one. Without that
number the user believes they have a measurement where they have a zero.

## Phase 7 — Comparison page

Every representation against the same outcome under the same design: volume,
lexical indices, words, narratives. On this project that comparison produced the
most useful result of all — knowing which method is worth using.

Only meaningful after 3, 4 and 6.

---

## Order

**0 → 1 → 2 → 5 → 3 → 4 → 6 → 7**

Phase 5 comes early because it does not depend on phase 1 and is cheap. Phase 2
comes before 3 because it needs no extra and delivers the strongest result.

## Verification, every phase

The pipeline on real data keeps producing files **byte-identical** to the frozen
reference. This work adds pages; it does not touch the existing analysis, and
that has to be demonstrated at each step.

The four existing test files stay green, and each phase adds one to the Makefile
and to CI. The end-to-end proof is done in the browser, because that is where the
feature lives — and repeated on the fake experiment with different column names,
to check it serves someone who does not have our files.

## Security

The new pages accept numeric parameters from the browser (penalty, minimum
frequency, k). They are validated and bounded, not passed to a model as they
arrive. Downloads stay confined with the same `resolve()` + `relative_to()`
already in use. Nothing is installed from the interface: the notice shows the
command, the user runs it.

## Out of scope

The matched-pair design **in the form used here** — a receiver facing exactly two
candidates — stays in the experiment's own repository. Only the generic version
described in phase 2 comes into chatlens, and it declares itself uncomputable
when the structure is absent.
