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

from chatlens.core import config
from chatlens.web import views
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

        if route == '/':
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

    def do_POST(self):  # noqa: N802
        route = urlparse(self.path).path

        if not self._host_is_ours():
            self._deny('This dashboard answers on 127.0.0.1 only.')
            return
        if not self._token_ok({}) or not self._origin_ok():
            # A run costs money. Refusing is the cheap side of the mistake.
            self._deny('Request refused: it did not come from this page.')
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


def serve(host='127.0.0.1', port=8765, open_browser=True):
    global TOKEN, BOUND

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

    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f'http://{host}:{port}/?t={TOKEN}'
    # flush: the address carries the session key and is the only place it
    # appears. Redirected to a file or a pipe, an unflushed line would leave
    # the dashboard unreachable until the process ended.
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
