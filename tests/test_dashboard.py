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
# Runs from a source checkout without installing: the package is under src/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from chatlens.web import views  # noqa: E402
from chatlens.web.runner import Runner, build_command  # noqa: E402


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
        # The module, not a script path: once installed there is no run.py.
        self.assertEqual(argv[1:3], ['-m', 'chatlens.cli'])
        self.assertEqual(argv[3], 'all')

    def test_the_workspace_is_passed_on_explicitly(self):
        """The child must analyse the same folder the dashboard is showing."""
        from chatlens.core import config

        argv = build_command({'command': ['all']})
        self.assertIn('--workspace', argv)
        self.assertEqual(argv[argv.index('--workspace') + 1],
                         str(config.WORKSPACE))

    def test_unknown_command_falls_back_instead_of_passing_through(self):
        argv = build_command({'command': ['rm -rf /']})
        self.assertEqual(argv[3], 'all')

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
        from chatlens.core import archive, config

        runs = archive.list_runs(config.OUTPUT_DIR)
        if not runs:
            self.skipTest('no archived run in this environment')
        return runs[0]

    def test_every_row_opens_its_own_run(self):
        import re

        from chatlens.core import archive, config

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
        from chatlens.core import archive, config

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



class ServerAuthorisationTests(unittest.TestCase):
    """The dashboard executes processes: reaching it must not be easy.

    These start the real handler on a free port, because the checks live in the
    headers and nothing below the HTTP layer would exercise them.
    """

    @classmethod
    def setUpClass(cls):
        import http.server
        import threading as _threading

        from chatlens.web import server as srv

        cls.srv = srv
        srv.TOKEN = 'test-token-not-guessable'
        cls.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0),
                                                    srv.Handler)
        cls.port = cls.httpd.server_address[1]
        srv.BOUND = ('127.0.0.1', cls.port)
        cls.thread = _threading.Thread(target=cls.httpd.serve_forever,
                                       daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def request(self, method, path, headers=None, body=None):
        import http.client

        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        head = {'Host': f'127.0.0.1:{self.port}'}
        head.update(headers or {})
        if body is not None:
            head.setdefault('Content-Type',
                            'application/x-www-form-urlencoded')
        conn.request(method, path, body=body, headers=head)
        response = conn.getresponse()
        payload = response.read()
        conn.close()
        return response, payload

    # --- the token --------------------------------------------------------

    def test_page_without_the_token_is_refused(self):
        response, _ = self.request('GET', '/')
        self.assertEqual(response.status, 403)

    def test_the_opening_url_carries_the_token_and_leaves_a_cookie(self):
        response, _ = self.request('GET', f'/?t={self.srv.TOKEN}')
        self.assertEqual(response.status, 200)
        cookie = response.getheader('Set-Cookie') or ''
        self.assertIn(self.srv.COOKIE_NAME, cookie)
        # Never sent on a cross-site request: that is the point of it.
        self.assertIn('SameSite=Strict', cookie)
        self.assertIn('HttpOnly', cookie)

    def test_the_cookie_alone_is_enough_afterwards(self):
        response, _ = self.request(
            'GET', '/log',
            {'Cookie': f'{self.srv.COOKIE_NAME}={self.srv.TOKEN}'})
        self.assertEqual(response.status, 200)

    def test_a_wrong_token_is_refused(self):
        response, _ = self.request(
            'GET', '/log', {'Cookie': f'{self.srv.COOKIE_NAME}=wrong'})
        self.assertEqual(response.status, 403)

    # --- DNS rebinding ----------------------------------------------------

    def test_a_foreign_host_header_is_refused(self):
        """The browser puts the attacker's domain in Host: that is the tell."""
        response, _ = self.request(
            'GET', f'/?t={self.srv.TOKEN}', {'Host': 'evil.example.com'})
        self.assertEqual(response.status, 403)

    # --- cross-site writes ------------------------------------------------

    def test_a_post_from_another_site_is_refused(self):
        response, _ = self.request(
            'POST', '/run',
            {'Cookie': f'{self.srv.COOKIE_NAME}={self.srv.TOKEN}',
             'Origin': 'https://evil.example.com'},
            body='command=all')
        self.assertEqual(response.status, 403)
        self.assertFalse(self.srv.runner.running)

    def test_a_post_marked_cross_site_is_refused(self):
        response, _ = self.request(
            'POST', '/run',
            {'Cookie': f'{self.srv.COOKIE_NAME}={self.srv.TOKEN}',
             'Sec-Fetch-Site': 'cross-site'},
            body='command=all')
        self.assertEqual(response.status, 403)
        self.assertFalse(self.srv.runner.running)

    def test_a_post_without_any_token_is_refused(self):
        response, _ = self.request('POST', '/estimate', body='command=all')
        self.assertEqual(response.status, 403)

    def test_a_post_from_this_page_goes_through(self):
        """The estimate, not the run: it must not cost anything to test."""
        response, _ = self.request(
            'POST', '/estimate',
            {'Cookie': f'{self.srv.COOKIE_NAME}={self.srv.TOKEN}',
             'Origin': f'http://127.0.0.1:{self.port}',
             'Sec-Fetch-Site': 'same-origin'},
            body='command=all')
        self.assertEqual(response.status, 200)

    # --- headers ----------------------------------------------------------

    def test_every_page_carries_a_content_security_policy(self):
        response, _ = self.request('GET', f'/?t={self.srv.TOKEN}')
        policy = response.getheader('Content-Security-Policy') or ''
        self.assertIn("script-src 'self'", policy)
        self.assertIn("frame-ancestors 'self'", policy)

    def test_the_report_can_still_be_framed_by_this_page(self):
        """The panel shows the report in an iframe, so the policy must allow it.

        'frame-ancestors none' blocks being framed by anyone at all, this
        server included: the report panel rendered an empty box and the file
        looked missing when it was not.
        """
        import tempfile

        from chatlens.core import config
        from chatlens.web import views

        # The panel only draws the iframe once a report exists, so make one.
        original = config.OUTPUT_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.OUTPUT_DIR = Path(tmpdir)
                (config.OUTPUT_DIR / 'x_report.html').write_text(
                    '<p>report</p>', encoding='utf-8')
                self.assertIn('<iframe', views.report_panel())
        finally:
            config.OUTPUT_DIR = original
        response, _ = self.request(
            'GET', '/report.html',
            {'Cookie': f'{self.srv.COOKIE_NAME}={self.srv.TOKEN}'})
        policy = response.getheader('Content-Security-Policy') or ''
        self.assertIn("frame-ancestors 'self'", policy)
        self.assertNotIn("frame-ancestors 'none'", policy)


class BindingTests(unittest.TestCase):
    def test_a_public_address_is_refused_with_a_way_out(self):
        from chatlens.web import server as srv

        with self.assertRaises(SystemExit) as raised:
            srv.serve(host='0.0.0.0', port=8765, open_browser=False)
        message = str(raised.exception)
        self.assertIn('Refusing to listen', message)
        # Refusing is only half of it: say what to do instead.
        self.assertIn('ssh', message)


if __name__ == '__main__':
    unittest.main(verbosity=2)
