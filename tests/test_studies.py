"""One collection, two samples.

A 2x2 with one cell not run supports two comparisons — baseline against each of
the other arms — and those are two papers, not one. What makes that a matter for
the code rather than for the prose is that the standardised language indices are
computed over the sample by design, so the same participant has a different
`clout_100` in the two studies.

These tests pin the two properties everything else rests on: a study that covers
the whole sample reproduces the pooled dataset exactly, and a study that covers
part of it leaves the raw columns alone while moving the standardised ones.

    python tests/test_studies.py
"""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from chatlens.core import config, experiment as em  # noqa: E402
from chatlens.core import perstudy, studies, tomlwrite  # noqa: E402

ARMS = ('private', 'public', 'private_no_dwl')

# Words chosen so the arms differ in how they write: the standardised indices
# are a function of the whole sample, so dropping an arm has to move them.
#
# Several variants per arm, differing in their mix of `i`, `we`, `you` and
# social words — the categories Clout is composed from. Repeating one sentence
# would not do: the indices are percentages of the unit's words, so they are
# scale-invariant and more of the same text leaves them exactly where they were.
SENTENCES = {
    'private': [
        'i will support you because the payoff is better for us',
        'i think i should take the larger share for myself',
        'we can split it evenly and you get the rest',
        'i am not sure i want to promise anything at all',
    ],
    'public': [
        'ok',
        'no i will not',
        'we agree on this',
        'you decide for us',
    ],
    'private_no_dwl': [
        'everyone can see this so i am telling you the truth',
        'we should all coordinate and you will benefit too',
        'they will know if i break my word to you',
        'the group can read everything we write to each other',
    ],
}


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _read(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def corpus(workspace: Path, stem: str = 'messages', per_arm: int = 12) -> None:
    """A merged corpus of triads across the three arms.

    The text varies *within* an arm as well as between them, and that is not
    decoration. With one sentence per arm the sample of two arms is a balanced
    two-point distribution, whose z-scores are ±1 whatever the two values are —
    so a baseline participant would score the same in both studies for a reason
    that has nothing to do with the code under test.
    """
    messages, by_partner, aggregated = [], [], []
    for arm_index, arm in enumerate(ARMS):
        for n in range(per_arm):
            group = f'{arm}-g{n:03d}'
            # A different one of the arm's sentences per group, repeated a
            # varying number of times: the first gives the indices a spread, the
            # second gives the word count one.
            variants = SENTENCES[arm]
            said = ' '.join([variants[n % len(variants)]] * (1 + (n // 4) % 3))
            for sender in (1, 2, 3):
                for receiver in (1, 2, 3):
                    if sender == receiver:
                        continue
                    messages.append({
                        'session_code': f's{arm_index}', 'group_uid': group,
                        'treatment': arm, 'timestamp': str(1000 + n),
                        'sender_id_in_group': str(sender),
                        'receiver_id_in_group': str(receiver),
                        'dyad_key': '-'.join(sorted([str(sender), str(receiver)])),
                        'body': said,
                    })
                    by_partner.append({
                        'group_uid': group, 'session_code': f's{arm_index}',
                        'treatment': arm, 'focal_id_in_group': str(sender),
                        'partner_id_in_group': str(receiver),
                        'dyad_key': '-'.join(sorted([str(sender), str(receiver)])),
                        'sent_transcript_text': said,
                        'accepted': 'yes' if (n + sender) % 2 else 'no',
                    })
            for who in (1, 2, 3):
                aggregated.append({
                    'group_uid': group, 'session_code': f's{arm_index}',
                    'treatment': arm, 'focal_id_in_group': str(who),
                    'sent_transcript_text': said,
                    'accepted': 'yes' if (n + who) % 2 else 'no',
                })
    merged = workspace / 'output' / 'merged'
    _write(merged / f'{stem}_messages_long.csv', messages)
    _write(merged / f'{stem}_chat_by_partner.csv', by_partner)
    _write(merged / f'{stem}_chat_aggregated.csv', aggregated)


class DeclarationTests(unittest.TestCase):
    def test_nothing_declared_is_the_ordinary_case(self):
        """Most experiments are one study, and they must not change."""
        self.assertEqual(studies.parse(None), ())
        self.assertEqual(studies.parse([]), ())
        self.assertEqual(em.Experiment().studies, ())

    def test_a_study_is_read_back(self):
        found = studies.parse([{'slug': 'study1', 'name': 'Study 1',
                                'treatments': ['private', 'public'],
                                'baseline': 'private'}])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].slug, 'study1')
        self.assertEqual(found[0].others, ('public',))
        self.assertTrue(found[0].holds('public'))
        self.assertFalse(found[0].holds('private_no_dwl'))

    def test_the_baseline_defaults_to_the_first_treatment(self):
        found = studies.parse([{'slug': 's', 'treatments': ['a', 'b']}])
        self.assertEqual(found[0].baseline, 'a')

    def test_what_is_refused(self):
        for block, because in (
                ([{'slug': 'a b', 'treatments': ['x', 'y']}], 'slug'),
                ([{'slug': 's', 'treatments': ['x']}], 'one treatment'),
                ([{'slug': 's', 'treatments': ['x', 'x']}], 'the same twice'),
                ([{'slug': 's', 'treatments': ['x', 'y'], 'baseline': 'z'}],
                 'baseline outside'),
                ([{'slug': 's', 'treatments': ['x', 'y']},
                  {'slug': 's', 'treatments': ['x', 'z']}], 'two with one slug'),
                ([{'slug': 's', 'treatments': ['x', 'y'], 'tratments': []}],
                 'a mistyped key'),
        ):
            with self.subTest(because=because):
                self.assertTrue(studies.problems(block),
                                f'{because} was accepted')

    def test_a_mistyped_key_is_refused_rather_than_ignored(self):
        """The whole reason `check_shape` exists: a setting with no effect and
        no message is worse than an error."""
        problem = studies.problems(
            [{'slug': 's', 'treatments': ['x', 'y'], 'baselien': 'x'}])[0]
        self.assertIn('baselien', problem)

    def test_the_declaration_survives_being_written_and_read(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: None)
        entries = [
            {'slug': 'study1', 'name': 'Study 1 — public',
             'treatments': ['private', 'public'], 'baseline': 'private'},
            {'slug': 'study2', 'name': 'Study 2 — slacker',
             'treatments': ['private', 'private_no_dwl'],
             'baseline': 'private'},
        ]
        path = tmp / 'experiment.toml'
        tomlwrite.save(path, {'experiment': {'name': 'X', 'adapter': 'generic_chat'},
                              'studies': entries})
        self.assertIn('[[studies]]', path.read_text(encoding='utf-8'))
        reread = em.load(tmp)
        self.assertEqual([s.slug for s in reread.studies], ['study1', 'study2'])
        self.assertEqual(reread.studies[1].others, ('private_no_dwl',))

    def test_the_rubric_dimensions_still_round_trip(self):
        """They share the array-of-tables writer now."""
        tmp = Path(tempfile.mkdtemp())
        path = tmp / 'experiment.toml'
        tomlwrite.save(path, {
            'experiment': {'name': 'X', 'adapter': 'generic_chat'},
            'rubric': {'context': 'A game.',
                       'dimensions': [{'name': 'aggression', 'kind': 'scale'}]},
        })
        text = path.read_text(encoding='utf-8')
        self.assertIn('[[rubric.dimensions]]', text)
        self.assertEqual(em.load(tmp).rubric_dimensions,
                         [{'name': 'aggression', 'kind': 'scale'}])


class SampleSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(self.tmp.name)
        corpus(self.workspace)
        config.use_workspace(self.workspace)
        config.use_experiment(em.Experiment())
        self.messages = _read(
            self.workspace / 'output' / 'merged' / 'messages_messages_long.csv')

    def study(self, slug, treatments, baseline=None):
        return studies.parse([{'slug': slug, 'treatments': list(treatments),
                               'baseline': baseline or treatments[0]}])[0]

    def test_only_the_declared_arms_are_selected(self):
        one = self.study('s1', ['private', 'public'])
        chosen = studies.rows_for(one, self.messages)
        self.assertEqual({r['treatment'] for r in chosen},
                         {'private', 'public'})
        self.assertLess(len(chosen), len(self.messages))

    def test_the_census_counts_groups_per_arm(self):
        one = self.study('s1', ['private', 'public'])
        census = studies.census(one, self.messages)
        self.assertEqual(census['groups_per_treatment'],
                         {'private': 12, 'public': 12})
        self.assertEqual(census['n_groups'], 24)
        self.assertEqual(census['baseline'], 'private')

    def test_the_studies_overlap_and_that_is_not_a_bug(self):
        """They share the baseline, so this is not a partition: the rows of the
        two studies together exceed the corpus."""
        first = studies.rows_for(self.study('s1', ['private', 'public']),
                                 self.messages)
        second = studies.rows_for(
            self.study('s2', ['private', 'private_no_dwl']), self.messages)
        self.assertGreater(len(first) + len(second), len(self.messages))


class PerStudyDatasetTests(unittest.TestCase):
    """The two properties the whole design rests on."""

    RAW = ('nlp_sent_analytic_cdi', 'nlp_sent_clout_raw',
           'nlp_sent_authenticity_raw', 'nlp_sent_tone_raw', 'nlp_sent_wc')
    SCALED = ('nlp_sent_analytic_z', 'nlp_sent_analytic_100',
              'nlp_sent_clout_z', 'nlp_sent_clout_100')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(self.tmp.name)
        corpus(self.workspace)
        config.use_workspace(self.workspace)
        config.use_experiment(em.Experiment())
        # The pooled dataset, built the way the pipeline builds it.
        from chatlens.core import aggregate as agg

        messages = _read(self.workspace / 'output' / 'merged'
                         / 'messages_messages_long.csv')
        features = agg.aggregate_all(agg.analyze_messages(messages))
        by_partner = _read(self.workspace / 'output' / 'merged'
                           / 'messages_chat_by_partner.csv')
        agg.merge_into_by_partner(by_partner, features)
        out = self.workspace / 'output' / 'datasets'
        out.mkdir(parents=True, exist_ok=True)
        agg.write_csv(out / 'messages_chat_by_partner_nlp.csv', by_partner)
        self.pooled = by_partner

    def study(self, slug, treatments):
        return studies.parse([{'slug': slug, 'treatments': list(treatments),
                               'baseline': treatments[0]}])[0]

    def key(self, row):
        return (row['group_uid'], row['focal_id_in_group'],
                row['partner_id_in_group'])

    def test_a_study_covering_everything_reproduces_the_pooled_dataset(self):
        whole = self.study('all', list(ARMS))
        built = perstudy.build(whole, 'messages')['tables']['chat_by_partner']
        pooled = {self.key(r): r for r in self.pooled}
        self.assertEqual(len(built), len(self.pooled))
        for row in built:
            against = pooled[self.key(row)]
            for column in self.RAW + self.SCALED:
                self.assertEqual(row.get(column), against.get(column),
                                 f'{column} moved on the whole sample')

    def test_a_subset_leaves_the_raw_columns_alone(self):
        """They are absolute: a word count is a word count."""
        part = self.study('s1', ['private', 'public'])
        built = perstudy.build(part, 'messages')['tables']['chat_by_partner']
        pooled = {self.key(r): r for r in self.pooled}
        self.assertLess(len(built), len(self.pooled))
        for row in built:
            against = pooled[self.key(row)]
            for column in self.RAW:
                self.assertEqual(row.get(column), against.get(column),
                                 f'{column} is not sample-independent')

    def test_a_subset_moves_the_standardised_columns(self):
        """The reason this machinery exists. Dropping an arm changes the mean
        and the deviation the z-score is taken against, so the same participant
        has a different value in the two studies."""
        part = self.study('s1', ['private', 'public'])
        built = perstudy.build(part, 'messages')['tables']['chat_by_partner']
        pooled = {self.key(r): r for r in self.pooled}
        moved = set()
        for row in built:
            against = pooled[self.key(row)]
            for column in self.SCALED:
                if row.get(column) != against.get(column):
                    moved.add(column)
        self.assertEqual(moved, set(self.SCALED),
                         'the standardised columns did not change, so they were '
                         'not recomputed on this study\'s sample')

    def test_the_two_studies_disagree_about_the_same_participant(self):
        first = perstudy.build(self.study('s1', ['private', 'public']),
                               'messages')['tables']['chat_by_partner']
        second = perstudy.build(
            self.study('s2', ['private', 'private_no_dwl']),
            'messages')['tables']['chat_by_partner']
        shared = {self.key(r): r for r in first}
        overlap = [r for r in second if self.key(r) in shared]
        self.assertTrue(overlap, 'the studies share no row, so the fixture is '
                                 'wrong')
        differing = [r for r in overlap
                     if r['nlp_sent_clout_100']
                     != shared[self.key(r)]['nlp_sent_clout_100']]
        self.assertTrue(differing,
                        'a baseline participant scored the same in both '
                        'studies, so the scale did not follow the sample')

    def test_it_is_written_outside_the_folder_the_do_files_glob(self):
        """`01_prepare.do` globs output/datasets for *_chat_by_partner_nlp.csv
        and aborts when it matches more than one file."""
        study = self.study('s1', ['private', 'public'])
        result = perstudy.write(study, 'messages')
        datasets = self.workspace / 'output' / 'datasets'
        self.assertEqual(
            len(list(datasets.glob('*_chat_by_partner_nlp.csv'))), 1,
            'a second file landed where the do-files look for exactly one')
        self.assertTrue(any(p.name == 'study.json' for p in result['paths']))
        for path in result['paths']:
            self.assertTrue(path.is_file())

    def test_the_record_says_what_the_sample_was(self):
        import json

        study = self.study('s1', ['private', 'public'])
        perstudy.write(study, 'messages')
        record = json.loads(
            (perstudy.directory(study) / 'study.json').read_text(
                encoding='utf-8'))
        self.assertEqual(record['n_groups'], 24)
        self.assertEqual(record['treatments'], ['private', 'public'])

    def test_an_arm_nobody_wrote_in_is_refused_with_a_reason(self):
        missing = self.study('s9', ['nonexistent', 'also_missing'])
        with self.assertRaises(perstudy.StudyBuildError) as ctx:
            perstudy.build(missing, 'messages')
        self.assertIn('nonexistent', str(ctx.exception))


class CarriedColumnTests(unittest.TestCase):
    """The paid columns are copied, never recomputed."""

    def test_rubric_and_topic_columns_are_recognised(self):
        rows = [{'nlp_sent_wc': '3', 'nlp_sent_llm_clout': '70',
                 'nlp_sent_topics': 'a|b', 'nlp_sent_clout_100': '50'}]
        self.assertEqual(sorted(perstudy.carried_columns(rows)),
                         ['nlp_sent_llm_clout', 'nlp_sent_topics'])

    def test_a_standardised_column_is_not_carried(self):
        """It has to be recomputed, not copied — that is the whole point."""
        rows = [{'nlp_sent_clout_100': '50', 'nlp_sent_clout_z': '0'}]
        self.assertEqual(perstudy.carried_columns(rows), [])


class SilentGroupTests(unittest.TestCase):
    """A triad that exchanged nothing is still in the sample.

    Selecting a study's groups from the messages looked obvious and was the one
    mistake this whole tool exists to point at: a sample conditional on having
    spoken. On the real corpus it quietly dropped six randomised triads.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(self.tmp.name)
        corpus(self.workspace)
        # One private triad that never wrote: present in both grafting tables,
        # absent from the messages, exactly as the merge leaves it.
        merged = self.workspace / 'output' / 'merged'
        for name, key in (('chat_by_partner',
                           ('focal_id_in_group', 'partner_id_in_group')),
                          ('chat_aggregated', ('focal_id_in_group',))):
            path = merged / f'messages_{name}.csv'
            rows = _read(path)
            template = dict(rows[0])
            extra = []
            for sender in (1, 2, 3):
                partners = [p for p in (1, 2, 3) if p != sender]
                for partner in (partners if len(key) == 2 else [None]):
                    row = dict(template)
                    row.update({'group_uid': 'silent-g000',
                                'treatment': 'private',
                                'focal_id_in_group': str(sender),
                                'sent_transcript_text': ''})
                    if partner is not None:
                        row['partner_id_in_group'] = str(partner)
                    extra.append(row)
            _write(path, rows + extra)
        config.use_workspace(self.workspace)
        config.use_experiment(em.Experiment())

    def study(self):
        return studies.parse([{'slug': 's1',
                               'treatments': ['private', 'public'],
                               'baseline': 'private'}])[0]

    def test_a_silent_triad_is_in_the_study(self):
        built = perstudy.build(self.study(), 'messages')
        groups = {r['group_uid'] for r in built['tables']['chat_by_partner']}
        self.assertIn('silent-g000', groups,
                      'a triad that said nothing was dropped from the sample')

    def test_it_is_counted_and_named_as_silent(self):
        census = perstudy.build(self.study(), 'messages')['census']
        self.assertEqual(census['n_silent_groups'], 1)
        # And it is in the group count, because it is in the sample.
        self.assertEqual(census['n_groups'],
                         sum(census['groups_per_treatment'].values()))

    def test_a_row_with_no_group_is_left_out(self):
        """Never-grouped participants have no partner and no conversation."""
        path = self.workspace / 'output' / 'merged' / 'messages_chat_by_partner.csv'
        rows = _read(path)
        stray = dict(rows[0])
        stray.update({'group_uid': '', 'treatment': 'private'})
        _write(path, rows + [stray])
        built = perstudy.build(self.study(), 'messages')
        self.assertTrue(all(r['group_uid']
                            for r in built['tables']['chat_by_partner']))


class StataProfileTests(unittest.TestCase):
    """The experimenter's own layout, which his do-files are written against."""

    def setUp(self):
        from chatlens.core import stata_profile

        self.sp = stata_profile

    def test_the_layout_is_his_hundred_and_eleven(self):
        self.assertEqual(len(self.sp.layout()), 111)
        self.assertEqual(len(set(self.sp.layout())), 111)

    def test_every_name_is_one_stata_accepts(self):
        """His script asserts this at runtime; here it is a test, so a
        researcher's run does not abort to tell us."""
        self.assertEqual(self.sp.problems(self.sp.layout()), [])

    def test_the_checks_catch_what_stata_would_refuse(self):
        """Each fault is named. A dotted name trips two of them — it is both a
        dot and not a legal identifier — so the count is not the assertion."""
        found = ' | '.join(self.sp.problems(
            ['a' * 33, 'has.dot', '9leading', 'ok', 'OK']))
        self.assertIn('33 characters', found)
        self.assertIn('contains a dot', found)
        self.assertIn('9leading', found)
        self.assertIn('appears twice', found)
        self.assertEqual(self.sp.problems(['ok', 'also_fine', 'v2']), [])

    def test_a_choice_is_resolved_to_the_player_it_points_at(self):
        """`Left` and `Right` are seats, not people: the export never says who
        was supported."""
        row = {self.sp.MAIN + 'player.id_in_group': '1',
               self.sp.MAIN + 'player.decision_choice': 'Left'}
        values = self.sp.choice_values(row)
        # Player 1's left partner is player 3.
        self.assertEqual(values['decision_target_id'], '3')
        self.assertEqual(values['decision_target_color'], 'Purple')

    def test_supporting_nobody_is_not_a_missing_value(self):
        row = {self.sp.MAIN + 'player.id_in_group': '2',
               self.sp.MAIN + 'player.decision_choice': 'NoOne'}
        self.assertEqual(
            self.sp.choice_values(row)['decision_target_id'], 'NoOne')

    def test_a_received_promise_points_at_the_one_who_received_it(self):
        """`split_you` sent means the partner; received it means the reader."""
        row = {self.sp.MAIN + 'player.id_in_group': '1',
               self.sp.MAIN + 'player.signal_left': 'split_you',
               self.sp.MAIN + 'player.received_signal_left': 'split_you'}
        values = self.sp.choice_values(row)
        self.assertEqual(values['signal_left_target_id'], '3')
        self.assertEqual(values['received_signal_left_target_id'], '1')

    def test_the_first_mover_is_read_off_the_dyad(self):
        opener = {'nlp_dyad_first_sender_id_in_group': '2',
                  'focal_id_in_group': '2', 'partner_id_in_group': '3'}
        self.assertEqual(self.sp.first_mover(opener), '1')
        self.assertEqual(self.sp.first_mover({**opener,
                                              'focal_id_in_group': '3',
                                              'partner_id_in_group': '2'}), '0')

    def test_a_silent_pair_has_no_first_mover_rather_than_a_zero(self):
        """Nobody went first is not "the partner went first", and Stata reads
        the empty string as missing."""
        self.assertEqual(self.sp.first_mover(
            {'nlp_dyad_first_sender_id_in_group': '',
             'focal_id_in_group': '1', 'partner_id_in_group': '2'}), '')

    def test_the_channel_comes_from_the_messages(self):
        channels = self.sp.channels([
            {'group_uid': 'g', 'dyad_key': '1_2', 'channel': 'x-1_2'},
            {'group_uid': 'g', 'dyad_key': '1_2', 'channel': 'ignored'},
        ])
        self.assertEqual(channels[('g', '1_2')], 'x-1_2')

    def test_our_measures_are_appended_and_the_oTree_names_are_not(self):
        rows = [{self.sp.MAIN + 'player.treatment': 'private',
                 self.sp.MAIN + 'player.id_in_group': '1',
                 'group_uid': 'g', 'focal_id_in_group': '1',
                 'partner_id_in_group': '2', 'dyad_status': 'matched',
                 'nlp_sent_clout_100': '55'}]
        built = self.sp.build(rows)
        self.assertIn('nlp_sent_clout_100', built['columns'])
        # The dotted names are already in the table under his names.
        self.assertFalse([c for c in built['columns'] if '.' in c])
        self.assertEqual(built['rows'][0]['treatment'], 'private')

    def test_a_participant_with_no_treatment_is_left_out(self):
        """They were never in a triad, so they are in no study — and his
        resolved-target columns cannot be computed for them."""
        rows = [{self.sp.MAIN + 'player.treatment': '', 'group_uid': ''}]
        self.assertEqual(self.sp.build(rows)['rows'], [])


class StataFileTests(unittest.TestCase):
    """What lands in a study's `stata/` folder.

    The CSV is what the do-files read and what was asked for. The `.dta` beside
    it is so the same rows can be opened by double-clicking, with the variable
    labels; it is written only when pandas is installed and its absence is never
    an error, because the CSV is the deliverable.
    """

    def setUp(self):
        from chatlens.core import optional, perstudy, studies

        self.perstudy = perstudy
        self.optional = optional
        self.study = studies.Study('s1', 'Study one', ('a', 'b'), 'a')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _rows(self):
        """Two triads, one per arm, in the shape the layout needs."""
        from chatlens.core import stata_profile as sp

        out = []
        for group, treatment in (('g1', 'a'), ('g2', 'b')):
            for focal in ('1', '2', '3'):
                for partner in ('1', '2', '3'):
                    if focal == partner:
                        continue
                    out.append({
                        'group_uid': group,
                        'focal_id_in_group': focal,
                        'partner_id_in_group': partner,
                        'treatment': treatment,
                        sp.MAIN + 'player.treatment': treatment,
                        'session.code': 'sess',
                        'participant.code': f'p{group}{focal}',
                        'sent_transcript_text': 'i support you ' * 40,
                        'nlp_dyad_clout_z': '0.5',
                    })
        return out

    def test_the_csv_and_the_codebook_are_written(self):
        written = self.perstudy.write_stata(self.study, 'stem', self._rows(),
                                            root=self.root)
        names = [p.name for p in written]
        self.assertIn('stem_s1_goodshape.csv', names)
        self.assertIn('stem_s1_codebook.csv', names)
        for path in written:
            self.assertTrue(path.is_file())

    def test_raw_values_only_and_the_complete_file_adds_the_words(self):
        """The experimenter standardises himself, so the rescaled copies stay
        out; the complete file is the logit file plus the bag of words."""
        written = self.perstudy.write_stata(self.study, 'stem', self._rows(),
                                            root=self.root,
                                            bow_min_documents=2)
        by_name = {p.name: p for p in written}
        header = lambda name: next(csv.reader(
            by_name[name].open(encoding='utf-8-sig')))
        shaped = header('stem_s1_goodshape.csv')
        complete = header('stem_s1_complete.csv')
        self.assertNotIn('nlp_dyad_clout_z', shaped)
        self.assertEqual(complete[:len(shaped)], shaped)
        added = complete[len(shaped):]
        self.assertTrue(added)
        self.assertTrue(all(name.startswith('bow_') for name in added))
        self.assertIn('bow_i_support', added)

    def test_the_dta_is_written_when_pandas_is_there_and_reads_back(self):
        if not self.optional.have('pandas'):
            self.skipTest('pandas not installed')
        written = self.perstudy.write_stata(self.study, 'stem', self._rows(),
                                            root=self.root)
        dta = [p for p in written if p.suffix == '.dta']
        # One for the logit file, one for the file with the bag of words.
        self.assertEqual(len(dta), 2)

        import pandas as pd

        frame = pd.read_stata(dta[0])
        self.assertEqual(len(frame), len(self._rows()))
        with pd.io.stata.StataReader(dta[0]) as reader:
            labels = reader.variable_labels()
        self.assertTrue(all(labels.values()))

    def test_a_stata_file_that_cannot_be_written_is_not_an_error(self):
        """The CSV is the deliverable; the .dta is a convenience."""
        from chatlens.core import fulltables

        real = fulltables._write_dta

        def refuse(*_args, **_kw):
            raise ValueError('no')

        fulltables._write_dta = refuse
        try:
            written = self.perstudy.write_stata(self.study, 'stem',
                                                self._rows(), root=self.root)
        finally:
            fulltables._write_dta = real
        self.assertEqual([p.name for p in written],
                         ['stem_s1_goodshape.csv', 'stem_s1_complete.csv',
                          'stem_s1_codebook.csv'])
        self.assertFalse((self.root / 's1' / 'stata'
                          / 'stem_s1_goodshape.dta').exists())


class RegressorTests(unittest.TestCase):
    """The measures as regressors: raw, ordinal, topics, bag of words."""

    def setUp(self):
        from chatlens.core import regressors

        self.r = regressors

    def test_the_rescaled_copies_are_left_out(self):
        kept = self.r.raw_only(['nlp_sent_clout_raw', 'nlp_sent_clout_z',
                                'nlp_sent_clout_100', 'group_uid',
                                'bow_100'])
        self.assertEqual(kept, ['nlp_sent_clout_raw', 'group_uid', 'bow_100'])

    def test_only_shares_with_a_natural_zero_get_an_ordinal_version(self):
        chosen = self.r.ordinal_columns([
            'nlp_sent_pct_we', 'nlp_sent_pct_funcwords', 'nlp_sent_clout_raw',
            'nrc_sent_anger', 'nrc_sent_matched', 'nlp_sent_tone_raw'])
        self.assertEqual(chosen, ['nlp_sent_pct_we', 'nrc_sent_anger'])

    def test_one_is_absent_and_blank_stays_blank(self):
        rows = [{'x': v} for v in ('0', '', '1', '2', '3', '4', '5', '6')]
        label = self.r.ordinal(rows, 'x')
        self.assertEqual([r['x_lik'] for r in rows],
                         ['1', '', '2', '2', '3', '3', '4', '4'])
        self.assertIn('1 = 0', label)

    def test_a_category_never_present_is_all_ones(self):
        rows = [{'x': '0'}, {'x': '0'}, {'x': ''}]
        self.r.ordinal(rows, 'x')
        self.assertEqual([r['x_lik'] for r in rows], ['1', '1', ''])

    def test_topics_become_indicators(self):
        rows = [{'nlp_sent_topics': 'Commitment|Payoff Reasoning',
                 'nlp_sent_wc': '12'},
                {'nlp_sent_topics': 'Commitment', 'nlp_sent_wc': '3'},
                {'nlp_sent_topics': '', 'nlp_sent_wc': ''}]
        names = self.r.topic_indicators(rows, 'nlp_sent_topics')
        self.assertEqual(set(names), {'topic_sent_commitment',
                                      'topic_sent_payoff_reasoning'})
        self.assertEqual([r['topic_sent_payoff_reasoning'] for r in rows],
                         ['1', '0', ''])

    def test_the_bag_of_words_counts_unigrams_and_bigrams(self):
        rows = [{'t': 'Yellow -> Orange: i support you\nYellow -> Orange: '
                      'i support you'}] * 3 + [{'t': ''}]
        names = self.r.bag_of_words(rows, 't', min_documents=2)
        by_term = {term: name for name, term in names.items()}
        self.assertIn('i support', by_term)
        self.assertIn('i', by_term)
        # The speaker prefix is structure, not speech.
        self.assertNotIn('yellow', by_term)
        self.assertEqual(rows[0][by_term['i support']], '2')
        self.assertEqual(rows[3][by_term['i']], '')

    def test_no_bigram_spans_two_messages(self):
        """The last word of one message and the first of the next were never
        written as a phrase."""
        rows = [{'t': 'hello there\nyou win'}] * 2
        names = self.r.bag_of_words(rows, 't', min_documents=1)
        self.assertNotIn('there you', names.values())
        self.assertIn('you win', names.values())

    def test_a_rare_term_gets_no_column(self):
        rows = [{'t': 'common rare'}, {'t': 'common'}]
        names = self.r.bag_of_words(rows, 't', min_documents=2)
        self.assertEqual(list(names.values()), ['common'])


class DeclaredSessionsTests(unittest.TestCase):
    """`[sample] sessions`: the experimenter says which sessions are the study."""

    def test_the_list_is_read_cleaned_and_kept_in_order(self):
        loaded = em.Experiment({'sample': {'sessions': ['b', ' a ', 'b', '']}})
        self.assertEqual(loaded.sessions, ('b', 'a'))

    def test_no_declaration_means_no_restriction(self):
        self.assertEqual(em.Experiment({}).sessions, ())

    def test_a_mistyped_key_is_refused(self):
        with self.assertRaises(em.ConfigError):
            em.Experiment({'sample': {'sesions': ['a']}}, path=Path('x.toml'))

    def test_the_adapter_drops_other_sessions_and_says_how_many(self):
        from chatlens.adapters import otree_coalition as oc

        def player(session, code):
            return {'session.code': session, 'participant.code': code,
                    'participant.label': 'a' * 24,
                    oc.MAIN + 'player.id_in_group': '1',
                    'participant.part1_group_id': '7'}

        rows = [player('keep', 'c1'), player('pilot', 'c2')]
        original = oc.is_grouped
        oc.is_grouped = lambda row: True
        try:
            kept, dropped = oc.select_participants(rows, sessions=('keep',))
        finally:
            oc.is_grouped = original
        self.assertEqual([r['participant.code'] for r in kept], ['c1'])
        self.assertEqual(dropped['outside_declared_sessions'], 1)

    def test_it_round_trips_through_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'experiment.toml'
            loaded = em.Experiment({'experiment': {'name': 'x'}})
            loaded.set('sample', {'sessions': ['w0k1pp1v', 'um435zd7']})
            loaded.save(path)
            again = em.load(Path(tmp))
        self.assertEqual(again.sessions, ('w0k1pp1v', 'um435zd7'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
