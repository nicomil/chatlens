*==============================================================================
* 00_master.do — runs the whole analysis, in order
*
*   1. open Stata
*   2. change directory to this folder:
*        cd "<...>/text_analysis/stata"
*   3. do 00_master.do
*
* Everything it needs is what `python run.py all` left in output/datasets/.
* The results go to the screen and to logs/analysis.log (plain text), so a run
* can be sent to someone or diffed against the previous one.
*
* The files can also be run one at a time, in this order: 01 prepares the data,
* the others only read what 01 saved.
*==============================================================================

version 16
clear all
set more off
set linesize 100

capture mkdir "logs"
capture mkdir "data"

capture log close _all
log using "logs/analysis.log", replace text

display as text "Analysis run on $S_DATE at $S_TIME"

do 01_prepare.do
do 02_descriptives.do
do 03_treatment_effects.do
do 04_language_and_persuasion.do
do 05_validation_and_topics.do

display _n as text "{hline 78}"
display as text "Done. Full log in logs/analysis.log"
display as text "{hline 78}"

log close
