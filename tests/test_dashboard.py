"""Test della dashboard.

Non avviano il server: verificano le due parti dove si annidano i problemi
veri — la costruzione del comando, che esegue processi, e la lettura del log,
che deve rendere leggibili le barre di avanzamento.

    python tests/test_dashboard.py
"""

import sys
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from web.runner import Runner, build_command  # noqa: E402


class CommandBuildingTests(unittest.TestCase):
    """Il comando si costruisce da valori noti: mai da testo del browser."""

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
        # Il valore valido nello stesso campo sopravvive.
        self.assertIn('group', argv)

    def test_options_are_separate_arguments(self):
        """Niente shell: ogni opzione e' un elemento della lista."""
        argv = build_command({'command': ['all'], 'llm': ['1'],
                              'llm_model': ['gpt-4o']})
        self.assertIn('--llm-models', argv)
        self.assertEqual(argv[argv.index('--llm-models') + 1], 'gpt-4o')

    def test_topics_carry_the_repository_path(self):
        argv = build_command({'command': ['all'], 'topics': ['1']})
        self.assertIn('--topicgpt-repo', argv)
        self.assertIn('--topicgpt-model', argv)


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
        """Cento riscritture non devono lasciare cento righe."""
        state = self._run(
            "import sys\n"
            "for i in range(100): sys.stdout.write(f'{i}%|## | {i}/100\\r')\n"
            "sys.stdout.write('\\nfinito\\n')"
        )
        self.assertEqual(state['lines'], ['99%|## | 99/100', 'finito'])

    def test_plain_lines_are_all_kept(self):
        state = self._run(
            "print('uno'); print('due'); print('tre')"
        )
        self.assertEqual(state['lines'], ['uno', 'due', 'tre'])

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
        # Si tiene la coda, che e' la parte che interessa.
        self.assertEqual(state['lines'][-1], '899')


if __name__ == '__main__':
    unittest.main(verbosity=2)
