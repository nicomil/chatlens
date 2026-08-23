"""
Archive of runs.

`output/` always holds the latest run, at fixed paths: that is what you open and
what you take into Stata. Every run is also copied to
`output/runs/<date_time>/`, so that re-running does not erase what came before.

This matters because two runs do not produce the same files. One without `--llm`
rewrites the datasets without the rubric columns: with no archive, work already
paid for would vanish from the final files even though it survives in the cache.
With the archive, the previous version stays available together with the
parameters that produced it.

Only what is needed to re-read a run is archived — the two datasets, the report,
the topic list and the parameters — not the intermediate measures, which can be
regenerated.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

RUN_INFO = 'run.json'


def stages_of(args) -> list[str]:
    """The stages actually run, as they were requested."""
    stages = ['measures']
    if getattr(args, 'llm', False) and not getattr(args, 'llm_dry_run', False):
        stages.append('rubric')
    if getattr(args, 'topics', False) and not getattr(args, 'topicgpt_dry_run', False):
        stages.append('topics')
    return stages


def describe(args, summary: dict) -> dict:
    """Parameters and figures of the run, so it can be recognised later."""
    info = dict(
        timestamp=datetime.now().isoformat(timespec='seconds'),
        stem=getattr(args, 'stem', ''),
        stages=stages_of(args),
        n_messages=summary.get('n_messages'),
        levels=summary.get('levels'),
        failed_stage=(summary.get('failed_stage') or [None])[0],
    )
    if 'rubric' in info['stages']:
        info['rubric'] = dict(
            provider=getattr(args, 'llm_provider', None) or 'automatic',
            models=getattr(args, 'llm_models', None) or 'default',
            replicates=getattr(args, 'llm_replicates', 1),
            levels=list(getattr(args, 'llm_levels', []) or []),
        )
    if 'topics' in info['stages']:
        info['topics'] = dict(
            api=getattr(args, 'topicgpt_api', None),
            model=getattr(args, 'topicgpt_model', None),
            unit=getattr(args, 'topicgpt_unit', None),
            assign_unit=getattr(args, 'topicgpt_assign_unit', None),
            seed=str(getattr(args, 'topicgpt_seed', '') or ''),
        )
    return info


def save(outdir: Path, stem: str, args, summary: dict) -> Path:
    """Copy the run into a dated folder. Returns the path."""
    stamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    run_dir = outdir / 'runs' / stamp
    # Two runs can finish within the same second: without a suffix the second
    # would erase the first, which is exactly what the archive exists to
    # prevent.
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

    # The topic list defines the ontology that was used: without it, a run with
    # topics is no longer interpretable months later.
    topics = outdir / 'topicgpt' / 'generation_1.md'
    if topics.is_file() and 'topics' in stages_of(args):
        shutil.copy2(topics, run_dir / 'topics.md')

    info = describe(args, summary)
    (run_dir / RUN_INFO).write_text(
        json.dumps(info, indent=2, ensure_ascii=False), encoding='utf-8'
    )
    return run_dir


# Runs archived before the interface was translated carry Italian keys. Reading
# both spellings costs two lines and keeps an old archive readable, which is the
# whole point of having one.
LEGACY_KEYS = {'rubric': 'rubrica', 'topics': 'topic'}
LEGACY_STAGES = {'misure': 'measures', 'rubrica': 'rubric', 'topic': 'topics'}


def _normalise(info: dict) -> dict:
    for new, old in LEGACY_KEYS.items():
        if new not in info and old in info:
            info[new] = info[old]
        # Old runs wrote 'automatico' where the current ones write 'automatic'
        # (provider) or 'default' (model).
        block = info.get(new)
        if isinstance(block, dict):
            for field, current in (('provider', 'automatic'), ('models', 'default')):
                if block.get(field) == 'automatico':
                    block[field] = current
    if info.get('stages'):
        info['stages'] = [LEGACY_STAGES.get(s, s) for s in info['stages']]
    return info


def list_runs(outdir: Path) -> list[dict]:
    """Archived runs, most recent first."""
    runs_dir = outdir / 'runs'
    if not runs_dir.is_dir():
        return []

    runs = []
    for path in runs_dir.iterdir():
        if not path.is_dir():
            continue
        try:
            info = _normalise(json.loads((path / RUN_INFO).read_text(encoding='utf-8')))
        except (OSError, ValueError):
            info = {}
        info['path'] = path
        runs.append(info)

    # Sorted on the recorded instant rather than the folder name: collision
    # suffixes do not follow alphabetical order past the ninth.
    runs.sort(key=lambda r: (r.get('timestamp') or '', r['path'].name),
              reverse=True)
    return runs


def prune(outdir: Path, keep: int) -> list[Path]:
    """Remove the oldest runs, keeping the `keep` most recent.

    Returns the paths removed. The archive exists so that work already done is
    not lost, not to keep every trial for ever: after a session of attempts
    there is a long tail of identical runs that says nothing.
    """
    if keep < 0:
        raise ValueError('keep cannot be negative')

    runs = list_runs(outdir)
    to_remove = [run['path'] for run in runs[keep:]]
    for path in to_remove:
        # Delete only inside output/runs: a path that escapes it means
        # something has gone wrong, and we stop.
        path.resolve().relative_to((outdir / 'runs').resolve())
        shutil.rmtree(path)
    return to_remove


def render_list(runs) -> str:
    if not runs:
        return 'No archived runs.'

    lines = []
    for run in runs:
        stamp = run['path'].name
        stages = ', '.join(run.get('stages') or ['?'])
        line = f'  {stamp}   {stages}'
        if run.get('failed_stage'):
            line += f"   [incomplete: {run['failed_stage']}]"
        lines.append(line)
        details = []
        if run.get('rubric'):
            r = run['rubric']
            replicates = ('1 replicate' if r.get('replicates') == 1
                          else f"{r.get('replicates')} replicates")
            details.append(
                f"rubric: {r.get('provider')}, {replicates}, "
                f"levels {'/'.join(r.get('levels') or [])}"
            )
        if run.get('topics'):
            t = run['topics']
            details.append(
                f"topics: {t.get('model')} on {t.get('unit')} -> "
                f"{t.get('assign_unit')}"
            )
        for detail in details:
            lines.append(f'      {detail}')
    return '\n'.join(lines)
