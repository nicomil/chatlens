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


class Experiment:
    """The workspace's description of its experiment."""

    def __init__(self, data=None, path: Path | None = None):
        data = data or {}
        self.path = path
        self.raw = data

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

        rubric = data.get('rubric') or {}
        self.rubric_dimensions = rubric.get('dimensions')
        self.rubric_context = str(rubric.get('context') or '').strip()

    # --- reading ----------------------------------------------------------

    @property
    def configured(self) -> bool:
        """True when a file was actually read, as opposed to defaults."""
        return self.path is not None

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
