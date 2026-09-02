# Changelog

Notable changes to chatlens. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
