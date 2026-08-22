"""
Archivio delle esecuzioni.

`output/` contiene sempre l'ultima esecuzione, a percorsi fissi: e' quello che
si apre e che si porta in Stata. Ogni esecuzione viene pero' anche copiata in
`output/runs/<data_ora>/`, cosi' rilanciare non cancella quello che c'era prima.

Serve perche' due esecuzioni non producono gli stessi file. Una senza `--llm`
riscrive i dataset senza le colonne della rubrica: senza archivio, il lavoro
gia' pagato sparirebbe dai file finali pur restando in cache. Con l'archivio
resta consultabile la versione precedente, insieme ai parametri con cui era
stata prodotta.

Viene archiviato solo cio' che serve a rileggere un'esecuzione — i due dataset,
il rapporto, l'elenco dei topic e i parametri — non le misure intermedie, che
si rigenerano.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

RUN_INFO = 'run.json'


def stages_of(args) -> list[str]:
    """Stadi effettivamente eseguiti, per come sono stati chiesti."""
    stages = ['misure']
    if getattr(args, 'llm', False) and not getattr(args, 'llm_dry_run', False):
        stages.append('rubrica')
    if getattr(args, 'topics', False) and not getattr(args, 'topicgpt_dry_run', False):
        stages.append('topic')
    return stages


def describe(args, summary: dict) -> dict:
    """Parametri e numeri dell'esecuzione, per poterla riconoscere dopo."""
    info = dict(
        timestamp=datetime.now().isoformat(timespec='seconds'),
        stem=getattr(args, 'stem', ''),
        stages=stages_of(args),
        n_messages=summary.get('n_messages'),
        levels=summary.get('levels'),
        failed_stage=(summary.get('failed_stage') or [None])[0],
    )
    if 'rubrica' in info['stages']:
        info['rubrica'] = dict(
            provider=getattr(args, 'llm_provider', None) or 'automatico',
            models=getattr(args, 'llm_models', None) or 'predefinito',
            replicates=getattr(args, 'llm_replicates', 1),
            levels=list(getattr(args, 'llm_levels', []) or []),
        )
    if 'topic' in info['stages']:
        info['topic'] = dict(
            api=getattr(args, 'topicgpt_api', None),
            model=getattr(args, 'topicgpt_model', None),
            unit=getattr(args, 'topicgpt_unit', None),
            assign_unit=getattr(args, 'topicgpt_assign_unit', None),
            seed=str(getattr(args, 'topicgpt_seed', '') or ''),
        )
    return info


def save(outdir: Path, stem: str, args, summary: dict) -> Path:
    """Copia l'esecuzione in una cartella datata. Restituisce il percorso."""
    stamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    run_dir = outdir / 'runs' / stamp
    # Due esecuzioni possono concludersi nello stesso secondo: senza suffisso
    # la seconda cancellerebbe la prima, che e' esattamente cio' che l'archivio
    # deve impedire.
    counter = 2
    while run_dir.exists():
        run_dir = outdir / 'runs' / f'{stamp}_{counter}'
        counter += 1
    (run_dir / 'datasets').mkdir(parents=True, exist_ok=True)

    for path in sorted((outdir / 'datasets').glob(f'{stem}_*.csv')):
        shutil.copy2(path, run_dir / 'datasets' / path.name)

    for suffix in ('md', 'html'):
        source = outdir / f'{stem}_report.{suffix}'
        if source.is_file():
            shutil.copy2(source, run_dir / f'report.{suffix}')

    # L'elenco dei topic definisce l'ontologia usata: senza, un'esecuzione con
    # topic non e' piu' interpretabile a distanza di tempo.
    topics = outdir / 'topicgpt' / 'generation_1.md'
    if topics.is_file() and 'topic' in stages_of(args):
        shutil.copy2(topics, run_dir / 'topics.md')

    info = describe(args, summary)
    (run_dir / RUN_INFO).write_text(
        json.dumps(info, indent=2, ensure_ascii=False), encoding='utf-8'
    )
    return run_dir


def list_runs(outdir: Path) -> list[dict]:
    """Esecuzioni archiviate, dalla piu' recente."""
    runs_dir = outdir / 'runs'
    if not runs_dir.is_dir():
        return []

    runs = []
    for path in runs_dir.iterdir():
        if not path.is_dir():
            continue
        try:
            info = json.loads((path / RUN_INFO).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            info = {}
        info['path'] = path
        runs.append(info)

    # Si ordina sull'istante registrato, non sul nome della cartella: i suffissi
    # delle collisioni non seguono l'ordine alfabetico oltre il nono.
    runs.sort(key=lambda r: (r.get('timestamp') or '', r['path'].name),
              reverse=True)
    return runs


def prune(outdir: Path, keep: int) -> list[Path]:
    """Rimuove le esecuzioni piu' vecchie, conservando le `keep` piu' recenti.

    Restituisce i percorsi rimossi. L'archivio serve a non perdere il lavoro
    fatto, non a conservare per sempre ogni prova: dopo una sessione di
    tentativi resta una lunga coda di esecuzioni identiche che non dice nulla.
    """
    if keep < 0:
        raise ValueError('keep non puo essere negativo')

    runs = list_runs(outdir)
    da_rimuovere = [run['path'] for run in runs[keep:]]
    for path in da_rimuovere:
        # Si cancella solo dentro output/runs: un percorso che ne esce
        # significa che qualcosa e' andato storto, e ci si ferma.
        path.resolve().relative_to((outdir / 'runs').resolve())
        shutil.rmtree(path)
    return da_rimuovere


def render_list(runs) -> str:
    if not runs:
        return 'Nessuna esecuzione archiviata.'

    lines = []
    for run in runs:
        stamp = run['path'].name
        stages = ', '.join(run.get('stages') or ['?'])
        line = f'  {stamp}   {stages}'
        if run.get('failed_stage'):
            line += f"   [incompleta: {run['failed_stage']}]"
        lines.append(line)
        details = []
        if run.get('rubrica'):
            r = run['rubrica']
            repliche = ('1 replica' if r['replicates'] == 1
                        else f"{r['replicates']} repliche")
            details.append(
                f"rubrica: {r['provider']}, {repliche}, "
                f"livelli {'/'.join(r['levels'])}"
            )
        if run.get('topic'):
            t = run['topic']
            details.append(
                f"topic: {t['model']} su {t['unit']} -> {t['assign_unit']}"
            )
        for detail in details:
            lines.append(f'      {detail}')
    return '\n'.join(lines)
