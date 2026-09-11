# Commands

Everything `chatlens` can be asked to do from a terminal. The dashboard covers
the same ground with buttons; this is the list for anyone who would rather
type, or script it.

| Command | What it does | API key |
|---|---|---|
| `chatlens dashboard` | opens the library of experiments in the browser | — |
| `chatlens all` | merge + automatic measures, a few seconds | **no** |
| `chatlens merge` / `chatlens analyze` | the two steps separately | no |
| `chatlens keys` | configures the API keys, guided | — |
| `chatlens analyze --llm --llm-replicates 2` | measures + validation rubric | yes |
| `chatlens analyze --topics` | measures + topics with TopicGPT | yes |
| `chatlens subtopics` | subdivides the topics a run already found | yes |
| `chatlens all --llm --topics` | everything: rubric and topics included | yes |
| `chatlens experiments` | lists the experiments from the terminal | — |
| `chatlens report` | regenerates the readable summary | — |
| `chatlens tables` | the two complete datasets for Stata and R — every measure, relations and emotions included — and a codebook | — |
| `chatlens runs` | lists the archived runs | — |
| `chatlens runs --prune 2` | keeps the last 2 and deletes the others | — |
| `chatlens status` | what is in input, in output and among the keys | — |
| `chatlens demo` | writes a synthetic study and analyses it | — |
| `chatlens export <name>` | packs a study into one file, results included | — |
| `chatlens import <file>` | opens one somebody sent | — |
| `chatlens install-model` | downloads the spaCy language model (for the relations) | — |
| `chatlens install-topicgpt` | installs TopicGPT (only needed for the topics) | — |
| `chatlens install-relatio` | installs RELATIO (optional, for the narratives) | — |

**`all` is both *steps*, not everything.** It means merge plus analysis, as
opposed to `merge` and `analyze` taken singly: it runs only the automatic
measures, needs no key at all and takes a few seconds. Adding `--llm` and
`--topics` brings in the validation rubric and the topics, which need a key and
take far longer. You start from `chatlens all`; you add the rest once the keys
are there.
