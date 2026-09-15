# The analysis procedure

The commands here are identical on macOS, Windows and Linux, and
they all act on the current folder unless `--workspace` names another one.

**This page follows the oTree experiment this tool grew out of.** If your export
is already one message per row — which most are — the steps are the same from
step 3 onward, and step 1 is "put the CSV in `input/`". What each column has to
be called is in [your own experiment](your-experiment.md), and nothing below
depends on the adapter except the two filenames in step 1.

### Step 1 — Download the exports from oTree

From the admin interface, **Data** section, two files are needed:

| Export | Typical name |
|---|---|
| All apps — wide | `all_apps_wide_<date>.csv` |
| Chat messages | `ChatMessages_<date>.csv` |

The two custom exports of the randomisation (**RCT slots** and **RCT
assignments**) should be downloaded too: they are not used by this procedure,
but they cannot be reconstructed afterwards and must be kept along with the
others.

### Step 2 — Merge choices and chat

```bash
chatlens merge
```

This is where the experiment's variables already get built: persuasion,
signal-choice consistency, strategic deception, group payoff and the triad
validity flags.

**Who enters the analysis.** The participants kept are those who satisfy two
conditions:

- they have a valid Prolific identifier in `participant.label`, which discards
  the internal test sessions;
- they were part of a triad, which keeps only those who could communicate.

Whoever was later **excluded for inactivity stays in the dataset**: they did
communicate, and their exclusion from the main analyses is governed with
`group_valid`, not by removing them from the data. With `--keep-all` nothing is
filtered, so the raw export can be inspected.

**What to check in the on-screen summary.** The command prints how many
participants were in the export, how many it excluded and for what reason, how
many triads it reconstructed and how many messages it analysed. The message
count must add up: those of excluded participants plus those analysed make the
export's total. If it does not, warning lines at the end explain which ones were
not traced back to a participant.

### Step 3 — Text analysis

**Automatic measures only** — no key needed, a few seconds:

```bash
chatlens analyze
```

**With the validation rubric:**

```bash
chatlens analyze --llm --llm-replicates 2
```

`--llm-replicates 2` has every text scored twice in independent calls, so the
spread between the two lands in the dataset as an estimate of measurement error.

**With the topics:**

```bash
chatlens analyze --topics
```

On Windows the repository path is a Windows one, so
`chatlens analyze --topics --topicgpt-repo <path>` if it lives somewhere
unusual.

**All together:** combine the options of the two commands above.

---

### Which sessions are the experiment

An export carries every session ever run on the server, pilots and internal
tests included. Name the ones that are the study, and nothing else enters the
merge:

```toml
[sample]
sessions = ["w0k1pp1v", "um435zd7", "z7x47k43"]
```

The merge summary says how many participants were left out for belonging to
another session, and a code the export does not contain stops it.

### Step 4 — One dataset per study, where there is more than one

One collection of sessions can be the material of two papers. A 2×2 with one
cell not run supports two comparisons — the baseline against each of the other
arms — and those are two samples, not two slices of one.

```toml
[[studies]]
slug       = "study1"
name       = "Study 1 — public communication"
treatments = ["private", "public"]
baseline   = "private"

[[studies]]
slug       = "study2"
name       = "Study 2 — slacker (no deadweight loss)"
treatments = ["private", "private_no_dwl"]
baseline   = "private"
```

```bash
chatlens studies
```

This is not cosmetic, and the reason is the standardised measures. `clout_100`
and its siblings are z-scores turned into a 0–100 scale **against the sample
under analysis** — that is the documented choice, and it is the right one for
comparing units of the same study. It also means the same participant has a
different `clout_100` in the two studies: on the collection this was built for,
59.8 in one and 68.9 in the other, off an identical raw score. A figure from the
pooled dataset belongs to neither paper.

So each study gets the measures stage re-applied to its own rows, which is what
recomputes those columns. Nothing is paid for twice: the rubric ratings and the
topic assignments are absolute — a 0–100 judgement of one transcript does not
depend on who else is in the file — so they are copied across from the pooled
run.

Each study lands in its own folder, and deliberately **not** beside the pooled
dataset: the Stata do-files find their input by globbing `output/datasets/` and
abort when the glob matches more than one file.

```
output/studies/study1/
├── datasets/     the two tables, under the names the do-files expect
├── stata/        goodshape: the experiment's columns and every measure as a raw
│              regressor; complete: the same plus the bag of words, for a
│              LASSO. Each as .csv and .dta, with one codebook
└── study.json    what the sample was — the count every interval rests on
```

The two studies **share** the baseline arm, so they are not a partition: the
rows of both together exceed the corpus. That is correct. What is not correct is
comparing a number from one with a number from the other, because the two
conditions differ in two respects at once.

**In the dashboard** the masthead then carries a selector — *the whole sample*,
or one of the declared studies — and every findings page below it reads that
study's own tables: the same figures, the same table of terms, the same verdicts,
computed on that sample. A study that has no folder yet is still selectable, and
the page says in as many words that what it is showing is the pooled sample until
`chatlens studies` has been run. The choice also keys the page caches, so moving
between the two studies does not serve one study's model under the other's name.

### Choosing between the representations

Each page turns the conversations into numbers a different way, and each looks
reasonable on its own. The **Compare** page puts them against the same outcome,
on the same rows and the same folds, with whole groups held out.

**The question is what a representation adds to length, not how it scores on its
own.** Longer documents contain more of everything, so a bag of words on a corpus
where the winners simply wrote more will score well and add nothing. So each
block is put *beside* length in the same model and compared against length alone
on the same folds:

```
baseline    outcome ~ log(words + 1)
with X      outcome ~ log(words + 1) + X
```

and what the table reports is the **difference**, fold by fold, with a 95%
interval. The two models share their folds, so their errors are correlated and
the paired difference is what has an interval worth quoting — differencing two
separate ones throws away most of the precision the design has. The interval
carries the correction of Nadeau and Bengio (2003) for the overlap between the
training sets, which on five folds widens it by about half again.

The claim this supports is the one a paper can make: *the lexical features of the
message improve the prediction of the outcome even after accounting for the
quantity of text.*

**Three verdicts, not two.** A block adds something when its interval excludes
zero and the improvement reaches the declared floor of 0.02 AUC; it adds nothing
when the interval rules that floor out; and it is **too close to call** when the
interval covers both. On a few hundred groups the third is the commonest answer,
and a rule forced to say yes or no said one of them by accident. The figures for
this design:

| Groups | Interval half-width | Smallest difference it can resolve |
|---|---|---|
| 250 | 0.025 | 0.051 |
| ~355 (one study) | ~0.020 | ~0.040 |
| 538 (pooled) | 0.015 | 0.030 |

Which is a reason to read the interval and not the verdict: splitting a
collection into two studies roughly doubles the smallest difference either paper
can establish.

The p-values behind the verdicts carry a Holm correction across the blocks, since
they all ask the same question of the same baseline.

A representation that could not be built appears with the reason rather than
being skipped. Comparing three things while the reader believes they are seeing
five is the worse failure.

**Predicting well and mattering are different questions, and the page answers
the first.** A relation can carry a large and reliable effect and still predict
poorly, because it appears in a fraction of the rows and brings a handful of
variables where a bag of words brings a thousand. On the corpus this tool was
built for, the narrative relations barely beat length as predictors while
several of them survived a properly controlled regression — read this page to
choose what to build on, and the narratives page to decide what is true.

The strongest result is often not in the table at all, which is why whether
anything was written appears above it: on that corpus it separated the outcome
better than any representation of what was said, on a sample the table cannot
see.

## Before analysing: three filters


**`group_valid == 1`** — excludes the interrupted triads and those where at
least one member let a timer expire, as agreed. The full sample stays available
for robustness checks. The column has the same name in both files.

**`low_language_flag == 0`** — excludes text that is not language. It is needed
because keyboard mashing comes out paradoxically *maximally analytic*: the index
subtracts the function words, and a text containing none suffers no subtraction
at all. On the pilot, groups made only of test strings scored a median of 93
against 43 for the real groups.

The flag carries the prefix of the block it refers to, so use the one consistent
with the measures being analysed: `nlp_sent_low_language_flag`,
`nlp_dyad_low_language_flag`, `nlp_group_low_language_flag`. On very short units
the threshold does not trip, so at the dyadic level it must be read together
with `nlp_sent_wc`.

**`nlp_sent_wc > 0`** (or the `wc` of the block in use) — units with no text
have **blank** indices by construction, not zeros: without this filter they
would enter the means as missing values rather than as an absence of
conversation.
