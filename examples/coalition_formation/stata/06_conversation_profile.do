*==============================================================================
* 06_conversation_profile.do — every conversation described on 1-4 scales
*
* What the experimenter asked for: each conversation carries the characteristics
* the text analysis extracted — tone, authenticity, sentiment, volume, clout,
* analytic thinking, and every topic found — and each of them gets an intensity
* from 1 (barely present) to 4 (strongly present). They coexist: a conversation
* has a value on all of them at once.
*
* Two units, because "the conversation" can mean either and both are useful:
*   group          the triad's whole conversation      -> data/profile_group.dta
*   directed pair  what i wrote to j                   -> data/profile_pair.dta
*
* HOW THE 1-4 IS BUILT — this is the choice to approve
*
*   Continuous characteristics (tone, authenticity, sentiment, volume, clout,
*   analytic): quartiles within the analysis sample. 1 is the bottom quarter of
*   these conversations, 4 the top quarter. The bands are therefore relative to
*   the study, which is what the underlying measures are too: they are
*   standardised within the sample, not against an external corpus.
*
*   Set `absolute' to 1 below to use fixed cut-offs on the 0-100 scales instead
*   (1: 0-25, 2: 25-50, 3: 50-75, 4: 75-100). Those do not move when the sample
*   changes, but they can leave a band empty.
*
*   Topics are not continuous: TopicGPT says present or absent for each unit.
*   The intensity of a topic in a triad's conversation is the share of its six
*   directed pairs that carry it: 1 up to a quarter of them, 4 above three
*   quarters. A topic that never appears gets 1, and the companion dummy
*   `*_any' keeps absence recoverable exactly.
*==============================================================================

version 19
clear all
set more off

* 0 = quartiles within the sample (default), 1 = fixed cut-offs
local absolute = 0

capture mkdir "tables"

*==============================================================================
* The 1-4 recode, in one place
*==============================================================================

capture program drop intensity4
program define intensity4
    version 19
    syntax varname(numeric), Generate(name) [ Cuts(numlist min=3 max=3 ascending) ///
                                              Label(string) ]

    * The sample is whatever the caller left in memory: every call below is
    * preceded by `keep if in_sample`, so the quartiles are the quartiles of
    * the analysis sample and not of the raw export.
    tempvar touse
    quietly generate byte `touse' = 1

    if "`cuts'" != "" {
        * Fixed bands: the same value always lands in the same level, whatever
        * else is in the dataset.
        local c1 : word 1 of `cuts'
        local c2 : word 2 of `cuts'
        local c3 : word 3 of `cuts'
        quietly generate byte `generate' = .
        quietly replace `generate' = 1 if `touse' & `varlist' <= `c1'
        quietly replace `generate' = 2 if `touse' & `varlist' >  `c1' & `varlist' <= `c2'
        quietly replace `generate' = 3 if `touse' & `varlist' >  `c2' & `varlist' <= `c3'
        quietly replace `generate' = 4 if `touse' & `varlist' >  `c3' & !missing(`varlist')
    }
    else {
        * Quartiles. xtile can return fewer than four groups when the variable
        * takes few distinct values; saying so in the log beats a scale that
        * silently has three levels.
        capture xtile `generate' = `varlist' if `touse', nq(4)
        if _rc {
            display as error "  `varlist': quartiles failed (rc=" _rc "), skipped"
            exit
        }
        quietly levelsof `generate', local(levels)
        local nlev : word count `levels'
        if `nlev' < 4 {
            display as text "  `varlist': only `nlev' distinct levels " ///
                            "(too few distinct values for quartiles)"
        }
    }

    label define intensity4_lbl 1 "1 barely" 2 "2 some" 3 "3 clear" 4 "4 strong", replace
    label values `generate' intensity4_lbl
    if "`label'" != "" label variable `generate' "`label'"
end

*==============================================================================
* 1. Topic intensity, computed on the directed pairs
*==============================================================================
* Built first because the group-level topic shares are an aggregate of these.

use "data/pairs.dta", clear
keep if in_sample

local has_topics = 0
capture confirm variable nlp_sent_topics
if !_rc {
    local has_topics = 1

    * The topic list is induced by TopicGPT, so it is not known in advance: the
    * dummies are built from what the data actually contains. No `clean' on
    * levelsof, so a name with a space stays one item.
    levelsof nlp_sent_topic_primary, local(primaries)
    local t = 0
    foreach name of local primaries {
        if "`name'" == "" | "`name'" == "None" continue
        local ++t
        generate byte topic`t'_any = strpos(nlp_sent_topics, "`name'") > 0
        label variable topic`t'_any "Topic present: `name'"
        local topicnames "`topicnames' `t'"
        local topiclabel`t' "`name'"
    }
    local n_topics = `t'
    display as text "Topics found: `n_topics'"
}
else {
    display as text "No topic columns: run the pipeline with --topics to get them."
    local n_topics = 0
}

*==============================================================================
* 2. The directed pair's profile
*==============================================================================

display _n as text "{hline 78}"
display as text "Directed pairs: 1-4 intensities"
display as text "{hline 78}"

if `absolute' {
    intensity4 nlp_sent_clout_100, generate(clout_lvl) ///
               cuts(25 50 75) label("Clout, 1-4")
    intensity4 nlp_sent_analytic_100, generate(analytic_lvl) ///
               cuts(25 50 75) label("Analytic, 1-4")
    intensity4 nlp_sent_authenticity_100, generate(authent_lvl) ///
               cuts(25 50 75) label("Authenticity, 1-4")
    intensity4 nlp_sent_tone_100, generate(tone_lvl) ///
               cuts(25 50 75) label("Tone, 1-4")
    * VADER runs from -1 to +1; the cut-offs are its own conventional ones.
    intensity4 nlp_sent_sentiment_compound_mean, generate(sentiment_lvl) ///
               cuts(-0.05 0.05 0.5) label("Sentiment, 1-4")
    * Words have no natural scale, so volume stays on quartiles either way.
    intensity4 nlp_sent_wc, generate(volume_lvl) label("Volume, 1-4")
}
else {
    intensity4 nlp_sent_clout_100, generate(clout_lvl) label("Clout, 1-4")
    intensity4 nlp_sent_analytic_100, generate(analytic_lvl) label("Analytic, 1-4")
    intensity4 nlp_sent_authenticity_100, generate(authent_lvl) label("Authenticity, 1-4")
    intensity4 nlp_sent_tone_100, generate(tone_lvl) label("Tone, 1-4")
    intensity4 nlp_sent_sentiment_compound_mean, generate(sentiment_lvl) ///
               label("Sentiment, 1-4")
    intensity4 nlp_sent_wc, generate(volume_lvl) label("Volume, 1-4")
}

* At the level of a single directed pair a topic is either there or not, so its
* intensity has only two values: 1 absent, 4 present. The graded version lives
* at group level, where there are six pairs to count.
forvalues t = 1/`n_topics' {
    generate byte topic`t'_lvl = cond(topic`t'_any == 1, 4, 1)
    label values topic`t'_lvl intensity4_lbl
    label variable topic`t'_lvl "Topic 1-4: `topiclabel`t''"
    local topiclvls "`topiclvls' topic`t'_lvl"
}

summarize *_lvl

local keepvars "group_uid triad treat focal_id_in_group partner_id_in_group"
local keepvars "`keepvars' nlp_sent_wc nlp_sent_n_messages persuasion_ij S_ij A_ji C_ij"
local keepvars "`keepvars' clout_lvl analytic_lvl authent_lvl tone_lvl sentiment_lvl volume_lvl"
forvalues t = 1/`n_topics' {
    local keepvars "`keepvars' topic`t'_any topic`t'_lvl"
}
keep `keepvars'
label data "Directed pairs, characteristics on 1-4 scales"
save "data/profile_pair.dta", replace
export delimited using "tables/conversation_profile_pairs.csv", replace
display as text "Saved data/profile_pair.dta"

*==============================================================================
* 3. The triad's profile
*==============================================================================
* The topic shares come from the pairs, the language measures from the group
* block: the group's Clout is computed on the triad's joined text, not averaged
* over its pairs, and averaging percentages of short messages is exactly what
* the pipeline avoids.

use "data/pairs.dta", clear
keep if in_sample
if `n_topics' > 0 {
    * Rebuild the dummies on the full pair sample, then average them per triad.
    local t = 0
    levelsof nlp_sent_topic_primary, local(primaries)
    foreach name of local primaries {
        if "`name'" == "" | "`name'" == "None" continue
        local ++t
        generate byte topic`t'_any = strpos(nlp_sent_topics, "`name'") > 0
    }
    collapse (mean) topic*_any, by(triad)
    rename (topic*_any) (topic*_share)
    tempfile shares
    save "`shares'"
}

use "data/triads.dta", clear
generate byte in_sample = (group_valid == 1) & (nlp_group_low_language_flag == 0) ///
                          & (nlp_group_wc > 0) & !missing(nlp_group_wc)
keep if in_sample

if `n_topics' > 0 {
    merge 1:1 triad using "`shares'", nogenerate
    forvalues t = 1/`n_topics' {
        quietly replace topic`t'_share = 0 if missing(topic`t'_share)
        label variable topic`t'_share "Share of the triad's pairs carrying: `topiclabel`t''"
        generate byte topic`t'_any = topic`t'_share > 0
        label variable topic`t'_any "Topic present in the triad: `topiclabel`t''"
        * Fixed bands on a share: they mean the same thing in every dataset,
        * and a topic that is in one pair out of six should not become "strong"
        * just because the others are rarer.
        intensity4 topic`t'_share, generate(topic`t'_lvl) cuts(0.25 0.50 0.75) ///
                   label("Topic 1-4: `topiclabel`t''")
    }
}

display _n as text "{hline 78}"
display as text "Triads: 1-4 intensities"
display as text "{hline 78}"

if `absolute' {
    intensity4 nlp_group_clout_100, generate(clout_lvl) ///
               cuts(25 50 75) label("Clout, 1-4")
    intensity4 nlp_group_analytic_100, generate(analytic_lvl) ///
               cuts(25 50 75) label("Analytic, 1-4")
    intensity4 nlp_group_authenticity_100, generate(authent_lvl) ///
               cuts(25 50 75) label("Authenticity, 1-4")
    intensity4 nlp_group_tone_100, generate(tone_lvl) ///
               cuts(25 50 75) label("Tone, 1-4")
    intensity4 nlp_group_sentiment_compound_mean, generate(sentiment_lvl) ///
               cuts(-0.05 0.05 0.5) label("Sentiment, 1-4")
    intensity4 nlp_group_wc, generate(volume_lvl) label("Volume, 1-4")
}
else {
    intensity4 nlp_group_clout_100, generate(clout_lvl) label("Clout, 1-4")
    intensity4 nlp_group_analytic_100, generate(analytic_lvl) label("Analytic, 1-4")
    intensity4 nlp_group_authenticity_100, generate(authent_lvl) label("Authenticity, 1-4")
    intensity4 nlp_group_tone_100, generate(tone_lvl) label("Tone, 1-4")
    intensity4 nlp_group_sentiment_compound_mean, generate(sentiment_lvl) ///
               label("Sentiment, 1-4")
    intensity4 nlp_group_wc, generate(volume_lvl) label("Volume, 1-4")
}

label data "Triads, characteristics on 1-4 scales"
save "data/profile_group.dta", replace
export delimited using "tables/conversation_profile_groups.csv", replace
display as text "Saved data/profile_group.dta"

*==============================================================================
* 4. What the profiles look like
*==============================================================================

display _n as text "The profile of each conversation, side by side:"
list triad treat clout_lvl analytic_lvl authent_lvl tone_lvl sentiment_lvl ///
     volume_lvl, noobs abbreviate(14) separator(0)

display _n as text "Intensity by treatment (mean of the 1-4 levels):"
table (treat) (), statistic(mean clout_lvl analytic_lvl authent_lvl tone_lvl ///
                                 sentiment_lvl volume_lvl) ///
                  statistic(frequency) nformat(%5.2f)

if `n_topics' > 0 {
    display _n as text "Topic intensity by treatment:"
    table (treat) (), statistic(mean `topiclvls') statistic(frequency) nformat(%5.2f)
}

* The 1-4 scales are an ordinal recode of continuous measures: they are made
* for reading tables and for ordered models, not for replacing the continuous
* variables in the main regressions, where the recode would throw away the
* variation inside each band.
display _n as text "{hline 78}"
display as text "The 1-4 levels are for description and ordered models."
display as text "The main regressions use the continuous measures (file 04)."
display as text "{hline 78}"
