# The analysis procedure

The commands in this section are identical on macOS, Windows and Linux, and
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
