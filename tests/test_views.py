"""Characterisation tests for the three pages nothing else imports.

`views_library`, `views_participation` and `views_compare` are a thousand lines
of the newest interface and no other suite so much as imports them. These tests
do not describe how the pages should look — that is about to change — but what
they must keep doing while they are rebuilt: render each of the three states
without raising, say why when they cannot show anything, and escape the text
that came from outside.

    python tests/test_views.py
"""

import sys
import tempfile
import threading
import unittest
from pathlib import Path

# Runs from a source checkout without installing: the package is under src/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from chatlens.core import library  # noqa: E402
from chatlens.web import active, ui, views_compare, views_library  # noqa: E402
from chatlens.web import views_participation  # noqa: E402


class LibraryPageTests(unittest.TestCase):
    """The first screen, before and after there is anything on it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        library.use_library(Path(self.tmp.name))
        library.ensure_root()

    def test_an_empty_library_still_renders_a_whole_page(self):
        page = views_library.library_page()
        self.assertIn('<!doctype html>', page.lower())
        self.assertIn('</html>', page.lower())
        # Whatever the wording becomes, the page has to offer the way in.
        self.assertIn('<form', page)

    def test_an_experiment_appears_once_it_exists(self):
        library.create('Ultimatum with pre-play chat', 'generic_chat')
        page = views_library.library_page()
        self.assertIn('Ultimatum with pre-play chat', page)

    def test_a_name_carrying_markup_is_escaped(self):
        """The name is typed by a person and lands inside the HTML."""
        library.create('<script>alert(1)</script>', 'generic_chat')
        page = views_library.library_page()
        self.assertNotIn('<script>alert(1)</script>', page)

    def test_the_settings_page_of_a_bare_experiment_renders(self):
        library.create('Bare study', 'generic_chat')
        with active.experiment('bare-study'):
            page = views_library.step_outcome('bare-study')
        self.assertIn('<!doctype html>', page.lower())

    def test_the_panels_of_a_bare_experiment_explain_rather_than_raise(self):
        """No files uploaded yet is a state, not an error."""
        library.create('Bare study', 'generic_chat')
        with active.experiment('bare-study'):
            files = views_library.files_panel('bare-study')
            columns = views_library.columns_panel('bare-study')
            treatments = views_library.treatments_panel('bare-study')
        for panel in (files, columns, treatments):
            self.assertTrue(panel.strip(), 'a panel rendered nothing at all')


class AnalysisPageTests(unittest.TestCase):
    """Pages that need a run behind them, on an experiment that has none."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        library.use_library(Path(self.tmp.name))
        library.ensure_root()
        library.create('Bare study', 'generic_chat')

    def test_participation_says_what_is_missing(self):
        with active.experiment('bare-study'):
            body = views_participation.body('bare-study')
        self.assertTrue(body.strip())
        self.assertNotIn('Traceback', body)

    def test_comparison_says_what_is_missing(self):
        with active.experiment('bare-study'):
            body = views_compare.panel('bare-study')
        self.assertTrue(body.strip())
        self.assertNotIn('Traceback', body)

    def test_the_findings_area_frames_whatever_was_asked_for(self):
        """The register is navigation made of content, so it has to be there
        even when nothing can be computed yet."""
        from chatlens.web import views_findings
        with active.experiment('bare-study'):
            page = views_findings.page('bare-study', 'compare')
        self.assertIn('<!doctype html>', page.lower())
        self.assertIn('class="register"', page)
        self.assertIn('class="spine"', page)

    def test_neither_page_leaves_a_table_header_over_nothing(self):
        """An empty table with headings and no rows is not an empty state.

        This currently fails on neither page because neither reaches its table
        without data; it is here so that the rebuilt pages keep that property.
        """
        with active.experiment('bare-study'):
            for body in (views_participation.body('bare-study'),
                         views_compare.panel('bare-study')):
                if '<tbody></tbody>' in body.replace('\n', ''):
                    self.fail('a table was rendered with no rows in it')


class ConcurrencyTests(unittest.TestCase):
    """A slow page must not stop the rest of the dashboard.

    The words, narratives and comparison pages take from seconds to minutes,
    and they used to hold one process-wide mutex for the whole of it — so the
    log poll that shows a run progressing was frozen by a page looking at that
    same run's output.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        library.use_library(Path(self.tmp.name))
        library.ensure_root()
        library.create('One', 'generic_chat')
        library.create('Two', 'generic_chat')

    def _enter(self, name, holding, done, entered=None):
        def run():
            with active.experiment(name):
                if entered is not None:
                    entered.set()
                holding.wait(5)
            done.set()
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread

    def test_two_requests_for_the_same_experiment_do_not_queue(self):
        holding, first_done = threading.Event(), threading.Event()
        entered = threading.Event()
        self._enter('one', holding, first_done, entered)
        self.assertTrue(entered.wait(5), 'the first request never started')

        second_holding, second_done = threading.Event(), threading.Event()
        second_entered = threading.Event()
        self._enter('one', second_holding, second_done, second_entered)

        self.assertTrue(
            second_entered.wait(2),
            'a second request for the same experiment waited for the first')
        second_holding.set()
        holding.set()
        self.assertTrue(first_done.wait(5) and second_done.wait(5))

    def test_a_request_for_another_experiment_waits_its_turn(self):
        """The state really is shared, so this one has to queue."""
        holding, first_done = threading.Event(), threading.Event()
        entered = threading.Event()
        self._enter('one', holding, first_done, entered)
        self.assertTrue(entered.wait(5))

        other_holding, other_done = threading.Event(), threading.Event()
        other_entered = threading.Event()
        other_holding.set()
        self._enter('two', other_holding, other_done, other_entered)

        self.assertFalse(
            other_entered.wait(0.5),
            'a second experiment was activated while the first was in flight')
        holding.set()
        self.assertTrue(first_done.wait(5))
        self.assertTrue(other_entered.wait(5), 'it never got its turn')
        self.assertTrue(other_done.wait(5))


class FindingShapeTests(unittest.TestCase):
    """Every finding opens with its question and its answer.

    The order is the argument: these screens used to open with a paragraph of
    reasoning, then the controls, then the numbers, and put the answer in a
    grey sentence halfway down.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        library.use_library(Path(self.tmp.name))
        library.ensure_root()
        library.create('Bare study', 'generic_chat')

    def _bodies(self):
        from chatlens.web import (views_compare, views_emotions,
                                  views_narratives, views_participation,
                                  views_words)
        return {
            'participation': lambda: views_participation.body('bare-study'),
            'compare': lambda: views_compare.panel('bare-study'),
            'narratives': lambda: views_narratives.panel('bare-study'),
            'emotions': lambda: views_emotions.panel(),
            'words': lambda: views_words.body('bare-study'),
        }

    def test_each_one_asks_a_question_even_when_it_cannot_answer(self):
        """A study with nothing run is the commonest state there is, and the
        reader should still be told what the screen is for."""
        with active.experiment('bare-study'):
            for entry, render in self._bodies().items():
                with self.subTest(finding=entry):
                    body = render()
                    self.assertIn('class="question"', body, entry)
                    self.assertIn('class="answer"', body, entry)

    def test_each_finding_names_its_method_even_when_it_cannot_answer(self):
        """A reader who already knows the technique's name — "bag of
        words", "RELATIO" — cannot find it anywhere, on any page, because
        every title here is a plain-English question by design. `method=`
        is the one place the name is actually printed, and it has to survive
        every blocked state too: a bare study with nothing declared yet is
        the commonest state there is."""
        expected = {'words': 'bag of words', 'narratives': 'relatio',
                   'emotions': 'nrc', 'compare': 'nadeau-bengio'}
        with active.experiment('bare-study'):
            bodies = self._bodies()
            for entry, needle in expected.items():
                with self.subTest(finding=entry):
                    self.assertIn(needle, bodies[entry]().lower())

    def test_a_panel_is_the_computed_thing_not_the_placeholder(self):
        """A panel request is the fill-in. Answering it with the same
        placeholder the page already showed leaves the screen saying "Working
        it out…" for ever — which is what a generic panel route did, and what a
        screenshot caught."""
        from chatlens.web import views_findings

        with active.experiment('bare-study'):
            for entry in ('words', 'compare', 'narratives'):
                with self.subTest(finding=entry):
                    panel = views_findings.panel('bare-study', entry)
                    self.assertNotIn('Working it out', panel)
                    self.assertNotIn('hx-trigger="load"', panel)

    def test_a_name_that_is_not_a_finding_is_refused(self):
        """It used to become the first entry, which is how a routing mistake
        comes to look like a working screen."""
        from chatlens.web import views_findings

        with active.experiment('bare-study'):
            with self.assertRaises(views_findings.Unknown):
                views_findings.panel('bare-study', 'nonsense')
            with self.assertRaises(views_findings.Unknown):
                views_findings.page('bare-study', 'nonsense')

    def test_a_negative_answer_is_not_marked_as_an_error(self):
        """`no` is the commonest honest result on a corpus of short messages;
        the register must not colour it like a failure."""
        markup = ui.register('s', [
            {'id': 'words', 'name': 'The words', 'verdict': ui.NO, 'note': ''},
        ])
        self.assertIn('entry no', markup)
        self.assertNotIn('entry bad', markup)

    def test_a_no_does_not_leapfrog_the_orientation_pages(self):
        """It used to sort second, right after `yes` — so on a study where
        Words and Emotions come back negative, those two entries jumped above
        `What was said` and `Who spoke to whom` a moment after the page had
        already painted them in the right order, because the register's
        async refresh reorders by verdict. A `no` is still an answer, so it
        stays ahead of a question nothing has settled — but not ahead of the
        two orientation pages, which are always `open`."""
        markup = ui.register('s', [
            {'id': 'emotions', 'name': 'The emotions', 'verdict': ui.NO,
             'note': '', 'order': 5},
            {'id': 'corpus', 'name': 'What was said', 'verdict': ui.OPEN,
             'note': '', 'order': 0},
            {'id': 'participation', 'name': 'Who spoke to whom',
             'verdict': ui.OPEN, 'note': '', 'order': 1},
        ])
        self.assertLess(markup.index('What was said'),
                        markup.index('The emotions'))
        self.assertLess(markup.index('Who spoke to whom'),
                        markup.index('The emotions'))

    def test_a_yes_still_leads(self):
        """The register's whole point survives the reordering: a definite
        answer still outranks an open question."""
        markup = ui.register('s', [
            {'id': 'corpus', 'name': 'What was said', 'verdict': ui.OPEN,
             'note': '', 'order': 0},
            {'id': 'compare', 'name': 'Which representation to trust',
             'verdict': ui.YES, 'note': '', 'order': 2},
        ])
        self.assertLess(markup.index('Which representation to trust'),
                        markup.index('What was said'))

    def test_the_register_offers_a_glossary_of_method_names(self):
        """Nothing on any page ever says "bag of words" or "RELATIO" in so
        many words — the titles are plain-English questions by design — so a
        reader who already knows the method's name has nowhere to search for
        it. This is the bridge, always present regardless of what is passed."""
        markup = ui.register('bare-study', [])
        for term in ('Bag of words', 'RELATIO', 'NRC', 'TopicGPT', 'Rubric'):
            self.assertIn(term, markup)
        self.assertIn('/experiment/bare-study/findings/words', markup)
        self.assertIn('/experiment/bare-study/report.html', markup)

    def test_the_glossary_still_renders_without_a_slug(self):
        """Single-workspace mode has no experiment slug to link through."""
        markup = ui.register('', [])
        self.assertIn('Bag of words', markup)
        self.assertNotIn('href="/experiment//', markup)

    def test_the_shell_links_to_the_published_guide(self):
        """The illustrated walkthrough existed only as a file nobody inside
        the running app was ever pointed at."""
        page = ui.shell('t', '<p>x</p>')
        self.assertIn('nicomil.github.io/chatlens/guide', page)


def _write_csv(path, rows):
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class PageCacheScopeTests(unittest.TestCase):
    """A remembered answer belongs to the study it was computed on.

    The three slow pages keep their last result in memory, and the key said
    what the analysis depends on — the outcome column, the unit, the knobs —
    and nothing about which study it came from. Two experiments configured
    alike therefore shared one entry, and the second one opened was served the
    first one's model, figures and verdicts.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        library.use_library(Path(self.tmp.name))
        library.ensure_root()
        for name in ('One', 'Two'):
            path = library.create(name, 'generic_chat')
            experiment = self._configured(path)
            experiment.save()

    def _configured(self, path):
        """Both studies get the same outcome, which is the whole point."""
        from chatlens.core import experiment as experiment_module

        loaded = experiment_module.load(path)
        loaded.set('outcome', {'column': 'y', 'kind': 'binary',
                               'unit': 'sender_group', 'label': 'y'})
        return loaded

    def test_the_scope_is_the_workspace(self):
        seen = set()
        for name in ('one', 'two'):
            with active.experiment(name):
                seen.add(active.scope())
        self.assertEqual(len(seen), 2)

    def test_two_studies_configured_alike_are_fitted_separately(self):
        import unittest.mock

        from chatlens.core import config, words as words_core
        from chatlens.web import views_words

        views_words._CACHE.clear()
        self.addCleanup(views_words._CACHE.clear)
        fitted = []

        def dataset():
            """Rows that say which workspace they came from."""
            marker = Path(config.WORKSPACE).name
            rows = [{'group_uid': 'g', 'sent_transcript_text': marker,
                     'y': '1'}]
            return rows, {'column': 'y', 'unit': 'sender_group',
                          'label': 'y'}, ''

        def fit(rows, text_column, outcome_column, **params):
            fitted.append(rows[0][text_column])
            return {'marker': rows[0][text_column]}

        with unittest.mock.patch.object(views_words, '_dataset', dataset), \
                unittest.mock.patch.object(words_core, 'fit', fit):
            with active.experiment('one'):
                first = views_words.result({})[0]
            with active.experiment('two'):
                second = views_words.result({})[0]
            with active.experiment('one'):
                again = views_words.result({})[0]

        self.assertEqual(first['marker'], 'one')
        self.assertEqual(second['marker'], 'two')
        # Each study is fitted once and served its own model. Coming back to the
        # first does not refit it: the cache holds several entries now, so the
        # two do not evict each other on every move between them.
        self.assertEqual(fitted, ['one', 'two'])
        self.assertEqual(again['marker'], 'one')


class ParticipationLineTests(unittest.TestCase):
    """The paragraph the comparison page opens with.

    Two separate faults: it indexed rows by a column only the directed-pair
    table has, whatever unit the outcome was declared at, and it read the
    outcome by comparing strings to "0" and "1" where the rest of the tool goes
    through `outcome.as_binary`.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        library.use_library(Path(self.tmp.name))
        library.ensure_root()
        self.path = library.create('Study', 'generic_chat')

    def _merged(self, accepted='yes'):
        """One group of three in which seat 1 wrote to seat 2 and seat 3 did
        not, so a receiver has two candidate senders and one of them spoke."""
        merged = self.path / 'output' / 'merged'
        _write_csv(merged / 'messages_messages_long.csv', [
            {'group_uid': 'g1', 'sender_id_in_group': '1',
             'receiver_id_in_group': '2', 'body': 'i will back you',
             'timestamp': '1'},
        ])
        _write_csv(merged / 'messages_chat_aggregated.csv', [
            {'group_uid': 'g1', 'focal_id_in_group': seat}
            for seat in ('1', '2', '3')
        ])
        _write_csv(merged / 'messages_chat_by_partner.csv', [
            {'group_uid': 'g1', 'focal_id_in_group': '1',
             'partner_id_in_group': '2', 'accepted': accepted},
            {'group_uid': 'g1', 'focal_id_in_group': '3',
             'partner_id_in_group': '2', 'accepted': 'no'},
        ])

    def _declare(self, unit, kind='binary'):
        from chatlens.core import experiment as experiment_module

        loaded = experiment_module.load(self.path)
        loaded.set('outcome', {'column': 'accepted', 'kind': kind,
                               'unit': unit, 'label': 'chose i'})
        loaded.save()

    def test_an_outcome_per_person_is_declined_rather_than_crashed_on(self):
        """It used to raise KeyError from inside the page: the request died
        with a traceback on the server and nothing in the browser."""
        self._merged()
        self._declare('sender_group')
        with active.experiment('study'):
            self.assertEqual(views_compare._participation_line('study'), '')

    def test_a_yes_no_outcome_is_read(self):
        """A roster exported from a spreadsheet holds words, not 0 and 1."""
        self._merged(accepted='yes')
        self._declare('dyad_directed')
        with active.experiment('study'):
            line = views_compare._participation_line('study')
        self.assertIn('whether anything was written at all', line)
        self.assertIn('1 times against', line)

    def test_zero_and_one_still_work(self):
        self._merged(accepted='1')
        self._declare('dyad_directed')
        with active.experiment('study'):
            line = views_compare._participation_line('study')
        self.assertIn('1 times against', line)


class LatestTableTests(unittest.TestCase):
    """Which of several merged tables the pages describe.

    The stem of the declared input is the authority, and the lookup asked for
    the role called "wide" — which only the oTree adapter has. On every other
    experiment it raised, the exception was swallowed, and the authority became
    the modification time.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        library.use_library(Path(self.tmp.name))
        library.ensure_root()
        self.path = library.create('Study', 'generic_chat')
        (self.path / 'input' / 'messages.csv').write_text(
            'group,sender,receiver,body\n', encoding='utf-8')
        merged = self.path / 'output' / 'merged'
        merged.mkdir(parents=True, exist_ok=True)
        # The pilot is written second, so modification time and the declared
        # input disagree about which table is the current one.
        (merged / 'messages_chat_by_partner.csv').write_text(
            'group_uid\n', encoding='utf-8')
        (merged / 'pilot_chat_by_partner.csv').write_text(
            'group_uid\n', encoding='utf-8')
        import os
        import time

        os.utime(merged / 'messages_chat_by_partner.csv',
                 (time.time() - 600, time.time() - 600))

    def test_the_declared_input_names_the_table(self):
        from chatlens.core import config

        with active.experiment('study'):
            found = views_participation._latest(config.MERGED_DIR,
                                                '_chat_by_partner.csv')
        self.assertEqual(found.name, 'messages_chat_by_partner.csv')


class RunnerPerStudyTests(unittest.TestCase):
    """One runner per workspace, not one per process.

    With a single runner, starting a run in study A made study B's Run page show
    A's log and refuse to start — the state it read was A's.
    """

    def setUp(self):
        from chatlens.web import runner as runner_module

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        library.use_library(Path(self.tmp.name))
        library.ensure_root()
        library.create('One', 'generic_chat')
        library.create('Two', 'generic_chat')
        self.runner_module = runner_module
        runner_module.forget_all()
        self.addCleanup(runner_module.forget_all)

    def test_two_studies_get_two_runners(self):
        seen = []
        for name in ('one', 'two'):
            with active.experiment(name):
                seen.append(self.runner_module.current())
        self.assertIsNot(seen[0], seen[1])

    def test_the_same_study_gets_the_same_runner(self):
        with active.experiment('one'):
            first = self.runner_module.current()
        with active.experiment('one'):
            self.assertIs(self.runner_module.current(), first)

    def test_a_run_in_one_study_does_not_block_the_other(self):
        import sys as _sys

        with active.experiment('one'):
            started = self.runner_module.current().start(
                [_sys.executable, '-c', 'import time; time.sleep(3)'])
            self.assertTrue(started)
            self.addCleanup(self.runner_module.current().stop)
        with active.experiment('two'):
            other = self.runner_module.current()
            self.assertFalse(other.running,
                             "the other study's run showed as this one's")
            self.assertTrue(other.start([_sys.executable, '-c', 'pass']))

    def test_the_other_study_is_named_rather_than_hidden(self):
        """They share the rate limit and the bill, so the page says so."""
        import sys as _sys

        with active.experiment('one'):
            self.runner_module.current().start(
                [_sys.executable, '-c', 'import time; time.sleep(3)'])
            self.addCleanup(self.runner_module.current().stop)
        with active.experiment('two'):
            self.assertIn('one', self.runner_module.elsewhere())


class BusyTests(unittest.TestCase):
    """A request for another experiment waits, but not for ever.

    The wait had no bound: the other study's log polls once a second and a page
    that fits a model holds the state for minutes, so a second tab sat there
    with no page and no message.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        library.use_library(Path(self.tmp.name))
        library.ensure_root()
        library.create('One', 'generic_chat')
        library.create('Two', 'generic_chat')
        self.previous = active.WAIT_SECONDS
        active.WAIT_SECONDS = 0.3
        self.addCleanup(lambda: setattr(active, 'WAIT_SECONDS', self.previous))

    def test_it_gives_up_and_says_which_study_is_busy(self):
        holding, released = threading.Event(), threading.Event()

        def hold():
            with active.experiment('one'):
                holding.set()
                released.wait(5)

        thread = threading.Thread(target=hold, daemon=True)
        thread.start()
        self.assertTrue(holding.wait(5))
        try:
            with self.assertRaises(active.Busy) as ctx:
                with active.experiment('two'):
                    pass
            self.assertIn('one', str(ctx.exception))
            self.assertIn('wait', str(ctx.exception).lower())
        finally:
            released.set()
            thread.join(5)

    def test_the_same_study_never_waits(self):
        holding, released = threading.Event(), threading.Event()

        def hold():
            with active.experiment('one'):
                holding.set()
                released.wait(5)

        thread = threading.Thread(target=hold, daemon=True)
        thread.start()
        self.assertTrue(holding.wait(5))
        try:
            with active.experiment('one'):
                pass
        finally:
            released.set()
            thread.join(5)


class PageCacheTests(unittest.TestCase):
    """A few entries, not one.

    With a single entry, moving between two studies refits both on every move —
    and the register on every page reads the comparison, so the eviction happened
    on page loads that were not even about the analysis.
    """

    def test_it_keeps_more_than_one_study(self):
        from chatlens.web import pagecache

        cache = pagecache.Cache()
        for study in ('one', 'two'):
            cache.put((study, 'words'), f'{study} model')
        self.assertEqual(cache.get(('one', 'words')), 'one model')
        self.assertEqual(cache.get(('two', 'words')), 'two model')

    def test_the_oldest_used_goes_first(self):
        from chatlens.web import pagecache

        cache = pagecache.Cache(keep=2)
        cache.put('a', 1)
        cache.put('b', 2)
        # Touching `a` makes `b` the least recently used.
        self.assertEqual(cache.get('a'), 1)
        cache.put('c', 3)
        self.assertIsNone(cache.get('b'))
        self.assertEqual(cache.get('a'), 1)
        self.assertEqual(cache.get('c'), 3)

    def test_it_does_not_grow_without_limit(self):
        from chatlens.web import pagecache

        cache = pagecache.Cache(keep=3)
        for n in range(50):
            cache.put(n, n)
        self.assertEqual(len(cache), 3)

    def test_a_missing_key_is_not_an_error(self):
        from chatlens.web import pagecache

        cache = pagecache.Cache()
        self.assertIsNone(cache.get('absent'))
        self.assertNotIn('absent', cache)

    def test_the_pages_use_it(self):
        from chatlens.web import (pagecache, views_compare, views_narratives,
                                  views_words)

        for module in (views_words, views_compare, views_narratives):
            with self.subTest(module=module.__name__):
                self.assertIsInstance(module._CACHE, pagecache.Cache)


class SampleSelectorTests(unittest.TestCase):
    """Reading one experiment through one declared study.

    Two papers come out of this collection, on two samples that must not be
    mixed: the standardised columns are computed with the sample's own mean and
    variance, so the same participant's `clout_100` differs between them. The
    selector is what makes that visible in the dashboard rather than only in the
    files `chatlens studies` writes.
    """

    STUDIES = [
        {'slug': 'study1', 'name': 'Study 1 — public',
         'treatments': ['private', 'public'], 'baseline': 'private'},
        {'slug': 'study2', 'name': 'Study 2 — slacker',
         'treatments': ['private', 'private_no_dwl'], 'baseline': 'private'},
    ]

    def setUp(self):
        from chatlens.core import experiment as experiment_module

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        library.use_library(Path(self.tmp.name))
        library.ensure_root()
        self.path = library.create('Coalitions', 'generic_chat')
        loaded = experiment_module.load(self.path)
        loaded.set('studies', self.STUDIES)
        loaded.save()
        active.forget_choices()
        self.addCleanup(active.forget_choices)

    def test_no_studies_declared_means_no_control_at_all(self):
        from chatlens.web import views_findings

        other = library.create('Plain', 'generic_chat')
        self.assertTrue(other.is_dir())
        with active.experiment('plain'):
            self.assertEqual(active.studies(), ())
            self.assertEqual(views_findings.sample_picker('plain', '/x'), '')

    def test_the_declared_studies_are_offered_with_the_whole_sample_first(self):
        from chatlens.web import views_findings

        with active.experiment('coalitions'):
            html = views_findings.sample_picker('coalitions',
                                                '/experiment/coalitions/findings')
        self.assertIn('The whole sample', html)
        self.assertIn('value="study1"', html)
        self.assertIn('value="study2"', html)
        self.assertLess(html.index('The whole sample'), html.index('study1'))

    def test_nothing_in_the_markup_relies_on_an_inline_handler(self):
        """The content security policy blocks one silently."""
        from chatlens.web import views_findings

        with active.experiment('coalitions'):
            html = views_findings.sample_picker('coalitions', '/x')
        self.assertNotIn('onchange=', html)
        self.assertIn('data-submit-on-change', html)

    def test_choosing_a_study_changes_the_scope_of_every_cache(self):
        with active.experiment('coalitions'):
            pooled = active.scope()
            active.choose('study1')
            first = active.scope()
            active.choose('study2')
            second = active.scope()
        self.assertEqual(len({pooled, first, second}), 3)

    def test_an_unknown_slug_falls_back_to_the_whole_sample(self):
        with active.experiment('coalitions'):
            self.assertEqual(active.choose('../../etc'), '')
            self.assertEqual(active.chosen(), '')
            self.assertIsNone(active.study())

    def test_a_slug_that_stops_being_declared_stops_being_chosen(self):
        """The experiment can be edited while the dashboard is open."""
        from chatlens.core import experiment as experiment_module

        with active.experiment('coalitions'):
            active.choose('study2')
            self.assertEqual(active.chosen(), 'study2')

        loaded = experiment_module.load(self.path)
        loaded.set('studies', self.STUDIES[:1])
        loaded.save()

        with active.experiment('coalitions'):
            self.assertEqual(active.chosen(), '')

    def test_rows_are_filtered_to_the_chosen_treatments(self):
        rows = [{'treatment': 'private', 'x': '1'},
                {'treatment': 'public', 'x': '2'},
                {'treatment': 'private_no_dwl', 'x': '3'}]
        with active.experiment('coalitions'):
            self.assertEqual(len(active.within(rows)), 3)
            active.choose('study2')
            kept = active.within(rows)
        self.assertEqual([r['x'] for r in kept], ['1', '3'])

    def test_a_table_without_treatments_is_left_alone(self):
        rows = [{'group_uid': 'g', 'x': '1'}]
        with active.experiment('coalitions'):
            active.choose('study1')
            self.assertEqual(active.within(rows), rows)

    def test_the_pooled_tables_are_used_until_the_study_has_its_own(self):
        from chatlens.core import config

        with active.experiment('coalitions'):
            active.choose('study1')
            self.assertEqual(active.datasets_dir(), config.DATASETS_DIR)
            said = active.missing_datasets()
        self.assertIn('Study 1', said)
        self.assertIn('chatlens studies', said)

    def test_a_built_study_is_read_from_its_own_folder(self):
        from chatlens.core import config, perstudy

        with active.experiment('coalitions'):
            active.choose('study1')
            folder = perstudy.directory(active.study()) / 'datasets'
            folder.mkdir(parents=True, exist_ok=True)
            (folder / 'x_chat_by_partner_nlp.csv').write_text(
                'group_uid\ng\n', encoding='utf-8')
            self.assertEqual(active.datasets_dir(), folder)
            self.assertNotEqual(active.datasets_dir(), config.DATASETS_DIR)
            self.assertEqual(active.missing_datasets(), '')


class UnitsWithinStudyTests(unittest.TestCase):
    """The relations table and the test beside it describe the same sample.

    The extraction is made once on the whole corpus, because a relation comes
    out of a single sentence and parsing eight thousand messages takes two
    minutes. What has to be narrowed is the result: the frequencies shown and
    the threshold a relation must reach to be tested are properties of the
    sample under analysis.
    """

    STUDIES = [
        {'slug': 'study1', 'name': 'Study 1', 'treatments': ['a', 'b'],
         'baseline': 'a'},
    ]

    def setUp(self):
        from chatlens.core import experiment as experiment_module

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        library.use_library(Path(self.tmp.name))
        library.ensure_root()
        path = library.create('Narrow', 'generic_chat')
        loaded = experiment_module.load(path)
        loaded.set('studies', self.STUDIES)
        loaded.save()
        active.forget_choices()
        self.addCleanup(active.forget_choices)

        self.messages = [{'group_uid': 'g1', 'treatment': 'a'},
                         {'group_uid': 'g2', 'treatment': 'b'},
                         {'group_uid': 'g3', 'treatment': 'c'}]
        self.per_unit = {('g1', '1', '2'): {('i', 'support', 'you')},
                         ('g2', '1', '2'): {('i', 'help', 'you')},
                         ('g3', '1', '2'): {('i', 'leave', 'you')}}

    def test_the_whole_sample_keeps_every_unit(self):
        with active.experiment('narrow'):
            kept = active.units_within(self.per_unit, self.messages)
        self.assertEqual(len(kept), 3)

    def test_a_chosen_study_keeps_only_its_groups(self):
        with active.experiment('narrow'):
            active.choose('study1')
            kept = active.units_within(self.per_unit, self.messages)
        self.assertEqual(sorted(k[0] for k in kept), ['g1', 'g2'])

    def test_a_group_level_key_is_narrowed_too(self):
        per_unit = {('g1',): {('i', 'support', 'you')},
                    ('g3',): {('i', 'leave', 'you')}}
        with active.experiment('narrow'):
            active.choose('study1')
            kept = active.units_within(per_unit, self.messages)
        self.assertEqual(list(kept), [('g1',)])


if __name__ == '__main__':
    unittest.main()
