"""What the rubric measures, declared once.

The dimensions used to be written out three times — as prose in the system
prompt, as fields on a pydantic model, and as two tuples of column names — and
kept in step by hand. Nothing enforced the agreement, so a dimension could be
described to the model and never read back, or read back under a name the model
was never told about.

Here they are declared once and the three forms are generated. That is what
makes the rubric configurable: another experiment measuring something else
writes its dimensions in `experiment.toml` and gets a coherent prompt, a
matching schema and matching columns, without touching any code.

    [rubric]
    context = "Two participants bargain over how to divide a sum of money."

    [[rubric.dimensions]]
    name    = "aggression"
    label   = "AGGRESSIVENESS"
    kind    = "scale"
    summary = "How forcefully the writer pushes their own claim, 0-100"
    high    = "ultimatums, threats to walk away, refusal to move"
    low     = "concessions, hedging, invitations to find a middle ground"

A note on the cache. Ratings are cached under a signature that includes the
prompt text, so changing a description invalidates the cached ratings that used
the old one — correctly, since they answered a different question. Which is
also why the default dimensions generate a prompt byte-identical to the one
written by hand before this existed: our own cached ratings stay valid.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_CONTEXT = (
    'Three participants play a coalition-formation game and exchange short '
    'private chat messages before deciding whom to support.'
)

NUMBER_WORDS = {
    1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six',
    7: 'seven', 8: 'eight', 9: 'nine', 10: 'ten',
}


@dataclass(frozen=True)
class Dimension:
    """One thing the rubric measures."""

    name: str                   # the column name, and the model's field name
    kind: str = 'scale'         # 'scale' (0-100) or 'flag' (true/false)
    label: str = ''             # the heading in the prompt
    summary: str = ''           # one line, becomes the field's description
    high: str = ''              # what a high score looks like
    low: str = ''               # what a low score looks like
    note: str = ''              # anything else the rater needs, e.g. tone's 50
    clause: str = ''            # for flags: how the prompt asks for it

    def heading(self) -> str:
        return f'{self.label or self.name.upper()} ({self.name})'

    def block(self) -> str:
        """The dimension as it appears in the system prompt."""
        lines = [self.heading()]
        body = self.note
        if self.high:
            body = f'{body} High: {self.high}.' if body else f'High: {self.high}.'
        if self.low:
            body = f'{body} Low: {self.low}.'
        lines.append(body.strip())
        return '\n'.join(lines)


DEFAULT_DIMENSIONS = (
    Dimension(
        name='analytic', label='ANALYTICAL THINKING',
        summary='Analytical thinking, 0-100',
        note='Formal, logical, hierarchical reasoning versus narrative, '
             'here-and-now, informal language.',
        high='reasoning about payoffs, conditions, consequences, structured '
             'argument',
        low='greetings, reactions, unstructured chatter',
    ),
    Dimension(
        name='clout', label='CLOUT',
        summary='Confidence and social status, 0-100',
        note='The confidence and social status the writer projects.',
        high='speaks with authority, focuses on the other person and on the '
             'group, makes offers and proposals, appears to lead the exchange',
        low='tentative, self-focused, anxious, deferential, hedging',
    ),
    Dimension(
        name='authenticity', label='AUTHENTICITY',
        summary='Spontaneous honesty, 0-100',
        note='How spontaneous and personally honest the language reads.',
        high='unguarded, self-disclosing, admits uncertainty or self-interest '
             'openly',
        low='guarded, strategic, distanced, impression-managing, evasive',
    ),
    Dimension(
        name='tone', label='EMOTIONAL TONE',
        summary='Emotional tone, 50 = neutral',
        note='Emotional valence. Above 50: positive, warm, friendly. Below 50: '
             'negative, hostile, anxious. Exactly 50: neutral or no emotional '
             'content.',
    ),
    Dimension(
        name='contains_support_commitment', kind='flag',
        summary='The text explicitly promises support to someone',
        clause='contains an explicit commitment to support someone',
    ),
    Dimension(
        name='contains_support_request', kind='flag',
        summary='The text explicitly asks someone for support',
        clause='contains an explicit request for support',
    ),
)

# Always present, whatever the experiment measures: without it an empty
# transcript is scored 50 across the board and looks like a real reading.
INSUFFICIENT = Dimension(
    name='insufficient_text', kind='flag',
    summary='True when the transcript carries too little language to rate',
)


def scales(dimensions) -> tuple:
    return tuple(d.name for d in dimensions if d.kind == 'scale')


def flags(dimensions) -> tuple:
    return tuple(d.name for d in dimensions if d.kind == 'flag') + (
        INSUFFICIENT.name,)


def build_system_prompt(dimensions, context: str = DEFAULT_CONTEXT) -> str:
    """The prompt, generated from the declaration."""
    scale_dims = [d for d in dimensions if d.kind == 'scale']
    flag_dims = [d for d in dimensions if d.kind == 'flag']
    count = NUMBER_WORDS.get(len(scale_dims), str(len(scale_dims)))
    noun = 'construct' if len(scale_dims) == 1 else 'constructs'

    parts = [
        'You are a research assistant coding transcripts for a behavioural '
        f'economics experiment. {context}',
        '',
        f'You rate a transcript on {count} {noun}, each on a 0-100 scale. Use '
        'the full range: 50 is the midpoint for an unremarkable transcript of '
        'this kind, not a default answer. Rate only what the text shows; never '
        'infer from what you imagine happened outside the transcript.',
    ]
    for dimension in scale_dims:
        parts += ['', dimension.block()]

    clauses = [d.clause or f'shows {d.name}' for d in flag_dims]
    if clauses:
        if len(clauses) == 1:
            listed = f'whether the transcript {clauses[0]}'
        else:
            listed = ', and '.join([
                ', '.join(f'whether the transcript {c}' for c in clauses[:-1]),
                f'whether it {clauses[-1]}',
            ])
        parts += ['', f'Also record {listed}.']

    parts += [
        '',
        'If the transcript is empty or contains no usable language, return 50 '
        f'for every scale and set {INSUFFICIENT.name} to true.',
    ]
    return '\n'.join(parts)


def build_model(dimensions):
    """The pydantic model the provider validates its answer against."""
    try:
        from pydantic import Field, create_model
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError(
            'The rubric needs pydantic and the chosen provider client.\n'
            '  pip install "chatlens[llm]"'
        ) from exc

    fields = {}
    for dimension in dimensions:
        if dimension.kind == 'scale':
            fields[dimension.name] = (
                int, Field(ge=0, le=100, description=dimension.summary))
        else:
            fields[dimension.name] = (
                bool, Field(description=dimension.summary))
    fields[INSUFFICIENT.name] = (bool, Field(description=INSUFFICIENT.summary))
    fields['rationale'] = (
        str, Field(description='One sentence, at most 25 words, justifying '
                               'the ratings'))

    model = create_model('RubricScores', **fields)
    model.__doc__ = 'Rubric scores for a single transcript.'
    return model


def from_config(entries, context='') -> tuple:
    """Dimensions declared in experiment.toml, or the defaults."""
    if not entries:
        return DEFAULT_DIMENSIONS

    dimensions = []
    for entry in entries:
        if not entry.get('name'):
            raise ValueError(
                'Every [[rubric.dimensions]] needs a name: it becomes the '
                'column in the output and the field the model fills in.')
        kind = entry.get('kind', 'scale')
        if kind not in ('scale', 'flag'):
            raise ValueError(
                f'Dimension "{entry["name"]}" has kind "{kind}"; it must be '
                f'"scale" (0-100) or "flag" (true/false).')
        dimensions.append(Dimension(
            name=str(entry['name']).strip(),
            kind=kind,
            label=str(entry.get('label') or '').strip(),
            summary=str(entry.get('summary') or '').strip(),
            high=str(entry.get('high') or '').strip(),
            low=str(entry.get('low') or '').strip(),
            note=str(entry.get('note') or '').strip(),
            clause=str(entry.get('clause') or '').strip(),
        ))
    return tuple(dimensions)
