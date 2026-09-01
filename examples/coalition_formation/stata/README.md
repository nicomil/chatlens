# Stata analysis

Seven do-files that take the pipeline's output and produce the tables. They
read `../output/datasets/`, so run `python run.py all` first.

**Read `ANALYSIS_PLAN.md` first.** It states which hypothesis each dependent
variable tests, how it is built, and which test and regression are used — and
marks the decisions that need the experimenter's approval before these become
the paper's tables.

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
| `03_treatment_effects.do` | what the treatment changes, by regression | triad, pair, participant |
| `04_language_and_persuasion.do` | does the sender's language predict being supported | directed pair |
| `05_validation_and_topics.do` | dictionaries against the rubric; topics | triad, directed pair |
| `06_conversation_profile.do` | every characteristic of a conversation on a 1–4 intensity scale | triad, directed pair |
| `07_nonparametric.do` | the same treatment comparisons without a functional form | triad |

`01_prepare.do` saves three datasets in `data/`:

| Dataset | One row per |
|---|---|
| `pairs.dta` | directed pair i→j, six per triad |
| `participants.dta` | participant |
| `triads.dta` | triad — the group variables collapsed, so a group payoff of 6 is not counted three times |

`06_conversation_profile.do` adds two more, `profile_pair.dta` and
`profile_group.dta`, along with the same content as CSV in `tables/` for anyone
who would rather look at it in Excel.

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

**Stata 19**, and only commands that ship with it: `table`/`collect` for the
descriptive tables, `etable` for the regression tables. No user-written package
is needed — in particular not `estout` — and the regression tables export to
`tables/*.html`, which becomes `.docx` or `.tex` by changing the extension on
the `collect export` line.

**The triad is the independent unit.** Randomisation happens there, so every
non-parametric test in `07` is run on the triad-level mean of the variable, not
on the participant or pair rows: six directed pairs from one conversation are
not six independent observations, and a rank test has no way of knowing that.
The regressions keep the finer unit and cluster on the triad instead.

## What is not here

The specifications follow from the variables the experiment produces, not from
a pre-registration: there is none in the repository. `ANALYSIS_PLAN.md` lists
the hypotheses it reconstructs from the design and marks with ⬜ every choice
that needs a decision — the hypothesis list itself, the efficiency benchmark,
the expected directions, the families for the multiple-testing correction, and
the three choices behind the 1–4 scales.
