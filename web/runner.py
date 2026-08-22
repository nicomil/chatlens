"""
Esecuzione dei run in background, con log leggibile in diretta.

Un run alla volta: due esecuzioni concorrenti scriverebbero negli stessi file
di output e si sovrascriverebbero a vicenda.

Il comando viene costruito da un elenco chiuso di opzioni, mai da testo
digitato: la dashboard esegue processi, e comporre una riga di comando con
valori arbitrari sarebbe un'iniezione di comandi servita su un piatto.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Valori ammessi. Tutto ciò che arriva dal browser viene confrontato con questi
# elenchi: quello che non c'è viene ignorato, non passato al comando.
ALLOWED = {
    'command': {'all', 'merge', 'analyze'},
    'llm_provider': {'', 'openai', 'anthropic', 'ollama'},
    'llm_model': {
        '', 'gpt-4o', 'gpt-4.1', 'gpt-5.6-terra', 'gpt-5.6-luna',
        'gpt-5.6-sol', 'claude-opus-5', 'llama3',
    },
    'llm_replicates': {'1', '2', '3'},
    'llm_level': {'group', 'dyad_directed', 'dyad', 'sender_group'},
    'topicgpt_model': {'gpt-4o', 'gpt-4.1'},
    'topicgpt_unit': {'group', 'dyad_directed', 'dyad', 'sender_group'},
    'topicgpt_assign_unit': {'dyad_directed', 'dyad', 'sender_group', 'group'},
}


def _pick(form, field, default=''):
    """Valore dal modulo, solo se compreso fra quelli ammessi."""
    value = (form.get(field) or [''])[0].strip()
    return value if value in ALLOWED[field] else default


def build_command(form) -> list[str]:
    """Traduce il modulo in argomenti, uno per uno e solo da valori noti."""
    argv = [sys.executable, 'run.py', _pick(form, 'command', 'all')]

    if form.get('llm'):
        argv.append('--llm')
        provider = _pick(form, 'llm_provider')
        if provider:
            argv += ['--llm-provider', provider]
        model = _pick(form, 'llm_model')
        if model:
            argv += ['--llm-models', model]
        argv += ['--llm-replicates', _pick(form, 'llm_replicates', '1')]
        levels = [v for v in form.get('llm_level', [])
                  if v in ALLOWED['llm_level']]
        if levels:
            argv += ['--llm-levels'] + levels

    if form.get('topics'):
        argv += [
            '--topics',
            '--topicgpt-repo', str(Path.home() / 'src' / 'topicGPT'),
            '--topicgpt-model', _pick(form, 'topicgpt_model', 'gpt-4o'),
            '--topicgpt-unit', _pick(form, 'topicgpt_unit', 'group'),
            '--topicgpt-assign-unit',
            _pick(form, 'topicgpt_assign_unit', 'dyad_directed'),
        ]
    return argv


class Runner:
    """Un run alla volta, con il log accumulato riga per riga."""

    def __init__(self):
        self._lock = threading.Lock()
        self._process = None
        self._lines = []
        self._provisional = False
        self._command = ''
        self._started = None
        self._finished = None
        self._returncode = None

    # --- stato ------------------------------------------------------------

    @property
    def running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def snapshot(self) -> dict:
        with self._lock:
            return dict(
                running=self._process is not None and self._process.poll() is None,
                lines=list(self._lines),
                command=self._command,
                started=self._started,
                finished=self._finished,
                returncode=self._returncode,
            )

    # --- esecuzione -------------------------------------------------------

    def start(self, argv) -> bool:
        """Avvia un run. False se ce n'è già uno in corso."""
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return False
            self._lines = []
            self._provisional = False
            self._command = ' '.join(
                a if a != sys.executable else 'python' for a in argv
            )
            self._started = datetime.now().strftime('%H:%M:%S')
            self._finished = None
            self._returncode = None
            self._process = subprocess.Popen(
                argv,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            # Senza questo, Python traduce \r in \n e il ritorno a capo delle
            # barre di avanzamento non arriva mai qui: ogni riscrittura
            # diventerebbe una riga nuova, che e' esattamente cio' che si vuole
            # evitare.
            self._process.stdout.reconfigure(newline='')
        threading.Thread(target=self._pump, daemon=True).start()
        return True

    def _pump(self):
        """Legge l'output riga per riga, collassando le barre di avanzamento."""
        process = self._process
        buffer = ''
        while True:
            chunk = process.stdout.read(1)
            if not chunk:
                break
            if chunk == '\n':
                self._append(buffer, provisional=False)
                buffer = ''
            elif chunk == '\r':
                self._append(buffer, provisional=True)
                buffer = ''
            else:
                buffer += chunk
        if buffer.strip():
            self._append(buffer, provisional=False)

        process.wait()
        with self._lock:
            self._returncode = process.returncode
            self._finished = datetime.now().strftime('%H:%M:%S')

    def _append(self, line: str, provisional: bool = False):
        """Aggiunge una riga, o rimpiazza quella in corso di riscrittura.

        Un ritorno a capo senza avanzamento (\r) significa "riscrivi la riga
        corrente": e' cosi' che tqdm anima la barra. Va quindi sostituita
        l'ultima riga, non aggiunta una nuova, altrimenti una barra da cento
        passi lascia cento righe nel log.
        """
        line = line.rstrip()
        with self._lock:
            if not line:
                # Riga vuota. Se arriva da un \n chiude comunque quella in
                # corso: senza, l'ultimo stato della barra verrebbe rimpiazzato
                # dalla prima riga successiva invece di restare visibile.
                if not provisional:
                    self._provisional = False
                return
            if self._provisional and self._lines:
                self._lines[-1] = line
            else:
                self._lines.append(line)
            # Finche' la riga e' provvisoria, la prossima la sostituisce; una
            # riga terminata da \n la fissa e le successive si accodano.
            self._provisional = provisional
            # Il log di un run lungo non deve crescere senza limite.
            if len(self._lines) > 500:
                del self._lines[:-500]

    def stop(self) -> bool:
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                return False
            self._process.terminate()
        return True


runner = Runner()
