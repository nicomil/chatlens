# Changelog

Notable changes to chatlens. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **A technical name under every finding's question**, and a glossary in the
  register itself. Every title in the dashboard has always been a
  plain-English question — "Which words go with X?", never "run a
  bag-of-words model" — which is right for a reader who does not know what to
  call the thing they want, and left one who already does with nowhere to
  search: the phrase "bag of words" appeared in no title anywhere in the
  project, nor did "RELATIO" or "NRC". `ui.finding()` takes an optional
  `method=` now, printed once under the question, and the register carries a
  standing "Looking for a method by name" disclosure that also points rubric
  and topics — which have no page of their own yet — at the run's report
  instead of leaving them unmentioned.
- **A link to the illustrated guide from inside the running app.** It existed
  only as a file (`GUIDE.md`, published at
  `nicomil.github.io/chatlens/guide/`) that a reader had to already know to
  look for; the masthead now carries a link to it, next to the theme toggle.
- **`[sample] sessions`: the experimenter names the sessions that are the
  study.** Everything else in the export — pilots, internal tests, sessions
  launched without the recruitment parameter — is left out and counted under its
  own reason. It replaces a rule that only happened to be right: the missing
  Prolific label coincided with the test sessions on the coalition collection,
  and on that collection the declared list gives a merge identical byte for byte
  to the one before it. A session in the list that the export does not contain
  stops the merge, since it is either a typo or the wrong export.
- **Every block of measures as regressors, for the logit and for a LASSO.** The
  text analysis in these papers is exploratory: it supplies covariates, and the
  experimenter chooses, standardises and penalises them in Stata. So each
  study's `stata/` folder now carries two files. `goodshape` is the 111
  experimental columns followed by all the measures as raw values — the
  standardised copies left out — together with the relations, the NRC emotions,
  one indicator per topic, and a 1-4 ordinal version of every category share
  (1 absent, then the thirds of the rows where it occurs, with the cut points
  in the codebook). `complete` adds the bag of words: unigrams and bigrams as
  raw counts of what the focal participant sent, one column per term in at least
  ten documents of the study (`--bow-min-documents`), bigrams never spanning two
  messages. About 1 250 columns on one study, which opens in every edition of
  Stata.

- **A sample selector in the dashboard**, for an experiment that declares more
  than one study. It sits in the masthead because it applies to every findings
  page at once, and each page then reads that study's own tables — the same
  figures, the same terms, the same verdicts, computed on that sample. On the
  collection this was built for the participation grid goes from 531 groups
  pooled to 355 and 356, which is the number every interval in either paper
  rests on. The chosen sample is part of the key each page caches under, so
  moving between the two does not serve one study's model under the other's
  name, and a study whose tables have not been built yet is shown with a line
  saying what is on screen is still the pooled sample.
- **`core/tokens.py`: one definition of a word.** Two token sets, named and
  documented: `words`, which is letters and internal apostrophes, for every
  dictionary measure, and `terms`, which admits digits, for the bag of words.
  Four modules had four regular expressions before, so the same message could
  be 40 words on one page and 42 on another.
- **A count of what is identifying in the messages themselves.** Pseudonymising
  rewrites the identifier columns and the module has always said that this does
  not make a dataset anonymous, because people write their addresses and their
  phone numbers into a chat window. The bundle manifest now carries a count of
  what a pattern can find — addresses, links, long numbers, handles — so an
  ethics submission has a figure instead of "some risk", with the stated limit
  that no pattern finds a name.
- **A notice when the corpus is not in English.** Every dictionary here is an
  English word list, which was said in one comment in one module. The share of
  function words is the check, and below a quarter the pages say the numbers
  below are not measuring what their labels claim.
- **`topics-legacy`, an extra for the environment TopicGPT wants.** Its
  requirements pin `openai<2`, `anthropic<1` and `numpy<2`, so installing it
  into a shared interpreter pulls all three back; the pin is now a declared
  state with a documented alternative, which is a second virtual environment for
  the topic stage alone.
- **A weekly CI job that installs RELATIO and extracts with it.** The suites
  mock the package away or skip themselves, so the path that needs 1.6 GB of
  torch and transformers — and the one a dependency clash breaks first — had
  never run. `tests/relatio_smoke.py` is the same check by hand.
- **`static/VENDORED.md`**, recording the one file in the static folder that is
  not ours, with its version and its SHA-256, and a test that checks the hash.
  The filename carries no version, so the only way to know which htmx was in a
  release was to read the minified source.

- **`[[studies]]`, and `chatlens studies`: two papers out of one collection.**
  A 2x2 with one cell not run supports two comparisons — baseline against each
  of the other arms — and those are two samples, so two replication packages.
  The reason it is not cosmetic is that the standardised language indices are
  computed over the sample by design: on the collection this was built for, the
  same baseline participant has a Clout of 59.8 in one study and 68.9 in the
  other, off an identical raw score. So each study gets the measures stage
  re-applied to its own rows — which is what recomputes those columns — with the
  rubric ratings and the topics copied across from the pooled run rather than
  paid for again. The datasets land in `output/studies/<slug>/`, deliberately
  not beside the pooled ones: `01_prepare.do` finds its input by globbing
  `output/datasets/` and aborts when the glob matches more than one file. A
  `study.json` records what the sample was, because every interval in the paper
  follows from that count.
- **The experiment's own Stata layout**, for the collection that has one. The
  111 columns the experimenter's do-files are written against, under his names
  rather than the ones `chatlens tables` derives mechanically, with the
  resolved-choice and dyadic-chat columns computed the way he computes them and
  our measures appended. Verified column by column against his file: 110 of the
  111 identical on every row of both studies, the one difference being the
  transcript, which stays in the form every page and every measure here reads. A
  `.dta` is written beside the CSV when pandas is installed, with the variable
  labels and the transcript as `strL`; the CSV is what the do-files read, and a
  `.dta` that cannot be written is not an error.
- **`first_sender_id_in_group`**, among the measures of every unit: who opened
  the conversation. At the pair level it is the first mover, a choice that
  nothing else in the output records — the counts say how much each person
  wrote, never who began.

- **`chatlens tables`: every measure in one table per unit, for Stata and R.**
  The two datasets again, with the relations and the NRC emotions added — the
  two findings computed by their pages that never reached a file — every
  column renamed to something Stata and R both accept, a `.dta` beside each
  CSV when pandas is installed (the new `stata` extra), and a codebook. The
  findings summary offers the same tables as a download. Besides one 0/1
  column per frequent relation, `rel_sent_all` carries every relation a row
  sent as text: dimensions built by keyword ("agree", "leave") found nothing
  in the frequent ones alone, where the rare verbs never reach 25 units.
- **Six pages of analysis.** *Participation* shows the whole sender × receiver
  grid, including the directions nobody used, which every other page is blind
  to because it can only measure text that exists. *Words* fits a penalised
  regression over unigrams and bigrams, with the penalty as a control you move
  and watch. *Narratives* reads the text as relations — who does what to whom —
  through the RELATIO package, and tests which of them matter with a
  Benjamini-Hochberg correction across the whole family. *Emotions* scores the
  NRC categories and says, beside them, how much of the corpus could be
  measured at all. *Comparison* puts every representation against the same
  outcome on the same folds, with length always among them. And second-level
  subtopics, with the diagnostic that says why "None" came back.
- **`[outcome]`**: an experiment declares what its analysis is trying to
  explain — the column, whether it is binary or continuous, and the unit it
  belongs to. Everything descriptive still runs without one.
- **`chatlens demo` is reachable from the interface.** The empty library
  offered a "Try an example" button that did not exist; it does now, and the
  synthetic study it makes declares an outcome, so it demonstrates the whole
  tool rather than half of it.
- A run can be **stopped** from the page it was started on.
- A **navigation bar**: seven destinations that could not previously reach one
  another, with the ones needing a dependency that is not installed saying so
  where the choice is made.
- **Light and dark themes**, with an explicit toggle over the system setting.
- `tests/test_golden_merge.py` pins the merge's output against a recorded
  baseline, which is the automatable half of the rule this project calls the
  one that matters.

### Fixed

- **A definite "no" jumped above the orientation pages a moment after the
  study loaded.** The register sorts by verdict, and it used to put "no"
  right after "yes" — fine for a register that already has its verdicts, but
  this one fills in *after* the page has painted: a reader lands on a fresh
  study, sees "What was said" and "Who spoke to whom" first, and a second
  later two crossed-out entries jump above both of them because two blocks on
  this corpus came back negative. A "no" still outranks a question nothing
  has settled, so it is not pushed to the very end; it can no longer leapfrog
  the two pages a first-time reader has not reached yet.
- **The comparison could call an effect the design cannot see.** A block was
  held to a fixed 0.02 of AUC, and on one study of 355 groups the interval
  cannot tell 0.02 from zero. The bar is now the larger of 0.02 and the smallest
  difference this design can observe — the half-width of the block's interval —
  shown in its own column, so an effect below what the sample can resolve is
  not considered.

- **The comparison fitted its vocabulary on the rows it then scored.** The term
  matrix and the scaler were built once, over every row, and only then split
  into folds, so each fold's model had seen the test rows' vocabulary and their
  means. Everything that learns from the data now sits in a pipeline fitted
  inside the fold. Measured on the real corpus the difference this makes is
  below the noise — the selection steps are unsupervised, so the leak is real
  but small — which is worth saying plainly: the reason to fix it is that a
  replication package has to be defensible line by line, not that the number
  moved.
- **The comparison answered the wrong question.** It ranked representations
  against each other, when what a paper needs to know is whether a
  representation adds anything to knowing how much was written. Each block is
  now fitted **beside** `log(words + 1)` rather than instead of it, and the
  table reports the paired per-fold difference with a 95% interval, the standard
  error corrected for the overlap between cross-validation folds after Nadeau
  and Bengio (2003), Holm's step-down across the blocks, and a three-state
  verdict — adds something, adds nothing, too close to call. The third state is
  the commonest on a few hundred groups and had no way of being said before. On
  one study rather than the pooled collection the smallest difference either
  paper can resolve is about 0.040 of AUC, against 0.030 pooled; the 0.02 the
  page used as its bar is too permissive for both.
- **The Anthropic rubric could not run on the version of the SDK the project
  asked for.** It is built on `client.messages.parse` with an output schema, a
  call that arrived in `anthropic` 0.77.0, and `pyproject.toml` declared
  `>=0.40,<1` — a floor left behind from when the module used `messages.create`.
  So an environment could satisfy every declared dependency and still fail with
  an `AttributeError` on the first call of a paid run. It is not hypothetical:
  the project's own virtual environment happens to hold 0.125.0 and is fine,
  while a second interpreter on the same machine resolved to 0.69.0, where the
  method does not exist. The floor is now the version that introduced the call,
  the upper bound is `<2` after checking that 1.0.0 still has it, `chatlens
  status` says so in words when something has put an older one back, and the
  preflight that exists to fail before spending checks it too.
- **One execution log for every experiment.** The runner was a single global,
  and with it the log, the Stop button and the refusal "a run is already in
  progress": a run started on one study showed its log on another study's page,
  and that page could not start anything. There is a runner per workspace now,
  and a page whose experiment is idle while another is busy says which one is
  busy.
- **A page for a second experiment could wait for ever.** The guard that keeps
  two experiments from sharing the module state waited without a timeout, so a
  page that computes for minutes — and the other study's log, polling once a
  second — held a second tab with no page, no message and nothing to distinguish
  waiting from broken. It waits ten seconds and then answers 503 with a sentence
  saying which study is computing.
- **A silent standardisation of a single unit.** With fewer than two units the
  z-score is not defined, and the columns were written as 0 and 50 — a value
  that reads like a measurement. They are left empty now, and a sample with two
  or more units that genuinely has no variation still gets 0 and 50, which is
  what that means.
- **A report of a failed run read as a complete one.** The stage that failed was
  recorded in `run.json` and nowhere the reader looks, so a report missing its
  topic columns looked like a study without topics. Both renderings now open
  with what did not finish.
- **The archive extracted a shared study without a filter or a ceiling.** The
  tar member filter that refuses absolute paths and links is now explicit rather
  than left to the Python version's default, and the sum of the declared member
  sizes is checked before anything is written.
- **An upload could overwrite a file, or land while a run was reading it.** The
  first keeps a `.replaced` copy of what was there; the second is refused while
  a run is in progress, with the reason.
- **The spending confirmation never appeared in the dashboard.** It asks on a
  terminal, and in the dashboard's subprocess there is no terminal, so every run
  under the refusal ceiling started without asking. The page asks before
  starting, with the estimate and what it is made of.
- **"Run: done" on a run that failed.** The spine looked for a dataset, not for
  how the last run ended.
- **"Appears after the first run"** where the estimate of paid calls should be:
  it read the run archive, and the counts it needs are in the merge.
- **The words page's CSV called `C` a penalty.** It is scikit-learn's inverse of
  one, so a reader rebuilding the model in R or Stata from that column had it
  backwards. The column is named for what it holds.
- **Two documents describing the same run, each missing half of it.** The static
  report knew the coverage, the treatments and the data-quality notes and none
  of the findings; the findings export knew the findings and nothing about what
  they were computed on. The export now opens with the sample it rests on.
- **Accessibility of the explanations and the figures.** The hover tips were
  invisible to a screen reader — they are `aria-describedby` now — the word
  clouds carried `role="img"` with no accessible name, and the five-step spine
  did not fold at the narrow breakpoint, so the first thing on a small screen
  was a row that would not fit.
- Extra headers that cost nothing and close the gap between "this page never
  uses the camera" and "the browser will not let it": `Permissions-Policy`,
  `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`.

- **`median_gap_seconds` was not the median.** With an even number of gaps
  between turns it returned the upper of the two middle values, so a pair with
  gaps of ten and twenty seconds was reported as twenty. It is
  `statistics.median` now, the same function the corpus page already used, so a
  figure on a page and the same figure in a dataset agree.
- **A study's findings could be another study's.** The words, relations and
  comparison pages each remember their last result, and the key said what the
  analysis depends on — the outcome column, the unit, the entities, the knobs —
  and nothing about which study it came from. Two experiments configured alike,
  which is what copying one to try a variation produces, shared one entry: the
  second opened was served the first one's model, figures, AUC and verdicts,
  with nothing on screen to say so. The register's ✓ and ✗ read from the same
  cache.
- **Every file of an archived run answered 404** in the library, the report
  included: the links were written to the root, where what is served is
  whichever folder the dashboard process was started in and not the study.
- **The comparison page died on an outcome declared per person.** It chose the
  file by the outcome's unit and then indexed its rows by a column only the
  directed-pair table has, so the request ended in a traceback on the server
  and nothing in the browser. The paragraph it opens with also read the outcome
  by comparing strings to "0" and "1", so on the yes/no column a roster
  exported from a spreadsheet carries, it silently showed nothing.
- **The multiple-testing correction was half a correction.** Benjamini-Hochberg
  adjusts a p-value to `p × m / rank` and then pulls each one down to the
  smallest such value at or above its rank; only the first step was there, so
  the q-values were not monotone and a relation could be reported as weaker
  than one it dominates. On a family of five the smallest p came out at .005
  where the method gives .0028, and the count of survivors inherited it.
- **One-letter words never reached the model.** scikit-learn's default token
  pattern requires two characters, so "i" and "u" were dropped from the bag of
  words before it was fitted — in a game about who supports whom, the two words
  that say who. The dictionary measures have always counted them, so two parts
  of the tool disagreed about what a word is.
- **The transcript cleaner cut every line at its first colon**, whatever stood
  before it, and it is applied to plain message columns as well as to
  transcripts: `"ratio is 2:1 and i think: yes"` became `"1 and i think: yes"`,
  so a bargaining corpus lost the words before every number it argued about.
  Only a real `Yellow -> Orange:` prefix is removed now.
- **The theme was forgotten on every reload.** It was applied by an inline
  script, which the content security policy this server sends refuses — the
  policy working as written against a page that had not been told. It is a file
  now, still loaded before the first paint, so there is no flash either.
- **Relations went untested where there was no text to count.** With no
  transcript column the length control was passed a function returning zero for
  every row: log words was a constant, every design was singular, every fit
  raised and was skipped, and the page reported that nothing had been frequent
  enough to test — a claim about the corpus, made when no model had been fitted.
  The control is now left out and its absence is stated beside the table.
- An experiment whose name ran past 64 characters on a word boundary got a slug
  ending in a dash, which `path_for` then refused: the study `create` had just
  written could not be opened.
- The table the pages describe was chosen by modification time on every
  experiment that is not the oTree one, because the stem lookup asked for an
  input role only that adapter has and the failure was swallowed. So a pilot
  merged in August could be described as the current study.
- A run in the list could be reached from the keyboard but not opened with it:
  the row said `role="button"` and htmx was listening for a click alone.
- "Check again" on the relations page could not change its answer. Two things
  remember that RELATIO is missing — the import outcome, kept for the life of
  the process, and the import machinery's directory cache — and neither was
  cleared, so somebody who had just run the command the page printed was told
  to run it again.
- The rubric's judge models and TopicGPT's were listed twice each, once as the
  dropdown and once as the runner's allow-list, kept in step by hand: a model
  added to one alone either never appeared or was dropped from the command
  without a word. Each list now has one home.
- Dictionary entries that no tokeniser in the project can produce — `"'m"`,
  `"'re"`, `"n't"` — were listed as if they counted. The whole forms beside
  them are what does the work.
- `ui.table` took a `sortable` flag that added a class name no script looked
  for and no stylesheet styled, so the only thing it could do was promise a
  reader the headings were clickable.
- **The spending guard was not guarding.** `check` decided whether to refuse
  after it had already returned, so a ceiling below the confirmation threshold
  never applied: `--max-calls 10` let a run of nine hundred calls through, and
  `--yes` took the same exit, turning "do not ask me" into "no limit at all".
- The TopicGPT estimate counted two of the four paid phases, so a run could
  cost about twice the figure the guard had checked. The rubric asked the guard
  before consulting its cache, so a re-run costing nothing could be refused.
- `--llm-batch` neither read nor wrote that cache and polled without a
  deadline; with several judges it kept the first and dropped the rest.
- `--llm-replicates 0` produced a row with no errors and cached it as a paid
  result. A bad key made the OpenAI-compatible path retry every request five
  times before returning empty scores.
- The words page emitted its figures whatever happened, so with nothing
  surviving the penalty the reader got two broken-image icons and no
  explanation.
- The whole dashboard froze while any one page computed: requests for the same
  experiment now share the state they need rather than queue for it.
- Errors the user can fix — a column mapped to a name the file does not have,
  above all — stop printing tracebacks. A `[colums]` or a `kinde` is refused
  with the name it was probably meant to be, instead of being ignored.
- `report` and `analyze` no longer need `input/` to still be there.
- The default adapter is `generic_chat`: a workspace with no `experiment.toml`
  was silently configured for the coalition-formation study this grew out of.
- **An imported study asked for RELATIO to show relations it already had.**
  The bundle carries the extraction, but the relations page, the comparison
  and the register all checked for the 1.6 GB package before looking for its
  output, so the recipient was told "relatio unusable: not installed". An
  extraction made for the same messages, entities, unit and model is now read
  back without it; the package is needed only to extract. When it is needed,
  the page lists the commands that install it instead of only saying that it
  cannot run.
- The comparison raised when RELATIO could not cluster a corpus, instead of
  leaving the relations row out as its comment said it would.
- **Relations too rare to use were reported as a missing package.** On a
  corpus where no relation reaches the 25 units a test needs, the comparison
  and the register said "needs RELATIO and declared entities" on a machine
  that had just extracted them, and marked the finding unavailable. They now
  say that no relation is frequent enough, and the register shows it as an
  answer. The relations page, which said "None. Of 0 relations tested, none
  survives", now says there was nothing to test. Found by walking the guide
  on the synthetic study.

### Changed

- One page shell, one stylesheet and one set of components, where there were
  seven of each. The report consumes the same stylesheet instead of a second,
  already drifted, copy of the design.
- The word clouds are vector text in the page's own colours rather than a
  matplotlib raster on a white ground.
- The explanations are kept but moved behind a disclosure on each page, so the
  result is what arrives first.
- `core/tables.py` holds the one CSV reader and the one writer, replacing five
  and three. The generic adapter's merged files now carry a byte-order mark
  like every other output; their content is unchanged.

- **Experiments are managed from the interface.** `chatlens dashboard` opens a
  library: make an experiment, upload its CSVs, say which file plays which
  role, and map the columns from menus filled with the file's own header and
  pre-selected by a guess. Choosing the treatment column reads its values and
  asks for a name for each. `experiment.toml` is still the format — it is what
  makes an experiment portable — but writing it by hand is now optional.
- `chatlens experiments` lists and creates them from the terminal;
  `-e/--experiment` opens one by name; `--library` moves where they live.

- `--topicgpt-unsupervised` induces the topics with no starting list at all:
  every topic comes from the documents. The run archive records which mode was
  used, since a list steered by a seed and one invented from the documents are
  not the same object.
- `--topicgpt-shuffle-seed` controls the document order used for induction.

- `chatlens demo` writes a synthetic four-player bargaining study and analyses
  it, so the tool can be tried without anybody's participant data.
- `experiment.toml`: a workspace describes its experiment — which adapter, what
  its files are called, how its columns map, what to call a group and each
  treatment — instead of coding it.
- `generic_chat` adapter: no code at all where the export is already one
  message per row.
- `core/schema.py` states the contract between an adapter and the core, and
  reports a violation before any work starts rather than as a `KeyError` three
  stages later.
- The rubric's dimensions are declared once and the prompt, the output schema
  and the column names are generated from that declaration; a workspace can
  declare its own.
- `--pseudonymise` replaces participant identifiers with keyed hashes that are
  stable within a workspace and not reversible without its key.
- A spending guard: above a thousand paid calls a run asks, above twenty
  thousand it refuses. `--max-calls` and `--yes` override it.
- `chatlens install-topicgpt` installs TopicGPT into this machine's application
  data directory.
- Windows/macOS/Linux CI across Python 3.11–3.13.

### Changed

- The project is an installable package with a `chatlens` command, and no
  longer a folder to be run from inside. Data lives in a **workspace** — any
  folder holding `input/` and `output/` — chosen with `--workspace` or simply
  by being in it.
- API keys moved to the machine's configuration directory, outside any
  repository.
- The report is built in two layers: sections every experiment has are always
  present, game sections appear only where their columns do.
- `core/schema.parse_timestamp` accepts ISO 8601 as well as epoch seconds.

### Fixed

- The dashboard could be driven by any other page the researcher had open: a
  cross-site form post to `/run` started a run and spent API credit. It now
  checks the `Host` header, a session token in a `SameSite=Strict` cookie, and
  `Origin`/`Sec-Fetch-Site` on writes, and refuses to listen on a non-loopback
  address.
- The rubric cache and TopicGPT's working directory were not scoped by dataset,
  so a second dataset in the same workspace overwrote the first one's topics.
- The oTree chat-channel pattern read member ids as single digits, so from a
  group of ten upwards the messages were dropped without a word.
- **Topic induction read the documents sorted by treatment.** Induction is
  order-dependent: the list accumulates and each document is shown the list so
  far, told to reuse an existing topic where one fits. The documents arrived
  sorted by `group_uid`, which begins with the session code, and each session
  is one treatment, so one whole condition was read only after the taxonomy had
  settled on the other two. The documents are now shuffled with a reported seed
  before induction. This
  changes the induced topics of a seeded run as well as an unsupervised one;
  no topic run had yet been made on the final dataset.
- The topics dry run wrote the input in a different order from the one the real
  run would send, so it inspected something that never happened.

## [1.0.0] — 2026-08-26

The state in which the pipeline produced the coalition-formation dataset:
507 triads, 481 valid, 8,041 messages. Tagged `text_analysis-v1.0-coalition`
in the experiment's repository, and the baseline every later change is checked
against — the merge still produces byte-identical output on that data.
