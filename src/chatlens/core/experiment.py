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

DEFAULT_ADAPTER = 'otree_coalition'

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


class Experiment:
    """The workspace's description of its experiment."""

    def __init__(self, data=None, path: Path | None = None):
        data = data or {}
        self.path = path
        self.raw = data

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
                         'lexicons', 'rubric', 'outcome')
        }
        self.declared['rubric'].pop('dimensions', None)
        if (data.get('rubric') or {}).get('dimensions'):
            self.declared['rubric']['dimensions'] = [
                dict(d) for d in data['rubric']['dimensions']
            ]

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

        # What the experiment is trying to explain, if it says. None is a
        # legitimate answer: everything descriptive works without it.
        self.outcome = outcome_module.parse(data.get('outcome'))

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
        config = {name: dict(table) for name, table in self.declared.items()
                  if table}
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
        elif table == 'lexicons':
            self.lexicons = kept

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
