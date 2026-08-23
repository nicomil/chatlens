"""Tests for the text analysis (src/).

They need no credentials, no network and no optional dependencies: the LLM
rubric is exercised on its pure parts (building the prompt and combining the
ratings), while no API call is ever made.

    python tests/test_analysis.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import aggregate as agg  # noqa: E402
from src import lexicons, text_metrics, topicgpt as topicgpt_runner  # noqa: E402


class TokenizerTests(unittest.TestCase):
    def test_contractions_stay_whole(self):
        self.assertEqual(
            text_metrics.tokenize("I don't know, you're right"),
            ['i', "don't", 'know', "you're", 'right'],
        )

    def test_punctuation_and_case(self):
        self.assertEqual(text_metrics.tokenize('Hello!! WORLD?'), ['hello', 'world'])

    def test_empty_input(self):
        self.assertEqual(text_metrics.tokenize(''), [])
        self.assertEqual(text_metrics.tokenize(None), [])


class AdverbHeuristicTests(unittest.TestCase):
    def test_ly_words_that_are_not_adverbs(self):
        for token in ('family', 'reply', 'supply', 'apply', 'ugly'):
            self.assertFalse(lexicons.is_adverb(token), msg=token)

    def test_genuine_ly_adverbs(self):
        for token in ('quickly', 'honestly', 'seriously'):
            self.assertTrue(lexicons.is_adverb(token), msg=token)

    def test_explicit_list(self):
        self.assertTrue(lexicons.is_adverb('very'))


class CountTests(unittest.TestCase):
    def test_categories_overlap_by_design(self):
        """"don't" is both an auxiliary and a negation, as in LIWC."""
        counts = text_metrics.count_categories("don't")
        self.assertEqual(counts['wc'], 1)
        self.assertEqual(counts['auxverb'], 1)
        self.assertEqual(counts['negate'], 1)

    def test_pronoun_subsets(self):
        counts = text_metrics.count_categories('I told you we should')
        self.assertEqual(counts['i'], 1)
        self.assertEqual(counts['you'], 1)
        self.assertEqual(counts['we'], 1)
        # ppron is the union of the personal subsets.
        self.assertEqual(counts['ppron'], 3)

    def test_sum_counts_matches_concatenated_text(self):
        parts = ['I will support you', "but I don't trust him", 'the deal is fine']
        summed = text_metrics.sum_counts(
            text_metrics.count_categories(p) for p in parts
        )
        joined = text_metrics.count_categories(' '.join(parts))
        for key in ('wc', 'ppron', 'auxverb', 'negate', 'article', 'i', 'you'):
            self.assertEqual(summed[key], joined[key], msg=key)


class AnalyticFormulaTests(unittest.TestCase):
    """The CDI is a published formula: here it is checked to the letter."""

    def test_cdi_matches_hand_computation(self):
        text = 'the deal'  # 2 words: 1 article, no other function word
        counts = text_metrics.count_categories(text)
        self.assertEqual(counts['wc'], 2)
        self.assertEqual(counts['article'], 1)
        scores = text_metrics.score_counts(counts)
        # CDI = 30 + 50 (articles) - 0 = 80
        self.assertAlmostEqual(scores['analytic_cdi'], 80.0, places=6)

    def test_cdi_drops_with_pronouns_and_negations(self):
        formal = text_metrics.score_counts(
            text_metrics.count_categories('the allocation of the payoff')
        )
        informal = text_metrics.score_counts(
            text_metrics.count_categories("i really don't know")
        )
        self.assertGreater(formal['analytic_cdi'], informal['analytic_cdi'])

    def test_empty_text_gives_baseline(self):
        scores = text_metrics.score_counts(text_metrics.count_categories(''))
        self.assertEqual(scores['wc'], 0)
        self.assertAlmostEqual(scores['analytic_cdi'], 30.0, places=6)


class CompositeDirectionTests(unittest.TestCase):
    """The composites' signs must follow the reference literature."""

    def _score(self, text):
        return text_metrics.score_counts(text_metrics.count_categories(text))

    def test_clout_higher_when_focused_on_the_other(self):
        other_focused = self._score('you and we should both win together')
        self_focused = self._score('i think i cannot do it')
        self.assertGreater(other_focused['clout_raw'], self_focused['clout_raw'])

    def test_authenticity_higher_with_self_reference_and_exclusives(self):
        authentic = self._score('i want the points but i like you')
        guarded = self._score('the group went and the deal failed badly')
        self.assertGreater(
            authentic['authenticity_raw'], guarded['authenticity_raw']
        )

    def test_tone_does_not_saturate_on_one_emotion_word(self):
        """The difference between percentages must not jump to +/-100 on one word."""
        scores = self._score('great to see the rest of the message here ok')
        self.assertLess(abs(scores['tone_raw']), 100.0)
        self.assertEqual(scores['has_emotion_words'], 1)

    def test_gibberish_is_flagged_as_non_language(self):
        """With no function words the CDI stays high: spot it, do not believe it."""
        gibberish = self._score('shshahah dhsrhahah qwkjhas zxcvbn mnbvcx')
        self.assertEqual(gibberish['low_language_flag'], 1)
        self.assertEqual(gibberish['pct_funcwords'], 0.0)
        # And this is exactly the case where the CDI would look maximal.
        self.assertGreater(gibberish['analytic_cdi'], 25.0)

    def test_real_conversation_is_not_flagged(self):
        real = self._score(
            'If you want to do that, we can support each other, '
            'but one person must be left out'
        )
        self.assertEqual(real['low_language_flag'], 0)
        self.assertGreater(real['pct_funcwords'], 30.0)

    def test_short_text_is_never_flagged(self):
        """On fewer than five words the indicator is not reliable."""
        self.assertEqual(self._score('blah')['low_language_flag'], 0)

    def test_tone_balance_flagged_when_no_emotion_words(self):
        scores = self._score('the allocation of the payoff')
        self.assertEqual(scores['has_emotion_words'], 0)
        self.assertEqual(scores['tone_balance'], '')


class StandardizeTests(unittest.TestCase):
    def test_z_scores_have_zero_mean_unit_sd(self):
        rows = [
            dict(wc=10, analytic_cdi=v, clout_raw=0.0,
                 authenticity_raw=0.0, tone_raw=0.0)
            for v in (10.0, 20.0, 30.0, 40.0)
        ]
        text_metrics.standardize(rows)
        zs = [r['analytic_z'] for r in rows]
        # The values come out rounded to six decimals: the tolerance reflects that.
        self.assertAlmostEqual(sum(zs) / len(zs), 0.0, places=6)
        self.assertAlmostEqual(
            (sum(z * z for z in zs) / (len(zs) - 1)) ** 0.5, 1.0, places=6
        )

    def test_empty_units_are_left_blank(self):
        rows = [
            dict(wc=0, analytic_cdi=30.0, clout_raw=0.0,
                 authenticity_raw=0.0, tone_raw=0.0),
            dict(wc=5, analytic_cdi=10.0, clout_raw=0.0,
                 authenticity_raw=0.0, tone_raw=0.0),
            dict(wc=5, analytic_cdi=50.0, clout_raw=0.0,
                 authenticity_raw=0.0, tone_raw=0.0),
        ]
        text_metrics.standardize(rows)
        self.assertEqual(rows[0]['analytic_z'], '')
        self.assertNotEqual(rows[1]['analytic_z'], '')

    def test_constant_values_map_to_the_midpoint(self):
        rows = [
            dict(wc=5, analytic_cdi=7.0, clout_raw=0.0,
                 authenticity_raw=0.0, tone_raw=0.0)
            for _ in range(3)
        ]
        text_metrics.standardize(rows)
        self.assertEqual(rows[0]['analytic_100'], 50.0)


def make_message(uid, sender, receiver, body, timestamp, treatment='private'):
    return dict(
        group_uid=uid,
        sender_id_in_group=str(sender),
        receiver_id_in_group=str(receiver),
        dyad_key=f'{min(sender, receiver)}_{max(sender, receiver)}',
        sender_color='X', receiver_color='Y',
        treatment=treatment,
        timestamp=str(timestamp),
        body=body,
    )


SAMPLE = [
    make_message('g1', 1, 2, 'I will support you', 100),
    make_message('g1', 2, 1, 'ok deal', 110),
    make_message('g1', 1, 3, "I don't trust them", 120),
    make_message('g2', 2, 3, 'the payoff is fine', 200),
]


class AggregationTests(unittest.TestCase):
    def setUp(self):
        self.enriched = agg.analyze_messages(SAMPLE)
        self.features = agg.aggregate_all(self.enriched)

    def test_word_count_is_conserved_across_levels(self):
        total = sum(m['wc'] for m in self.enriched)
        for level in agg.LEVELS:
            self.assertEqual(
                sum(r['wc'] for r in self.features[level]), total, msg=level
            )

    def test_message_count_is_conserved_across_levels(self):
        for level in agg.LEVELS:
            self.assertEqual(
                sum(r['n_messages'] for r in self.features[level]),
                len(SAMPLE), msg=level,
            )

    def test_directed_dyads_are_not_symmetric(self):
        directed = {
            (r['group_uid'], r['sender_id_in_group'], r['receiver_id_in_group']): r
            for r in self.features['dyad_directed']
        }
        # 1->2 and 2->1 are distinct units, with different texts.
        self.assertIn(('g1', '1', '2'), directed)
        self.assertIn(('g1', '2', '1'), directed)
        self.assertNotEqual(
            directed[('g1', '1', '2')]['wc'], directed[('g1', '2', '1')]['wc']
        )

    def test_undirected_dyad_sums_both_directions(self):
        directed = {
            (r['sender_id_in_group'], r['receiver_id_in_group']): r
            for r in self.features['dyad_directed'] if r['group_uid'] == 'g1'
        }
        dyad = next(
            r for r in self.features['dyad']
            if r['group_uid'] == 'g1' and r['dyad_key'] == '1_2'
        )
        self.assertEqual(
            dyad['wc'], directed[('1', '2')]['wc'] + directed[('2', '1')]['wc']
        )

    def test_indices_come_from_summed_counts_not_averaged_percentages(self):
        """The group's CDI is that of the joined text, not the per-message mean."""
        group = next(r for r in self.features['group'] if r['group_uid'] == 'g1')
        joined = ' '.join(m['body'] for m in SAMPLE if m['group_uid'] == 'g1')
        expected = text_metrics.score_counts(text_metrics.count_categories(joined))
        self.assertAlmostEqual(group['analytic_cdi'], expected['analytic_cdi'], places=6)

    def test_duration_and_gaps(self):
        group = next(r for r in self.features['group'] if r['group_uid'] == 'g1')
        self.assertEqual(group['duration_seconds'], 20.0)
        self.assertEqual(group['n_messages'], 3)


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.features = agg.aggregate_all(agg.analyze_messages(SAMPLE))

    def test_by_partner_gets_sent_recv_and_dyad_blocks(self):
        rows = [dict(group_uid='g1', focal_id_in_group='1',
                     partner_id_in_group='2', dyad_key='1_2')]
        agg.merge_into_by_partner(rows, self.features)
        row = rows[0]
        # Sent from 1 to 2: "I will support you" = 4 words.
        self.assertEqual(row['nlp_sent_wc'], 4)
        # Received from 2: "ok deal" = 2 words.
        self.assertEqual(row['nlp_recv_wc'], 2)
        self.assertEqual(row['nlp_dyad_wc'], 6)

    def test_missing_unit_yields_blank_columns_not_crash(self):
        rows = [dict(group_uid='unknown', focal_id_in_group='1',
                     partner_id_in_group='2', dyad_key='1_2')]
        agg.merge_into_by_partner(rows, self.features)
        self.assertEqual(rows[0]['nlp_sent_wc'], '')
        self.assertEqual(rows[0]['nlp_dyad_analytic_z'], '')

    def test_rubric_columns_reach_the_final_datasets(self):
        """The ratings are paid for: they must not stop at the intermediate files."""
        group_row = next(
            r for r in self.features['group'] if r['group_uid'] == 'g1'
        )
        group_row['llm_analytic'] = 42.0
        group_row['llm_contains_support_commitment'] = 1

        rows = [dict(group_uid='g1', focal_id_in_group='1')]
        agg.merge_into_aggregated(rows, self.features)
        self.assertEqual(rows[0]['nlp_group_llm_analytic'], 42.0)
        self.assertEqual(rows[0]['nlp_group_llm_contains_support_commitment'], 1)

    def test_aggregated_gets_sender_and_group_blocks(self):
        rows = [dict(group_uid='g1', focal_id_in_group='1')]
        agg.merge_into_aggregated(rows, self.features)
        # 1 wrote "I will support you" and "I don't trust them" = 8 words.
        self.assertEqual(rows[0]['nlp_sent_wc'], 8)
        self.assertEqual(rows[0]['nlp_group_n_messages'], 3)


class TopicGPTAdapterTests(unittest.TestCase):
    def test_documents_carry_a_rejoinable_id(self):
        documents = topicgpt_runner.build_documents(SAMPLE, 'dyad_directed')
        ids = {d['id'] for d in documents}
        self.assertIn('g1|1|2', ids)
        self.assertIn('g2|2|3', ids)
        for document in documents:
            self.assertTrue(document['text'].strip())

    def test_group_level_documents_join_the_whole_triad(self):
        documents = topicgpt_runner.build_documents(SAMPLE, 'group')
        by_id = {d['id']: d for d in documents}
        self.assertEqual(by_id['g1']['n_messages'], 3)

    def test_parse_assignments_reads_the_official_response_format(self):
        import json
        import tempfile

        rows = [
            {'id': 'g1|1|2',
             'responses': "[1] Direct Offer: promises support\n[1] Trust Appeal: x"},
            {'id': 'g1|2|1', 'responses': 'no topics here'},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'a.jsonl'
            path.write_text(
                '\n'.join(json.dumps(r) for r in rows), encoding='utf-8'
            )
            parsed = topicgpt_runner.parse_assignments(path)

        self.assertEqual(parsed['g1|1|2']['n_topics'], 2)
        self.assertEqual(parsed['g1|1|2']['topic_primary'], 'Direct Offer')
        self.assertEqual(parsed['g1|2|1']['n_topics'], 0)

    def test_rollup_from_directed_to_group_unions_topics(self):
        assignments = {
            'g1|1|2': dict(topics='Offer', topic_primary='Offer', n_topics=1),
            'g1|1|3': dict(topics='Offer|Threat', topic_primary='Offer', n_topics=2),
            'g2|2|3': dict(topics='Trust', topic_primary='Trust', n_topics=1),
        }
        rolled = topicgpt_runner.rollup_topics(assignments, 'dyad_directed', 'group')
        self.assertEqual(rolled[('g1',)]['n_topics'], 2)
        self.assertEqual(set(rolled[('g1',)]['topics'].split('|')), {'Offer', 'Threat'})
        self.assertEqual(rolled[('g2',)]['topics'], 'Trust')

    def test_missing_installation_gives_actionable_error(self):
        with self.assertRaises(topicgpt_runner.TopicGPTUnavailable) as ctx:
            topicgpt_runner.check_installation(Path('/path/that/does/not/exist'))
        self.assertIn('topicgpt', str(ctx.exception).lower())


class LLMRubricPureTests(unittest.TestCase):
    """The parts of the rubric that never touch the network."""

    def setUp(self):
        from src import llm_rubric
        self.llm = llm_rubric

    def test_units_skip_empty_transcripts(self):
        features = [
            dict(group_uid='g1', sender_id_in_group='1',
                 receiver_id_in_group='2', n_messages=2, treatment='private'),
            dict(group_uid='g1', sender_id_in_group='3',
                 receiver_id_in_group='2', n_messages=0, treatment='private'),
        ]
        transcripts = {('g1', '1', '2'): 'X -> Y: hello', ('g1', '3', '2'): '   '}
        units = self.llm.build_units(features, 'dyad_directed', transcripts)
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].key, ('g1', '1', '2'))

    def test_request_carries_transcript_and_caches_the_system_prompt(self):
        unit = self.llm.RubricUnit(
            key=('g1', '1', '2'), unit='dyad_directed',
            transcript='X -> Y: I will support you', n_messages=1,
            treatment='public', target='the sender',
        )
        params = self.llm._request_params(unit, 'claude-opus-5')
        self.assertEqual(params['model'], 'claude-opus-5')
        self.assertEqual(
            params['system'][0]['cache_control'], {'type': 'ephemeral'}
        )
        self.assertIn('I will support you', params['messages'][0]['content'])
        self.assertIn('public', params['messages'][0]['content'])

    def test_summary_averages_scores_and_reports_dispersion(self):
        unit = self.llm.RubricUnit(
            key=('g1', '1', '2'), unit='dyad_directed', transcript='x',
            n_messages=1, treatment='private', target='the sender',
        )
        judgements = [
            dict(analytic=40, clout=60, authenticity=50, tone=55,
                 contains_support_commitment=1, contains_support_request=0,
                 insufficient_text=0, rationale='a', error='', model='m'),
            dict(analytic=50, clout=70, authenticity=50, tone=45,
                 contains_support_commitment=1, contains_support_request=1,
                 insufficient_text=0, rationale='b', error='', model='m'),
        ]
        row = self.llm._summarize(unit, judgements)
        self.assertEqual(row['group_uid'], 'g1')
        self.assertEqual(row['llm_analytic'], 45.0)
        self.assertAlmostEqual(row['llm_analytic_sd'], 7.071, places=2)
        self.assertEqual(row['llm_n_judgements'], 2)
        # A support commitment recognised by both ratings.
        self.assertEqual(row['llm_contains_support_commitment'], 1)
        # A request recognised by only one: there is no majority.
        self.assertEqual(row['llm_contains_support_request'], 0)

    def test_failed_judgements_are_counted_not_silently_dropped(self):
        unit = self.llm.RubricUnit(
            key=('g1',), unit='group', transcript='x', n_messages=1,
            treatment='private', target='all three participants',
        )
        judgements = [
            dict(analytic=40, clout=40, authenticity=40, tone=40,
                 contains_support_commitment=0, contains_support_request=0,
                 insufficient_text=0, rationale='a', error='', model='m'),
            dict(analytic=None, clout=None, authenticity=None, tone=None,
                 contains_support_commitment=None, contains_support_request=None,
                 insufficient_text=None, rationale='', error='refusal:cyber'),
        ]
        row = self.llm._summarize(unit, judgements)
        self.assertEqual(row['llm_n_judgements'], 1)
        self.assertEqual(row['llm_n_errors'], 1)
        self.assertIn('refusal', row['llm_errors'])


class ProviderSelectionTests(unittest.TestCase):
    """The rubric must be able to run without an Anthropic key."""

    def setUp(self):
        import os
        from src import llm_rubric
        self.llm = llm_rubric
        self.os = os
        self._saved = {
            k: os.environ.pop(k, None)
            for k in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY')
        }
        # Ollama depends on what is running on the machine: it is neutralised
        # so the test measures the selection logic, not the environment.
        self._real_probe = llm_rubric._ollama_is_running
        llm_rubric._ollama_is_running = lambda: False

    def tearDown(self):
        self.llm._ollama_is_running = self._real_probe
        for key, value in self._saved.items():
            if value is None:
                self.os.environ.pop(key, None)
            else:
                self.os.environ[key] = value

    def test_openai_key_alone_is_enough(self):
        self.os.environ['OPENAI_API_KEY'] = 'sk-fake'
        self.assertEqual(self.llm.resolve_provider(None), 'openai')
        self.assertTrue(self.llm.has_credentials())

    def test_anthropic_preferred_when_both_present(self):
        self.os.environ['OPENAI_API_KEY'] = 'sk-fake'
        self.os.environ['ANTHROPIC_API_KEY'] = 'sk-ant-fake'
        self.assertEqual(self.llm.resolve_provider(None), 'anthropic')

    def test_local_backend_needs_no_key(self):
        self.llm._ollama_is_running = lambda: True
        self.assertEqual(self.llm.resolve_provider(None), 'ollama')
        self.assertIsNone(self.llm.PROVIDERS['ollama']['env_key'])

    def test_no_provider_lists_every_option(self):
        with self.assertRaises(SystemExit) as ctx:
            self.llm.resolve_provider(None)
        message = str(ctx.exception)
        self.assertIn('OPENAI_API_KEY', message)
        self.assertIn('ANTHROPIC_API_KEY', message)
        self.assertIn('ollama', message)

    def test_explicit_provider_without_its_key_is_refused(self):
        self.os.environ['OPENAI_API_KEY'] = 'sk-fake'
        with self.assertRaises(SystemExit) as ctx:
            self.llm.resolve_provider('anthropic')
        self.assertIn('ANTHROPIC_API_KEY', str(ctx.exception))

    def test_each_provider_has_a_default_model(self):
        for name in self.llm.PROVIDERS:
            self.assertTrue(self.llm.default_model_for(name), msg=name)

    def test_json_instruction_names_every_field(self):
        """The OpenAI-compatible path describes the schema in the prompt."""
        instruction = self.llm._json_instruction()
        for field in self.llm.SCALE_FIELDS + self.llm.FLAG_FIELDS:
            self.assertIn(field, instruction, msg=field)


class RubricCacheTests(unittest.TestCase):
    """Ratings cost money: once paid for, they are not paid for again."""

    def _setup(self):
        import os
        from src import llm_rubric
        self.llm = llm_rubric
        self.os = os
        os.environ['OPENAI_API_KEY'] = 'sk-fake'
        self._real_score = llm_rubric.score_unit
        self._real_client = llm_rubric.make_client
        self.calls = []

        def fake_score(client, unit, model, provider):
            self.calls.append(unit.key)
            return dict(
                analytic=40, clout=50, authenticity=60, tone=55,
                contains_support_commitment=1, contains_support_request=0,
                insufficient_text=0, rationale='x', error='', model=model,
            )

        llm_rubric.score_unit = fake_score
        llm_rubric.make_client = lambda provider: object()

    def _teardown(self):
        self.llm.score_unit = self._real_score
        self.llm.make_client = self._real_client
        self.os.environ.pop('OPENAI_API_KEY', None)

    def _units(self):
        return [
            self.llm.RubricUnit(key=('g1',), unit='group', transcript='ciao a tutti',
                                n_messages=2, treatment='private',
                                target='all three participants'),
            self.llm.RubricUnit(key=('g2',), unit='group', transcript='altro testo',
                                n_messages=3, treatment='public',
                                target='all three participants'),
        ]

    def test_second_run_reuses_and_does_not_pay_again(self):
        import tempfile
        from pathlib import Path as P

        self._setup()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                cache = P(tmpdir) / 'rubric.jsonl'
                units = self._units()

                rows1, reused1 = self.llm.score_units(
                    units, provider='openai', cache_path=cache)
                self.assertEqual(len(rows1), 2)
                self.assertEqual(reused1, 0)
                self.assertEqual(len(self.calls), 2)

                self.calls.clear()
                rows2, reused2 = self.llm.score_units(
                    units, provider='openai', cache_path=cache)
                self.assertEqual(reused2, 2)
                self.assertEqual(self.calls, [], 'it called the API for nothing')
                self.assertEqual(rows1, rows2)
        finally:
            self._teardown()

    def test_changed_transcript_is_not_reused(self):
        """New data must be scored again, not fished out of the cache."""
        import tempfile
        from pathlib import Path as P

        self._setup()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                cache = P(tmpdir) / 'rubric.jsonl'
                units = self._units()
                self.llm.score_units(units, provider='openai', cache_path=cache)

                self.calls.clear()
                units[0].transcript = 'modified text'
                _rows, reused = self.llm.score_units(
                    units, provider='openai', cache_path=cache)
                self.assertEqual(reused, 1)
                self.assertEqual(self.calls, [('g1',)])
        finally:
            self._teardown()

    def test_more_replicates_is_a_different_measurement(self):
        import tempfile
        from pathlib import Path as P

        self._setup()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                cache = P(tmpdir) / 'rubric.jsonl'
                units = self._units()
                self.llm.score_units(units, provider='openai', replicates=1,
                                     cache_path=cache)
                self.calls.clear()
                _rows, reused = self.llm.score_units(
                    units, provider='openai', replicates=2, cache_path=cache)
                self.assertEqual(reused, 0)
                self.assertEqual(len(self.calls), 4)
        finally:
            self._teardown()

    def test_failed_evaluations_are_not_cached(self):
        """A temporary error must not stay frozen for ever."""
        import tempfile
        from pathlib import Path as P

        self._setup()
        try:
            def failing(client, unit, model, provider):
                self.calls.append(unit.key)
                return dict(
                    analytic=None, clout=None, authenticity=None, tone=None,
                    contains_support_commitment=None,
                    contains_support_request=None, insufficient_text=None,
                    rationale='', error='api_status_500',
                )

            self.llm.score_unit = failing
            with tempfile.TemporaryDirectory() as tmpdir:
                cache = P(tmpdir) / 'rubric.jsonl'
                units = self._units()
                self.llm.score_units(units, provider='openai', cache_path=cache)
                self.calls.clear()
                _rows, reused = self.llm.score_units(
                    units, provider='openai', cache_path=cache)
                self.assertEqual(reused, 0)
                self.assertEqual(len(self.calls), 2)
        finally:
            self._teardown()

    def test_truncated_cache_line_is_ignored(self):
        """An interruption mid-write must not make everything unreadable."""
        import tempfile
        from pathlib import Path as P

        self._setup()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                cache = P(tmpdir) / 'rubric.jsonl'
                units = self._units()
                self.llm.score_units(units, provider='openai', cache_path=cache)
                with cache.open('a', encoding='utf-8') as handle:
                    handle.write('{"signature": "trunc')

                entries = self.llm.load_cache(cache)
                self.assertEqual(len(entries), 2)
        finally:
            self._teardown()


def analysis_args(outdir, merged_dir, stem, **overrides):
    """A namespace equivalent to the one run.py builds."""
    from types import SimpleNamespace

    base = dict(
        merged_dir=merged_dir, outdir=outdir, stem=stem, verbose=False,
        llm=False, llm_provider=None, llm_models=None, llm_replicates=1,
        llm_levels=['group'], llm_batch=False, llm_dry_run=False,
        topics=False, topicgpt_repo='/path/that/does/not/exist',
        topicgpt_api='openai', topicgpt_model='gpt-4o',
        topicgpt_unit='dyad_directed', topicgpt_no_refine=False,
        topicgpt_dry_run=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class PreflightTests(unittest.TestCase):
    """Prerequisites are checked before spending, not after."""

    def setUp(self):
        import os
        from src import llm_rubric, pipeline
        self.pipeline = pipeline
        self.llm = llm_rubric
        self.os = os
        self._saved = {
            k: os.environ.pop(k, None)
            for k in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY')
        }
        self._real_probe = llm_rubric._ollama_is_running
        llm_rubric._ollama_is_running = lambda: False

    def tearDown(self):
        self.llm._ollama_is_running = self._real_probe
        for key, value in self._saved.items():
            if value is None:
                self.os.environ.pop(key, None)
            else:
                self.os.environ[key] = value

    def _args(self, **kw):
        return analysis_args(Path('/tmp'), Path('/tmp'), 't', **kw)

    def test_passes_when_nothing_extra_is_requested(self):
        self.pipeline.preflight(self._args())  # must not raise

    def test_missing_topicgpt_stops_before_any_call(self):
        with self.assertRaises(SystemExit) as ctx:
            self.pipeline.preflight(self._args(topics=True))
        message = str(ctx.exception)
        self.assertIn('No call', message)
        # The exact branch depends on what is missing — package or prompt
        # file — and that is not what this test means to pin down.
        self.assertIn('topicgpt', message.lower())

    def test_all_problems_are_reported_together(self):
        """Better one list than discovering them one at a time."""
        with self.assertRaises(SystemExit) as ctx:
            self.pipeline.preflight(self._args(llm=True, topics=True))
        message = str(ctx.exception)
        self.assertIn('topicgpt', message.lower())
        self.assertIn('OPENAI_API_KEY', message)

    def test_dry_run_needs_no_prerequisites(self):
        self.pipeline.preflight(
            self._args(llm=True, topics=True,
                       llm_dry_run=True, topicgpt_dry_run=True)
        )

    def test_batch_with_the_wrong_provider_is_caught_upfront(self):
        self.os.environ['OPENAI_API_KEY'] = 'sk-fake'
        with self.assertRaises(SystemExit) as ctx:
            self.pipeline.preflight(self._args(llm=True, llm_batch=True))
        self.assertIn('--llm-batch', str(ctx.exception))


class PartialResultsTests(unittest.TestCase):
    """If a later stage fails, the one already paid for must still be saved."""

    STEM = 't'

    def setUp(self):
        import os
        # The rubric is simulated, but the preflight check still demands a
        # provider: one is declared, otherwise it would stop before reaching
        # the scenario this test means to exercise.
        self.os = os
        self._saved = os.environ.get('OPENAI_API_KEY')
        os.environ['OPENAI_API_KEY'] = 'sk-fake'

    def tearDown(self):
        if self._saved is None:
            self.os.environ.pop('OPENAI_API_KEY', None)
        else:
            self.os.environ['OPENAI_API_KEY'] = self._saved

    def _write_merged(self, merged_dir):
        import csv as _csv

        merged_dir.mkdir(parents=True, exist_ok=True)
        messages = [dict(
            group_uid='g1', sender_id_in_group='1', receiver_id_in_group='2',
            dyad_key='1_2', sender_color='Yellow', receiver_color='Orange',
            treatment='private', timestamp='100.0',
            body='I will support you if you support me',
        )]
        by_partner = [dict(group_uid='g1', focal_id_in_group='1',
                           partner_id_in_group='2', dyad_key='1_2')]
        aggregated = [dict(group_uid='g1', focal_id_in_group='1')]

        for name, rows in (
            ('messages_long', messages),
            ('chat_by_partner', by_partner),
            ('chat_aggregated', aggregated),
        ):
            path = merged_dir / f'{self.STEM}_{name}.csv'
            with path.open('w', encoding='utf-8', newline='') as handle:
                writer = _csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)

    def test_datasets_are_written_even_if_topics_fails(self):
        import contextlib
        import csv as _csv
        import io
        import tempfile
        from src import pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir) / 'output'
            merged_dir = outdir / 'merged'
            self._write_merged(merged_dir)

            real_topics = pipeline.run_topics_stage
            real_llm = pipeline.run_llm_stage

            def failing_topics(messages, args):
                raise RuntimeError('TopicGPT blew up halfway through')

            def fake_llm(features, transcripts, args):
                # Simulates ratings already paid for.
                for row in features['group']:
                    row['llm_analytic'] = 77.0

            pipeline.run_topics_stage = failing_topics
            pipeline.run_llm_stage = fake_llm
            try:
                args = analysis_args(outdir, merged_dir, self.STEM,
                                     llm=True, topics=True,
                                     topicgpt_dry_run=True)
                with contextlib.redirect_stdout(io.StringIO()):
                    summary = pipeline.run(args)
            finally:
                pipeline.run_topics_stage = real_topics
                pipeline.run_llm_stage = real_llm

            # The failure is recorded, not hidden.
            self.assertIsNotNone(summary['failed_stage'])
            self.assertEqual(summary['failed_stage'][0], 'TopicGPT')

            # The datasets exist and hold the ratings already paid for.
            for path in summary['datasets']:
                self.assertTrue(path.is_file(), msg=str(path))
            with summary['datasets'][1].open(encoding='utf-8-sig') as handle:
                rows = list(_csv.DictReader(handle))
            self.assertEqual(float(rows[0]['nlp_group_llm_analytic']), 77.0)

            # And the program must report the partial outcome with a non-zero code.
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(pipeline.print_summary(summary), 1)

    def test_run_refuses_to_start_when_prerequisites_are_missing(self):
        """The check must be invoked by run(), not merely exist."""
        import contextlib
        import io
        import tempfile
        from src import pipeline

        self.os.environ.pop('OPENAI_API_KEY', None)
        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir) / 'output'
            merged_dir = outdir / 'merged'
            self._write_merged(merged_dir)
            args = analysis_args(outdir, merged_dir, self.STEM, topics=True)

            with self.assertRaises(SystemExit) as ctx:
                with contextlib.redirect_stdout(io.StringIO()):
                    pipeline.run(args)
            self.assertIn('No call', str(ctx.exception))
            # And it must have produced nothing.
            self.assertFalse((outdir / 'datasets').exists())

    def test_clean_run_returns_zero(self):
        import contextlib
        import io
        import tempfile
        from src import pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir) / 'output'
            merged_dir = outdir / 'merged'
            self._write_merged(merged_dir)
            args = analysis_args(outdir, merged_dir, self.STEM)
            with contextlib.redirect_stdout(io.StringIO()):
                summary = pipeline.run(args)
                self.assertEqual(pipeline.print_summary(summary), 0)
            self.assertIsNone(summary['failed_stage'])


class ReportTests(unittest.TestCase):
    """The summary must hold up even when the optional stages are missing."""

    def _write(self, outdir, aggregated, by_partner, summary=None):
        import csv as _csv
        import json as _json

        datasets = outdir / 'datasets'
        merged = outdir / 'merged'
        datasets.mkdir(parents=True, exist_ok=True)
        merged.mkdir(parents=True, exist_ok=True)
        for name, rows in (('chat_aggregated_nlp', aggregated),
                           ('chat_by_partner_nlp', by_partner)):
            path = datasets / f't_{name}.csv'
            with path.open('w', encoding='utf-8', newline='') as handle:
                writer = _csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        if summary is not None:
            (merged / 't_summary.json').write_text(
                _json.dumps(summary), encoding='utf-8')

    def _minimal(self):
        aggregated = [
            dict(group_uid='g1', treatment='private', group_valid='1',
                 focal_decision='Right', cc_i='1.0', strategic_deception='0',
                 group_outcome='mutual_12', group_coordinate='1',
                 group_total_payoff='6', focal_payoff_theoretical='3'),
            dict(group_uid='g1', treatment='private', group_valid='1',
                 focal_decision='Left', cc_i='0.5', strategic_deception='0',
                 group_outcome='mutual_12', group_coordinate='1',
                 group_total_payoff='6', focal_payoff_theoretical='3'),
        ]
        by_partner = [
            dict(group_uid='g1', treatment='private', persuasion_ij='1',
                 S_ij='1', C_ij='1'),
            dict(group_uid='g1', treatment='private', persuasion_ij='0',
                 S_ij='0', C_ij='1'),
        ]
        return aggregated, by_partner

    def test_works_without_any_optional_stage(self):
        import tempfile
        from src import report

        aggregated, by_partner = self._minimal()
        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir)
            self._write(outdir, aggregated, by_partner)
            paths = report.write(outdir, 't')
            self.assertEqual(len(paths), 2)
            markdown = paths[0].read_text(encoding='utf-8')
        self.assertIn('Coverage', markdown)
        self.assertIn('Game outcomes', markdown)
        # The sections of the stages not run must not appear.
        self.assertNotIn('Validation rubric', markdown)
        self.assertNotIn('## Topics', markdown)

    def test_group_variables_are_not_counted_once_per_member(self):
        """Triad variables repeat on every row: they must be deduplicated."""
        import tempfile
        from src import report

        aggregated, by_partner = self._minimal()
        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir)
            self._write(outdir, aggregated, by_partner)
            data = report.collect(outdir, 't')

        self.assertEqual(data['coverage']['n_triads'], 1)
        self.assertEqual(data['coverage']['n_participants'], 2)
        # The group payoff is 6, not 12.
        self.assertEqual(data['outcomes']['per_treatment'][0]['mean_group_payoff'], 6.0)

    def test_optional_sections_appear_when_their_data_is_there(self):
        import tempfile
        from src import report

        aggregated, by_partner = self._minimal()
        for row in aggregated:
            row.update({'nlp_group_analytic_100': '70.0',
                        'nlp_group_clout_100': '50.0',
                        'nlp_group_wc': '120',
                        'nlp_group_llm_analytic': '40.0'})
        for row in by_partner:
            row['nlp_sent_topics'] = 'Commitment|Coalition Proposal'

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir)
            self._write(outdir, aggregated, by_partner)
            markdown = report.write(outdir, 't')[0].read_text(encoding='utf-8')

        self.assertIn('Language', markdown)
        self.assertIn('Validation rubric', markdown)
        self.assertIn('## Topics', markdown)
        self.assertIn('Commitment', markdown)

    def test_html_is_self_contained_and_escaped(self):
        import tempfile
        from src import report

        aggregated, by_partner = self._minimal()
        aggregated[0]['group_outcome'] = '<script>alert(1)</script>'
        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir)
            self._write(outdir, aggregated, by_partner)
            page = report.write(outdir, 't')[1].read_text(encoding='utf-8')

        self.assertIn('<style>', page)          # no external stylesheets
        self.assertNotIn('<script>alert', page)  # content escaped
        self.assertIn('&lt;script&gt;', page)

    def test_empty_values_do_not_crash(self):
        import tempfile
        from src import report

        aggregated, by_partner = self._minimal()
        for row in aggregated:
            row['group_total_payoff'] = ''
            row['cc_i'] = ''
        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir)
            self._write(outdir, aggregated, by_partner)
            markdown = report.write(outdir, 't')[0].read_text(encoding='utf-8')
        self.assertIn('—', markdown)


class ArchiveTests(unittest.TestCase):
    """Launching again must not erase the previous run."""

    def _args(self, **kw):
        from types import SimpleNamespace

        base = dict(stem='t', llm=False, llm_dry_run=False, topics=False,
                    topicgpt_dry_run=False, llm_provider=None, llm_models=None,
                    llm_replicates=1, llm_levels=['group'])
        base.update(kw)
        return SimpleNamespace(**base)

    def _prepare(self, outdir, marker='a'):
        (outdir / 'datasets').mkdir(parents=True, exist_ok=True)
        (outdir / 'datasets' / 't_chat_aggregated_nlp.csv').write_text(
            f'col\n{marker}\n', encoding='utf-8')
        (outdir / 't_report.md').write_text(f'# report {marker}',
                                            encoding='utf-8')

    def test_stages_reflect_what_was_actually_run(self):
        from src import archive

        self.assertEqual(archive.stages_of(self._args()), ['measures'])
        self.assertEqual(
            archive.stages_of(self._args(llm=True, topics=True)),
            ['measures', 'rubric', 'topics'])
        # Dry runs are not runs.
        self.assertEqual(
            archive.stages_of(self._args(llm=True, llm_dry_run=True)),
            ['measures'])

    def test_a_second_run_does_not_erase_the_first(self):
        import tempfile
        from src import archive

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir)
            self._prepare(outdir, 'first')
            first = archive.save(outdir, 't', self._args(), {})

            self._prepare(outdir, 'second')
            second = archive.save(outdir, 't', self._args(llm=True), {})

            self.assertNotEqual(first, second)
            self.assertIn('first', (first / 'datasets' /
                                    't_chat_aggregated_nlp.csv').read_text())
            self.assertIn('second', (second / 'datasets' /
                                     't_chat_aggregated_nlp.csv').read_text())
            self.assertEqual(len(archive.list_runs(outdir)), 2)

    def test_same_second_collision_is_resolved(self):
        """Two runs can finish within the same second."""
        import tempfile
        from src import archive

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir)
            self._prepare(outdir)
            paths = {archive.save(outdir, 't', self._args(), {})
                     for _ in range(3)}
            self.assertEqual(len(paths), 3)

    def test_parameters_are_recorded_so_runs_can_be_told_apart(self):
        import json as _json
        import tempfile
        from src import archive

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir)
            self._prepare(outdir)
            args = self._args(llm=True, llm_provider='openai',
                              llm_replicates=2, llm_levels=['group', 'dyad'])
            run_dir = archive.save(outdir, 't', args, dict(n_messages=283))

            info = _json.loads((run_dir / 'run.json').read_text(encoding='utf-8'))
        self.assertEqual(info['stages'], ['measures', 'rubric'])
        self.assertEqual(info['rubric']['provider'], 'openai')
        self.assertEqual(info['rubric']['replicates'], 2)
        self.assertEqual(info['n_messages'], 283)

    def test_listing_is_ordered_by_recorded_instant(self):
        """The collision suffixes do not follow alphabetical order."""
        import json as _json
        import tempfile
        from src import archive

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir)
            runs = outdir / 'runs'
            for name, stamp in (('2026-01-01_120000_10', '2026-01-01T12:00:10'),
                                ('2026-01-01_120000_2', '2026-01-01T12:00:02')):
                (runs / name).mkdir(parents=True)
                (runs / name / 'run.json').write_text(
                    _json.dumps({'timestamp': stamp, 'stages': ['measures']}),
                    encoding='utf-8')
            listed = [r['path'].name for r in archive.list_runs(outdir)]
        self.assertEqual(listed[0], '2026-01-01_120000_10')

    def test_unreadable_run_does_not_break_the_listing(self):
        import tempfile
        from src import archive

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir)
            (outdir / 'runs' / 'broken').mkdir(parents=True)
            (outdir / 'runs' / 'broken' / 'run.json').write_text(
                '{not json', encoding='utf-8')
            runs = archive.list_runs(outdir)
        self.assertEqual(len(runs), 1)
        self.assertIn('?', archive.render_list(runs))


class PruneTests(unittest.TestCase):
    """Pruning the archive: irreversible, so it must be well fenced in."""

    def _archive(self, tmpdir, how_many):
        import json as _json

        outdir = Path(tmpdir)
        for i in range(how_many):
            run = outdir / 'runs' / f'2026-01-01_1200{i:02d}'
            (run / 'datasets').mkdir(parents=True)
            (run / 'datasets' / 'x.csv').write_text('a', encoding='utf-8')
            (run / 'run.json').write_text(
                _json.dumps({'timestamp': f'2026-01-01T12:00:{i:02d}',
                             'stages': ['measures']}), encoding='utf-8')
        return outdir

    def test_keeps_the_most_recent(self):
        import tempfile
        from src import archive

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = self._archive(tmpdir, 5)
            removed = archive.prune(outdir, 2)
            kept = [r['path'].name for r in archive.list_runs(outdir)]

        self.assertEqual(len(removed), 3)
        self.assertEqual(kept, ['2026-01-01_120004', '2026-01-01_120003'])

    def test_is_idempotent(self):
        import tempfile
        from src import archive

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = self._archive(tmpdir, 3)
            archive.prune(outdir, 2)
            self.assertEqual(archive.prune(outdir, 2), [])

    def test_keeping_more_than_there_are_removes_nothing(self):
        import tempfile
        from src import archive

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = self._archive(tmpdir, 2)
            self.assertEqual(archive.prune(outdir, 10), [])
            self.assertEqual(len(archive.list_runs(outdir)), 2)

    def test_negative_is_refused(self):
        import tempfile
        from src import archive

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = self._archive(tmpdir, 2)
            with self.assertRaises(ValueError):
                archive.prune(outdir, -1)
            self.assertEqual(len(archive.list_runs(outdir)), 2)

    def test_only_touches_the_archive(self):
        """It deletes inside output/runs and nowhere else."""
        import tempfile
        from src import archive

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = self._archive(tmpdir, 3)
            elsewhere = outdir / 'datasets'
            elsewhere.mkdir()
            (elsewhere / 'important.csv').write_text('data', encoding='utf-8')
            archive.prune(outdir, 1)
            self.assertTrue((elsewhere / 'important.csv').is_file())


class ConfigTests(unittest.TestCase):
    """API keys and paths: they must be predictable and never surprise."""

    def setUp(self):
        from src import config
        self.secrets = config

    def test_parses_the_forms_people_actually_write(self):
        parsed = self.secrets.parse_env(
            '# a comment\n'
            'OPENAI_API_KEY=sk-one\n'
            'export ANTHROPIC_API_KEY="sk-ant-two"\n'
            "OPENAI_BASE_URL='https://example/v1'\n"
            '\n'
            'a line without an equals sign\n'
        )
        self.assertEqual(parsed['OPENAI_API_KEY'], 'sk-one')
        self.assertEqual(parsed['ANTHROPIC_API_KEY'], 'sk-ant-two')
        self.assertEqual(parsed['OPENAI_BASE_URL'], 'https://example/v1')
        self.assertNotIn('a line without an equals sign', parsed)

    def test_values_containing_equals_survive(self):
        parsed = self.secrets.parse_env('K=abc=def==\n')
        self.assertEqual(parsed['K'], 'abc=def==')

    def test_environment_wins_over_the_file(self):
        """Whoever manages their keys their own way must not be overridden."""
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / '.env'
            path.write_text('TEST_KEY_A=from_file\nTEST_KEY_B=from_file\n',
                            encoding='utf-8')
            os.environ['TEST_KEY_A'] = 'from_environment'
            os.environ.pop('TEST_KEY_B', None)
            try:
                loaded = self.secrets.load_env(path)
                self.assertEqual(os.environ['TEST_KEY_A'], 'from_environment')
                self.assertEqual(os.environ['TEST_KEY_B'], 'from_file')
                self.assertIn('TEST_KEY_B', loaded)
                self.assertNotIn('TEST_KEY_A', loaded)
            finally:
                os.environ.pop('TEST_KEY_A', None)
                os.environ.pop('TEST_KEY_B', None)

    def test_missing_file_is_not_an_error(self):
        self.assertEqual(self.secrets.load_env(Path('/path/that/does/not/exist')), [])

    def test_missing_key_explains_what_to_do(self):
        import os

        os.environ.pop('OPENAI_API_KEY', None)
        with self.assertRaises(SystemExit) as ctx:
            self.secrets.require_key('OPENAI_API_KEY')
        message = str(ctx.exception)
        self.assertIn('run.py keys', message)
        self.assertIn('TopicGPT', message)

    def test_secrets_file_is_git_ignored(self):
        """The keys must never be able to end up under version control."""
        self.assertIs(
            self.secrets.is_git_ignored(self.secrets.ENV_FILE), True
        )


if __name__ == '__main__':
    unittest.main(verbosity=2)
