"""
Esegue la pipeline NLP sui messaggi dell'esperimento e arricchisce i dataset.

Tre stadi indipendenti, attivabili separatamente:

1. **Misure testuali** (sempre attivo, nessuna credenziale richiesta) —
   volume, sentiment e gli indici in stile LIWC-22 (analytic, clout,
   authenticity, tone), calcolati a livello di coppia ordinata, coppia,
   partecipante e gruppo.
2. **Rubrica LLM** (``--llm``) — seconda misura degli stessi costrutti
   valutata da Claude, per validazione convergente. Richiede una credenziale
   Anthropic.
3. **TopicGPT** (``--topics``) — codice ufficiale di Pham et al. (2024).
   Richiede il repository clonato e la credenziale del backend scelto.

L'output finale sono i due dataset dell'esperimento arricchiti, pronti per
Stata, più i file di feature intermedi per i controlli.

Esempi (dal punto di ingresso del progetto)
------------------------------------------
    python run.py analyze                          misure automatiche
    python run.py analyze --llm --llm-replicates 2 + rubrica di validazione
    python run.py analyze --topics --topicgpt-repo ~/src/topicGPT
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from . import aggregate as agg  # noqa: E402
from . import config, llm_rubric, report, topicgpt  # noqa: E402


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def build_transcripts(messages, level: str) -> dict:
    """Trascrizioni leggibili per livello, usate dalla rubrica LLM."""
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
    """Innesta le colonne della rubrica nelle righe aggregate del livello."""
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
        print(f'  fornitore: {llm_rubric.PROVIDERS[provider]["label"]}')

    models = [m.strip() for m in (args.llm_models or '').split(',') if m.strip()]
    if not models:
        models = [llm_rubric.default_model_for(provider)]
    for level in args.llm_levels:
        units = llm_rubric.build_units(
            features[level], level, transcripts_by_level[level]
        )
        if not units:
            print(f'  {level}: nessuna trascrizione da valutare')
            continue

        if args.llm_dry_run:
            print(f'  {level}: {len(units)} unità; anteprima della prima richiesta')
            print(llm_rubric.dry_run_payload(units, models[0]))
            continue

        total_calls = len(units) * len(models) * args.llm_replicates
        print(f'  {level}: {len(units)} unità, {total_calls} chiamate')

        if args.llm_batch and provider != 'anthropic':
            raise SystemExit(
                "--llm-batch e' disponibile solo con il fornitore anthropic; "
                'con gli altri backend usa la modalita\' sincrona.'
            )

        if args.llm_batch:
            batch_id = llm_rubric.submit_batch(
                units, models[0], args.llm_replicates
            )
            print(f'    batch inviato: {batch_id}')
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
                print(f'    {reused} unità riprese dalla cache, non ripagate')

        _merge_llm(scored, features[level], level)
        errors = sum(int(r.get('llm_n_errors', 0) or 0) for r in scored)
        if errors:
            print(f'    ATTENZIONE: {errors} valutazioni fallite', file=sys.stderr)


def run_topics_stage(messages, args):
    """Esegue TopicGPT e restituisce le assegnazioni ai vari livelli."""
    repo = Path(args.topicgpt_repo).expanduser()
    # I backend locali (ollama, vllm) non usano chiavi: si controlla solo dove serve.
    if not args.topicgpt_dry_run and args.topicgpt_api == 'openai':
        config.require_key('OPENAI_API_KEY')

    documents = topicgpt.build_documents(messages, args.topicgpt_unit)
    print(f'  documenti per l induzione: {len(documents)} ({args.topicgpt_unit})')

    assign_unit = args.topicgpt_assign_unit or args.topicgpt_unit
    assignment_documents = None
    if assign_unit != args.topicgpt_unit:
        assignment_documents = topicgpt.build_documents(messages, assign_unit)
        print(f'  documenti per l assegnazione: '
              f'{len(assignment_documents)} ({assign_unit})')

    if args.topicgpt_dry_run:
        outdir = Path(args.outdir) / 'topicgpt'
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / 'topicgpt_input.jsonl'
        topicgpt.write_jsonl(path, documents)
        print(f'  input scritto in {path} (nessuna chiamata effettuata)')
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
        # Manca un prerequisito: è una cosa da sistemare, non un errore del
        # programma. Si mostra l'istruzione, non la traccia dello stack.
        raise SystemExit(f'\n{exc}\n') from None
    assignments = topicgpt.parse_assignments(corrected)
    print(f'  topic assegnati a {len(assignments)} documenti')

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
    """Verifica i prerequisiti di tutti gli stadi prima di eseguirne uno.

    Gli stadi a pagamento costano soldi e tempo: scoprire dopo la rubrica che
    TopicGPT non è installato significa aver speso per nulla. I controlli sono
    tutti istantanei e vengono raccolti insieme, così si sistema una volta sola
    invece di scoprire un problema per volta.
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
                    "--llm-batch è disponibile solo con il fornitore anthropic."
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
            except SystemExit as exc:
                problems.append(str(exc).strip())

    if problems:
        raise SystemExit(
            '\nControllo preliminare: mancano dei prerequisiti.\n'
            'Nessuna chiamata è stata effettuata.\n\n'
            + '\n\n'.join(f'- {p}' for p in problems)
            + '\n'
        )


def run(args) -> dict:
    """Passo 2: misure testuali, rubrica e topic sui file prodotti dal merge.

    `args` è lo spazio dei nomi costruito da run.py: si passa così com'è, per
    non duplicare l'elenco delle opzioni in due punti.
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
                f'File mancante: {path}\n'
                f'  Esegui prima il passo di unione:  python run.py merge'
            )

    preflight(args)

    messages = agg.read_messages(messages_path)
    print(f'Messaggi letti: {len(messages)}')

    print('Misure testuali...')
    enriched = agg.analyze_messages(messages)
    features = agg.aggregate_all(enriched)
    for level, rows in features.items():
        print(f'  {level}: {len(rows)} unità')

    transcripts_by_level = {
        level: build_transcripts(messages, level) for level in agg.LEVELS
    }

    if args.llm:
        print('Rubrica di validazione...')
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
            # I risultati della rubrica sono già costati chiamate a pagamento:
            # si scrive comunque quello che c'è, e il fallimento viene riportato
            # alla fine invece di far perdere tutto il lavoro svolto.
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

    report_paths = report.write(outdir, args.stem)

    return dict(
        report=report_paths,
        n_messages=len(messages),
        levels={level: len(rows) for level, rows in features.items()},
        datasets=[out_partner, out_aggregated],
        features_dir=features_dir,
        failed_stage=failed_stage,
    )


def print_summary(summary: dict) -> int:
    """Stampa l'esito. Restituisce il codice di uscita del programma."""
    print()
    print('Dataset da portare in Stata:')
    for path in summary['datasets']:
        print(f'  {path}')
    print(f"Misure intermedie: {summary['features_dir']}")
    if summary.get('report'):
        print()
        print('Riassunto leggibile:')
        for path in summary['report']:
            print(f'  {path}')

    failed = summary.get('failed_stage')
    if not failed:
        return 0

    stage, message = failed
    print()
    print(f'ATTENZIONE: lo stadio {stage} non e\' stato completato.')
    print('I risultati degli stadi precedenti sono stati salvati comunque:')
    print(f'  nei file qui sopra mancano solo le colonne di {stage}.')
    print()
    print(message)
    return 1
