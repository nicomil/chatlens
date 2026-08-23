"""
Running jobs in the background, with a readable live log.

One run at a time: two concurrent runs would write to the same output files and
overwrite each other.

The command is built from a closed list of options, never from typed text: the
dashboard executes processes, and composing a command line from arbitrary
values would be command injection served on a plate.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Allowed values. Everything arriving from the browser is checked against these
# lists: anything absent is ignored, not passed to the command.
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
    """Value from the form, only if among those allowed."""
    value = (form.get(field) or [''])[0].strip()
    return value if value in ALLOWED[field] else default


def build_command(form) -> list[str]:
    """Turn the form into arguments, one by one and only from known values."""
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
    """One run at a time, with the log accumulated line by line."""

    def __init__(self):
        self._lock = threading.Lock()
        self._process = None
        self._lines = []
        self._provisional = False
        self._command = ''
        self._started = None
        self._finished = None
        self._returncode = None

    # --- state ------------------------------------------------------------

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

    # --- execution --------------------------------------------------------

    def start(self, argv) -> bool:
        """Start a run. False if one is already in progress."""
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
            # Without this, Python translates \r into \n and the progress
            # bars' carriage return never reaches us: every rewrite would become
            # a new line, which is exactly what we are trying to avoid.
            self._process.stdout.reconfigure(newline='')
        threading.Thread(target=self._pump, daemon=True).start()
        return True

    def _pump(self):
        """Read the output line by line, collapsing the progress bars."""
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
        """Append a line, or replace the one being rewritten.

        A carriage return without a line feed (\r) means "rewrite the current
        line": that is how tqdm animates the bar. The last line must therefore
        be replaced, not a new one added, otherwise a hundred-step bar leaves a
        hundred lines in the log.
        """
        line = line.rstrip()
        with self._lock:
            if not line:
                # Empty line. Coming from a \n it still closes the current one:
                # without this, the bar's final state would be replaced by the
                # next line rather than staying visible.
                if not provisional:
                    self._provisional = False
                return
            if self._provisional and self._lines:
                self._lines[-1] = line
            else:
                self._lines.append(line)
            # While the line is provisional the next one replaces it; a line
            # ended by \n fixes it and later ones are appended.
            self._provisional = provisional
            # A long run's log must not grow without limit.
            if len(self._lines) > 500:
                del self._lines[:-500]

    def stop(self) -> bool:
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                return False
            self._process.terminate()
        return True


runner = Runner()
