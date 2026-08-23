*==============================================================================
* 04_language_and_persuasion.do — does how you write change who supports you?
*
* This is the analysis the text measures exist for. The unit is the directed
* pair i->j: persuasion happens in one direction, and the language that can
* cause it is the sender's, so the regressors are the nlp_sent_* block and
* never nlp_recv_* or nlp_dyad_*.
*
* Two things make the estimates interpretable:
*   - standard errors clustered on the triad, since the six directed pairs of a
*     triad share the same conversation;
*   - triad fixed effects in the second specification, which compare the two
*     messages the same person sent inside the same game and so remove
*     everything about the triad that language might otherwise proxy for.
*==============================================================================

version 16
clear all
set more off
estimates clear

use "data/pairs.dta", clear
keep if in_sample

*==============================================================================
* 1. What the language variables look like in this sample
*==============================================================================

display _n as text "{hline 78}"
display as text "Sender's language, directed pairs in the main sample"
display as text "{hline 78}"
summarize nlp_sent_wc nlp_sent_analytic_100 nlp_sent_clout_100 ///
          nlp_sent_authenticity_100 nlp_sent_tone_100 ///
          nlp_sent_sentiment_compound_mean nlp_sent_pct_commitment

* The measures are correlated with one another: reading the table before the
* regressions saves interpreting as independent what is not.
display _n as text "Correlations among the sender's measures:"
correlate nlp_sent_analytic_100 nlp_sent_clout_100 ///
          nlp_sent_authenticity_100 nlp_sent_tone_100 ///
          nlp_sent_sentiment_compound_mean

*==============================================================================
* 2. Persuasion on language
*==============================================================================

* Volume first, on its own: writing more is the simplest explanation of being
* supported, and any language effect has to survive it.
regress persuasion_ij nlp_sent_wc, vce(cluster triad)
estimates store p_volume

regress persuasion_ij nlp_sent_clout_100 nlp_sent_analytic_100 ///
        nlp_sent_authenticity_100 nlp_sent_tone_100 nlp_sent_wc, ///
        vce(cluster triad)
estimates store p_lang

* Same, plus the treatment.
regress persuasion_ij nlp_sent_clout_100 nlp_sent_analytic_100 ///
        nlp_sent_authenticity_100 nlp_sent_tone_100 nlp_sent_wc i.treat, ///
        vce(cluster triad)
estimates store p_treat

* Triad fixed effects: the comparison is now within a single game, between the
* two partners the same sender wrote to.
areg persuasion_ij nlp_sent_clout_100 nlp_sent_analytic_100 ///
     nlp_sent_authenticity_100 nlp_sent_tone_100 nlp_sent_wc, ///
     absorb(triad) vce(cluster triad)
estimates store p_fe

* Logit as a robustness check on the functional form.
logit persuasion_ij nlp_sent_clout_100 nlp_sent_analytic_100 ///
      nlp_sent_authenticity_100 nlp_sent_tone_100 nlp_sent_wc, ///
      vce(cluster triad)
estimates store p_logit
margins, dydx(*)

*==============================================================================
* 3. The two halves of persuasion
*==============================================================================
* persuasion_ij is S_ij = 1 and A_ji = 1. Language could be moving either: the
* decision to promise support, or the partner's response to the promise. They
* are different findings and are worth separating.

regress S_ij nlp_sent_clout_100 nlp_sent_analytic_100 ///
        nlp_sent_authenticity_100 nlp_sent_tone_100 nlp_sent_wc, ///
        vce(cluster triad)
estimates store h_signal

* Conditional on i having promised support: does i's language predict whether j
* went along with it? This is persuasion in the narrow sense.
regress A_ji nlp_sent_clout_100 nlp_sent_analytic_100 ///
        nlp_sent_authenticity_100 nlp_sent_tone_100 nlp_sent_wc if S_ij == 1, ///
        vce(cluster triad)
estimates store h_support

*==============================================================================
* 4. Tables
*==============================================================================

capture which esttab
if _rc {
    estimates table p_volume p_lang p_treat p_fe h_signal h_support, ///
        b(%7.4f) se(%7.4f) stats(N r2) varwidth(28)
}
else {
    esttab p_volume p_lang p_treat p_fe, se star(* 0.10 ** 0.05 *** 0.01) ///
        mtitles("Volume" "Language" "+ treatment" "Triad FE") ///
        stats(N r2, labels("Observations" "R-squared"))

    esttab h_signal h_support, se star(* 0.10 ** 0.05 *** 0.01) ///
        mtitles("Signals support" "Is supported | signalled") ///
        stats(N r2, labels("Observations" "R-squared"))
}

*==============================================================================
* 5. A caution worth keeping in the log
*==============================================================================

display _n as text "{hline 78}"
display as text "These are associations, not effects: the language is chosen by"
display as text "the participant, not assigned. What is exogenous here is the"
display as text "treatment, and that is what section 3 estimates."
display as text "{hline 78}"
