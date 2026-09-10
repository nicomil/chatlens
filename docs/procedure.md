# The analysis procedure

The commands here are identical on macOS, Windows and Linux, and
they all act on the current folder unless `--workspace` names another one.

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

### Choosing between the representations

Each page turns the conversations into numbers a different way, and each looks
reasonable on its own. The **Compare** page puts them against the same outcome,
on the same rows and the same folds, with whole groups held out.

Length is always the first row, because it is the null hypothesis of text
analysis: longer documents contain more of everything, and a representation that
does not beat "how much was written" has not shown that content matters. The bar
is the higher of length and chance — length can score below 0.5, and beating it
would then be no achievement at all.

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
