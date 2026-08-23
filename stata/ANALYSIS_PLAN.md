# Analysis plan — for approval

This document says, before anything is estimated, how each dependent variable is
built, which non-parametric test and which regression is used for each
hypothesis, and how the conversation profiles on a 1–4 scale are constructed.

**Nothing here is settled.** Two things in particular need a decision from the
experimenter, and they are marked ⬜ throughout:

1. **the list of hypotheses.** There is no pre-registration in the repository,
   so the hypotheses below were reconstructed from the design — the treatments,
   the payoff rule and the variables the experiment records. They are a
   proposal, not a reading of an existing document. Correct them, cut them, add
   the ones that are missing.
2. **the construction choices** where more than one defensible option exists.
   Each is stated with its alternative and the reason for the default.

---

## 1. The design, as the code implements it

The three treatments are a 2×2 with one cell not run:

| | Total deadweight loss | No deadweight loss |
|---|---|---|
| **Private communication** | `private` — **Baseline** | `private_no_dwl` — *Slacker* |
| **Public communication** | `public` | *(not run)* |

`public` differs from the baseline in the communication protocol only
(`reveal_third_party_chat = True`: a player sees the conversation the other two
are having). `private_no_dwl` differs in the payoff rule only: when two players
support the same third and that third supports no one, the outcome is (6,0,0)
instead of (0,0,0).

This shape decides the comparisons:

- **`public` vs `private`** isolates the effect of communication being
  observable;
- **`private_no_dwl` vs `private`** isolates the effect of the payoff rule;
- **`public` vs `private_no_dwl`** differs on both dimensions at once, so it is
  reported descriptively and never interpreted as one effect.

Baseline is the reference category in every regression.

## 2. The sample

Three filters, applied together as the `in_sample` flag (README §6):

| Filter | Why |
|---|---|
| `group_valid == 1` | the triad is complete, was not interrupted, and no member let a timer expire or was excluded for inactivity |
| `low_language_flag == 0` | the text is language, not keyboard mashing — which would otherwise score as maximally analytic |
| `wc > 0` | units with no text have blank indices by construction, not zeros |

They are flags, not deletions: every robustness check on the full sample is one
`keep if` away.

⬜ **To approve:** whether the main tables use `in_sample`, with the full sample
in an appendix, or the reverse.

## 3. The units of observation

| Unit | File | Rows | Used for |
|---|---|---|---|
| Triad | `triads.dta` | 1 per game | coordination, efficiency, group language |
| Participant | `participants.dta` | 3 per triad | consistency, deception, individual language |
| Directed pair i→j | `pairs.dta` | 6 per triad | signals, support, persuasion, the language i used with j |

Group-level variables (payoff, outcome) are collapsed to one row per triad
before being averaged: on the participant file a group payoff of 6 would be
counted as 18.

---

## 4. Hypotheses and dependent variables

For each hypothesis: the dependent variable, exactly how it is built, the unit,
the non-parametric test and the regression.

### H1 — Public communication changes coordination

*Observable promises make a minimal winning coalition easier (or harder) to
reach than private ones.*

| | |
|---|---|
| **DV** | `coordinated` = 1 if the triad reached a minimal winning coalition |
| **Built from** | `group_coordinate`, which is 1 when `group_outcome` is one of `mutual_12`, `mutual_23`, `mutual_31` |
| **Unit** | triad (1 obs per game) |
| **Non-parametric** | Fisher's exact test on the 3×2 table treatment × coordinated; pairwise Fisher against baseline, Holm-corrected |
| **Regression** | LPM `regress coordinated i.treat, robust`; logit as a robustness check with `margins, dydx(treat)` |

No clustering: the triad is the unit and the observations are independent.

### H2 — The payoff rule changes efficiency

*When failing to coordinate is not fully destructive, the surplus produced
changes.*

| | |
|---|---|
| **DV** | `efficiency` = `group_total_payoff` / 6 |
| **Built from** | `group_total_payoff`, the theoretical payoff of the choice profile, summed over the three members. 6 is the surplus of a minimal winning coalition and is the same benchmark in all three treatments, which is why it is the denominator |
| **Unit** | triad |
| **Non-parametric** | Kruskal–Wallis across the three treatments; Mann–Whitney (`ranksum`) for `private_no_dwl` vs `private`, Holm-corrected |
| **Regression** | `regress efficiency i.treat, robust` |

⬜ **To approve:** the benchmark. Alternative denominator: the maximum
attainable in *that* treatment, which in `private_no_dwl` is also 6 (the star
outcome pays 6 in total), so the two coincide — but if the intended benchmark is
the paid payoff rather than the theoretical one, `focal_payoff_paid` summed over
members is the variable to use instead, and the two differ whenever a member was
excluded for inactivity.

### H3 — Public communication changes persuasion

*Does a promise of support translate into actual support more often when the
third player can see it?*

| | |
|---|---|
| **DV** | `persuasion_ij` = 1 when i signalled support to j **and** j chose i |
| **Built from** | `S_ij` (i's final signal to j is `split_you`) and `A_ji` (j's `decision_choice` resolves to i). Both are already in the dataset; the product is `persuasion_ij` |
| **Unit** | directed pair (6 per triad) |
| **Non-parametric** | the pair is not independent within a triad, so the test is run on the triad-level mean: `persuasion_rate` = mean of `persuasion_ij` over the triad's six pairs, then Kruskal–Wallis and pairwise Mann–Whitney |
| **Regression** | LPM `regress persuasion_ij i.treat, vce(cluster triad)`; logit + `margins` as robustness |

**Decomposition.** `persuasion_ij` is a product of two decisions, and a
treatment can move either. Both halves are estimated separately: `S_ij` on
treatment (does i promise at all), and `A_ji` on treatment **conditional on
`S_ij == 1`** (does the promise get honoured). Reporting only the product hides
which of the two moved.

### H4 — Public communication reduces inconsistency and deception

*A promise everybody can see is harder to break.*

| | |
|---|---|
| **DV 1** | `cc_i` — consistency between i's final signals and i's choice; 1, 0.5 or 0 |
| **DV 2** | `strategic_deception` = 1 when i promised support to both partners and then supported neither |
| **Built from** | `C_ij` per directed pair; `cc_i` is its mean over i's two partners. `strategic_deception` is already computed in the merge step |
| **Unit** | participant |
| **Non-parametric** | `cc_i`: Kruskal–Wallis, then pairwise Mann–Whitney on the triad-level mean of `cc_i` (participants within a triad are not independent). `strategic_deception`: Fisher's exact on the triad-level count |
| **Regression** | `cc_i`: ordered logit (`ologit`, three levels 0/0.5/1) with `vce(cluster triad)`, and OLS with clustering as the linear counterpart. `strategic_deception`: LPM and logit, both `vce(cluster triad)` |

### H5 — The treatment changes how people write

*Visibility gives the message an audience; that should show in the language.*

| | |
|---|---|
| **DV** | `nlp_sent_clout_100`, `nlp_sent_analytic_100`, `nlp_sent_authenticity_100`, `nlp_sent_tone_100`, `nlp_sent_sentiment_compound_mean`, `nlp_sent_wc` |
| **Built from** | the pipeline, on the summed counts of the unit's text; the `_100` versions are standardised within the sample |
| **Unit** | participant (what i wrote to everyone) — and directed pair as a secondary reading |
| **Non-parametric** | Kruskal–Wallis and pairwise Mann–Whitney on the triad-level mean of each measure |
| **Regression** | `regress <measure> i.treat, vce(cluster triad)` for each; word count with `poisson` as well, since it is a skewed count |

⬜ **To approve:** the direction expected for each measure. The plausible signs
are Clout ↑ and Authenticity ↓ under public communication, but that is a
prediction to state before looking, not one to read off the estimates. This is
also the family with the most tests, so the multiple-testing correction in §6
matters most here.

### H6 — Language predicts being supported

*Within the same game, does how i writes to j predict whether j supports i?*

| | |
|---|---|
| **DV** | `persuasion_ij`, and separately `A_ji` conditional on `S_ij == 1` |
| **Regressors** | the sender's block only: `nlp_sent_clout_100`, `nlp_sent_analytic_100`, `nlp_sent_authenticity_100`, `nlp_sent_tone_100`, controlling for `nlp_sent_wc` |
| **Unit** | directed pair |
| **Non-parametric** | Spearman correlation between each measure and `persuasion_ij`, and a Mann–Whitney of each measure between persuaded and non-persuaded pairs |
| **Regression** | four specifications, in this order: volume alone; language + volume; the same plus `i.treat`; the same with triad fixed effects (`areg …, absorb(triad) vce(cluster triad)`). The fixed-effects one compares the two messages the *same* sender wrote inside the *same* game, which removes everything about the triad that language might otherwise stand in for |

**This is an association, not an effect.** The treatment is assigned; how a
participant writes is not. The wording in the paper has to keep that
distinction, and the do-file prints it into the log so it survives being read
months later.

### H7 — Topics differ by treatment and predict support

| | |
|---|---|
| **DV** | one indicator per topic (present / absent for that unit), plus `topic*_lvl` on 1–4 (§7) |
| **Built from** | `nlp_sent_topics`, the pipeline's TopicGPT assignment on directed pairs |
| **Unit** | directed pair; aggregated to triad as a share of its six pairs |
| **Non-parametric** | Fisher's exact per topic on treatment × presence, Holm-corrected across topics |
| **Regression** | `regress persuasion_ij topic_k nlp_sent_wc, vce(cluster triad)` one topic at a time, and a joint specification with all topics |

⬜ **To approve:** the topic ontology itself. On the pilot the three seed topics
were reused and no new one emerged; the seed's content is a research choice and
should be approved before the topics enter any analysis (README §8).

---

## 5. Which test, and why

**Non-parametric tests are the primary evidence for the treatment comparisons.**
The counts per treatment are moderate, several variables are bounded (0/1, 0–1,
0–100), and none of them is plausibly normal. They also require no functional
form.

| Situation | Test | Stata |
|---|---|---|
| Binary outcome, three treatments | Fisher's exact | `tabulate treat y, exact` |
| Continuous or ordinal, three treatments | Kruskal–Wallis | `kwallis y, by(treat)` |
| Continuous or ordinal, two treatments | Mann–Whitney | `ranksum y if inlist(treat,1,2), by(treat)` |
| Two measures on the same unit | Wilcoxon signed-rank | `signrank a = b` |
| Two continuous measures, association | Spearman | `spearman a b` |

**The independence rule.** Randomisation is at the level of the triad, so the
triad is the independent unit. Any non-parametric test on a participant-level or
pair-level variable is run on the **triad-level mean** of that variable, never
on the raw rows: six directed pairs from one conversation are not six
independent observations, and a rank test has no way of knowing that.

**Regressions are the secondary evidence**, where controls, fixed effects or
several regressors at once are needed. Every regression on a unit finer than the
triad has `vce(cluster triad)`.

| Outcome | Main model | Robustness |
|---|---|---|
| Binary | LPM (`regress`) | `logit` + `margins, dydx(*)` |
| Ordinal (`cc_i`, the 1–4 scales) | `ologit` | OLS on the same variable |
| Count (words, messages) | `poisson` | OLS on the log |
| Continuous 0–100 | OLS | OLS with triad FE where the unit allows it |

The linear probability model is the main specification for binary outcomes
because its coefficients are differences in probability and clustering is
straightforward; the logit is there to show the result does not depend on the
functional form.

⬜ **To approve:** whether the paper's tables lead with the non-parametric tests
(the design's own logic) or with the regressions (comparability with the
literature). The do-files produce both.

## 6. Multiple testing

Within each family of hypotheses — the six language measures of H5, the topics
of H7 — p-values are Holm-corrected. Across families they are not: H1 to H4 are
distinct pre-specified questions, not repeated attempts at one.

⬜ **To approve:** the composition of the families, and whether H5 should be
reduced to two primary measures (Clout and Authenticity, the two the design
speaks to) with the rest exploratory. That would be a stronger claim than
correcting for six.

## 7. The conversation profile on a 1–4 scale

What was asked: every conversation carries the characteristics the text analysis
extracted — tone, authenticity, sentiment, volume, clout, analytic thinking and
every topic present — and each one gets an intensity from 1 (barely present) to
4 (strongly present). They coexist: a conversation has a value on all of them at
once.

Implemented in `06_conversation_profile.do`, at two units, because "the
conversation" can reasonably mean either:

| Unit | Output |
|---|---|
| The triad's whole conversation | `data/profile_group.dta`, `tables/conversation_profile_groups.csv` |
| What i wrote to j | `data/profile_pair.dta`, `tables/conversation_profile_pairs.csv` |

**The continuous characteristics** (tone, authenticity, sentiment, volume,
clout, analytic) are cut into **quartiles within the analysis sample**: 1 is the
bottom quarter of these conversations, 4 the top quarter. The bands are relative
to the study, which is what the underlying measures already are — they are
standardised within the sample, not against an external corpus.

*The alternative*, one line to switch on at the top of the file: fixed cut-offs
on the 0–100 scales (1: 0–25, 2: 25–50, 3: 50–75, 4: 75–100). Those do not move
when the sample changes, which matters if the intensities are to be compared
with another study, but they can leave a band empty. Volume stays on quartiles
in both variants: a word count has no natural 0–100 scale.

**The topics** are not continuous — TopicGPT says present or absent for each
unit. The intensity of a topic in a triad's conversation is the **share of its
six directed pairs that carry it**: 1 up to a quarter of them, 2 up to a half,
3 up to three quarters, 4 above. At the level of a single directed pair the
share can only be 0 or 1, so there the scale has two values, 1 and 4.

⬜ **Three choices to approve here:**

1. **Quartiles or fixed cut-offs** as the default (currently quartiles).
2. **A topic that never appears gets 1**, on the reading that 1 means "barely
   present". If absence should be its own category, the scale becomes 0–4; the
   companion dummy `topic*_any` is saved either way, so absence is recoverable
   exactly.
3. **Sentiment** is cut by quartiles like the rest. Its own scale is a polarity
   from −1 to +1, so in the fixed-cut-off variant the bands are VADER's
   conventional ones (≤ −0.05 negative, −0.05 to 0.05 neutral, up to 0.5
   positive, above 0.5 strongly positive) — which measures direction, not
   intensity. If what is wanted is the *intensity* of sentiment regardless of
   sign, the variable to cut is its absolute value; say which.

**Where these variables are used.** They are an ordinal recode of continuous
measures: good for the descriptive tables, for a profile a reader can scan, and
as outcomes in ordered models. They are not a replacement for the continuous
measures in the main regressions of H5 and H6, where the recode would throw away
the variation inside each band.

## 8. What I need in order to proceed

1. The **hypothesis list**: confirm, correct or replace §4.
2. The **⬜ decisions**: sample for the main tables (§2), efficiency benchmark
   (H2), expected directions (H5), topic ontology (H7), tables leading with
   tests or regressions (§5), families for multiple testing (§6), and the three
   scale choices (§7).
3. Anything the experiment measures that is **not** in the datasets and should
   be — the survey, the control questions, response times — before the
   specifications are fixed rather than after.
