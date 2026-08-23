*==============================================================================
* 05_validation_and_topics.do — the optional stages
*
* Both sections run only if the corresponding stage was run in the pipeline:
*   llm_*  columns come from `--llm`      (the validation rubric)
*   nlp_*_topics from `--topics`          (TopicGPT)
*
* If the columns are not there the section is skipped with a message, so this
* file can be run after any pipeline run without editing it.
*==============================================================================

version 16
clear all
set more off

*==============================================================================
* 1. Convergent validity: dictionaries against a language model
*==============================================================================
* The two roads are methodologically independent — one counts function words,
* the other reads the text — so their correlation is evidence about the
* measures, not a tautology. A weak correlation is a finding to report, not a
* fault to fix.

use "data/participants.dta", clear
keep if in_sample

capture confirm variable nlp_group_llm_clout
if _rc {
    display as text _n "No rubric columns: run the pipeline with --llm first."
}
else {
    display _n as text "{hline 78}"
    display as text "LIWC-style measures against the rubric's ratings"
    display as text "{hline 78}"

    * One row per triad: the rubric was run at group level, so its values repeat
    * on the three members and would otherwise be counted three times.
    preserve
        collapse (first) treat nlp_group_analytic_100 nlp_group_clout_100 ///
                 nlp_group_authenticity_100 nlp_group_tone_100 ///
                 nlp_group_llm_analytic nlp_group_llm_clout ///
                 nlp_group_llm_authenticity nlp_group_llm_tone ///
                 nlp_group_llm_analytic_sd nlp_group_llm_clout_sd, by(triad)

        correlate nlp_group_analytic_100 nlp_group_llm_analytic
        correlate nlp_group_clout_100 nlp_group_llm_clout
        correlate nlp_group_authenticity_100 nlp_group_llm_authenticity
        correlate nlp_group_tone_100 nlp_group_llm_tone

        display _n as text "All four at once:"
        correlate nlp_group_analytic_100 nlp_group_clout_100 ///
                  nlp_group_authenticity_100 nlp_group_tone_100 ///
                  nlp_group_llm_analytic nlp_group_llm_clout ///
                  nlp_group_llm_authenticity nlp_group_llm_tone

        * With --llm-replicates 2 or more, the _sd columns hold the spread
        * between independent ratings of the same text: that is the rubric's
        * own measurement error, and it bounds how high the correlation above
        * can possibly go.
        capture confirm variable nlp_group_llm_analytic_sd
        if !_rc {
            display _n as text "Dispersion between replicate ratings:"
            summarize nlp_group_llm_analytic_sd nlp_group_llm_clout_sd
        }
    restore

    * The rubric's flags are a second reading of the same conversations: they
    * should line up with the behaviour recorded by the experiment.
    capture confirm variable nlp_group_llm_contains_support_commitment
    if !_rc {
        display _n as text "Rubric's support-commitment flag against the signals:"
        tabulate nlp_group_llm_contains_support_commitment, missing
    }
}

*==============================================================================
* 2. Topics
*==============================================================================
* nlp_sent_topics holds the topics of that directed pair, separated by "|".
* Turning them into indicator variables is what makes them usable in a
* regression; the loop below builds one dummy per topic found in the data.

use "data/pairs.dta", clear
keep if in_sample

capture confirm variable nlp_sent_topics
if _rc {
    display as text _n "No topic columns: run the pipeline with --topics first."
}
else {
    display _n as text "{hline 78}"
    display as text "Topics assigned to directed pairs"
    display as text "{hline 78}"

    display as text "Primary topic:"
    tabulate nlp_sent_topic_primary treat, column

    display _n as text "Topics per pair:"
    tabulate nlp_sent_n_topics

    * The list of topics is not known in advance — TopicGPT induces it — so the
    * dummies are built from what is actually in the column.
    * Without `clean` the levels come back quoted, which is what keeps a topic
    * name with a space in it ("Coalition Proposal") as one item.
    levelsof nlp_sent_topic_primary, local(topics)
    local k = 0
    foreach t of local topics {
        if "`t'" == "" | "`t'" == "None" continue
        local ++k
        generate byte topic`k' = strpos(nlp_sent_topics, "`t'") > 0
        label variable topic`k' "Topic: `t'"
        local topicvars "`topicvars' topic`k'"
    }

    if "`topicvars'" != "" {
        display _n as text "How often each topic appears, by treatment:"
        tabstat `topicvars', by(treat) statistics(mean n) format(%6.3f)

        display _n as text "Persuasion by topic (associations, one at a time):"
        foreach v of local topicvars {
            display _n as text "`: variable label `v''"
            regress persuasion_ij `v' nlp_sent_wc, vce(cluster triad)
        }
    }
}
