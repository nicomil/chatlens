*==============================================================================
* 07_nonparametric.do — the treatment comparisons without a functional form
*
* These are the primary tests for the treatment hypotheses: the counts per
* treatment are moderate, the variables are bounded (0/1, 0-1, 0-100) and none
* is plausibly normal.
*
* THE INDEPENDENCE RULE. Randomisation is at the level of the triad, so the
* triad is the independent unit. Every test on a participant-level or
* pair-level variable is therefore run on the triad-level MEAN of that
* variable: six directed pairs from one conversation are not six independent
* observations, and a rank test has no way of knowing that.
*
* Comparisons, from the design (a 2x2 with one cell not run):
*   public vs private          the effect of communication being observable
*   private_no_dwl vs private  the effect of the payoff rule
*   public vs private_no_dwl   differs on both dimensions: descriptive only
*==============================================================================

version 19
clear all
set more off

*==============================================================================
* Holm correction, for a family of p-values collected along the way
*==============================================================================

capture program drop holm
program define holm
    version 19
    syntax anything, [Names(string asis)]

    local k : word count `anything'
    display _n as text "Holm correction over `k' tests:"
    display as text "{hline 64}"
    display as text %-36s "test" %12s "p" %12s "p (Holm)"
    display as text "{hline 64}"

    * Column 1 is the p-value, column 2 remembers which test it came from, so
    * the report can be read back in the order the tests were run.
    tempname P
    matrix `P' = J(`k', 2, .)
    forvalues i = 1/`k' {
        local p`i' : word `i' of `anything'
        matrix `P'[`i', 1] = `p`i''
        matrix `P'[`i', 2] = `i'
    }
    mata: st_matrix("`P'", sort(st_matrix("`P'"), 1))

    local running = 0
    forvalues i = 1/`k' {
        local p    = `P'[`i', 1]
        local orig = `P'[`i', 2]
        local adj  = min(1, (`k' - `i' + 1) * `p')
        * Holm is monotone: an adjusted p can never fall below the previous one.
        local adj  = max(`adj', `running')
        local running = `adj'
        local nm : word `orig' of `names'
        if `"`nm'"' == "" local nm "test `orig'"
        display as result %-36s `"`nm'"' %12.4f `p' %12.4f `adj'
    }
    display as text "{hline 64}"
end

*==============================================================================
* 1. One row per triad, carrying everything the tests need
*==============================================================================

* Pair-level variables, averaged within the triad.
use "data/pairs.dta", clear
keep if in_sample
collapse (mean) persuasion_rate = persuasion_ij ///
                signal_rate     = S_ij ///
                support_rate    = A_ji ///
                consistency_ij  = C_ij ///
                sent_clout      = nlp_sent_clout_100 ///
                sent_analytic   = nlp_sent_analytic_100 ///
                sent_authent    = nlp_sent_authenticity_100 ///
                sent_tone       = nlp_sent_tone_100 ///
                sent_sentiment  = nlp_sent_sentiment_compound_mean ///
                sent_wc         = nlp_sent_wc, by(triad)
tempfile pairmeans
save "`pairmeans'"

* Participant-level variables, averaged within the triad.
use "data/participants.dta", clear
keep if in_sample
collapse (mean) mean_cc = cc_i ///
                deception_rate = strategic_deception ///
                persuaded_partners = n_partners_persuaded, by(triad)
tempfile partmeans
save "`partmeans'"

use "data/triads.dta", clear
generate efficiency = group_total_payoff / 6
merge 1:1 triad using "`pairmeans'", nogenerate keep(master match)
merge 1:1 triad using "`partmeans'", nogenerate keep(master match)
keep if group_valid == 1

display as text "Triads entering the tests: " _N
tabulate treat

*==============================================================================
* 2. H1 — coordination
*==============================================================================

display _n as text "{hline 78}"
display as text "H1  Coordination by treatment"
display as text "{hline 78}"

tabulate treat group_coordinate, row exact

* Pairwise against baseline. Fisher's exact is reported by tabulate; the p-value
* it leaves behind is r(p_exact).
tabulate treat group_coordinate if inlist(treat, 1, 2), exact
local p_h1_pub = r(p_exact)
tabulate treat group_coordinate if inlist(treat, 1, 3), exact
local p_h1_dwl = r(p_exact)

holm `p_h1_pub' `p_h1_dwl', names("public vs private" "no-DWL vs private")

*==============================================================================
* 3. H2 — efficiency
*==============================================================================

display _n as text "{hline 78}"
display as text "H2  Efficiency by treatment"
display as text "{hline 78}"

kwallis efficiency, by(treat)

ranksum efficiency if inlist(treat, 1, 2), by(treat)
local p_h2_pub = 2 * normal(-abs(r(z)))
ranksum efficiency if inlist(treat, 1, 3), by(treat)
local p_h2_dwl = 2 * normal(-abs(r(z)))

holm `p_h2_pub' `p_h2_dwl', names("public vs private" "no-DWL vs private")

*==============================================================================
* 4. H3 — persuasion, and its two halves
*==============================================================================

display _n as text "{hline 78}"
display as text "H3  Persuasion, signalling and support (triad means)"
display as text "{hline 78}"

foreach y in persuasion_rate signal_rate support_rate {
    display _n as text "--- `y' ---"
    kwallis `y', by(treat)
    ranksum `y' if inlist(treat, 1, 2), by(treat)
    local p_`y'_pub = 2 * normal(-abs(r(z)))
    ranksum `y' if inlist(treat, 1, 3), by(treat)
    local p_`y'_dwl = 2 * normal(-abs(r(z)))
}

holm `p_persuasion_rate_pub' `p_persuasion_rate_dwl' ///
     `p_signal_rate_pub' `p_signal_rate_dwl' ///
     `p_support_rate_pub' `p_support_rate_dwl', ///
     names("persuasion: public" "persuasion: no-DWL" ///
           "signal: public" "signal: no-DWL" ///
           "support: public" "support: no-DWL")

*==============================================================================
* 5. H4 — consistency and deception
*==============================================================================

display _n as text "{hline 78}"
display as text "H4  Consistency and deception (triad means)"
display as text "{hline 78}"

kwallis mean_cc, by(treat)
ranksum mean_cc if inlist(treat, 1, 2), by(treat)
local p_h4_cc_pub = 2 * normal(-abs(r(z)))
ranksum mean_cc if inlist(treat, 1, 3), by(treat)
local p_h4_cc_dwl = 2 * normal(-abs(r(z)))

kwallis deception_rate, by(treat)
ranksum deception_rate if inlist(treat, 1, 2), by(treat)
local p_h4_dec_pub = 2 * normal(-abs(r(z)))
ranksum deception_rate if inlist(treat, 1, 3), by(treat)
local p_h4_dec_dwl = 2 * normal(-abs(r(z)))

holm `p_h4_cc_pub' `p_h4_cc_dwl' `p_h4_dec_pub' `p_h4_dec_dwl', ///
     names("consistency: public" "consistency: no-DWL" ///
           "deception: public" "deception: no-DWL")

*==============================================================================
* 6. H5 — language
*==============================================================================
* This is the family with the most tests, so the correction matters most here.

display _n as text "{hline 78}"
display as text "H5  Language by treatment (triad means of what was sent)"
display as text "{hline 78}"

local langvars sent_clout sent_analytic sent_authent sent_tone sent_sentiment sent_wc
local plist ""
local pnames ""
foreach y of local langvars {
    display _n as text "--- `y' ---"
    kwallis `y', by(treat)
    ranksum `y' if inlist(treat, 1, 2), by(treat)
    local p1 = 2 * normal(-abs(r(z)))
    ranksum `y' if inlist(treat, 1, 3), by(treat)
    local p2 = 2 * normal(-abs(r(z)))
    local plist  "`plist' `p1' `p2'"
    local pnames `"`pnames' "`y': public" "`y': no-DWL""'
}
holm `plist', names(`"`pnames'"')

*==============================================================================
* 7. H6 — language and persuasion, without a functional form
*==============================================================================
* Back to the directed pair: the association is within-sample, not between
* treatments, so the triad-mean rule does not apply — but the ranks still come
* from non-independent rows, which is why this is a description and the
* clustered regressions in 04 are the estimate.

use "data/pairs.dta", clear
keep if in_sample

display _n as text "{hline 78}"
display as text "H6  Sender's language and persuasion (directed pairs)"
display as text "{hline 78}"

spearman persuasion_ij nlp_sent_clout_100 nlp_sent_analytic_100 ///
         nlp_sent_authenticity_100 nlp_sent_tone_100 ///
         nlp_sent_sentiment_compound_mean nlp_sent_wc, stats(rho p)

foreach y in nlp_sent_clout_100 nlp_sent_analytic_100 ///
             nlp_sent_authenticity_100 nlp_sent_tone_100 nlp_sent_wc {
    display _n as text "--- `y', persuaded vs not ---"
    ranksum `y', by(persuasion_ij)
}
