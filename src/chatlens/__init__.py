"""chatlens — text analysis of chat data from behavioural experiments.

The project is split along the line where the reusable part ends and the
experiment-specific part begins:

- ``core``: everything that does not know which experiment produced the data.
  Deterministic LIWC-style measures, sentiment, the LLM validation rubric,
  the TopicGPT wrapper, aggregation to the four units of analysis, the report
  and the run archive.
- ``adapters``: one module per experiment, whose only job is to turn that
  experiment's export into the canonical message tables the core consumes.
- ``web``: the local dashboard that launches runs and shows their output.

The entry point is ``chatlens`` on the command line, or ``python -m
chatlens.cli``.
"""

__version__ = '1.0.0'
