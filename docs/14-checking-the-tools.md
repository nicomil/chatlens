# Checking the tools

From a source checkout:

```bash
make test
```

```powershell
# Windows, where make is absent: one command per file, in tests\
.venv\Scripts\python tests\test_golden_merge.py
.venv\Scripts\python tests\test_merge.py
.venv\Scripts\python tests\test_analysis.py
.venv\Scripts\python tests\test_dashboard.py
.venv\Scripts\python tests\test_library.py
.venv\Scripts\python tests\test_views.py
.venv\Scripts\python tests\test_participation.py
.venv\Scripts\python tests\test_words.py
.venv\Scripts\python tests\test_narratives.py
.venv\Scripts\python tests\test_emotions.py
.venv\Scripts\python tests\test_compare.py
```

They run with no network and no credentials. If they all end with `OK`, the
tools are in order and any problem lies in the input data.

The most stringent check of the first is not an example but a property: for
**all 27 possible choice profiles**, under both payoff rules, the variables
built must come out consistent with the game's payoff function. If the mapping
between `decision_choice` — which is relative to the circular topology — and the
absolute players were wrong by even a single rotation, the test would fail.

The second covers tokenisation of contracted forms, the heuristic on *-ly*
adverbs, the CDI formula recomputed by hand, the expected direction of the
composites, standardisation, the preservation of words and messages across the
aggregation levels, the asymmetry of directed pairs, the grafting onto the
datasets, parsing of TopicGPT's response format, recognition of text that is not
language, key loading and provider selection.
