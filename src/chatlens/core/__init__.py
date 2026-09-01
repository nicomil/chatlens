"""Everything that does not depend on which experiment produced the data.

- ``text_metrics`` / ``lexicons``: deterministic LIWC-style measures, volume
  and sentiment. No mandatory external dependency.
- ``llm_rubric``: a second, independent measurement of the same constructs
  through a rubric scored by a language model, for convergent validation.
- ``topicgpt``: adapter for the official TopicGPT code (Pham et al., 2024).
- ``aggregate``: aggregation to directed dyad, dyad, participant and group,
  and grafting onto the experiment datasets.
- ``report`` / ``archive``: readable summary of a run, and its archived copy.

These modules consume the canonical tables produced by an adapter; they never
read an experiment's raw export themselves.
"""
