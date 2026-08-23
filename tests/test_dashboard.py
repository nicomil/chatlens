"""Dashboard tests.

They do not start the server: they check the two parts where the real problems
nest — building the command, which executes processes, and reading the log,
which has to make progress bars legible.

    python tests/test_dashboard.py
"""

import sys
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from web import views  # noqa: E402
from web.runner import Runner, build_command  # noqa: E402


class FormWiringTests(unittest.TestCase):
    """A run must start only from the form submission."""

    def test_form_tag_has_exactly_one_destination(self):
        """Two hx-post on the same element: every change launched a run.

        It really happened: the estimate request had been put on the form,
        which already carried the run's, and ticking a box started the
        execution.
        """
        import re

        form = views.form_panel()
        opening = re.search(r'<form\b[^>]*>', form).group(0)
        self.assertEqual(opening.count('hx-post'), 1, msg=opening)
        self.assertIn('/run', opening)

    def test_estimate_lives_on_its_own_element(self):
        import re

        panel = views.estimate_panel({})
        opening = re.search(r'<div\b[^>]*>', panel).group(0)
        self.assertIn('/estimate', opening)
        # It refreshes by listening to the form, without being an active part
        # of it.
        self.assertIn('hx-trigger="change from:#launch"', opening)
        self.assertIn('hx-include="#launch"', opening)

    def test_no_element_triggers_run_on_change(self):
        """No element may call /run except on an explicit submission."""
        import re

        form = views.form_panel()
        for tag in re.findall(r'<[a-z]+\b[^>]*hx-post="/run"[^>]*>', form):
            self.assertNotIn('hx-trigger', tag, msg=tag)

    def test_presets_are_choices_not_submitters(self):
        form = views.form_panel()
        self.assertIn('type="radio" name="preset"', form)
        self.assertNotIn('type="submit" class="preset"', form)


class CommandBuildingTests(unittest.TestCase):
    """The command is built from known values: never from browser text."""

    def test_minimal_command(self):
        argv = build_command({'command': ['all']})
        self.assertEqual(argv[1:], ['run.py', 'all'])

    def test_unknown_command_falls_back_instead_of_passing_through(self):
        argv = build_command({'command': ['rm -rf /']})
        self.assertEqual(argv[2], 'all')

    def test_injected_values_are_discarded(self):
        argv = build_command({
            'command': ['analyze'], 'llm': ['1'],
            'llm_model': ['gpt-4o; rm -rf /'],
            'llm_replicates': ['99'],
            'llm_level': ['group', '../../etc/passwd'],
        })
        joined = ' '.join(argv)
        self.assertNotIn('rm -rf', joined)
        self.assertNotIn('passwd', joined)
        self.assertNotIn('99', joined)
        # The valid value in the same field survives.
        self.assertIn('group', argv)

    def test_options_are_separate_arguments(self):
        """No shell: every option is an element of the list."""
        argv = build_command({'command': ['all'], 'llm': ['1'],
                              'llm_model': ['gpt-4o']})
        self.assertIn('--llm-models', argv)
        self.assertEqual(argv[argv.index('--llm-models') + 1], 'gpt-4o')

    def test_topics_carry_the_repository_path(self):
        argv = build_command({'command': ['all'], 'topics': ['1']})
        self.assertIn('--topicgpt-repo', argv)
        self.assertIn('--topicgpt-model', argv)


class ArchiveViewTests(unittest.TestCase):
    """The archive is an index: from one row you reach all of that run."""

    def _a_run(self):
        from src import archive, config

        runs = archive.list_runs(config.OUTPUT_DIR)
        if not runs:
            self.skipTest('no archived run in this environment')
        return runs[0]

    def test_every_row_opens_its_own_run(self):
        import re

        from src import archive, config

        panel = views.runs_panel()
        if not archive.list_runs(config.OUTPUT_DIR):
            self.skipTest('no archived run in this environment')
        targets = re.findall(r'hx-get="/run/([^"]+)"', panel)
        self.assertTrue(targets)
        # Every row leads to its own run, not all to the same one.
        self.assertEqual(len(targets), len(set(targets)))

    def test_detail_shows_parameters_and_files(self):
        run = self._a_run()
        detail = views.run_detail(run['path'].name)
        self.assertIn('Messages analysed', detail)
        # The files produced are reachable from there.
        self.assertIn(f'/runs/{run["path"].name}/', detail)
        # And you can go back to the latest result.
        self.assertIn('hx-get="/report"', detail)

    def test_time_includes_seconds(self):
        """Runs a few moments apart must be told apart."""
        first = views._run_time('2026-01-01T12:00:24')
        second = views._run_time('2026-01-01T12:00:29')
        self.assertNotEqual(first, second)
        self.assertTrue(first.endswith('12:00:24'), msg=first)

    def test_unknown_run_is_handled(self):
        self.assertIn('not found', views.run_detail('does-not-exist'))

    def test_failure_is_stated_not_implied(self):
        """An incomplete run must say so in words, not only with a colour."""
        from src import archive, config

        failed = [r for r in archive.list_runs(config.OUTPUT_DIR)
                  if r.get('failed_stage')]
        if not failed:
            self.skipTest('no incomplete run in this environment')
        detail = views.run_detail(failed[0]['path'].name)
        self.assertIn('not completed', detail)


class LogReadingTests(unittest.TestCase):
    def _run(self, script):
        runner = Runner()
        self.assertTrue(runner.start([sys.executable, '-c', script]))
        for _ in range(200):
            if not runner.running:
                break
            time.sleep(0.05)
        return runner.snapshot()

    def test_progress_bar_collapses_to_one_line(self):
        """A hundred rewrites must not leave a hundred lines."""
        state = self._run(
            "import sys\n"
            "for i in range(100): sys.stdout.write(f'{i}%|## | {i}/100\\r')\n"
            "sys.stdout.write('\\ndone\\n')"
        )
        self.assertEqual(state['lines'], ['99%|## | 99/100', 'done'])

    def test_plain_lines_are_all_kept(self):
        state = self._run(
            "print('one'); print('two'); print('three')"
        )
        self.assertEqual(state['lines'], ['one', 'two', 'three'])

    def test_exit_code_is_reported(self):
        state = self._run("import sys; print('ko'); sys.exit(3)")
        self.assertEqual(state['returncode'], 3)
        self.assertFalse(state['running'])

    def test_only_one_run_at_a_time(self):
        runner = Runner()
        self.assertTrue(runner.start([sys.executable, '-c', 'import time; time.sleep(2)']))
        self.assertFalse(runner.start([sys.executable, '-c', 'pass']))
        runner.stop()

    def test_log_does_not_grow_without_limit(self):
        state = self._run("[print(i) for i in range(900)]")
        self.assertLessEqual(len(state['lines']), 500)
        # The tail is kept, which is the part that matters.
        self.assertEqual(state['lines'][-1], '899')


if __name__ == '__main__':
    unittest.main(verbosity=2)
