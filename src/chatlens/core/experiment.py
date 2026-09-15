"""What the workspace says about the experiment it holds.

Without a file, everything below falls back to the coalition-formation
defaults, so the project this grew out of keeps working with no configuration
at all. With one, another experiment can be described rather than coded.

    # experiment.toml, at the root of the workspace
    [experiment]
    name       = "Ultimatum with pre-play chat"
    adapter    = "generic_chat"
    group_noun = "team"        # what the report calls a group; default "group"

    [input]
    messages     = "messages*.csv"
    participants = "participants*.csv"

    [columns]
    group     = "group_id"
    sender    = "sender"
    receiver  = "recipient"
    body      = "text"
    timestamp = "sent_at"
    treatment = "condition"

    [treatments]
    control = "Control"
    chat    = "Free chat"

The file is read once, at startup, and passed down as an object. It is not
allowed to reach into the analysis: the core still works from the canonical
tables alone, and nothing here changes how a measure is computed. What it
changes is how the raw export is read and how the report is labelled.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

FILENAME = 'experiment.toml'

# A workspace that does not say gets the general adapter, not the one written
# for the coalition-formation experiment this tool grew out of. It was the
# other way round, which meant a new user's first run was silently configured
# for somebody else's study: it looked for oTree's `all_apps_wide*.csv` and
# reported it missing, naming a file they had never heard of.
DEFAULT_ADAPTER = 'generic_chat'

# Column names the generic adapter looks for when the file does not say.
DEFAULT_COLUMNS = {
    'group': 'group_id',
    'sender': 'sender',
    'receiver': 'receiver',
    'body': 'body',
    'timestamp': 'timestamp',
    'treatment': 'treatment',
    'session': 'session_code',
    'participant': 'participant_code',
}


class ConfigError(RuntimeError):
    """The file is there but says something that cannot be acted on."""


from chatlens.core import outcome as outcome_module
from chatlens.core import studies as studies_module


# Everything the file may contain. A key not in here was silently dropped: a
# mistyped `[colums]` or `group_nown` was a no-op with nothing said, and the
# behaviour that resulted looked like the tool ignoring the configuration.
KNOWN_TABLES = {
    'experiment': {'name', 'adapter', 'group_noun', 'group_target'},
    'input': None,          # the roles are the adapter's, not ours to list
    'columns': None,        # likewise the column roles
    'treatments': None,     # the values are the experiment's own
    'lexicons': None,
    'rubric': {'context', 'dimensions'},
    'outcome': {'column', 'kind', 'unit', 'label'},
    'narratives': {'entities', 'model'},
    # Which collected sessions are the experiment. Everything else in the export
    # — pilots, internal tests, sessions launched without the recruitment
    # parameter — is noise, and the only person who can say which is which is
    # the experimenter. A list rather than a rule inferred from the data: a
    # missing Prolific label happened to coincide with the test sessions on the
    # collection this was written for, and that is a coincidence, not a design.
    'sample': {'sessions'},
    # An array of tables, like [[rubric.dimensions]]: one collection of sessions
    # can be the material of two papers, and each of those is a sample of its
    # own. The keys of each entry are checked by core/studies.py, which is also
    # where the reason it matters is written down.
    'studies': None,
}


def _did_you_mean(name: str, candidates) -> str:
    import difflib

    close = difflib.get_close_matches(name, sorted(candidates), n=1, cutoff=0.6)
    return f' Did you mean "{close[0]}"?' if close else ''


def check_shape(data: dict, path: Path) -> None:
    """Refuse a file whose tables or keys are not ones we act on.

    Silently ignoring them is the worst of the three options: the run proceeds,
    the setting has no effect, and the only symptom is a result that does not
    match what the file appears to say.
    """
    unknown = [name for name in data if name not in KNOWN_TABLES]
    if unknown:
        name = unknown[0]
        raise ConfigError(
            f'{path}: there is no [{name}] section.{_did_you_mean(name, KNOWN_TABLES)}\n'
            f'  The sections that mean something are: '
            f'{", ".join(sorted(KNOWN_TABLES))}.')

    for table, allowed in KNOWN_TABLES.items():
        if allowed is None:
            continue
        block = data.get(table) or {}
        if not isinstance(block, dict):
            continue
        strays = [key for key in block if key not in allowed]
        if strays:
            key = strays[0]
            raise ConfigError(
                f'{path}: [{table}] has no "{key}" setting.'
                f'{_did_you_mean(key, allowed)}\n'
                f'  It takes: {", ".join(sorted(allowed))}.')


def _sessions(value) -> tuple:
    """The declared session codes, cleaned, in the order given, without repeats."""
    if value in (None, ''):
        return ()
    if isinstance(value, str):
        value = value.replace(',', ' ').split()
    if not isinstance(value, (list, tuple)):
        raise ConfigError('[sample] sessions must be a list of session codes.')
    seen = []
    for item in value:
        code = str(item).strip()
        if code and code not in seen:
            seen.append(code)
    return tuple(seen)


class Experiment:
    """The workspace's description of its experiment."""

    def __init__(self, data=None, path: Path | None = None):
        data = data or {}
        self.path = path
        self.raw = data
        if path is not None:
            check_shape(data, path)

        # What the file actually said, kept apart from what was worked out
        # afterwards. Several attributes below are resolved rather than read —
        # `group_noun` becomes "triad" once the coalition adapter has had its
        # say, `columns` is filled in from the defaults — and writing those back
        # would put derived values into a file that never declared them, where
        # they would then survive a change of adapter. `declared` is what
        # `to_config()` writes; the attributes are what everything else reads.
        self.declared = {
            name: dict(data.get(name) or {})
            for name in ('experiment', 'input', 'columns', 'treatments',
                         'lexicons', 'rubric', 'outcome', 'narratives',
                         'sample')
        }
        self.declared['rubric'].pop('dimensions', None)
        if (data.get('rubric') or {}).get('dimensions'):
            self.declared['rubric']['dimensions'] = [
                dict(d) for d in data['rubric']['dimensions']
            ]
        # An array of tables rather than a table, so it is kept as a list and
        # not run through `dict()` like the others.
        self.declared['studies'] = [dict(entry) for entry
                                    in (data.get('studies') or [])
                                    if isinstance(entry, dict)]

        block = data.get('experiment') or {}
        self.name = str(block.get('name') or '').strip()
        self.adapter = str(block.get('adapter') or DEFAULT_ADAPTER).strip()
        # What the report calls a group of participants. "Triad" is right for
        # three players and reads as a bug for any other number.
        self.group_noun = str(block.get('group_noun') or 'group').strip()
        # How the rubric's prompt refers to everyone in a group.
        self.group_target = str(
            block.get('group_target')
            or f'everyone in the {self.group_noun}').strip()

        self.input = dict(data.get('input') or {})
        self.columns = {**DEFAULT_COLUMNS, **(data.get('columns') or {})}

        # Order matters: it is the order the report puts the sections in.
        self.treatments = dict(data.get('treatments') or {})

        # Only 'commitment' can be replaced; see core/lexicons.py.
        self.lexicons = dict(data.get('lexicons') or {})

        # Who the relational analysis should treat as an entity. The players
        # of this experiment are entities and nothing else can know that: in a
        # game about who supports whom, leaving "i" and "you" to be clustered
        # puts the speaker and the person spoken to in one group and erases the
        # only distinction that matters.
        narratives = data.get('narratives') or {}
        self.narrative_entities = [str(e).strip().lower()
                                   for e in (narratives.get('entities') or [])
                                   if str(e).strip()]
        self.narrative_model = str(
            narratives.get('model') or 'en_core_web_md').strip()

        # The sessions the analysis is restricted to. Empty means every session
        # the adapter's own rules keep, which is what an experiment that does not
        # declare this has always had.
        self.sessions = _sessions((data.get('sample') or {}).get('sessions'))

        # What the experiment is trying to explain, if it says. None is a
        # legitimate answer: everything descriptive works without it.
        self.outcome = outcome_module.parse(data.get('outcome'))

        # The samples it is analysed as. Empty is the ordinary case — one
        # collection, one sample — and every page then behaves as it always
        # has. See core/studies.py for why more than one changes the numbers.
        try:
            self.studies = studies_module.parse(data.get('studies'))
        except studies_module.StudyError as exc:
            raise ConfigError(f'{path or FILENAME}, [[studies]]: {exc}') from None
        # Written back normalised — a slug is lower-cased on the way in, and
        # `declared` is what `save()` emits, so without this the file would keep
        # saying "S1" while everything else called the study "s1".
        if self.studies:
            self.declared['studies'] = studies_module.to_config(self.studies)

        rubric = data.get('rubric') or {}
        self.rubric_dimensions = rubric.get('dimensions')
        self.rubric_context = str(rubric.get('context') or '').strip()

    # --- reading ----------------------------------------------------------

    @property
    def configured(self) -> bool:
        """True when a file was actually read, as opposed to defaults."""
        return self.path is not None

    def to_config(self) -> dict:
        """The configuration as it should be written back.

        Only what was declared, plus whatever has since been set through the
        interface. Empty tables are dropped by the writer.
        """
        config = {name: (list(table) if isinstance(table, list) else dict(table))
                  for name, table in self.declared.items() if table}
        # These two are the identity of the experiment and are always written,
        # even when the file was created empty.
        experiment = config.setdefault('experiment', {})
        experiment['name'] = self.name
        experiment['adapter'] = self.adapter
        return config

    def set(self, table: str, values: dict) -> None:
        """Replace one table of the declaration.

        A value of None or the empty string removes the key rather than
        writing it empty: "not set" and "set to nothing" are different, and
        only the first is a thing a configuration can say.
        """
        if table not in self.declared:
            raise ConfigError(f'There is no [{table}] to set.')
        if table == 'studies':
            # An array of tables: a list in, a list kept, and validated on the
            # way through so a bad declaration is refused here rather than
            # discovered by whatever reads it next.
            entries = [dict(entry) for entry in (values or [])]
            self.studies = studies_module.parse(entries)
            self.declared['studies'] = studies_module.to_config(self.studies)
            return
        kept = {k: v for k, v in (values or {}).items()
                if v not in (None, '', [], {})}
        self.declared[table] = kept
        # Keep the read side in step, so a page rendered right after a save
        # shows what was saved rather than what was loaded.
        if table == 'experiment':
            self.name = str(kept.get('name') or self.name).strip()
            self.adapter = str(kept.get('adapter') or self.adapter).strip()
            if kept.get('group_noun'):
                self.group_noun = str(kept['group_noun']).strip()
        elif table == 'columns':
            self.columns = {**DEFAULT_COLUMNS, **kept}
        elif table == 'input':
            self.input = kept
        elif table == 'treatments':
            self.treatments = kept
        elif table == 'outcome':
            self.outcome = outcome_module.parse(kept)
        elif table == 'narratives':
            self.narrative_entities = [str(e).strip().lower()
                                       for e in (kept.get('entities') or [])
                                       if str(e).strip()]
            self.narrative_model = str(
                kept.get('model') or 'en_core_web_md').strip()
        elif table == 'lexicons':
            self.lexicons = kept
        elif table == 'sample':
            self.sessions = _sessions(kept.get('sessions'))

    def save(self, path: Path | None = None) -> Path:
        """Write the configuration back. Verified before it counts as saved."""
        from . import tomlwrite

        target = Path(path) if path else self.path
        if target is None:
            raise ConfigError('Nowhere to save to: this experiment has no file.')
        return tomlwrite.save(
            target, self.to_config(),
            header=('Written by chatlens. Editing it by hand is fine — the '
                    'interface reads\nwhatever is here.'),
        )

    def label(self, treatment: str) -> str:
        """The name to print for a treatment; the raw value if unnamed."""
        return self.treatments.get(treatment, treatment)

    def describe(self) -> str:
        if not self.configured:
            return f'no {FILENAME}: using the {self.adapter} defaults'
        name = self.name or '(unnamed)'
        return f'{name} — adapter {self.adapter}'


def load(workspace: Path) -> Experiment:
    """Read the workspace's file, or return the defaults."""
    path = Path(workspace) / FILENAME
    if not path.is_file():
        return Experiment()

    try:
        data = tomllib.loads(path.read_text(encoding='utf-8'))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(
            f'{path} cannot be read: {exc}\n'
            f'  It is TOML. The commonest cause is a value left unquoted.'
        ) from None

    experiment = Experiment(data, path=path)

    from chatlens import adapters
    if experiment.adapter not in adapters.available():
        raise ConfigError(
            f'{path} asks for the adapter "{experiment.adapter}", '
            f'which does not exist.\n'
            f'  Available: {", ".join(sorted(adapters.available()))}\n'
            f'  An adapter turns your export into the canonical tables; see '
            f'chatlens/core/schema.py for what it has to produce.'
        )
    return experiment
