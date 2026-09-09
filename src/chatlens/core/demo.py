"""A working workspace, generated from nothing.

Until this existed, trying the tool meant already having an experiment's data —
real conversations between real participants. That is a poor first step for a
piece of research software: the people best placed to evaluate it are exactly
the ones who should not be handed somebody else's participant data to do so.

`chatlens demo` writes a small synthetic study into a folder of its own and
runs the whole pipeline over it. Nothing here is real: the groups, the seats and
the sentences are generated from a fixed seed, so the same command produces the
same dataset on every machine, which also makes it usable in the tests and in
the documentation.

The study is a four-player bargaining game with pre-play chat, deliberately not
the coalition-formation experiment the project grew out of. Two treatments
differ in how people are allowed to talk, and the phrasing differs with them, so
the language measures have something to find and the report is worth reading
rather than merely non-empty.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

SEED = 20260901

GROUPS = 48
PLAYERS = 4

TREATMENTS = ('open', 'restricted')

# Two registers. The point is not realism but contrast: the restricted
# condition is terser and more transactional, which the volume and the
# dictionary measures should both pick up.
OPENERS = {
    'open': [
        "i think we should just split it evenly, nobody loses that way",
        "honestly seat {other} has been quiet, are you still with us?",
        "what if we agree now and stop wasting the clock",
        "i'd rather take a bit less and know it's settled",
        "does anyone actually object to equal shares? i don't",
        "seat {other}, tell me what you want and i'll work around it",
        "we keep going in circles, let me put a number on the table",
        "i'm happy with 60/40 if you take the larger half, you argued for it",
        "look, i trust you more than i trust the timer",
        "if we all hold out we all get nothing, that's the whole point",
        "i was going to propose the same thing, glad we agree",
        "can we settle this before someone drops out",
    ],
    'restricted': [
        "even split",
        "60/40",
        "agree",
        "seat {other}?",
        "no",
        "propose 50/50",
        "accept",
        "not enough",
        "final offer",
        "counter: 55/45",
        "waiting",
        "confirm",
    ],
}

REPLIES = {
    'open': [
        "that works for me, let's lock it in",
        "i'm not sure that's fair to seat {other} though",
        "fine, but i want it on the record that i moved first",
        "give me a second, i'm reading the payoff table again",
        "you're right, i was overthinking it",
        "i'd accept that if seat {other} agrees too",
        "that's the third time you've said the same thing",
        "ok. done. agreed.",
    ],
    'restricted': [
        "ok",
        "no",
        "agreed",
        "seat {other} first",
        "too low",
        "yes",
        "wait",
        "done",
    ],
}


def _messages(rng) -> list[dict]:
    rows = []
    for index in range(1, GROUPS + 1):
        treatment = TREATMENTS[index % len(TREATMENTS)]
        group = f'grp{index:03d}'
        # Talkative groups and quiet ones, so the volume measures vary.
        exchanges = rng.randint(4, 14)
        minute = rng.randint(0, 20)
        for _ in range(exchanges):
            sender, receiver = rng.sample(range(1, PLAYERS + 1), 2)
            other = rng.choice([s for s in range(1, PLAYERS + 1)
                                if s not in (sender, receiver)])
            bank = OPENERS if rng.random() < 0.55 else REPLIES
            body = rng.choice(bank[treatment]).format(other=other)
            minute += rng.randint(1, 3)
            rows.append({
                'group': group,
                'treatment': treatment,
                'sender': sender,
                'receiver': receiver,
                'sent_at': f'2026-03-{10 + index % 18:02d}'
                           f'T14:{minute % 60:02d}:{rng.randint(0, 59):02d}',
                'text': body,
            })
    return rows


def _roster(rng) -> list[dict]:
    rows = []
    for index in range(1, GROUPS + 1):
        for seat in range(1, PLAYERS + 1):
            rows.append({
                'group': f'grp{index:03d}',
                'sender': seat,
                'offer': rng.randint(20, 80),
                'accepted': rng.choice(['yes', 'yes', 'no']),
            })
    return rows


EXPERIMENT_TOML = '''# A synthetic study, written by "chatlens demo".
#
# Nothing here is real. It exists so that the tool can be tried, and its output
# read, without anybody's participant data.

[experiment]
name       = "Four-player bargaining with pre-play chat (demo)"
adapter    = "generic_chat"
group_noun = "group"

[input]
messages     = "messages*.csv"
participants = "roster*.csv"

[columns]
group     = "group"
sender    = "sender"
receiver  = "receiver"
body      = "text"
timestamp = "sent_at"
treatment = "treatment"

[treatments]
open       = "Open chat"
restricted = "Restricted chat"

# Without this the descriptive pages work and the four that explain something
# do not, so the example would demonstrate half the tool.
[outcome]
column = "accepted"
kind   = "binary"
unit   = "sender_group"
label  = "Offer accepted"
'''


def _write(path: Path, rows, columns) -> None:
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def create(workspace: Path) -> dict:
    """Write the demo workspace. Returns what was made."""
    workspace = Path(workspace).expanduser()
    (workspace / 'input').mkdir(parents=True, exist_ok=True)

    rng = random.Random(SEED)
    messages = _messages(rng)
    roster = _roster(rng)

    _write(workspace / 'input' / 'messages.csv', messages,
           ['group', 'treatment', 'sender', 'receiver', 'sent_at', 'text'])
    _write(workspace / 'input' / 'roster.csv', roster,
           ['group', 'sender', 'offer', 'accepted'])
    (workspace / 'experiment.toml').write_text(EXPERIMENT_TOML,
                                               encoding='utf-8')

    return dict(workspace=workspace, n_messages=len(messages),
                n_groups=GROUPS, n_participants=GROUPS * PLAYERS)
