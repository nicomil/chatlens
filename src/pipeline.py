"""
Runs the text-analysis pipeline over the experiment's messages and enriches the
datasets.

Three independent stages, each switchable on its own:

1. **Text measures** (always on, no credential required) — volume, sentiment
   and the LIWC-style indices (analytic, clout, authenticity, tone), computed
   at directed-dyad, dyad, participant and group level.
2. **Validation rubric** (``--llm``) — a second measurement of the same
   constructs, scored by a language model, for convergent validation. Needs a
   credential from any one supported provider.
3. **TopicGPT** (``--topics``) — the official code of Pham et al. (2024). Needs
   the cloned repository and the credential of the chosen backend.

The final output is the experiment's two datasets, enriched and ready for
Stata, plus the intermediate feature files for checking.

Examples (from the project entry point)
---------------------------------------
    python run.py analyze                          automatic measures
    python run.py analyze --llm --llm-replicates 2 + validation rubric
    python run.py analyze --topics --topicgpt-repo ~/src/topicGPT
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from . import aggregate as agg  # noqa: E402
from . import archive, config, llm_rubric, report, topicgpt  # noqa: E402


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def build_transcripts(messages, level: str) -> dict:
    """Readable transcripts per level, used by the rubric."""
    from collections import defaultdict

    keys = agg.LEVEL_KEYS[level]
    buckets = defaultdict(list)
    for message in messages:
        buckets[tuple(str(message.get(k, '')) for k in keys)].append(message)

    transcripts = {}
    for key, bucket in buckets.items():
        bucket.sort(key=lambda m: float(m.get('timestamp') or 0))
        transcripts[key] = '\n'.join(
            f"{m.get('sender_color', '?')} -> {m.get('receiver_color', '?')}: "
            f"{m.get('body', '')}"
            for m in bucket
        )
    return transcripts


def _merge_llm(rows, level_rows, level):
    """Graft the rubric columns onto the level's aggregated rows."""
    keys = agg.LEVEL_KEYS[level]
    index = {tuple(str(r.get(k, '')) for k in keys): r for r in level_rows}
    for row in rows:
        target = index.get(tuple(str(row.get(k, '')) for k in keys))
        if target is None:
            continue
        for column, value in row.items():
            if column.startswith('llm_'):
                target[column] = value


def run_llm_stage(features, transcripts_by_level, args) -> None:
    if args.llm_dry_run:
        provider = args.llm_provider or 'anthropic'
    else:
        provider = llm_rubric.resolve_provider(args.llm_provider)
        print(f'  provider: {llm_rubric.PROVIDERS[provider]["label"]}')

    models = [m.strip() for m in (args.llm_models or '').split(',') if m.strip()]
    if not models:
        models = [llm_rubric.default_model_for(provider)]
    for level in args.llm_levels:
        units = llm_rubric.build_units(
            features[level], level, transcripts_by_level[level]
        )
        if not units:
            print(f'  {level}: no transcript to score')
            continue

        if args.llm_dry_run:
            print(f'  {level}: {len(units)} units; preview of the first request')
            print(llm_rubric.dry_run_payload(units, models[0]))
            continue

        total_calls = len(units) * len(models) * args.llm_replicates
        print(f'  {level}: {len(units)} units, {total_calls} calls')

        if args.llm_batch and provider != 'anthropic':
            raise SystemExit(
                '--llm-batch is available with the anthropic provider only; '
                'with the other backends use the synchronous mode.'
            )

        if args.llm_batch:
            batch_id = llm_rubric.submit_batch(
                units, models[0], args.llm_replicates
            )
            print(f'    batch submitted: {batch_id}')
            scored = llm_rubric.collect_batch(batch_id, units)
        else:
            def progress(done, total, level=level):
                if done % 25 == 0 or done == total:
                    print(f'    {level}: {done}/{total}', flush=True)

            cache_path = Path(args.outdir) / 'cache' / f'rubrica_{level}.jsonl'
            scored, reused = llm_rubric.score_units(
                units, models=models, replicates=args.llm_replicates,
                progress=progress, provider=provider, cache_path=cache_path,
            )
            if reused:
                print(f'    {reused} units reused from cache, not paid again')

        _merge_llm(scored, features[level], level)
        errors = sum(int(r.get('llm_n_errors', 0) or 0) for r in scored)
        if errors:
            print(f'    WARNING: {errors} ratings failed', file=sys.stderr)


def run_topics_stage(messages, args):
    """Run TopicGPT and return the assignments at the various levels."""
    repo = Path(args.topicgpt_repo).expanduser()
    # Local backends (ollama, vllm) use no key: check only where it matters.
    if not args.topicgpt_dry_run and args.topicgpt_api == 'openai':
        config.require_key('OPENAI_API_KEY')

    documents = topicgpt.build_documents(messages, args.topicgpt_unit)
    print(f'  documents for induction: {len(documents)} ({args.topicgpt_unit})')

    assign_unit = args.topicgpt_assign_unit or args.topicgpt_unit
    assignment_documents = None
    if assign_unit != args.topicgpt_unit:
        assignment_documents = topicgpt.build_documents(messages, assign_unit)
        print(f'  documents for assignment: '
              f'{len(assignment_documents)} ({assign_unit})')

    if args.topicgpt_dry_run:
        outdir = Path(args.outdir) / 'topicgpt'
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / 'topicgpt_input.jsonl'
        topicgpt.write_jsonl(path, documents)
        print(f'  input written to {path} (no call made)')
        return None, None, None

    try:
        corrected = topicgpt.run_topicgpt(
            documents=documents,
            outdir=Path(args.outdir) / 'topicgpt',
            repo_path=repo,
            api=args.topicgpt_api,
            model=args.topicgpt_model,
            refine=not args.topicgpt_no_refine,
            verbose=args.verbose,
            seed_file=Path(args.topicgpt_seed).expanduser()
            if args.topicgpt_seed else None,
            assignment_documents=assignment_documents,
        )
    except topicgpt.TopicGPTUnavailable as exc:
        # A prerequisite is missing: something to fix, not a program error.
        # Show the instruction, not the stack trace.
        raise SystemExit(f'\n{exc}\n') from None
    assignments = topicgpt.parse_assignments(corrected)
    print(f'  topics assigned to {len(assignments)} documents')

    unit = assign_unit
    by_directed = (
        topicgpt.topics_by_key(assignments, unit)
        if unit == 'dyad_directed' else None
    )
    by_sender = (
        topicgpt.rollup_topics(assignments, unit, 'sender_group')
        if unit in ('dyad_directed', 'sender_group') else None
    )
    by_group = topicgpt.rollup_topics(assignments, unit, 'group')
    return by_directed, by_sender, by_group


def preflight(args) -> None:
    """Check every stage's prerequisites before running any of them.

    The paid stages cost money and time: discovering after the rubric that
    TopicGPT is not installed means having spent for nothing. The checks are all
    instant and are collected together, so everything is fixed in one go instead
    of one problem at a time.
    """
    problems = []

    if args.llm and not args.llm_dry_run:
        try:
            provider = llm_rubric.resolve_provider(args.llm_provider)
            models = [m.strip() for m in (args.llm_models or '').split(',') if m.strip()]
            llm_rubric.check_models_available(
                provider, models or [llm_rubric.default_model_for(provider)]
            )
            if args.llm_batch and provider != 'anthropic':
                problems.append(
                    '--llm-batch is available with the anthropic provider only.'
                )
        except SystemExit as exc:
            problems.append(str(exc).strip())

    if args.topics and not args.topicgpt_dry_run:
        try:
            topicgpt.check_installation(Path(args.topicgpt_repo).expanduser())
        except topicgpt.TopicGPTUnavailable as exc:
            problems.append(str(exc).strip())
        if args.topicgpt_api == 'openai':
            try:
                config.require_key('OPENAI_API_KEY')
                topicgpt.check_model_compatibility(
                    args.topicgpt_api, args.topicgpt_model)
            except SystemExit as exc:
                problems.append(str(exc).strip())
            except topicgpt.TopicGPTUnavailable as exc:
                problems.append(str(exc).strip())

    if problems:
        raise SystemExit(
            '\nPreflight check: prerequisites are missing.\n'
            'No call has been made.\n\n'
            + '\n\n'.join(f'- {p}' for p in problems)
            + '\n'
        )


def run(args) -> dict:
    """Step 2: text measures, rubric and topics over the merged files.

    `args` is the namespace built by run.py, passed through as it is so the
    option list is not duplicated in two places.
    """
    merged_dir = Path(args.merged_dir)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    messages_path = merged_dir / f'{args.stem}_messages_long.csv'
    by_partner_path = merged_dir / f'{args.stem}_chat_by_partner.csv'
    aggregated_path = merged_dir / f'{args.stem}_chat_aggregated.csv'
    for path in (messages_path, by_partner_path, aggregated_path):
        if not path.is_file():
            raise SystemExit(
                f'Missing file: {path}\n'
                f'  Run the merge step first:  python run.py merge'
            )

    preflight(args)

    messages = agg.read_messages(messages_path)
    print(f'Messages read: {len(messages)}')

    print('Text measures...')
    enriched = agg.analyze_messages(messages)
    features = agg.aggregate_all(enriched)
    for level, rows in features.items():
        print(f'  {level}: {len(rows)} units')

    transcripts_by_level = {
        level: build_transcripts(messages, level) for level in agg.LEVELS
    }

    if args.llm:
        print('Validation rubric...')
        run_llm_stage(features, transcripts_by_level, args)

    topics_directed = topics_sender = topics_group = None
    failed_stage = None
    if args.topics:
        print('TopicGPT...')
        try:
            topics_directed, topics_sender, topics_group = run_topics_stage(
                messages, args
            )
        except (topicgpt.TopicGPTUnavailable, SystemExit, RuntimeError, OSError) as exc:
            # The rubric results have already cost paid calls: write what we
            # have anyway, and report the failure at the end instead of losing
            # all the work done.
            failed_stage = ('TopicGPT', str(exc).strip())

    features_dir = outdir / 'features'
    features_dir.mkdir(parents=True, exist_ok=True)
    agg.write_csv(features_dir / f'{args.stem}_messages_nlp.csv', enriched)
    for level, rows in features.items():
        agg.write_csv(features_dir / f'{args.stem}_features_{level}.csv', rows)

    by_partner = read_csv(by_partner_path)
    aggregated = read_csv(aggregated_path)
    agg.merge_into_by_partner(by_partner, features, topics_directed)
    agg.merge_into_aggregated(aggregated, features, topics_sender, topics_group)

    datasets_dir = outdir / 'datasets'
    datasets_dir.mkdir(parents=True, exist_ok=True)
    out_partner = datasets_dir / f'{args.stem}_chat_by_partner_nlp.csv'
    out_aggregated = datasets_dir / f'{args.stem}_chat_aggregated_nlp.csv'
    agg.write_csv(out_partner, by_partner)
    agg.write_csv(out_aggregated, aggregated)

    report_paths = report.write(outdir, args.stem,
                                stages=archive.stages_of(args))
    run_dir = archive.save(outdir, args.stem, args, dict(
        n_messages=len(messages),
        levels={level: len(rows) for level, rows in features.items()},
        failed_stage=failed_stage,
    ))

    return dict(
        report=report_paths,
        run_dir=run_dir,
        n_messages=len(messages),
        levels={level: len(rows) for level, rows in features.items()},
        datasets=[out_partner, out_aggregated],
        features_dir=features_dir,
        failed_stage=failed_stage,
    )


def print_summary(summary: dict) -> int:
    """Print the outcome. Returns the program's exit code."""
    print()
    print('Datasets to take into Stata:')
    for path in summary['datasets']:
        print(f'  {path}')
    print(f"Intermediate measures: {summary['features_dir']}")
    if summary.get('report'):
        print()
        print('Readable summary:')
        for path in summary['report']:
            print(f'  {path}')
    if summary.get('run_dir'):
        print(f"Archived copy: {summary['run_dir']}")

    failed = summary.get('failed_stage')
    if not failed:
        return 0

    stage, message = failed
    print()
    print(f'WARNING: stage {stage} was not completed.')
    print('The results of the earlier stages were saved anyway:')
    print(f'  the files above are missing only the {stage} columns.')
    print()
    print(message)
    return 1
