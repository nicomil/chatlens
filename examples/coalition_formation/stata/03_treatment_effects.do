*==============================================================================
* 03_treatment_effects.do — does the treatment change behaviour?
*
* The treatment varies between triads, so every standard error here is
* clustered on the triad: the three members of a triad are not three
* independent observations, and the six directed pairs are even less so.
*
* Baseline (private) is the reference category throughout.
*==============================================================================

version 19
clear all
set more off

estimates clear

*==============================================================================
* 1. Coordination and efficiency — the triad is the unit
*==============================================================================

use "data/triads.dta", clear
generate efficiency = group_total_payoff / 6

* One triad is one observation, so there is nothing to cluster: robust standard
* errors are the honest choice here.
regress group_coordinate i.treat, robust
estimates store coord

regress efficiency i.treat, robust
estimates store eff

* With few triads per treatment the normal approximation is optimistic. The
* exact test does not depend on it.
display _n as text "Coordination by treatment, exact test:"
tabulate treat group_coordinate, exact row

*==============================================================================
* 2. Persuasion — the directed pair is the unit
*==============================================================================

use "data/pairs.dta", clear
keep if in_sample

* The linear probability model is the main specification: the coefficients are
* differences in probability, and clustering is straightforward. The logit
* below is the robustness check, not the other way round.
regress persuasion_ij i.treat, vce(cluster triad)
estimates store pers_lpm

logit persuasion_ij i.treat, vce(cluster triad)
estimates store pers_logit
margins, dydx(treat)

* Whether i signals support at all, and whether j supports i, separately: a
* treatment can move persuasion by moving either half.
regress S_ij i.treat, vce(cluster triad)
estimates store signal

regress A_ji i.treat, vce(cluster triad)
estimates store support

*==============================================================================
* 3. Consistency and deception — the participant is the unit
*==============================================================================

use "data/participants.dta", clear
keep if in_sample

regress cc_i i.treat, vce(cluster triad)
estimates store consist

regress strategic_deception i.treat, vce(cluster triad)
estimates store deceive

*==============================================================================
* 4. Language — does the treatment change how people write?
*==============================================================================
* Public communication makes the message visible to the third player, so this
* is where a change in Clout or in tone would be expected.

* Stored under short names because Stata caps an estimates name at 32
* characters, and nlp_sent_sentiment_compound_mean alone is longer than that.
local k = 0
foreach y in nlp_sent_analytic_100 nlp_sent_clout_100 ///
             nlp_sent_authenticity_100 nlp_sent_tone_100 ///
             nlp_sent_sentiment_compound_mean nlp_sent_wc {
    local ++k
    display _n as text "{hline 78}"
    display as text "`y'"
    display as text "{hline 78}"
    regress `y' i.treat, vce(cluster triad)
    estimates store lang`k'
    local langnames "`langnames' lang`k'"
}

*==============================================================================
* 5. Tables
*==============================================================================
* etable is part of Stata, so no user-written package is needed. Change the
* export line to .docx, .tex or .html and the same table lands in the paper.

etable, estimates(coord eff pers_lpm signal support consist deceive) ///
        column(estimates) showstars showstarsnote ///
        stars(0.10 "*" 0.05 "**" 0.01 "***") ///
        cstat(_r_b, nformat(%7.3f)) cstat(_r_se, nformat(%7.3f)) ///
        title("Treatment effects on behaviour")
collect export "tables/treatment_effects.html", replace

etable, estimates(`langnames') column(estimates) showstars showstarsnote ///
        stars(0.10 "*" 0.05 "**" 0.01 "***") ///
        cstat(_r_b, nformat(%7.3f)) cstat(_r_se, nformat(%7.3f)) ///
        title("Treatment effects on language")
collect export "tables/treatment_language.html", replace
