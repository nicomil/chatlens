"""
Dashboard locale per lanciare i run e vederne i risultati.

    python run.py dashboard        (oppure: make dashboard)

Sta in ascolto solo su 127.0.0.1: e' uno strumento da scrivania, non un
servizio. Esegue processi, quindi non deve essere raggiungibile dalla rete, e
gli argomenti dei comandi vengono presi da un elenco chiuso (vedi runner.py) e
mai composti con testo arrivato dal browser.

Libreria standard soltanto: htmx e' incluso nel progetto, cosi' la dashboard
funziona anche senza connessione.
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
        """Silenzio: il terminale serve a mostrare l'indirizzo, non le richieste."""

    # --- risposte ---------------------------------------------------------

    def _send(self, body: bytes, content_type='text/html; charset=utf-8',
              status=200):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        # Le pagine sono generate a ogni richiesta: non vanno mai messe in cache.
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _html(self, markup: str, status=200):
        self._send(markup.encode('utf-8'), status=status)

    def _file(self, path: Path, base: Path):
        """Serve un file, rifiutando qualunque percorso fuori dalla sua radice."""
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

    # --- instradamento ----------------------------------------------------

    def do_GET(self):  # noqa: N802 - nome imposto da BaseHTTPRequestHandler
        route = urlparse(self.path).path

        if route == '/':
            self._html(views.page())
        elif route == '/log':
            self._html(views.log_body())
        elif route == '/done':
            self._html(views.after_run())
        elif route == '/report.html':
            reports = sorted(config.OUTPUT_DIR.glob('*_report.html'))
            if reports:
                self._file(reports[-1], config.OUTPUT_DIR)
            else:
                self._html('<p>Nessun rapporto ancora prodotto.</p>')
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
            self._html('<div class="logbody empty">Un run e\' gia\' in corso: '
                       'attendi che finisca.</div>')
            return
        self._html(views.log_panel())


def serve(host='127.0.0.1', port=8765, open_browser=True):
    config.ensure_dirs()
    config.load_env()

    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f'http://{host}:{port}/'
    print(f'Dashboard su {url}')
    print('Ctrl-C per chiudere.')
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nChiusa.')
    finally:
        httpd.server_close()


if __name__ == '__main__':
    serve()
