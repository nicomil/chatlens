"""Dashboard tests.

They do not start the server: they check the two parts where the real problems
nest — building the command, which executes processes, and reading the log,
which has to make progress bars legible.

    python tests/test_dashboard.py
"""

import sys
import tempfile
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
    """The archive is an index: from one row you reach all of that run.

    These used to read whichever workspace the process happened to have active
    and skip when it held no run — so in CI they never ran at all, and on a
    developer's machine they read that developer's own results. They build two
    runs of their own now.
    """

    @classmethod
    def setUpClass(cls):
        import json

        from chatlens.core import config

        cls.tmp = tempfile.TemporaryDirectory()
        workspace = Path(cls.tmp.name)
        (workspace / 'output' / 'datasets').mkdir(parents=True)
        # Put back on the way out: `config` is process-global, and a workspace
        # left pointing at a deleted directory breaks every test that runs
        # afterwards.
        cls.previous = config.WORKSPACE
        config.use_workspace(workspace)

        # Two runs, a second apart in name, each with a dataset and a report,
        # so that "every row opens its own run" is a claim about two things.
        for index, stamp in enumerate(('2026-01-01_120024', '2026-01-01_120029')):
            run = workspace / 'output' / 'runs' / stamp / 'datasets'
            run.mkdir(parents=True)
            (run / 'demo_chat_aggregated_nlp.csv').write_text(
                'group_uid\ng1\n', encoding='utf-8')
            (run.parent / 'report.html').write_text('<p>ok</p>', encoding='utf-8')
            (run.parent / 'run.json').write_text(json.dumps({
                'timestamp': f'2026-01-01T12:00:{24 + index * 5}',
                'stem': 'demo', 'stages': ['measures'],
                'n_messages': 100 + index,
                'levels': {'group': 4}, 'failed_stage': None,
            }), encoding='utf-8')

        # And one that did not finish, so that "a failure is stated in words"
        # is a claim about something rather than a skip.
        broken = workspace / 'output' / 'runs' / '2026-01-01_130000'
        broken.mkdir(parents=True)
        (broken / 'run.json').write_text(json.dumps({
            'timestamp': '2026-01-01T13:00:00', 'stem': 'demo',
            'stages': ['measures', 'topics'], 'n_messages': 100,
            'levels': {'group': 4}, 'failed_stage': 'TopicGPT',
        }), encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        from chatlens.core import config

        config.use_workspace(cls.previous)
        cls.tmp.cleanup()

    def _a_run(self):
        from chatlens.core import archive, config

        runs = archive.list_runs(config.OUTPUT_DIR)
        self.assertTrue(runs, 'the fixture wrote no runs')
        return runs[0]

    def test_every_row_opens_its_own_run(self):
        import re

        panel = views.runs_panel()
        targets = re.findall(r'hx-get="[^"]*/run/([^"]+)"', panel)
        self.assertEqual(len(targets), 3)
        # Every row leads to its own run, not all to the same one.
        self.assertEqual(len(targets), len(set(targets)))

    def test_detail_shows_parameters_and_files(self):
        from chatlens.core import archive, config

        run = next(r for r in archive.list_runs(config.OUTPUT_DIR)
                   if not r.get('failed_stage'))
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
        self.assertTrue(failed, 'the fixture wrote no incomplete run')
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
        # The runner is per workspace now, so it is asked for by the
        # workspace rather than read off the server module.
        from chatlens.web import runner as runner_module
        self.assertFalse(runner_module.current().running)

    def test_a_post_marked_cross_site_is_refused(self):
        response, _ = self.request(
            'POST', '/run',
            {'Cookie': f'{self.srv.COOKIE_NAME}={self.srv.TOKEN}',
             'Sec-Fetch-Site': 'cross-site'},
            body='command=all')
        self.assertEqual(response.status, 403)
        # The runner is per workspace now, so it is asked for by the
        # workspace rather than read off the server module.
        from chatlens.web import runner as runner_module
        self.assertFalse(runner_module.current().running)

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

    def test_the_policy_allows_what_the_page_actually_does(self):
        """A policy is only right if the page still works under it.

        Everything interactive here is htmx, and htmx works by XHR. With
        `default-src 'none'` and no `connect-src`, the browser refuses every
        one of those requests: the log stops polling, the estimate never
        updates, uploads fail. Nothing appears in the page and nothing appears
        in the console — it looks like a dead button.

        Checked as a pair, since the policy on its own always looks fine.
        """
        response, payload = self.request('GET', f'/?t={self.srv.TOKEN}')
        body = payload.decode('utf-8', 'replace')
        policy = response.getheader('Content-Security-Policy') or ''
        if 'htmx' in body:
            self.assertIn("connect-src 'self'", policy)
        if '<iframe' in body or 'frame-src' in policy:
            self.assertIn("frame-src 'self'", policy)

    def test_the_page_carries_no_script_the_policy_would_refuse(self):
        """`script-src 'self'` means an inline script never runs.

        The theme was applied by three lines inline in the head, so the
        browser refused them and a reader's choice of light or dark was lost
        on every reload — the policy working exactly as written, against a
        page that had not been told.
        """
        import re

        response, payload = self.request('GET', f'/?t={self.srv.TOKEN}')
        body = payload.decode('utf-8', 'replace')
        self.assertIn("script-src 'self'",
                      response.getheader('Content-Security-Policy') or '')
        inline = [tag for tag in re.findall(r'<script\b[^>]*>(.*?)</script>',
                                            body, re.S) if tag.strip()]
        self.assertEqual(inline, [], 'an inline script cannot run under the '
                                     'policy this server sends')

    def test_the_theme_is_applied_by_a_file_the_browser_may_fetch(self):
        response, payload = self.request('GET', f'/?t={self.srv.TOKEN}')
        body = payload.decode('utf-8', 'replace')
        self.assertIn('/static/theme.js', body)
        # With the session cookie, which is what a browser sends with it.
        served, script = self.request(
            'GET', '/static/theme.js',
            {'Cookie': f'{self.srv.COOKIE_NAME}={self.srv.TOKEN}'})
        self.assertEqual(served.status, 200)
        self.assertIn(b'chatlens-theme', script)

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



class LibraryRoutingTests(unittest.TestCase):
    """Several experiments reachable from one window.

    These run the real handler, because what is being checked is which
    workspace a request ends up reading — and that is decided in the routing,
    not in the views.
    """

    @classmethod
    def setUpClass(cls):
        import http.server
        import tempfile
        import threading as _threading

        from chatlens.core import library
        from chatlens.web import server as srv

        cls.tmp = tempfile.TemporaryDirectory()
        library.use_library(Path(cls.tmp.name))
        library.create('First Study')
        library.create('Second Study', adapter='otree_coalition')

        cls.srv = srv
        srv.TOKEN = 'library-test-token'
        srv.LIBRARY_MODE = True
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
        cls.tmp.cleanup()

    def get(self, path, extra=None):
        import http.client

        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        headers = {'Host': f'127.0.0.1:{self.port}',
                   'Cookie': f'{self.srv.COOKIE_NAME}={self.srv.TOKEN}'}
        headers.update(extra or {})
        conn.request('GET', path, headers=headers)
        response = conn.getresponse()
        body = response.read().decode('utf-8', 'replace')
        conn.close()
        return response, body

    def post(self, path, body):
        import http.client

        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        conn.request('POST', path, body=body, headers={
            'Host': f'127.0.0.1:{self.port}',
            'Cookie': f'{self.srv.COOKIE_NAME}={self.srv.TOKEN}',
            'Origin': f'http://127.0.0.1:{self.port}',
            'Sec-Fetch-Site': 'same-origin',
            'Content-Type': 'application/x-www-form-urlencoded'})
        response = conn.getresponse()
        payload = response.read().decode('utf-8', 'replace')
        conn.close()
        return response, payload

    # --- the list ---------------------------------------------------------

    def test_the_root_lists_the_experiments(self):
        response, body = self.get('/')
        self.assertEqual(response.status, 200)
        self.assertIn('First Study', body)
        self.assertIn('Second Study', body)

    def test_the_list_says_what_each_one_still_needs(self):
        _response, body = self.get('/')
        # Roles come from the adapter, so the two differ.
        self.assertIn('needs messages', body)
        self.assertIn('needs wide, chat', body)

    # --- one experiment ---------------------------------------------------

    def test_an_experiment_opens_where_the_work_is(self):
        """A study is a sequence, and its address lands on the unfinished part
        of it rather than always on the same screen.

        A real redirect, not an htmx header: sent only as the header, a person
        clicking a study in the library landed on the words "Moved to
        /experiment/…" and a link to click again.
        """
        response, _body = self.get('/experiment/first-study')
        self.assertEqual(response.status, 303)
        self.assertIn('/experiment/first-study/step/',
                      response.getheader('Location') or '')

    def test_htmx_is_told_to_move_the_window_instead(self):
        """It is swapping a fragment into a page that is already open, so a
        redirect would put the new page inside the old one."""
        response, _body = self.get('/experiment/first-study',
                                   {'HX-Request': 'true'})
        self.assertEqual(response.status, 200)
        self.assertIn('/experiment/first-study/step/',
                      response.getheader('HX-Redirect') or '')

    def test_an_experiment_opens_on_its_own_page(self):
        response, body = self.get('/experiment/first-study/step/data')
        self.assertEqual(response.status, 200)
        self.assertIn('First Study', body)

    def test_every_fragment_says_which_experiment_it_is_about(self):
        """The point of the whole arrangement.

        A log poll that did not name its experiment would read whichever one
        the server happened to have active when it arrived.
        """
        # The run form lives on step 4 now, which is where those two
        # endpoints are addressed from.
        _response, body = self.get('/experiment/first-study/step/run')
        for endpoint in ('/run', '/estimate'):
            self.assertIn(f'/experiment/first-study{endpoint}', body)
        self.assertNotIn('hx-post="/run"', body)

    def test_the_fragments_answer_under_the_experiment(self):
        for fragment in ('log', 'report', 'step/outcome'):
            response, _body = self.get(f'/experiment/first-study/{fragment}')
            self.assertEqual(response.status, 200, fragment)

    def test_an_unknown_experiment_is_a_404_not_a_crash(self):
        response, body = self.get('/experiment/does-not-exist')
        self.assertEqual(response.status, 404)
        self.assertIn('does-not-exist', body)

    def test_a_run_can_be_stopped_from_the_page(self):
        """`Runner.stop` has always existed and has always been tested; until
        now nothing in the interface called it."""
        response, _body = self.post('/experiment/first-study/stop', '')
        self.assertEqual(response.status, 200)

    def test_the_failure_badge_says_what_happened_not_only_a_number(self):
        from chatlens.web import views
        self.assertIn('missing', views.EXIT_MEANING[3])
        self.assertIn('request', views.EXIT_MEANING[-15])

    def test_the_export_says_what_it_could_not_answer(self):
        """A summary that quietly omits the findings that were blocked is a
        summary that misleads."""
        response, body = self.get('/experiment/first-study/findings/export')
        self.assertEqual(response.status, 200)
        self.assertIn('Not answered here', body)
        self.assertNotIn('Working it out', body)

    def test_the_preset_decides_the_run_without_any_javascript(self):
        """The three cards were decoration: `build_command` never read the
        field they set, and they worked only because a script in the browser
        copied them onto two checkboxes."""
        from chatlens.web.runner import build_command, stages

        self.assertEqual(stages({'preset': ['base']}),
                         {'llm': False, 'topics': False})
        self.assertEqual(stages({'preset': ['full']}),
                         {'llm': True, 'topics': True})

        argv = build_command({'preset': ['full']})
        self.assertIn('--llm', argv)
        self.assertIn('--topics', argv)
        self.assertNotIn('--llm', build_command({'preset': ['base']}))

    def test_an_invented_preset_does_not_start_a_paid_run(self):
        """It falls back to what the form otherwise says, and an empty form
        says nothing paid."""
        from chatlens.web.runner import build_command

        argv = build_command({'preset': ['expensive-please']})
        self.assertNotIn('--llm', argv)
        self.assertNotIn('--topics', argv)

    def test_a_number_leads_back_to_the_messages_behind_it(self):
        """The path that did not exist: from a term to the sentences it came
        from, with the two counts kept apart."""
        response, body = self.get(
            '/experiment/first-study/inspect?term=hello&unit=group')
        self.assertEqual(response.status, 200)
        self.assertTrue(body.strip())
        self.assertNotIn('Traceback', body)

    def test_the_inspector_says_when_there_is_nothing_merged_to_look_at(self):
        """This study has never been run, so the honest answer is that there
        are no messages yet — not an empty box."""
        _response, body = self.get(
            '/experiment/first-study/inspect'
            '?term=zzz-nothing-like-this&unit=group')
        self.assertIn('not been merged', body)

    def test_the_404_does_not_echo_markup_from_the_url(self):
        """The message quotes the path, and the path is written by whoever
        sends the request."""
        response, body = self.get('/experiment/%3Cb%3Ex%3C/b%3E')
        self.assertEqual(response.status, 404)
        self.assertNotIn('<b>', body)

    def test_an_unknown_words_download_is_a_404_not_a_word_cloud(self):
        """Anything under words/ that was not the CSV used to fall through to
        the image branch and be answered with a figure."""
        response, _body = self.get('/experiment/first-study/findings/words/anything')
        self.assertEqual(response.status, 404)

    def test_traversal_in_the_url_is_refused(self):
        for attempt in ('/experiment/..', '/experiment/../../etc',
                        '/experiment/First%20Study'):
            response, _body = self.get(attempt)
            self.assertEqual(response.status, 404, attempt)

    # --- creating ---------------------------------------------------------

    def test_creating_one_returns_the_updated_list(self):
        response, body = self.post('/experiments/new',
                                   'name=Third Study&adapter=generic_chat')
        self.assertEqual(response.status, 200)
        self.assertIn('Third Study', body)
        self.assertIn('First Study', body)

    def test_the_example_can_be_made_from_the_page(self):
        """The empty library invites you to press a button that, until now,
        did not exist anywhere in the interface.

        One test rather than two because the library is shared across the
        methods of this class: made and made-again are one sequence.
        """
        response, body = self.post('/experiments/example', '')
        self.assertEqual(response.status, 200)
        self.assertIn('Example ready', body)
        self.assertIn('demo', self.get('/')[1].lower())

        response, body = self.post('/experiments/example', '')
        self.assertEqual(response.status, 200)
        self.assertIn('already', body)

    def test_a_duplicate_name_is_a_message_in_the_form(self):
        """Something to correct, not an error page."""
        self.post('/experiments/new', 'name=Fourth Study&adapter=generic_chat')
        response, body = self.post('/experiments/new',
                                   'name=fourth   study&adapter=generic_chat')
        self.assertEqual(response.status, 200)
        self.assertIn('already exists', body)

    def test_an_unusable_name_is_a_message_too(self):
        response, body = self.post('/experiments/new',
                                   'name=%21%21%21&adapter=generic_chat')
        self.assertEqual(response.status, 200)
        self.assertIn('no letters or digits', body)

    def test_an_invented_adapter_falls_back_instead_of_being_used(self):
        self.post('/experiments/new', 'name=Fifth Study&adapter=rm -rf /')
        from chatlens.core import experiment, library

        loaded = experiment.load(library.path_for('fifth-study'))
        self.assertEqual(loaded.adapter, 'generic_chat')

    # --- an archived run, and the files it produced ------------------------

    def _archived_run(self, slug='first-study'):
        """A run folder of the shape `archive.save` leaves behind."""
        import json

        from chatlens.core import library

        run = (library.path_for(slug) / 'output' / 'runs'
               / '2026-01-01_000000')
        (run / 'datasets').mkdir(parents=True, exist_ok=True)
        (run / 'datasets' / 'x_chat_by_partner_nlp.csv').write_text(
            'group_uid\ng1\n', encoding='utf-8')
        (run / 'report.html').write_text('<p>report</p>', encoding='utf-8')
        (run / 'run.json').write_text(json.dumps({
            'timestamp': '2026-01-01T00:00:00', 'stem': 'x',
            'stages': ['measures'], 'n_messages': 1, 'levels': {'group': 1},
            'failed_stage': None}), encoding='utf-8')
        return run

    def test_every_link_on_a_run_detail_page_is_reachable(self):
        """They were written to the root, where in library mode nothing of
        this study is served: each one answered 404."""
        import re

        self._archived_run()
        response, body = self.get(
            '/experiment/first-study/run/2026-01-01_000000')
        self.assertEqual(response.status, 200)

        links = re.findall(r'(?:href|src)="([^"]*runs/[^"]*)"', body)
        self.assertTrue(links, 'the run detail page offered no files at all')
        for link in links:
            with self.subTest(link=link):
                self.assertTrue(
                    link.startswith('/experiment/first-study/'),
                    f'{link} does not name the study it belongs to')
                self.assertEqual(self.get(link)[0].status, 200)

    def test_a_run_file_is_served_from_its_own_study(self):
        """Not from whichever folder the process happened to start in."""
        self._archived_run()
        response, body = self.get(
            '/experiment/first-study/runs/2026-01-01_000000'
            '/datasets/x_chat_by_partner_nlp.csv')
        self.assertEqual(response.status, 200)
        self.assertIn('g1', body)


class MappingRoutesTests(unittest.TestCase):
    """Configuring an experiment without opening an editor."""

    @classmethod
    def setUpClass(cls):
        import http.server
        import tempfile
        import threading as _threading

        from chatlens.core import library
        from chatlens.web import server as srv

        cls.tmp = tempfile.TemporaryDirectory()
        library.use_library(Path(cls.tmp.name))
        path = library.create('Mapped Study')
        (path / 'input' / 'chat_log.csv').write_text(
            'team,condition,from_seat,to_seat,sent_at,text\n'
            'g1,ctrl,1,2,2026-01-01T10:00:00,hello\n'
            'g1,ctrl,2,1,2026-01-01T10:01:00,hi\n'
            'g2,treat,1,2,2026-01-01T10:02:00,hey\n',
            encoding='utf-8')

        cls.srv = srv
        srv.TOKEN = 'mapping-test-token'
        srv.LIBRARY_MODE = True
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
        cls.tmp.cleanup()

    def call(self, method, path, body=None):
        import http.client

        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        headers = {'Host': f'127.0.0.1:{self.port}',
                   'Cookie': f'{self.srv.COOKIE_NAME}={self.srv.TOKEN}'}
        if body is not None:
            headers.update({'Origin': f'http://127.0.0.1:{self.port}',
                            'Sec-Fetch-Site': 'same-origin',
                            'Content-Type':
                                'application/x-www-form-urlencoded'})
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        payload = response.read().decode('utf-8', 'replace')
        conn.close()
        return response, payload

    def config(self):
        from chatlens.core import experiment, library

        return experiment.load(library.path_for('mapped-study'))

    # --- assigning a file to a role ---------------------------------------

    def test_a_file_whose_name_matches_nothing_can_still_be_used(self):
        """The case that made this necessary: "chat_log.csv" is not
        "messages*.csv", and the answer cannot be "rename your file"."""
        response, body = self.call(
            'POST', '/experiment/mapped-study/input',
            'file=chat_log.csv&role=messages')
        self.assertEqual(response.status, 200)
        self.assertIn('is now the messages file', body)
        self.assertEqual(self.config().input['messages'], 'chat_log.csv')

    def test_an_assigned_file_counts_as_present(self):
        self.call('POST', '/experiment/mapped-study/input',
                  'file=chat_log.csv&role=messages')
        _response, body = self.call('GET', '/')
        self.assertIn('ready', body)
        self.assertNotIn('needs messages', body)

    def test_a_role_the_adapter_does_not_have(self):
        _response, body = self.call('POST', '/experiment/mapped-study/input',
                                    'file=chat_log.csv&role=invented')
        self.assertIn('not a role', body)

    def test_a_file_that_is_not_there(self):
        _response, body = self.call('POST', '/experiment/mapped-study/input',
                                    'file=../../etc/passwd&role=messages')
        self.assertIn('no file called', body)

    # --- the outcome ------------------------------------------------------

    def test_the_settings_page_offers_an_outcome(self):
        _response, body = self.call('GET', '/experiment/mapped-study/step/outcome')
        self.assertIn('What to explain', body)
        self.assertIn('name="unit"', body)

    def test_saving_an_outcome_writes_it(self):
        response, body = self.call(
            'POST', '/experiment/mapped-study/outcome',
            'column=accepted&kind=binary&unit=dyad_directed&label=Offer+taken')
        self.assertEqual(response.status, 200)
        self.assertIn('Saved', body)
        saved = self.config().declared['outcome']
        self.assertEqual(saved['column'], 'accepted')
        self.assertEqual(saved['unit'], 'dyad_directed')

    def test_clearing_the_outcome_removes_the_section(self):
        self.call('POST', '/experiment/mapped-study/outcome',
                  'column=accepted&kind=binary&unit=dyad_directed')
        _response, body = self.call('POST',
                                    '/experiment/mapped-study/outcome',
                                    'column=&kind=binary&unit=dyad_directed')
        self.assertIn('Cleared', body)
        # `declared` always holds every section key; what matters is that the
        # cleared one is empty and so is never written back to the file.
        self.assertFalse(self.config().declared['outcome'])
        self.assertNotIn('outcome', self.config().to_config())
        self.assertIsNone(self.config().outcome)

    def test_a_unit_we_never_offered_is_refused(self):
        """The selects are ours, so a value outside them is not our form."""
        _response, body = self.call(
            'POST', '/experiment/mapped-study/outcome',
            'column=accepted&kind=binary&unit=per_message')
        self.assertIn('Unit must be one of', body)

    def test_a_kind_we_never_offered_is_refused(self):
        _response, body = self.call(
            'POST', '/experiment/mapped-study/outcome',
            'column=accepted&kind=ordinal&unit=group')
        self.assertIn('Kind must be one of', body)

    def test_an_experiment_with_no_outcome_still_runs(self):
        """The whole descriptive side must not depend on declaring one."""
        self.call('POST', '/experiment/mapped-study/outcome',
                  'column=&kind=binary&unit=group')
        self.call('POST', '/experiment/mapped-study/input',
                  'file=chat_log.csv&role=messages')
        _response, body = self.call('GET', '/')
        self.assertIn('ready', body)

    # --- the columns ------------------------------------------------------

    def test_the_form_offers_the_columns_the_file_has(self):
        self.call('POST', '/experiment/mapped-study/input',
                  'file=chat_log.csv&role=messages')
        _response, body = self.call('GET',
                                    '/experiment/mapped-study/step/columns')
        for column in ('team', 'from_seat', 'to_seat', 'text', 'sent_at',
                       'condition'):
            self.assertIn(f'value="{column}"', body)

    def test_the_guess_arrives_already_chosen(self):
        self.call('POST', '/experiment/mapped-study/input',
                  'file=chat_log.csv&role=messages')
        _response, body = self.call('GET',
                                    '/experiment/mapped-study/step/columns')
        # In the ordinary case the mapping is right and only needs confirming.
        self.assertIn('value="team" selected', body)
        self.assertIn('value="text" selected', body)

    def test_saving_writes_the_configuration(self):
        self.call('POST', '/experiment/mapped-study/input',
                  'file=chat_log.csv&role=messages')
        response, body = self.call(
            'POST', '/experiment/mapped-study/columns',
            'col_group=team&col_sender=from_seat&col_receiver=to_seat'
            '&col_body=text&col_treatment=condition')
        self.assertEqual(response.status, 200)
        self.assertIn('Saved', body)
        columns = self.config().declared['columns']
        self.assertEqual(columns['group'], 'team')
        self.assertEqual(columns['body'], 'text')

    def test_a_column_the_file_does_not_have_is_refused(self):
        """Otherwise a value from anywhere lands in the configuration."""
        self.call('POST', '/experiment/mapped-study/input',
                  'file=chat_log.csv&role=messages')
        _response, body = self.call(
            'POST', '/experiment/mapped-study/columns',
            'col_group=team&col_sender=from_seat&col_receiver=to_seat'
            '&col_body=made_up_column')
        self.assertIn('not a column in chat_log.csv', body)
        self.assertNotEqual(
            self.config().declared.get('columns', {}).get('body'),
            'made_up_column')

    def test_saving_an_incomplete_mapping_says_what_is_still_needed(self):
        self.call('POST', '/experiment/mapped-study/input',
                  'file=chat_log.csv&role=messages')
        _response, body = self.call('POST',
                                    '/experiment/mapped-study/columns',
                                    'col_group=team&col_body=text')
        self.assertIn('still needs', body)
        self.assertIn('Sender', body)

    # --- the treatments ---------------------------------------------------

    def test_the_treatment_values_come_from_the_data(self):
        self.call('POST', '/experiment/mapped-study/input',
                  'file=chat_log.csv&role=messages')
        self.call('POST', '/experiment/mapped-study/columns',
                  'col_group=team&col_sender=from_seat&col_receiver=to_seat'
                  '&col_body=text&col_treatment=condition')
        _response, body = self.call('GET',
                                    '/experiment/mapped-study/step/columns')
        # Read from the column, not typed by anyone.
        self.assertIn('name="tr_ctrl"', body)
        self.assertIn('name="tr_treat"', body)

    def test_naming_them_writes_the_labels(self):
        self.call('POST', '/experiment/mapped-study/input',
                  'file=chat_log.csv&role=messages')
        self.call('POST', '/experiment/mapped-study/columns',
                  'col_group=team&col_sender=from_seat&col_receiver=to_seat'
                  '&col_body=text&col_treatment=condition')
        _response, body = self.call('POST',
                                    '/experiment/mapped-study/treatments',
                                    'tr_ctrl=Control&tr_treat=Treated')
        self.assertIn('Saved 2 names', body)
        self.assertEqual(self.config().treatments,
                         {'ctrl': 'Control', 'treat': 'Treated'})


class VendoredAssetTests(unittest.TestCase):
    """The one file in static/ that is not ours.

    The filename carries no version, so which htmx a release shipped could only
    be learnt by reading minified source — and nothing would have noticed the
    file being swapped by an editor's "save all" or a bad merge.
    """

    EXPECTED = 'e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447'
    VERSION = '2.0.4'

    def path(self):
        return (PROJECT_ROOT / 'src' / 'chatlens' / 'web' / 'static'
                / 'htmx.min.js')

    def test_it_is_the_version_we_wrote_down(self):
        import hashlib

        digest = hashlib.sha256(self.path().read_bytes()).hexdigest()
        self.assertEqual(
            digest, self.EXPECTED,
            'htmx.min.js is not the file this release was tested against. If '
            'the change was deliberate, update VENDORED.md and this test '
            'together.')

    def test_the_note_says_which_version(self):
        note = (self.path().parent / 'VENDORED.md').read_text(encoding='utf-8')
        self.assertIn(self.VERSION, note)
        self.assertIn(self.EXPECTED, note)

    def test_nothing_else_in_static_is_unaccounted_for(self):
        """A new file in here is either ours or somebody else's, and the note
        has to say which."""
        ours = {'style.css', 'app.js', 'theme.js', 'VENDORED.md'}
        theirs = {'htmx.min.js'}
        present = {p.name for p in self.path().parent.iterdir()
                   if p.is_file() and not p.name.startswith('.')}
        self.assertEqual(present - ours - theirs, set())


if __name__ == '__main__':
    unittest.main(verbosity=2)
