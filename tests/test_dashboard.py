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

from web import views  # noqa: E402
from web.runner import Runner, build_command  # noqa: E402


class FormWiringTests(unittest.TestCase):
    """Il run deve partire solo dall'invio del modulo."""

    def test_form_tag_has_exactly_one_destination(self):
        """Due hx-post sullo stesso elemento: ogni cambiamento lanciava un run.

        E' successo davvero: la richiesta della stima era stata messa sul form,
        che gia' aveva quella del run, e spuntare una casella faceva partire
        l'esecuzione.
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
        # Si aggiorna ascoltando il modulo, senza esserne parte attiva.
        self.assertIn('hx-trigger="change from:#launch"', opening)
        self.assertIn('hx-include="#launch"', opening)

    def test_no_element_triggers_run_on_change(self):
        """Nessun elemento deve chiamare /run se non per invio esplicito."""
        import re

        form = views.form_panel()
        for tag in re.findall(r'<[a-z]+\b[^>]*hx-post="/run"[^>]*>', form):
            self.assertNotIn('hx-trigger', tag, msg=tag)

    def test_presets_are_choices_not_submitters(self):
        form = views.form_panel()
        self.assertIn('type="radio" name="preset"', form)
        self.assertNotIn('type="submit" class="preset"', form)


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


class ArchiveViewTests(unittest.TestCase):
    """L'archivio e' un indice: da una riga si arriva a tutto quel run."""

    def _a_run(self):
        from src import archive, config

        runs = archive.list_runs(config.OUTPUT_DIR)
        if not runs:
            self.skipTest('nessun run archiviato in questo ambiente')
        return runs[0]

    def test_every_row_opens_its_own_run(self):
        import re

        from src import archive, config

        panel = views.runs_panel()
        if not archive.list_runs(config.OUTPUT_DIR):
            self.skipTest('nessun run archiviato in questo ambiente')
        targets = re.findall(r'hx-get="/run/([^"]+)"', panel)
        self.assertTrue(targets)
        # Ogni riga porta al proprio run, non tutte allo stesso.
        self.assertEqual(len(targets), len(set(targets)))

    def test_detail_shows_parameters_and_files(self):
        run = self._a_run()
        detail = views.run_detail(run['path'].name)
        self.assertIn('Messaggi analizzati', detail)
        # I file prodotti sono raggiungibili da lì.
        self.assertIn(f'/runs/{run["path"].name}/', detail)
        # E si può tornare all'ultimo risultato.
        self.assertIn('hx-get="/report"', detail)

    def test_identical_consecutive_runs_collapse_into_one_row(self):
        """Rilanciare per prova non deve moltiplicare le righe."""
        base = dict(stages=['misure', 'rubrica'], n_messages=283,
                    rubrica={'provider': 'openai', 'models': 'gpt-4o',
                             'replicates': 1, 'levels': ['group']},
                    topic=None, failed_stage=None)
        runs = [dict(base, timestamp=f'2026-01-01T12:00:0{i}',
                     path=Path(f'/tmp/r{i}')) for i in range(4)]
        gruppi = views._group_runs(runs)
        self.assertEqual(len(gruppi), 1)
        self.assertEqual(len(gruppi[0]), 4)

    def test_different_parameters_stay_separate(self):
        base = dict(stages=['misure', 'rubrica'], n_messages=283,
                    topic=None, failed_stage=None)
        runs = [
            dict(base, timestamp='2026-01-01T12:00:01', path=Path('/tmp/a'),
                 rubrica={'replicates': 1}),
            dict(base, timestamp='2026-01-01T12:00:02', path=Path('/tmp/b'),
                 rubrica={'replicates': 2}),
        ]
        self.assertEqual(len(views._group_runs(runs)), 2)

    def test_same_configuration_hours_apart_is_a_separate_session(self):
        """Solo le consecutive si accorpano: in mezzo c'e' stato altro."""
        base = dict(stages=['misure'], n_messages=283, rubrica=None,
                    topic=None, failed_stage=None)
        runs = [
            dict(base, timestamp='2026-01-01T18:00:00', path=Path('/tmp/c')),
            dict(base, stages=['misure', 'topic'],
                 timestamp='2026-01-01T15:00:00', path=Path('/tmp/b')),
            dict(base, timestamp='2026-01-01T12:00:00', path=Path('/tmp/a')),
        ]
        self.assertEqual(len(views._group_runs(runs)), 3)

    def test_a_failed_run_is_not_merged_with_a_successful_one(self):
        base = dict(stages=['misure', 'topic'], n_messages=283, rubrica=None,
                    topic={'model': 'gpt-4o'})
        runs = [
            dict(base, timestamp='2026-01-01T12:00:02', path=Path('/tmp/b'),
                 failed_stage=None),
            dict(base, timestamp='2026-01-01T12:00:01', path=Path('/tmp/a'),
                 failed_stage='TopicGPT'),
        ]
        self.assertEqual(len(views._group_runs(runs)), 2)

    def test_unknown_run_is_handled(self):
        self.assertIn('non trovato', views.run_detail('non-esiste'))

    def test_failure_is_stated_not_implied(self):
        """Un run incompleto deve dirlo a parole, non solo con un colore."""
        from src import archive, config

        failed = [r for r in archive.list_runs(config.OUTPUT_DIR)
                  if r.get('failed_stage')]
        if not failed:
            self.skipTest('nessun run incompleto in questo ambiente')
        detail = views.run_detail(failed[0]['path'].name)
        self.assertIn('non completato', detail)


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
