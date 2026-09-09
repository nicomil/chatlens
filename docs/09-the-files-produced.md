# The files produced

Everything under `output/`.

### The dashboard

```bash
chatlens dashboard
```

It opens `http://127.0.0.1:8765` in the browser: from there you pick the
options, launch the run and watch the log advance live, with the report embedded
in the page and the list of archived runs.

It is the same command running underneath: the dashboard does nothing that
cannot be done from the command line, and the two paths cannot diverge.

Three choices worth knowing about:

- **It listens on `127.0.0.1` only.** This is a desktop tool, not a service: it
  executes processes, so it must not be reachable from the network.
- **The arguments come from a closed list.** The form offers dropdowns and
  checkboxes, and the server checks every value against the allowed ones before
  building the command. Nothing arriving from the browser ends up in a command
  line as it is.
- **No new dependency**: a standard-library-only server, with htmx shipped in
  the project. It works offline too.

One run at a time: two concurrent runs would write to the same files.

### What happens when you run again

`output/` always holds the **latest** run, at fixed paths: that is what you open
and what you take into Stata. Every run is however also copied into
`output/runs/<date_time>/`, with the two datasets, the report, the list of
topics used and a `run.json` with the parameters.

It is needed because two runs do not produce the same files: one without `--llm`
rewrites the datasets **without** the rubric's columns, and with no archive that
work would vanish from the final files while still sitting in the cache.

```bash
chatlens runs             # lists the runs, with each one's stages and parameters
chatlens runs --prune 2   # keeps the 2 most recent and deletes the others
```

To clear results by hand, delete `output/` — or the single dataset's folder
inside it. Nothing there is needed to run again: it is all regenerated from
`input/`.

```powershell
chatlens runs
chatlens runs --prune 2
Get-ChildItem output -Exclude runs,cache,.gitkeep | Remove-Item -Recurse -Force
Remove-Item -Recurse -Force output\runs
```

A session of trials leaves a long tail of near-identical runs:
`chatlens runs --prune 2` shortens it while keeping the ones that matter.
Each run takes about 800 KB.

The intermediate measures are not archived: they are regenerated.

### The run's summary

Every run produces `output/<name>_report.md` and `<name>_report.html`: a single
page with sample coverage, game outcomes, behavioural variables, language
measures and — when those stages were run — rubric and topics. It is there to
show how it went without opening CSVs three hundred columns wide. The HTML is
self-contained: it opens on a double click and can be sent to someone.

The sections of the stages not run do not appear. The comparisons between
treatments are descriptive by choice: on numbers like the pilot's they serve to
check that the pipeline produces sensible results, not to draw conclusions from.
To regenerate it without redoing the analysis: `chatlens report` — then open
the `.html` in `output/` with a
double click.

### To take into Stata

| File | Unit of observation |
|---|---|
| `..._chat_by_partner_nlp.csv` | the directed pair i→j, six per triad |
| `..._chat_aggregated_nlp.csv` | the participant |

The text measures carry a prefix saying which conversation they refer to:

| Prefix | Content |
|---|---|
| `nlp_sent_*` | the messages **sent** by the subject (to the partner in the per-pair file, to the whole group in the per-participant file) |
| `nlp_recv_*` | those **received** |
| `nlp_dyad_*` | the pair's whole conversation |
| `nlp_group_*` | the triad's whole conversation |

The distinction between sent and received is not cosmetic: in persuasion what
counts is the speaker's language, so regressions on persuasion must use the
`nlp_sent_*` columns.

Main columns of each block: `n_messages`, `wc`, `mean_words_per_message`,
`type_token_ratio`, `duration_seconds`, `median_gap_seconds`, the triples
`analytic_cdi` / `analytic_z` / `analytic_100` and their equivalents for
`clout`, `authenticity`, `tone`, plus `sentiment_compound_mean` and the category
percentages (`pct_i`, `pct_we`, `pct_you`, `pct_negate`, `pct_posemo`,
`pct_negemo`, `pct_commitment`, `pct_exclusive`, `pct_social`).

With stages 2 and 3 active you also get `llm_analytic`, `llm_clout`,
`llm_authenticity`, `llm_tone` with their `_sd` counterparts, the flags
`llm_contains_support_commitment` and `llm_contains_support_request`, and
`nlp_*_topics` / `nlp_*_topic_primary` / `nlp_*_n_topics`.

### The experiment's variables, built at step 2

| Variable | Definition |
|---|---|
| `persuasion_ij` | i promises support to j **and** j actually chooses i. Six observations per game |
| `C_ij`, `cc_i` | consistency between final signal and choice, per pair and on average: 1, 0.5 or 0 |
| `strategic_deception` | promises support to both, then supports no one |
| `group_valid` | 0 if the triad was interrupted or if even a single member let a timer expire |
| `group_total_payoff` | the basis for Efficiency, in the theoretical version and in the paid one |
| `group_outcome_recomputed` | the outcome the stored decisions imply, under the game's rule |
| `payoff_decision_mismatch` | 1 when the recorded outcome is not reconstructable from those decisions |

**On `payoff_decision_mismatch`.** Normally it is 0. It turns 1 when a
participant let the Decision page time out *after* someone else had already
reached the final page: the payoff is computed from a random choice drawn on
their behalf, and the timeout then overwrites the stored decision with a
second, independent random draw. The row ends up carrying an outcome its own
decisions do not produce.

Nothing is corrected, because nothing can be: the replaced choice is not in the
export. The flag exists so the contradiction is visible in the data instead of
being found months later and mistaken for corruption. It is empty when the
triad is incomplete or the outcome has not been computed yet — "not checkable"
must not read as "checked and fine". On the three collection days it was 1 on a
single triad out of 262, already excluded by `group_valid == 0`.

### Analysis in Stata

`examples/coalition_formation/stata/` holds seven do-files that read
`output/datasets/` and produce the tables: preparation and labelling,
descriptives, treatment effects, the language-and-persuasion regressions, the
1–4 conversation profiles, the non-parametric tests and the optional
rubric/topics sections. They were written for the coalition-formation
experiment, and are as good a starting point as any for another one.

```
cd examples/coalition_formation/stata
do 00_master.do
```

They are documented in that folder's `README.md`, which also records the choices behind
them — clustering on the triad, the main-sample flag, the reference category —
and states plainly that the language regressions are associations, since the
treatment is assigned but the language is chosen.

### Intermediate files

`..._messages_long.csv` (one message per row), `..._messages_nlp.csv` (the same
with counts and sentiment) and `..._features_<level>.csv` for the four
aggregation levels. They serve the checks and analyses at different levels; they
are not needed for Stata.
