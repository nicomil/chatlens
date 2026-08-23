"""Text analysis for the bargaining_tdl experiment.

Modules:
- ``text_metrics`` / ``lexicons``: deterministic LIWC-style measures, volume
  and sentiment. No mandatory external dependency.
- ``llm_rubric``: a second, independent measurement of the same constructs
  through a rubric scored by a language model, for convergent validation.
- ``topicgpt``: adapter for the official TopicGPT code (Pham et al., 2024).
- ``aggregate``: aggregation to directed dyad, dyad, participant and group,
  and grafting onto the experiment datasets.
- ``report`` / ``archive``: readable summary of a run, and its archived copy.

The entry point is ``run.py`` at the project root.
"""
