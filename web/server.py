"""
Local dashboard for launching runs and seeing their results.

    python run.py dashboard        (or: make dashboard)

It listens on 127.0.0.1 only: this is a desktop tool, not a service. It executes
processes, so it must not be reachable from the network, and command arguments
are taken from a closed list (see runner.py), never composed from text arriving
from the browser.

Standard library only: htmx ships with the project, so the dashboard works
offline too.
"""

from __future__ import annotations

import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src import config  # noqa: E402
from web import views  # noqa: E402
from web.runner import build_command, runner  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / 'static'

CONTENT_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
}


class Handler(BaseHTTPRequestHandler):
    server_version = 'AnalisiTesto'

    def log_message(self, *_args):
        """Silence: the terminal is for showing the address, not requests."""

    # --- responses --------------------------------------------------------

    def _send(self, body: bytes, content_type='text/html; charset=utf-8',
              status=200):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        # Pages are generated on every request: never cache them.
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _html(self, markup: str, status=200):
        self._send(markup.encode('utf-8'), status=status)

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
        route = urlparse(self.path).path

        if route == '/':
            self._html(views.page())
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
    config.ensure_dirs()
    config.load_env()

    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f'http://{host}:{port}/'
    print(f'Dashboard at {url}')
    print('Ctrl-C to close.')
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
