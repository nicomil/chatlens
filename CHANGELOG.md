# Changelog

Notable changes to chatlens. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`chatlens tables`: every measure in one table per unit, for Stata and R.**
  The two datasets again, with the relations and the NRC emotions added — the
  two findings computed by their pages that never reached a file — every
  column renamed to something Stata and R both accept, a `.dta` beside each
  CSV when pandas is installed (the new `stata` extra), and a codebook. The
  findings summary offers the same tables as a download.
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
