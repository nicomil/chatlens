# Stata analysis

Five do-files that take the pipeline's output and produce the tables. They read
`../output/datasets/`, so run `python run.py all` first.

```
cd "<...>/text_analysis/stata"
do 00_master.do
```

That runs everything in order and writes `logs/analysis.log`. The files can also
be run one at a time — `01_prepare.do` must come first, the others only read
what it saved.

| File | What it does | Unit |
|---|---|---|
| `01_prepare.do` | imports the two CSVs, labels them, builds the sample flags, saves `data/*.dta` | — |
| `02_descriptives.do` | sample, treatments, game outcomes, behaviour, language | all three |
| `03_treatment_effects.do` | what the treatment changes | triad, pair, participant |
| `04_language_and_persuasion.do` | does the sender's language predict being supported | directed pair |
| `05_validation_and_topics.do` | dictionaries against the rubric; topics | triad, directed pair |

`01_prepare.do` saves three datasets in `data/`:

| Dataset | One row per |
|---|---|
| `pairs.dta` | directed pair i→j, six per triad |
| `participants.dta` | participant |
| `triads.dta` | triad — the group variables collapsed, so a group payoff of 6 is not counted three times |

## Choices worth knowing about

**Standard errors are clustered on the triad** wherever the unit is finer than
the triad. The three members of a triad played the same game and the six
directed pairs share one conversation; treating them as independent would
shrink every standard error.

**The main sample is a flag, not a deletion.** `in_sample` is 1 when the triad
is valid, the text is language and the sender wrote something — the three
filters of README §6. The rows that fail it stay in the datasets, so a
robustness check on the full sample is one `keep if` away.

**Baseline (private) is the reference category** in every regression, and the
treatment is coded by hand rather than with `encode`, which would have ordered
the levels alphabetically and put `private_no_dwl` second.

**The language regressions are associations.** The treatment is assigned; how a
participant writes is not. Section 5 of `04` says so in the log too, so the
distinction survives being read months later.

**Only Stata 16 syntax** is used (`tabstat`, `tabulate`, `summarize`, `areg`),
so the files run on an older installation. `esttab` is used when present and
skipped with a message when not: `ssc install estout` to get the
publication-ready tables.

## What is not here

The specifications follow from the variables the experiment produces, not from
a pre-registration: there is none in the repository. Before these become the
paper's tables, the experimenter should confirm which comparisons are the
hypotheses and which are exploratory, and the exploratory ones should be
labelled as such.
