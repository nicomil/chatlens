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
import unittest
from pathlib import Path

# Runs from a source checkout without installing: the package is under src/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from chatlens.core import library  # noqa: E402
from chatlens.web import active, views_compare, views_library  # noqa: E402
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
            page = views_library.settings_page('bare-study')
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
            page = views_participation.page('bare-study')
        self.assertIn('<!doctype html>', page.lower())
        self.assertNotIn('Traceback', page)

    def test_comparison_says_what_is_missing(self):
        with active.experiment('bare-study'):
            page = views_compare.page('bare-study')
        self.assertIn('<!doctype html>', page.lower())
        self.assertNotIn('Traceback', page)

    def test_neither_page_leaves_a_table_header_over_nothing(self):
        """An empty table with headings and no rows is not an empty state.

        This currently fails on neither page because neither reaches its table
        without data; it is here so that the rebuilt pages keep that property.
        """
        with active.experiment('bare-study'):
            for page in (views_participation.page('bare-study'),
                         views_compare.page('bare-study')):
                if '<tbody></tbody>' in page.replace('\n', ''):
                    self.fail('a table was rendered with no rows in it')


if __name__ == '__main__':
    unittest.main()
