*==============================================================================
* 02_descriptives.do — the sample, the treatments and the raw numbers
*
* Nothing here is a test: these are the tables you look at before running any
* model, and the ones a referee asks for first.
*
* Tables are built with `table ... statistic()` and collected with `collect`,
* so they can be exported to Word or LaTeX from the same code (Stata 17+).
*==============================================================================

version 19
clear all
set more off

*==============================================================================
* 1. How much data there is, and what the filters cost
*==============================================================================

use "data/participants.dta", clear

display _n as text "{hline 78}"
display as text "Participants by treatment"
display as text "{hline 78}"
tabulate treat

display _n as text "Triads by treatment:"
preserve
    collapse (first) treat, by(triad)
    tabulate treat
restore

display _n as text "What the sample filters remove (rows: valid triad):"
tabulate group_valid in_sample, row

use "data/pairs.dta", clear
display _n as text "Directed pairs, and how many carry text:"
tabulate has_text in_sample, row

*==============================================================================
* 2. Game outcomes
*==============================================================================

use "data/triads.dta", clear

* Efficiency is the group payoff against the maximum the rules allow. Six is
* what a minimal winning coalition produces in every treatment, so it is the
* benchmark in all three.
generate efficiency = group_total_payoff / 6
label variable efficiency "Group payoff over the coalition benchmark"

display _n as text "{hline 78}"
display as text "Game outcomes by treatment (one row per triad)"
display as text "{hline 78}"
table (treat) (), statistic(mean group_coordinate group_total_payoff efficiency) ///
                  statistic(sd group_total_payoff) ///
                  statistic(frequency) nformat(%6.3f)

display _n as text "Outcome types:"
tabulate group_outcome treat, column

*==============================================================================
* 3. Behavioural variables
*==============================================================================

use "data/pairs.dta", clear
keep if in_sample

display _n as text "{hline 78}"
display as text "Signals, support and persuasion, over directed pairs"
display as text "{hline 78}"
table (treat) (), statistic(mean S_ij A_ji persuasion_ij C_ij) ///
                  statistic(frequency) nformat(%6.3f)

use "data/participants.dta", clear
keep if in_sample

display _n as text "Consistency and deception, over participants"
table (treat) (), statistic(mean cc_i strategic_deception n_partners_persuaded) ///
                  statistic(frequency) nformat(%6.3f)

*==============================================================================
* 4. Language measures
*==============================================================================

display _n as text "{hline 78}"
display as text "Language of what each participant wrote (0-100 scales)"
display as text "{hline 78}"
table (treat) (), statistic(mean nlp_sent_analytic_100 nlp_sent_clout_100 ///
                                  nlp_sent_authenticity_100 nlp_sent_tone_100) ///
                  statistic(frequency) nformat(%6.1f)

display _n as text "Volume and sentiment:"
table (treat) (), statistic(mean nlp_sent_wc nlp_sent_n_messages ///
                                  nlp_sent_sentiment_compound_mean) ///
                  statistic(sd nlp_sent_wc) nformat(%7.2f)

* The z-scores are standardised within the sample, so their mean is 0 by
* construction: this is a check that the pipeline ran, not a result.
display _n as text "Standardisation check (means should be ~0, sd ~1):"
summarize nlp_sent_analytic_z nlp_sent_clout_z nlp_sent_authenticity_z ///
          nlp_sent_tone_z

display _n as text "Distributions, to see that they are not degenerate:"
summarize nlp_sent_analytic_100 nlp_sent_clout_100 ///
          nlp_sent_authenticity_100 nlp_sent_tone_100, detail
