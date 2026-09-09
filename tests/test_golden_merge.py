"""The merge is not allowed to change its output by accident.

CONTRIBUTING.md calls it the one rule that matters: on the collected data the
four merge outputs stay byte-identical. That check has always been a manual
`shasum` against a workspace of participants' chats, which cannot live in a
repository — so nothing enforced it here, and a reordered column, a rounding
change or a renamed header would have passed all the other tests.

This is the part that can be automated: a fixed synthetic export, run through
the same adapter, hashed. It does not prove anything about the real data — the
manual comparison still does that — but it does mean the shape of the output
cannot drift unnoticed between two of those comparisons.

    python tests/test_golden_merge.py

When the change is intended, record the new baseline and say so in the commit:

    CHATLENS_UPDATE_GOLDEN=1 python tests/test_golden_merge.py
"""

import contextlib
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_merge import (  # noqa: E402
    MAIN, WIDE_COLUMNS, make_player, mod,
)

GOLDEN = Path(__file__).resolve().parent / 'golden' / 'merge_outputs.json'

OUTPUTS = ('messages_long', 'chat_by_partner', 'chat_aggregated')


def build_export():
    """Two triads in two sessions, with a fixed conversation.

    Everything is spelled out rather than generated: a baseline built from a
    loop changes whenever the loop does, which is the opposite of the point.
    """
    def triad(session, prefix, treatment, decisions, payoffs, outcome):
        rows = [
            # The label is written out rather than taken from the shared
            # `fake_prolific_pid`, which derives it from `hash()` and therefore
            # changes with every interpreter. A baseline cannot be built on a
            # fixture that is not the same twice.
            make_player(session, f'{prefix}{pid}', pid, treatment,
                        decisions[pid - 1], 'split_you', 'split_me',
                        payoffs[pid - 1], group_db_id='7',
                        label=f'{prefix}0000000000000000000{pid}'[:24])
            for pid in (1, 2, 3)
        ]
        for row in rows:
            row[MAIN + 'group.group_outcome'] = outcome
        return rows

    wide = (
        triad('s1', 'a', 'private', ['Right', 'Left', 'NoOne'], [3, 3, 0],
              'mutual_12')
        + triad('s2', 'b', 'public', ['NoOne', 'NoOne', 'NoOne'], [0, 0, 0],
                'disagreement')
    )

    def message(session, pid, code, pair, body, at):
        return {'session_code': session, 'id_in_session': str(pid),
                'participant_code': code,
                'channel': f'4-bargaining_tdl_main-7_{pair}',
                'nickname': 'LeftPartner', 'body': body, 'timestamp': str(at)}

    chat = [
        message('s1', 1, 'a1', '1_2', 'i support you if you support me', 100.0),
        message('s1', 2, 'a2', '1_2', 'agreed, that works for me', 101.0),
        message('s1', 1, 'a1', '1_3', 'what do you want to do', 102.0),
        message('s1', 3, 'a3', '1_3', 'not sure yet, too low', 103.0),
        message('s1', 2, 'a2', '2_3', 'nothing for you here', 104.0),
        message('s2', 1, 'b1', '1_2', 'ok', 200.0),
        message('s2', 2, 'b2', '1_2', 'no', 201.0),
    ]
    return wide, chat


def run_merge_to(outdir: Path):
    """Run the adapter into `outdir` and return the paths it wrote."""
    wide, chat = build_export()
    wide_path = outdir / 'wide.csv'
    chat_path = outdir / 'chat.csv'

    with wide_path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=WIDE_COLUMNS)
        writer.writeheader()
        writer.writerows(wide)

    chat_cols = ['session_code', 'id_in_session', 'participant_code', 'channel',
                 'nickname', 'body', 'timestamp']
    with chat_path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=chat_cols)
        writer.writeheader()
        writer.writerows(chat)

    with contextlib.redirect_stdout(io.StringIO()):
        mod.run(wide_path, chat_path, outdir / 'out', 'golden')
    return outdir / 'out'


def describe(path: Path) -> dict:
    """Hash, plus the two things a hash alone will not tell you."""
    data = path.read_bytes()
    entry = {'sha256': hashlib.sha256(data).hexdigest()}
    if path.suffix == '.csv':
        with path.open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.reader(handle))
        entry['columns'] = rows[0] if rows else []
        entry['rows'] = max(len(rows) - 1, 0)
    return entry


def collect() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        out = run_merge_to(Path(tmp))
        found = {f'{name}.csv': describe(out / f'golden_{name}.csv')
                 for name in OUTPUTS}
        found['summary.json'] = describe(out / 'golden_summary.json')
        return found


class GoldenMergeTests(unittest.TestCase):
    """Every merge output, against the recorded baseline."""

    @classmethod
    def setUpClass(cls):
        cls.found = collect()

    def test_the_baseline_exists(self):
        self.assertTrue(
            GOLDEN.is_file(),
            f'no baseline at {GOLDEN}. Record one with '
            f'CHATLENS_UPDATE_GOLDEN=1 python tests/test_golden_merge.py',
        )

    def test_every_output_matches_the_baseline(self):
        expected = json.loads(GOLDEN.read_text(encoding='utf-8'))
        self.assertEqual(sorted(expected), sorted(self.found),
                         'the merge writes a different set of files')

        for name, want in expected.items():
            got = self.found[name]
            with self.subTest(file=name):
                # Named differences first: a failure that says "column X moved"
                # is actionable, one that says "the hash changed" is not.
                if 'columns' in want:
                    self.assertEqual(
                        want['columns'], got['columns'],
                        f'{name}: the columns changed')
                    self.assertEqual(
                        want['rows'], got['rows'],
                        f'{name}: the number of rows changed')
                self.assertEqual(
                    want['sha256'], got['sha256'],
                    f'{name}: the content changed while the columns and the '
                    f'row count stayed the same — a value, an order or a '
                    f'rounding. If that was the intention, re-record the '
                    f'baseline and say why in the commit.')


if __name__ == '__main__':
    if os.environ.get('CHATLENS_UPDATE_GOLDEN'):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(
            json.dumps(collect(), indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8')
        print(f'baseline recorded in {GOLDEN}')
    else:
        unittest.main()
