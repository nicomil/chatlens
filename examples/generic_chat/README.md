# A second experiment, with no code

`experiment.toml` here is a complete configuration for an export that is already
one message per row: an ultimatum game with pre-play chat, four players per
group, two treatments, ISO 8601 timestamps and a roster of participant
attributes joined on.

Nothing else is needed. Copy it into a workspace next to an `input/` folder
holding the two CSVs, adjust the names under `[columns]`, and run:

```bash
chatlens all
```

The report that comes out has the coverage, language, rubric and topic sections
and none of the coalition-formation ones, because the columns those are built
from are not in this data. That is the whole point of the split: see §5 of the
main README, and `core/schema.py` for the contract an adapter has to meet.

`../coalition_formation/` is the opposite case — an oTree export where the
groups, the chat channels and the choices all have to be reconstructed, which
takes a Python adapter rather than a configuration file.
