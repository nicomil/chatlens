"""Does RELATIO actually run here?

Not a unit test, and deliberately not named like one. `tests/test_narratives.py`
covers the logic around the extraction with the package mocked away or the suite
skipped, which is right for a dependency that pulls in torch, transformers and a
language model. What that leaves untested is the extraction itself — the path
that breaks when somebody else releases a version that will not import beside
its neighbours, which is the failure this project has actually had.

So this file runs the real thing on a handful of synthetic sentences, exits 0
when relations come out and 1 when they do not, and is wired into the `relations`
job in CI. Run it by hand after `chatlens install-relatio` if the narratives page
says the package is unusable and you want to see the error rather than a summary
of it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from chatlens.core import narratives  # noqa: E402

ENTITIES = ['i', 'you', 'we']

# Enough distinct sentences for the clustering to have something to group:
# RELATIO reduces and clusters the phrase embeddings, and a corpus of two
# sentences has fewer phrases than any clustering can use. The content is the
# shape of the coalition study this tool was written for — offers, support,
# refusals — because a relation needs an agent and a patient to exist at all.
SENTENCES = [
    'i support you in this round',
    'you should help me and we win together',
    'i will not betray you',
    'we can split the money evenly',
    'you promised me the larger share',
    'i offer you thirty and i keep forty',
    'we should exclude the third player',
    'you are cheating me again',
    'i trust you more than the other one',
    'we agree on this deal now',
    'you refused my offer last time',
    'i need you to accept quickly',
]


def messages():
    out = []
    for i, text in enumerate(SENTENCES):
        sender, receiver = ('1', '2') if i % 2 == 0 else ('2', '1')
        out.append({'group_uid': 'g1', 'sender_id_in_group': sender,
                    'receiver_id_in_group': receiver, 'body': text})
    # Repeated, because the extraction has a minimum number of documents below
    # which it declines to say anything, and the point here is to reach the code
    # rather than to measure anything.
    return out * 5


def main() -> int:
    ready, why = narratives.available()
    print(f'available: {ready}' + (f' — {why}' if why else ''))
    if not ready:
        return 1

    found = narratives.extract_with_relatio(messages(), ENTITIES,
                                            model='en_core_web_md')
    print(f'units with at least one relation: {len(found)}')
    for unit, relations in sorted(found.items()):
        for agent, verb, patient in sorted(relations):
            print(f'  {unit} :: {agent} | {verb} | {patient}')
    return 0 if found else 1


if __name__ == '__main__':
    raise SystemExit(main())
