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


if __name__ == '__main__':
    unittest.main()
