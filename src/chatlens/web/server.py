"""
Local dashboard for launching runs and seeing their results.

    chatlens dashboard

It listens on 127.0.0.1 only: this is a desktop tool, not a service. It executes
processes, so it must not be reachable from the network, and command arguments
are taken from a closed list (see runner.py), never composed from text arriving
from the browser.

Listening on the loopback address is not by itself enough. Any page the
researcher happens to have open can post a form to http://127.0.0.1:8765/run —
a simple request, so no preflight stands in the way — and although the reply is
unreadable to it, the run starts and the API calls get paid for. Worse, a
domain that resolves to 127.0.0.1 (DNS rebinding) makes the browser treat this
server as same-origin.

Three checks together close that off, and none of them costs the user anything:

- the ``Host`` header must be a loopback name, which is what defeats rebinding,
  since the browser sends the attacker's domain there;
- a token generated at startup, handed over in the opening URL and then kept in
  a ``SameSite=Strict`` cookie, so it is never sent on a cross-site request;
- on writes, ``Origin`` and ``Sec-Fetch-Site`` must say the request came from
  this same page.

Standard library only: htmx ships with the project, so the dashboard works
offline too.
"""

from __future__ import annotations

import http.cookies
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from chatlens import adapters
from chatlens.core import config, library, outcome
from chatlens.web import active, multipart, views, views_library
from chatlens.web import (views_compare, views_emotions,
                          views_narratives,
                          views_participation, views_words)
from chatlens.web.runner import build_command, runner

STATIC_DIR = Path(__file__).resolve().parent / 'static'

CONTENT_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
}

COOKIE_NAME = 'chatlens_session'

# The page loads nothing from anywhere else, so everything can be denied and
# only what is actually used allowed back. Inline styles stay permitted because
# the report embeds its own stylesheet; scripts do not, and that is the half
# that matters.
CSP = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    # htmx works by XHR, and every interactive part of the page is htmx: the
    # log poll, the estimate, the file list, the upload. Without this they all
    # fail silently at the network layer — the browser reports htmx:sendError
    # and nothing appears on screen, which looks like a dead button rather than
    # like a policy.
    "connect-src 'self'; "
    "frame-src 'self'; "
    "form-action 'self'; "
    "base-uri 'none'; "
    # 'self', not 'none': the report is shown in an iframe on this same page,
    # and 'none' forbids being framed by anyone at all — this server included.
    # Against clickjacking the two are equivalent, since any other origin is
    # still refused.
    "frame-ancestors 'self'"
)

# Set by serve(); a random value per run, never written to disk.
TOKEN = ''
BOUND = ('127.0.0.1', 0)

# True when the dashboard manages a library of experiments, False when it was
# pointed at a single folder with --workspace. In the second case there is no
# library page and `/` is the experiment, which is how it behaved before.
LIBRARY_MODE = True


def _split_experiment(route: str):
    """`/experiment/<name>/<action>` -> (name, action), or (None, None)."""
    if not route.startswith('/experiment/'):
        return None, None
    rest = route[len('/experiment/'):].strip('/')
    if not rest:
        return None, None
    name, _, action = rest.partition('/')
    return name, action


def loopback_hosts(host: str, port: int) -> set[str]:
    """The values of `Host` this server answers to.

    Anything else means the browser reached us through a name that is not ours,
    which is exactly the shape of a DNS rebinding attack.
    """
    names = {host, '127.0.0.1', 'localhost', '[::1]', '::1'}
    return {f'{name}:{port}' for name in names} | names


class Handler(BaseHTTPRequestHandler):
    server_version = 'chatlens'

    def log_message(self, *_args):
        """Silence: the terminal is for showing the address, not requests."""

    # --- authorisation ----------------------------------------------------

    def _host_is_ours(self) -> bool:
        host = (self.headers.get('Host') or '').strip().lower()
        return host in loopback_hosts(BOUND[0], BOUND[1])

    def _token_from_cookie(self) -> str:
        raw = self.headers.get('Cookie')
        if not raw:
            return ''
        try:
            jar = http.cookies.SimpleCookie(raw)
        except http.cookies.CookieError:
            return ''
        morsel = jar.get(COOKIE_NAME)
        return morsel.value if morsel else ''

    def _token_ok(self, query) -> bool:
        given = (query.get('t') or [''])[0] or self._token_from_cookie()
        # Constant time: the token is short-lived, but comparing it lazily is
        # the kind of detail that gets copied into somewhere it matters.
        return secrets.compare_digest(given, TOKEN)

    def _origin_ok(self) -> bool:
        """For writes: the request must come from this page, not another site."""
        fetch_site = (self.headers.get('Sec-Fetch-Site') or '').strip().lower()
        if fetch_site and fetch_site not in ('same-origin', 'none'):
            return False
        origin = (self.headers.get('Origin') or '').strip()
        if not origin:
            # Absent on a same-origin form post in older browsers; the token
            # cookie and the Host check still stand.
            return True
        return urlparse(origin).netloc.lower() in loopback_hosts(
            BOUND[0], BOUND[1])

    # --- responses --------------------------------------------------------

    def _send(self, body: bytes, content_type='text/html; charset=utf-8',
              status=200, cookie: str = ''):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        # Pages are generated on every request: never cache them.
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', CSP)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(body)

    def _html(self, markup: str, status=200, cookie: str = ''):
        self._send(markup.encode('utf-8'), status=status, cookie=cookie)

    def _deny(self, explanation: str):
        self._html(f'<h1>403</h1><p>{explanation}</p>', status=403)

    def _file(self, path: Path, base: Path):
        """Serve a file, refusing any path outside its root."""
        try:
            resolved = path.resolve()
            resolved.relative_to(base.resolve())
        except (ValueError, OSError):
            self._html('<h1>404</h1>', status=404)
            return
        if not resolved.is_file():
            self._html('<h1>404</h1>', status=404)
            return
        content_type = CONTENT_TYPES.get(resolved.suffix, 'application/octet-stream')
        self._send(resolved.read_bytes(), content_type=content_type)

    # --- routing ----------------------------------------------------------

    def do_GET(self):  # noqa: N802 - name imposed by BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)

        if not self._host_is_ours():
            self._deny('This dashboard answers on 127.0.0.1 only.')
            return
        if not self._token_ok(query):
            self._deny('Open the address the terminal printed: it carries the '
                       'key for this session.')
            return

        # Arriving with the token in the URL: park it in a cookie so that every
        # later request carries it, and a cross-site one does not.
        cookie = ''
        if (query.get('t') or [''])[0] == TOKEN:
            cookie = (f'{COOKIE_NAME}={TOKEN}; Path=/; HttpOnly; '
                      f'SameSite=Strict')

        name, action = _split_experiment(route)
        if name is not None:
            self._experiment_get(name, action, cookie, query)
            return

        if route == '/':
            if LIBRARY_MODE:
                self._html(views_library.library_page(), cookie=cookie)
            else:
                self._html(views.page(), cookie=cookie)
        elif route == '/log':
            self._html(views.log_body())
        elif route == '/done':
            self._html(views.after_run())
        elif route == '/report':
            self._html(views.report_panel())
        elif route.startswith('/run/'):
            # Folder name only: no paths, no traversal.
            name = route[len('/run/'):].strip('/')
            if '/' in name or name in ('', '.', '..'):
                self._html('<h1>404</h1>', status=404)
            else:
                self._html(views.run_detail(name))
        elif route == '/report.html':
            reports = sorted(config.OUTPUT_DIR.glob('*_report.html'))
            if reports:
                self._file(reports[-1], config.OUTPUT_DIR)
            else:
                self._html('<p>No report produced yet.</p>')
        elif route.startswith('/runs/'):
            self._file(config.OUTPUT_DIR / 'runs' / route[len('/runs/'):],
                       config.OUTPUT_DIR / 'runs')
        elif route.startswith('/static/'):
            self._file(STATIC_DIR / route[len('/static/'):], STATIC_DIR)
        else:
            self._html('<h1>404</h1>', status=404)

    def _experiment_get(self, name: str, action: str, cookie: str,
                        query=None) -> None:
        """Anything under /experiment/<name>/.

        The fragments live here rather than at the root because each of them
        reads the workspace: a log poll that did not say which experiment it
        was about would read whichever one the server had active when it
        arrived.
        """
        query = query or {}
        try:
            with active.experiment(name):
                if not action:
                    self._html(views.page(experiment_slug=name), cookie=cookie)
                elif action == 'settings':
                    self._html(views_library.settings_page(name), cookie=cookie)
                elif action == 'participation':
                    self._html(views_participation.page(name), cookie=cookie)
                elif action == 'words':
                    self._html(views_words.page(name, query), cookie=cookie)
                elif action == 'words/panel':
                    self._html(views_words.panel(name, query))
                elif action.startswith('words/'):
                    self._words_file(name, action, query)
                elif action == 'narratives':
                    self._html(views_narratives.page(name, query),
                               cookie=cookie)
                elif action == 'emotions':
                    self._html(views_emotions.page(name, query),
                               cookie=cookie)
                elif action == 'compare':
                    self._html(views_compare.page(name, query),
                               cookie=cookie)
                elif action == 'files':
                    self._html(views_library.files_panel(
                        name, confirm_delete=(query.get('confirm') or [''])[0]))
                elif action == 'log':
                    self._html(views.log_body())
                elif action == 'done':
                    self._html(views.after_run())
                elif action == 'report':
                    self._html(views.report_panel())
                elif action == 'report.html':
                    reports = sorted(config.OUTPUT_DIR.glob('*_report.html'))
                    if reports:
                        self._file(reports[-1], config.OUTPUT_DIR)
                    else:
                        self._html('<p>No report produced yet.</p>')
                elif action.startswith('run/'):
                    run = action[len('run/'):].strip('/')
                    if '/' in run or run in ('', '.', '..'):
                        self._html('<h1>404</h1>', status=404)
                    else:
                        self._html(views.run_detail(run))
                elif action.startswith('runs/'):
                    self._file(config.OUTPUT_DIR / 'runs' / action[len('runs/'):],
                               config.OUTPUT_DIR / 'runs')
                else:
                    self._html('<h1>404</h1>', status=404)
        except active.Unknown as exc:
            self._html(f'<h1>404</h1><p>{exc}</p>', status=404)

    def do_POST(self):  # noqa: N802
        route = urlparse(self.path).path

        if not self._host_is_ours():
            self._deny('This dashboard answers on 127.0.0.1 only.')
            return
        if not self._token_ok({}) or not self._origin_ok():
            # A run costs money. Refusing is the cheap side of the mistake.
            self._deny('Request refused: it did not come from this page.')
            return

        name, action = _split_experiment(route)
        if name is not None:
            self._experiment_post(name, action)
            return

        if route == '/experiments/new':
            self._create_experiment()
            return

        if route not in ('/run', '/estimate'):
            self._html('<h1>404</h1>', status=404)
            return

        length = int(self.headers.get('Content-Length') or 0)
        form = parse_qs(self.rfile.read(length).decode('utf-8'))

        if route == '/estimate':
            self._html(views.estimate_panel(form))
            return

        if not runner.start(build_command(form)):
            self._html('<div class="logbody empty">A run is already in '
                       'progress: wait for it to finish.</div>')
            return
        self._html(views.log_panel())


    def _form(self) -> dict:
        """A urlencoded body, with a cap: this is not where files arrive."""
        length = int(self.headers.get('Content-Length') or 0)
        if length > 1_000_000:
            self._deny('That form is far too large.')
            return {}
        return parse_qs(self.rfile.read(length).decode('utf-8'))

    def _create_experiment(self) -> None:
        form = self._form()
        name = (form.get('name') or [''])[0].strip()
        adapter = (form.get('adapter') or ['generic_chat'])[0]
        if adapter not in views_library.ADAPTERS:
            adapter = 'generic_chat'
        try:
            library.create(name, adapter=adapter)
        except library.LibraryError as exc:
            # Shown in the form rather than as an error page: the name is
            # something to correct, not a failure to report.
            self._html(views_library.library_panel(error=str(exc)))
            return
        self._html(views_library.library_panel())

    def _upload(self, name: str) -> None:
        """Receive files into an experiment's input/ folder.

        Deliberately outside the activation lock while the bytes are moving: a
        half-gigabyte upload holding it would stall the log poll and every
        other page for as long as it took. The destination is worked out from
        the name alone, which needs no shared state, and the lock is taken only
        at the end to render the result.
        """
        try:
            path = library.path_for(library.slug(name))
        except library.LibraryError as exc:
            self._html(f'<h1>404</h1><p>{exc}</p>', status=404)
            return
        if not path.is_dir():
            self._html('<h1>404</h1>', status=404)
            return

        destination = path / 'input'
        try:
            _fields, files = multipart.parse(
                self.rfile,
                int(self.headers.get('Content-Length') or 0),
                self.headers.get('Content-Type', ''),
                save_dir=destination,
                max_bytes=views_library.MAX_UPLOAD,
            )
        except multipart.UploadError as exc:
            with active.experiment(name):
                self._html(views_library.files_panel(name, error=str(exc)))
            return

        added = []
        for saved in files:
            target = destination / saved['filename']
            Path(saved['path']).replace(target)
            added.append(saved['filename'])

        message = ('Added ' + ', '.join(added)) if added else 'No file chosen.'
        with active.experiment(name):
            self._html(views_library.files_panel(name, message=message))

    def _delete_file(self, name: str) -> None:
        """Remove one file from input/, and only from there."""
        wanted = (self._form().get('file') or [''])[0]
        target = config.INPUT_DIR / Path(wanted).name
        try:
            resolved = target.resolve()
            resolved.relative_to(config.INPUT_DIR.resolve())
        except (ValueError, OSError):
            self._html(views_library.files_panel(
                name, error='That file is not in this experiment.'))
            return
        if not resolved.is_file():
            self._html(views_library.files_panel(
                name, error=f'There is no file called "{wanted}".'))
            return
        resolved.unlink()
        self._html(views_library.files_panel(
            name, message=f'Removed {resolved.name}.'))

    def _assign_role(self, name: str) -> None:
        """Say which uploaded file plays which of the adapter's roles."""
        form = self._form()
        filename = Path((form.get('file') or [''])[0]).name
        role = (form.get('role') or [''])[0].strip()

        patterns = adapters.inputs(config.EXPERIMENT.adapter)
        if role and role not in patterns:
            self._html(views_library.files_panel(
                name, error=f'"{role}" is not a role this adapter has.'))
            return
        if not (config.INPUT_DIR / filename).is_file():
            self._html(views_library.files_panel(
                name, error=f'There is no file called "{filename}".'))
            return

        experiment = config.EXPERIMENT
        declared = dict(experiment.declared.get('input') or {})
        # A role belongs to one file: pointing it at this one releases whatever
        # held it before.
        for existing, value in list(declared.items()):
            if value == filename:
                declared.pop(existing)
        if role:
            declared[role] = filename
        experiment.set('input', declared)
        experiment.save()
        config.use_experiment(experiment)

        message = (f'{filename} is now the {role} file.' if role
                   else f'{filename} is not used.')
        self._html(views_library.files_panel(name, message=message)
                   + f'<div hx-swap-oob="innerHTML:#columns">'
                     f'{views_library.columns_panel(name)}</div>')

    def _save_columns(self, name: str) -> None:
        """Write [columns] from the form, then say whether it is enough."""
        from chatlens.core import inspect

        form = self._form()
        experiment = config.EXPERIMENT
        chosen = {}
        for role in views_library.ROLE_LABELS:
            value = (form.get(f'col_{role}') or [''])[0].strip()
            if value:
                chosen[role] = value

        # Only names the file actually has: a column typed into the request by
        # something other than this form would otherwise be written straight
        # into the configuration.
        path = views_library._messages_file()
        if path is not None:
            try:
                available = set(inspect.header_of(path))
            except inspect.ReadError as exc:
                self._html(views_library.columns_panel(name, error=str(exc)))
                return
            unknown = sorted(set(chosen.values()) - available)
            if unknown:
                self._html(views_library.columns_panel(
                    name,
                    error=f'{", ".join(unknown)}: not a column in '
                          f'{path.name}.'))
                return

        missing = [views_library.ROLE_LABELS[r][0]
                   for r in views_library.REQUIRED_ROLES if r not in chosen]

        experiment.set('columns', chosen)
        experiment.save()
        config.use_experiment(experiment)

        message = ('Saved.' if not missing else
                   f'Saved, but the analysis still needs: '
                   f'{", ".join(missing)}.')
        self._html(views_library.columns_panel(name, message=message)
                   + f'<div hx-swap-oob="innerHTML:#treatments">'
                     f'{views_library.treatments_panel(name)}</div>')

    def _save_treatments(self, name: str) -> None:
        """Write [treatments]: one label per value the column takes."""
        form = self._form()
        experiment = config.EXPERIMENT
        labels = {}
        for field, values in form.items():
            if not field.startswith('tr_'):
                continue
            label = (values or [''])[0].strip()
            if label:
                labels[field[len('tr_'):]] = label
        experiment.set('treatments', labels)
        experiment.save()
        config.use_experiment(experiment)
        self._html(views_library.treatments_panel(
            name, message=f'Saved {len(labels)} names.'))

    def _save_entities(self, name: str) -> None:
        """Write [narratives].entities, then run with them."""
        raw = (self._form().get('entities') or [''])[0]
        chosen = [part.strip().lower() for part in raw.split(',')
                  if part.strip()]
        experiment = config.EXPERIMENT
        experiment.set('narratives',
                       {'entities': chosen,
                        'model': experiment.narrative_model})
        experiment.save()
        config.use_experiment(experiment)
        views_narratives._CACHE.clear()
        self._html(views_narratives.panel(name))

    def _words_file(self, name: str, action: str, query) -> None:
        """A figure or a table, generated for the parameters in the query.

        Nothing is written to disk. The page is a local server and the files it
        offers are small, so they are produced per request rather than left
        lying about in the workspace where a later run would have to explain
        them.
        """
        found, _declared, problem, params = views_words.result(query)
        if problem:
            self._deny(problem)
            return

        direction = (query.get('direction') or ['positive'])[0]
        stem = (f'{params["ngrams"]}-{params["min_df"]}-{params["penalty"]}-'
                f'{"with" if direction == "positive" else "against"}')
        try:
            if action == 'words/terms.csv':
                body = views_words.words.table_csv(found['kept']).encode('utf-8')
                self._download(body, 'text/csv; charset=utf-8',
                               f'terms-{params["ngrams"]}-'
                               f'{params["penalty"]}.csv')
                return
            fmt = 'svg' if action.endswith('.svg') else 'png'
            body = views_words.words.cloud_image(
                found['kept'], direction == 'positive', fmt)
        except ValueError as exc:
            self._deny(str(exc))
            return

        if fmt == 'svg':
            self._download(body, 'image/svg+xml', f'cloud-{stem}.svg')
        else:
            self._send(body, content_type='image/png')

    def _download(self, body: bytes, content_type: str, filename: str) -> None:
        """Offered as a file rather than rendered, with a name worth keeping."""
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Content-Disposition',
                         f'attachment; filename="{filename}"')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def _save_outcome(self, name: str) -> None:
        """Write [outcome], or clear it when no column is chosen."""
        form = self._form()
        field = lambda key: (form.get(key) or [''])[0].strip()
        column = field('column')
        experiment = config.EXPERIMENT

        if not column:
            experiment.set('outcome', {})
            experiment.save()
            config.use_experiment(experiment)
            self._html(views_library.outcome_panel(
                name, message='Cleared. The descriptive pages are unaffected.'))
            return

        chosen = {'column': column, 'kind': field('kind'),
                  'unit': field('unit'), 'label': field('label')}
        # The kind and the unit arrive from selects, so a value outside the
        # list means the form was not the one we served.
        found = outcome.problems(chosen)
        if found:
            self._html(views_library.outcome_panel(name, error=' '.join(found)))
            return

        experiment.set('outcome', chosen)
        experiment.save()
        config.use_experiment(experiment)
        self._html(views_library.outcome_panel(
            name, message=f'Saved: {column}.'))

    def _set_adapter(self, name: str) -> None:
        chosen = (self._form().get('adapter') or [''])[0]
        if chosen not in views_library.ADAPTERS:
            self._html(views_library.files_panel(
                name, error='That is not one of the adapters.'))
            return
        experiment = config.EXPERIMENT
        experiment.set('experiment', {**experiment.declared['experiment'],
                                      'adapter': chosen})
        experiment.save()
        config.use_experiment(experiment)
        self._html(views_library.files_panel(
            name, message=f'Now reading the files with {chosen}.'))

    def _experiment_post(self, name: str, action: str) -> None:
        try:
            if action == 'archive':
                library.archive(library.slug(name))
                self._html(views_library.library_panel())
                return

            if action == 'upload':
                self._upload(name)
                return

            with active.experiment(name):
                if action == 'files/delete':
                    self._delete_file(name)
                elif action == 'input':
                    self._assign_role(name)
                elif action == 'columns':
                    self._save_columns(name)
                elif action == 'treatments':
                    self._save_treatments(name)
                elif action == 'outcome':
                    self._save_outcome(name)
                elif action == 'narratives/entities':
                    self._save_entities(name)
                elif action == 'adapter':
                    self._set_adapter(name)
                elif action == 'run':
                    if not runner.start(build_command(self._form())):
                        self._html('<div class="logbody empty">A run is '
                                   'already in progress: wait for it to '
                                   'finish.</div>')
                        return
                    self._html(views.log_panel())
                elif action == 'estimate':
                    self._html(views.estimate_panel(self._form()))
                else:
                    self._html('<h1>404</h1>', status=404)
        except (active.Unknown, library.LibraryError) as exc:
            self._html(f'<h1>404</h1><p>{exc}</p>', status=404)


def serve(host='127.0.0.1', port=8765, open_browser=True, library_mode=True):
    global TOKEN, BOUND, LIBRARY_MODE

    if host not in ('127.0.0.1', 'localhost', '::1'):
        raise SystemExit(
            f'\nRefusing to listen on {host}.\n\n'
            f'  The dashboard starts processes on this machine and has no user\n'
            f'  accounts: anyone who can reach it can spend your API credit.\n'
            f'  To use it from another machine, forward the port over SSH:\n'
            f'      ssh -N -L {port}:127.0.0.1:{port} <this-machine>\n'
        )

    config.ensure_dirs()
    config.load_env()

    TOKEN = secrets.token_urlsafe(24)
    BOUND = (host, port)
    LIBRARY_MODE = library_mode
    if library_mode:
        library.ensure_root()

    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f'http://{host}:{port}/?t={TOKEN}'
    # flush: the address carries the session key and is the only place it
    # appears. Redirected to a file or a pipe, an unflushed line would leave
    # the dashboard unreachable until the process ended.
    if library_mode:
        print(f'Experiments: {library.ROOT}', flush=True)
    else:
        print(f'Workspace: {config.WORKSPACE}', flush=True)
    print(f'Dashboard at {url}', flush=True)
    print("The address carries this session's key: it changes every time.",
          flush=True)
    print('Ctrl-C to close.', flush=True)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nClosed.')
    finally:
        httpd.server_close()


if __name__ == '__main__':
    serve()
