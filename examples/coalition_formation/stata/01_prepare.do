*==============================================================================
* 01_prepare.do — from the pipeline's CSVs to two Stata datasets
*
* Reads what `python run.py all` leaves in output/datasets/, labels it, applies
* the sample filters and saves two .dta files:
*
*   pairs.dta         one row per directed pair i->j, six per triad
*   participants.dta  one row per participant
*
* Run it from this folder:  do 01_prepare.do
* It is also called by 00_master.do, which runs everything in order.
*==============================================================================

version 19
clear all
set more off

*--- Where things are ---------------------------------------------------------
* Paths are relative to this folder, so the project can be moved or copied
* without editing anything.

local project ".."
local datasets "`project'/output/datasets"
local out "data"

capture mkdir "`out'"

* The pipeline names its files after the oTree export, so the stem changes with
* every export. It is read from the folder rather than typed, otherwise the
* do-file would need editing after each download.
local files : dir "`datasets'" files "*_chat_by_partner_nlp.csv"
local n : word count `files'
if `n' == 0 {
    display as error "No *_chat_by_partner_nlp.csv in `datasets'."
    display as error "Run the pipeline first:  python run.py all"
    exit 601
}
if `n' > 1 {
    display as error "More than one dataset in `datasets': `files'"
    display as error "Keep only the export to analyse."
    exit 602
}
local pairsfile : word 1 of `files'
local stem = subinstr("`pairsfile'", "_chat_by_partner_nlp.csv", "", .)
display as text "Dataset: `stem'"

*==============================================================================
* 1. Directed pairs
*==============================================================================

* bindquote(strict) and maxquotedrows are what let the transcript columns
* through: they hold the chat text, so they contain commas and line breaks
* inside quotes.
import delimited using "`datasets'/`stem'_chat_by_partner_nlp.csv", ///
    varnames(1) case(preserve) encoding("UTF-8") ///
    bindquote(strict) maxquotedrows(unlimited) stringcols(_all) clear

* Everything arrives as a string so that no column is guessed wrongly; the ones
* that are numeric are converted explicitly below.
quietly destring, replace ignore(" ")

* The triad identifier is a string ("s1-db7"): the numeric version is what
* cluster(), absorb() and xtset need.
encode group_uid, generate(triad)
label variable triad "Triad (numeric id of group_uid)"

* Treatment is coded by hand rather than with encode: encode would order the
* levels alphabetically, putting private_no_dwl second, and every table would
* then read in an order nobody chose.
generate byte treat = .
replace treat = 1 if treatment == "private"
replace treat = 2 if treatment == "public"
replace treat = 3 if treatment == "private_no_dwl"
label define treat_lbl 1 "Baseline (private)" 2 "Public communication" ///
                       3 "Slacker (no DWL)", replace
label values treat treat_lbl
label variable treat "Treatment"
assert !missing(treat)

capture confirm variable dyad_key
if !_rc {
    encode dyad_key, generate(dyad)
    label variable dyad "Undirected pair within triad"
}

*--- Labels: the names are self-explanatory, the definitions are not -----------
label variable S_ij          "i signals support to j"
label variable A_ji          "j actually supports i"
label variable persuasion_ij "i persuaded j (S_ij = 1 and A_ji = 1)"
label variable C_ij          "i's final signal to j is consistent with i's choice"
label variable group_valid   "Triad complete, not interrupted, no timeout"

* Set when the recorded outcome cannot be reconstructed from the recorded
* decisions: see text_analysis/README.md. Rare, and already inside the triads
* that group_valid excludes, but it is the difference between an anomaly and a
* mystery.
capture confirm variable payoff_decision_mismatch
if !_rc {
    label variable payoff_decision_mismatch ///
        "Recorded outcome not reconstructable from the stored decisions"
    quietly count if payoff_decision_mismatch == 1
    if r(N) > 0 {
        display as text "Triads with an outcome/decision contradiction: " r(N)
    }
}

foreach block in sent recv dyad {
    label variable nlp_`block'_wc            "Words (`block')"
    label variable nlp_`block'_analytic_100  "Analytic, 0-100 (`block')"
    label variable nlp_`block'_clout_100     "Clout, 0-100 (`block')"
    label variable nlp_`block'_authenticity_100 "Authenticity, 0-100 (`block')"
    label variable nlp_`block'_tone_100      "Tone, 0-100 (`block')"
    label variable nlp_`block'_sentiment_compound_mean "Sentiment, VADER (`block')"
    label variable nlp_`block'_low_language_flag "Text is not language (`block')"
}

*--- Display order: controls for a position effect -----------------------------
* The experiment randomises, per player and persistently, which partner appears
* in the left column and the order of the three options on the Decision page.
* Neither changes the topology or the payoffs — the left partner in the payoff
* rule is still the left partner — but both are what a position effect would
* ride on, so they belong here as controls.
*
* Exports produced before the randomisation was added have the columns empty,
* which is why `shown_left` stays missing rather than becoming 0: no
* information must not be read as "was shown on the right".

capture confirm variable partner_shown_left
if !_rc {
    label variable partner_shown_left "Partner appeared in the focal's left column"
    label variable focal_decision_position "Screen position of the chosen option (1-3)"
    quietly count if !missing(partner_shown_left)
    display as text "Display order recorded for " r(N) " directed pairs"
}

*--- Sample flags -------------------------------------------------------------
* They are flags, not deletions: the excluded rows stay available for the
* robustness checks, which is the whole point of not dropping them here.

generate byte in_sample = (group_valid == 1) & ///
                          (nlp_sent_low_language_flag == 0) & ///
                          (nlp_sent_wc > 0) & !missing(nlp_sent_wc)
label variable in_sample "Main sample: valid triad, real language, non-empty text"

generate byte has_text = (nlp_sent_wc > 0) & !missing(nlp_sent_wc)
label variable has_text "The sender wrote something to this partner"

label data "Directed pairs i->j, with language measures"
save "`out'/pairs.dta", replace
display as text "Saved `out'/pairs.dta  (" _N " directed pairs)"

*==============================================================================
* 2. Participants
*==============================================================================

import delimited using "`datasets'/`stem'_chat_aggregated_nlp.csv", ///
    varnames(1) case(preserve) encoding("UTF-8") ///
    bindquote(strict) maxquotedrows(unlimited) stringcols(_all) clear

quietly destring, replace ignore(" ")

encode group_uid, generate(triad)
label variable triad "Triad (numeric id of group_uid)"
* Defined again because `clear` above dropped the value labels along with the
* data.
label define treat_lbl 1 "Baseline (private)" 2 "Public communication" ///
                       3 "Slacker (no DWL)", replace
generate byte treat = .
replace treat = 1 if treatment == "private"
replace treat = 2 if treatment == "public"
replace treat = 3 if treatment == "private_no_dwl"
label values treat treat_lbl
label variable treat "Treatment"
assert !missing(treat)

label variable cc_i                "Choice-signal consistency, mean over the two partners"
label variable strategic_deception "Promised support to both, then supported no one"
label variable group_coordinate    "The triad reached a coalition"
label variable group_total_payoff  "Group payoff, theoretical (Efficiency)"
label variable group_valid         "Triad complete, not interrupted, no timeout"

foreach block in sent group {
    label variable nlp_`block'_wc               "Words (`block')"
    label variable nlp_`block'_analytic_100     "Analytic, 0-100 (`block')"
    label variable nlp_`block'_clout_100        "Clout, 0-100 (`block')"
    label variable nlp_`block'_authenticity_100 "Authenticity, 0-100 (`block')"
    label variable nlp_`block'_tone_100         "Tone, 0-100 (`block')"
    label variable nlp_`block'_sentiment_compound_mean "Sentiment, VADER (`block')"
    label variable nlp_`block'_low_language_flag "Text is not language (`block')"
}

capture confirm variable left_partner_shown_left
if !_rc {
    label variable left_partner_shown_left ///
        "The topological left partner appeared in the left column"
    label variable focal_decision_position ///
        "Screen position of the chosen option (1-3)"
}

generate byte in_sample = (group_valid == 1) & ///
                          (nlp_group_low_language_flag == 0) & ///
                          (nlp_sent_wc > 0) & !missing(nlp_sent_wc)
label variable in_sample "Main sample: valid triad, real language, non-empty text"

label data "Participants, with language measures"
save "`out'/participants.dta", replace
display as text "Saved `out'/participants.dta  (" _N " participants)"

*==============================================================================
* 3. Triads
*==============================================================================
* The group variables repeat on every member's row. Collapsing to one row per
* triad is what keeps a group payoff of 6 from being counted as 18.

use "`out'/participants.dta", clear
collapse (first) treat group_valid group_coordinate group_total_payoff ///
         group_outcome nlp_group_* (mean) mean_cc_i = cc_i ///
         (max) any_deception = strategic_deception, by(triad)

label variable mean_cc_i     "Mean consistency in the triad"
label variable any_deception "At least one member deceived strategically"
label data "Triads"
save "`out'/triads.dta", replace
display as text "Saved `out'/triads.dta  (" _N " triads)"
