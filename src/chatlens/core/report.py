"""
Readable summary of a run, in Markdown and HTML.

It answers "how did it go?" in thirty seconds without opening CSVs of three
hundred columns: sample coverage, game outcomes, behavioural variables,
language measures and — where present — rubric and topics.

Sections for stages that did not run do not appear: a summary listing empty
boxes is harder to read than a shorter one.

The report is descriptive by choice. At a triad count like the pilot's any
comparison between treatments would be noise, so no tests are shown: the
per-treatment figures are there to see that the pipeline produced something
sensible, not to draw conclusions from.
"""

from __future__ import annotations

import csv
import html
import json
import statistics
from datetime import datetime
from pathlib import Path

TREATMENT_LABELS = {
    'private': 'Baseline (private)',
    'public': 'Public communication',
    'private_no_dwl': 'Slacker (no deadweight loss)',
}


# --- Reading and statistics ------------------------------------------------


def _read(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def _num(value):
    """Convert to a number, or None if the cell is empty or not numeric."""
    if value in (None, '', 'None'):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def _pct(part: int, whole: int) -> str:
    return f'{100.0 * part / whole:.0f}%' if whole else '—'


def _fmt(value, digits=2):
    if value is None:
        return '—'
    if isinstance(value, float):
        return f'{value:.{digits}f}'
    return str(value)


def _has_column(rows, column) -> bool:
    return bool(rows) and column in rows[0]


def _has_data(rows, column) -> bool:
    return _has_column(rows, column) and any(
        r.get(column) not in (None, '') for r in rows
    )


def _by_treatment(rows):
    """Rows bucketed by treatment, in a stable order."""
    groups = {}
    for row in rows:
        groups.setdefault(row.get('treatment', ''), []).append(row)
    order = [t for t in TREATMENT_LABELS if t in groups]
    order += [t for t in groups if t not in TREATMENT_LABELS]
    return [(t, groups[t]) for t in order]


def _triads(rows):
    """One representative row per triad: group variables repeat on each."""
    seen = {}
    for row in rows:
        uid = row.get('group_uid')
        if uid and uid not in seen:
            seen[uid] = row
    return list(seen.values())


def collect(outdir: Path, stem: str, stages=None) -> dict:
    """Collect everything needed from the files the run produced."""
    datasets = outdir / 'datasets'
    aggregated = _read(datasets / f'{stem}_chat_aggregated_nlp.csv')
    by_partner = _read(datasets / f'{stem}_chat_by_partner_nlp.csv')
    if not aggregated:
        # Without the text analysis, the merge-only files are still there.
        aggregated = _read(outdir / 'merged' / f'{stem}_chat_aggregated.csv')
        by_partner = _read(outdir / 'merged' / f'{stem}_chat_by_partner.csv')

    summary_path = outdir / 'merged' / f'{stem}_summary.json'
    merge_summary = (
        json.loads(summary_path.read_text(encoding='utf-8'))
        if summary_path.is_file() else {}
    )

    data = dict(
        stem=stem,
        stages=list(stages) if stages else None,
        generated=datetime.now().strftime('%d/%m/%Y %H:%M'),
        merge=merge_summary,
        coverage=_coverage(aggregated, by_partner, merge_summary),
        outcomes=_outcomes(aggregated),
        behaviour=_behaviour(aggregated, by_partner),
        language=_language(aggregated),
        rubric=_rubric(aggregated),
        topics=_topics(by_partner, aggregated),
        quality=_quality(aggregated, by_partner),
    )
    return data


def _coverage(aggregated, by_partner, merge_summary) -> dict:
    triads = _triads(aggregated)
    per_treatment = [
        dict(
            treatment=t,
            label=TREATMENT_LABELS.get(t, t or '—'),
            n_triads=len(_triads(rows)),
            n_participants=len(rows),
        )
        for t, rows in _by_treatment(aggregated)
    ]
    return dict(
        n_participants=len(aggregated),
        n_triads=len(triads),
        n_pairs=len(by_partner),
        n_valid_triads=sum(1 for r in triads if r.get('group_valid') == '1'),
        per_treatment=per_treatment,
        dropped=merge_summary.get('dropped') or {},
        n_input=merge_summary.get('n_input'),
        n_messages_in=merge_summary.get('n_messages_in'),
        n_messages_filtered=merge_summary.get('n_messages_filtered'),
        n_messages=merge_summary.get('n_messages_resolved'),
    )


def _outcomes(aggregated) -> dict:
    rows = []
    for treatment, participants in _by_treatment(aggregated):
        triads = _triads(participants)
        coordinated = [r for r in triads if r.get('group_coordinate') == '1']
        rows.append(dict(
            label=TREATMENT_LABELS.get(treatment, treatment or '—'),
            n_triads=len(triads),
            coordination=_pct(len(coordinated), len(triads)),
            mean_group_payoff=_mean(
                _num(r.get('group_total_payoff')) for r in triads
            ),
            mean_individual_payoff=_mean(
                _num(r.get('focal_payoff_theoretical')) for r in participants
            ),
        ))

    distribution = {}
    for row in _triads(aggregated):
        outcome = row.get('group_outcome') or '—'
        distribution[outcome] = distribution.get(outcome, 0) + 1

    decisions = {}
    for row in aggregated:
        choice = row.get('focal_decision') or '—'
        decisions[choice] = decisions.get(choice, 0) + 1

    return dict(per_treatment=rows,
                outcome_distribution=sorted(distribution.items(),
                                            key=lambda kv: -kv[1]),
                decisions=sorted(decisions.items(), key=lambda kv: -kv[1]))


def _behaviour(aggregated, by_partner) -> dict:
    rows = []
    pairs_by_treatment = dict(_by_treatment(by_partner))
    for treatment, participants in _by_treatment(aggregated):
        pairs = pairs_by_treatment.get(treatment, [])
        persuasion = [_num(p.get('persuasion_ij')) for p in pairs]
        signals = [_num(p.get('S_ij')) for p in pairs]
        rows.append(dict(
            label=TREATMENT_LABELS.get(treatment, treatment or '—'),
            n_pairs=len(pairs),
            support_signals=_mean(signals),
            persuasion=_mean(persuasion),
            consistency=_mean(_num(r.get('cc_i')) for r in participants),
            deception=_mean(_num(r.get('strategic_deception'))
                            for r in participants),
        ))
    return dict(per_treatment=rows)


LANGUAGE_METRICS = [
    ('nlp_group_wc', 'Words per triad', 0),
    ('nlp_group_n_messages', 'Messages per triad', 1),
    ('nlp_group_analytic_100', 'Analytic', 1),
    ('nlp_group_clout_100', 'Clout', 1),
    ('nlp_group_authenticity_100', 'Authenticity', 1),
    ('nlp_group_tone_100', 'Tone', 1),
    ('nlp_group_sentiment_compound_mean', 'Sentiment (VADER)', 3),
]


def _language(aggregated) -> dict:
    if not _has_data(aggregated, 'nlp_group_analytic_100'):
        return {}
    metrics = []
    for column, label, digits in LANGUAGE_METRICS:
        if not _has_column(aggregated, column):
            continue
        per_treatment = []
        for treatment, participants in _by_treatment(aggregated):
            triads = _triads(participants)
            per_treatment.append(_median(_num(r.get(column)) for r in triads))
        metrics.append(dict(label=label, digits=digits, values=per_treatment))
    return dict(
        labels=[TREATMENT_LABELS.get(t, t or '—')
                for t, _ in _by_treatment(aggregated)],
        metrics=metrics,
    )


RUBRIC_FIELDS = [
    ('nlp_group_llm_analytic', 'nlp_group_analytic_100', 'Analytic'),
    ('nlp_group_llm_clout', 'nlp_group_clout_100', 'Clout'),
    ('nlp_group_llm_authenticity', 'nlp_group_authenticity_100', 'Authenticity'),
    ('nlp_group_llm_tone', 'nlp_group_tone_100', 'Tone'),
]


def _correlation(pairs):
    pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
    if len(pairs) < 3:
        return None
    xs, ys = zip(*pairs)
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in pairs)
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / den if den else None


def _rubric(aggregated) -> dict:
    if not _has_data(aggregated, 'nlp_group_llm_analytic'):
        return {}
    triads = _triads(aggregated)
    rows = []
    for llm_col, dict_col, label in RUBRIC_FIELDS:
        if not _has_column(aggregated, llm_col):
            continue
        rows.append(dict(
            label=label,
            llm_median=_median(_num(r.get(llm_col)) for r in triads),
            dict_median=_median(_num(r.get(dict_col)) for r in triads),
            sd=_mean(_num(r.get(f'{llm_col}_sd')) for r in triads),
            correlation=_correlation(
                [(_num(r.get(dict_col)), _num(r.get(llm_col))) for r in triads]
            ),
        ))
    commitments = [r for r in triads
                   if r.get('nlp_group_llm_contains_support_commitment') == '1']
    return dict(
        n_triads=len(triads),
        rows=rows,
        n_with_commitment=len(commitments),
    )


def _topics(by_partner, aggregated) -> dict:
    if not _has_data(by_partner, 'nlp_sent_topics'):
        return {}
    counts = {}
    with_topic = 0
    for row in by_partner:
        topics = [t for t in (row.get('nlp_sent_topics') or '').split('|') if t]
        if topics:
            with_topic += 1
        for topic in topics:
            counts[topic] = counts.get(topic, 0) + 1

    per_treatment = []
    for treatment, pairs in _by_treatment(by_partner):
        local = {}
        for row in pairs:
            for topic in (row.get('nlp_sent_topics') or '').split('|'):
                if topic:
                    local[topic] = local.get(topic, 0) + 1
        per_treatment.append(dict(
            label=TREATMENT_LABELS.get(treatment, treatment or '—'),
            counts=local,
        ))

    return dict(
        n_pairs=len(by_partner),
        n_with_topic=with_topic,
        counts=sorted(counts.items(), key=lambda kv: -kv[1]),
        topics=[t for t, _ in sorted(counts.items(), key=lambda kv: -kv[1])],
        per_treatment=per_treatment,
    )


def _quality(aggregated, by_partner) -> dict:
    triads = _triads(aggregated)
    notes = []

    invalid = [r for r in triads if r.get('group_valid') != '1']
    if invalid:
        subject = (f'1 triad out of {len(triads)} has' if len(invalid) == 1
                   else f'{len(invalid)} triads out of {len(triads)} have')
        notes.append(
            f'{subject} at least one member excluded for inactivity or cut '
            f'short: they stay in the dataset, but the main analyses should be '
            f'run on group_valid == 1.'
        )

    if _has_column(aggregated, 'nlp_group_low_language_flag'):
        flagged = [r for r in triads
                   if r.get('nlp_group_low_language_flag') == '1']
        if flagged:
            subject = ('1 triad contains' if len(flagged) == 1
                       else f'{len(flagged)} triads contain')
            notes.append(
                f'{subject} text that does not look like language: the language '
                f'indices should not be read on those units.'
            )

    if _has_column(aggregated, 'nlp_group_llm_n_errors'):
        errors = sum(int(_num(r.get('nlp_group_llm_n_errors')) or 0)
                     for r in triads)
        if errors:
            notes.append(
                '1 rubric rating failed.' if errors == 1
                else f'{errors} rubric ratings failed.'
            )

    silent = [r for r in triads if (_num(r.get('nlp_group_n_messages')) or 0) == 0]
    if silent:
        subject = ('1 triad exchanged' if len(silent) == 1
                   else f'{len(silent)} triads exchanged')
        notes.append(f'{subject} no messages at all.')

    if len(triads) < 60:
        notes.append(
            f'With {len(triads)} triads the comparisons between treatments are '
            f'descriptive: the figures serve to check that the pipeline '
            f'produces sensible results, not to draw conclusions from.'
        )
    return dict(notes=notes)


# --- Markdown rendering ----------------------------------------------------


def _md_table(headers, rows) -> str:
    out = ['| ' + ' | '.join(headers) + ' |',
           '|' + '|'.join('---' for _ in headers) + '|']
    for row in rows:
        out.append('| ' + ' | '.join(str(c) for c in row) + ' |')
    return '\n'.join(out)


def render_markdown(data: dict) -> str:
    cov = data['coverage']
    parts = [
        f"# Text analysis — {data['stem']}",
        '',
        f"Run of {data['generated']}."
        + (f" Stages run: {', '.join(data['stages'])}."
           if data.get('stages') else ''),
        '',
        '## Coverage',
        '',
    ]

    rows = [
        ['Participants analysed', cov['n_participants']],
        ['Triads', cov['n_triads']],
        ['Valid triads', f"{cov['n_valid_triads']} of {cov['n_triads']}"],
        ['Directed pairs', cov['n_pairs']],
    ]
    if cov.get('n_messages') is not None:
        rows.append(['Messages analysed', cov['n_messages']])
    parts.append(_md_table(['', 'Value'], rows))

    if cov['dropped']:
        parts += ['', f"Of the {cov['n_input']} participants in the export, "
                      f"{cov['dropped'].get('never_grouped', 0)} were excluded "
                      f"as never grouped and "
                      f"{cov['dropped'].get('no_prolific_id', 0)} as having no "
                      f"Prolific identifier (test sessions)."]

    parts += ['', _md_table(
        ['Treatment', 'Triads', 'Participants'],
        [[t['label'], t['n_triads'], t['n_participants']]
         for t in cov['per_treatment']],
    )]

    out = data['outcomes']
    parts += ['', '## Game outcomes', '', _md_table(
        ['Treatment', 'Triads', 'Coordination', 'Group payoff',
         'Individual payoff'],
        [[r['label'], r['n_triads'], r['coordination'],
          _fmt(r['mean_group_payoff']), _fmt(r['mean_individual_payoff'])]
         for r in out['per_treatment']],
    )]
    parts += ['', 'Outcomes: ' + ', '.join(f'{k} ({v})'
                                           for k, v in out['outcome_distribution'])]
    parts += ['', 'Final choices: ' + ', '.join(f'{k} ({v})'
                                                for k, v in out['decisions'])]

    beh = data['behaviour']
    parts += ['', '## Behavioural variables', '', _md_table(
        ['Treatment', 'Pairs', 'Support signals', 'Persuasion',
         'Choice-signal consistency', 'Strategic deception'],
        [[r['label'], r['n_pairs'], _fmt(r['support_signals']),
          _fmt(r['persuasion']), _fmt(r['consistency']), _fmt(r['deception'])]
         for r in beh['per_treatment']],
    )]
    parts += ['', 'The first two columns are proportions over directed pairs, '
                  'the last two are means over participants.']

    lang = data['language']
    if lang:
        parts += ['', '## Language (medians per triad)', '', _md_table(
            [''] + lang['labels'],
            [[m['label']] + [_fmt(v, m['digits']) for v in m['values']]
             for m in lang['metrics']],
        )]

    rub = data['rubric']
    if rub:
        parts += ['', '## Validation rubric', '', _md_table(
            ['Construct', 'Rubric', 'Dictionary', 'Spread across replicates',
             'Correlation'],
            [[r['label'], _fmt(r['llm_median'], 1), _fmt(r['dict_median'], 1),
              _fmt(r['sd'], 1), _fmt(r['correlation'])] for r in rub['rows']],
        )]
        parts += ['', f"Explicit commitments to support detected in "
                      f"{rub['n_with_commitment']} triads out of "
                      f"{rub['n_triads']}.",
                  '', 'The correlation compares the rubric with the dictionary '
                      'measure: it is the convergent validation, not a '
                      'correctness check. If it is low or negative it should be '
                      'reported, not corrected.']

    top = data['topics']
    if top:
        parts += ['', '## Topics', '',
                  f"Assigned to {top['n_with_topic']} directed pairs out of "
                  f"{top['n_pairs']}.", '',
                  _md_table(['Topic', 'Pairs'],
                            [[k, v] for k, v in top['counts']])]
        if len(top['per_treatment']) > 1:
            parts += ['', _md_table(
                ['Treatment'] + top['topics'],
                [[t['label']] + [t['counts'].get(name, 0)
                                 for name in top['topics']]
                 for t in top['per_treatment']],
            )]

    notes = data['quality']['notes']
    if notes:
        parts += ['', '## Worth keeping in mind', '']
        parts += [f'- {n}' for n in notes]

    return '\n'.join(parts) + '\n'


# --- HTML rendering --------------------------------------------------------

HTML_STYLE = """
:root {
  --paper: #fbfbfd; --ink: #16181d; --soft: #4a5060; --muted: #6b7183;
  --rule: #e1e3ec; --accent: #2f4c8c; --band: #f3f4f8;
}
@media (prefers-color-scheme: dark) {
  :root {
    --paper: #0f1116; --ink: #e9ebf1; --soft: #c2c7d4; --muted: #929aac;
    --rule: #262a35; --accent: #8aa8ec; --band: #171a21;
  }
}
* { box-sizing: border-box; }
body {
  background: var(--paper); color: var(--ink); margin: 0;
  padding: 3rem 1.5rem 5rem; line-height: 1.6;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
main { max-width: 60rem; margin: 0 auto; }
h1 { font-size: 1.9rem; margin: 0 0 .3rem; letter-spacing: -.02em; }
h2 {
  font-size: 1.2rem; margin: 2.4rem 0 .8rem; padding-bottom: .3rem;
  border-bottom: 1px solid var(--rule);
}
p { margin: .6rem 0; max-width: 62ch; }
.meta { color: var(--muted); font-size: .9rem; margin-bottom: 1.5rem; }
.scroll { overflow-x: auto; margin: .8rem 0; }
table { border-collapse: collapse; width: 100%; font-size: .92rem; }
th, td {
  text-align: left; padding: .45rem .8rem .45rem 0;
  border-bottom: 1px solid var(--rule); font-variant-numeric: tabular-nums;
}
th { font-size: .72rem; text-transform: uppercase; letter-spacing: .07em;
     color: var(--muted); font-weight: 600; white-space: nowrap; }
td:not(:first-child), th:not(:first-child) { text-align: right; }
.cards { display: flex; flex-wrap: wrap; gap: 1px; background: var(--rule);
         border: 1px solid var(--rule); margin: 1rem 0; }
.card { background: var(--paper); padding: .8rem 1.1rem; flex: 1 1 8rem; }
.card .v { font-size: 1.6rem; font-weight: 600; letter-spacing: -.02em;
           font-variant-numeric: tabular-nums; }
.card .l { font-size: .7rem; text-transform: uppercase; letter-spacing: .07em;
           color: var(--muted); }
.note { background: var(--band); border-left: 3px solid var(--accent);
        padding: .8rem 1.1rem; margin: .5rem 0; font-size: .93rem;
        color: var(--soft); }
.caption { color: var(--muted); font-size: .87rem; }
"""


def _html_table(headers, rows) -> str:
    head = ''.join(f'<th>{html.escape(str(h))}</th>' for h in headers)
    body = ''.join(
        '<tr>' + ''.join(f'<td>{html.escape(str(c))}</td>' for c in row) + '</tr>'
        for row in rows
    )
    return (f'<div class="scroll"><table><thead><tr>{head}</tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def render_html(data: dict) -> str:
    cov = data['coverage']
    out = data['outcomes']
    beh = data['behaviour']

    cards = [
        (cov['n_triads'], 'triads'),
        (cov['n_participants'], 'participants'),
        (cov['n_pairs'], 'directed pairs'),
    ]
    if cov.get('n_messages') is not None:
        cards.append((cov['n_messages'], 'messages'))
    cards.append((f"{cov['n_valid_triads']}/{cov['n_triads']}", 'valid triads'))

    body = [
        f"<h1>Text analysis — {html.escape(data['stem'])}</h1>",
        f"<p class=\"meta\">Run of {html.escape(data['generated'])}"
        + (f" &middot; stages: {html.escape(', '.join(data['stages']))}"
           if data.get('stages') else '') + "</p>",
        '<div class="cards">',
        *(f'<div class="card"><div class="v">{v}</div>'
          f'<div class="l">{l}</div></div>' for v, l in cards),
        '</div>',
    ]

    if cov['dropped']:
        body.append(
            f"<p class=\"caption\">Of the {cov['n_input']} participants in the "
            f"export, {cov['dropped'].get('never_grouped', 0)} were excluded as "
            f"never grouped and {cov['dropped'].get('no_prolific_id', 0)} as "
            f"having no Prolific identifier (test sessions).</p>")

    body += ['<h2>Coverage</h2>', _html_table(
        ['Treatment', 'Triads', 'Participants'],
        [[t['label'], t['n_triads'], t['n_participants']]
         for t in cov['per_treatment']])]

    body += ['<h2>Game outcomes</h2>', _html_table(
        ['Treatment', 'Triads', 'Coordination', 'Group payoff',
         'Individual payoff'],
        [[r['label'], r['n_triads'], r['coordination'],
          _fmt(r['mean_group_payoff']), _fmt(r['mean_individual_payoff'])]
         for r in out['per_treatment']])]
    body.append('<p class="caption">Outcomes: ' + html.escape(
        ', '.join(f'{k} ({v})' for k, v in out['outcome_distribution'])) +
        '<br>Final choices: ' + html.escape(
        ', '.join(f'{k} ({v})' for k, v in out['decisions'])) + '</p>')

    body += ['<h2>Behavioural variables</h2>', _html_table(
        ['Treatment', 'Pairs', 'Support signals', 'Persuasion',
         'Consistency', 'Strategic deception'],
        [[r['label'], r['n_pairs'], _fmt(r['support_signals']),
          _fmt(r['persuasion']), _fmt(r['consistency']), _fmt(r['deception'])]
         for r in beh['per_treatment']]),
        '<p class="caption">The first two columns are proportions over '
        'directed pairs, the last two are means over participants.</p>']

    lang = data['language']
    if lang:
        body += ['<h2>Language (medians per triad)</h2>', _html_table(
            [''] + lang['labels'],
            [[m['label']] + [_fmt(v, m['digits']) for v in m['values']]
             for m in lang['metrics']])]

    rub = data['rubric']
    if rub:
        body += ['<h2>Validation rubric</h2>', _html_table(
            ['Construct', 'Rubric', 'Dictionary', 'Replicate spread',
             'Correlation'],
            [[r['label'], _fmt(r['llm_median'], 1), _fmt(r['dict_median'], 1),
              _fmt(r['sd'], 1), _fmt(r['correlation'])] for r in rub['rows']]),
            f'<p class="caption">Explicit commitments to support detected in '
            f"{rub['n_with_commitment']} triads out of {rub['n_triads']}. "
            f'The correlation is the convergent validation between the two '
            f'measures: if it is low or negative it should be reported, not '
            f'corrected.</p>']

    top = data['topics']
    if top:
        body += ['<h2>Topics</h2>',
                 f"<p>Assigned to {top['n_with_topic']} directed pairs out of "
                 f"{top['n_pairs']}.</p>",
                 _html_table(['Topic', 'Pairs'],
                             [[k, v] for k, v in top['counts']])]
        if len(top['per_treatment']) > 1:
            body.append(_html_table(
                ['Treatment'] + top['topics'],
                [[t['label']] + [t['counts'].get(n, 0) for n in top['topics']]
                 for t in top['per_treatment']]))

    notes = data['quality']['notes']
    if notes:
        body.append('<h2>Worth keeping in mind</h2>')
        body += [f'<div class="note">{html.escape(n)}</div>' for n in notes]

    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>Text analysis — {html.escape(data["stem"])}</title>'
        f'<style>{HTML_STYLE}</style></head><body><main>'
        + ''.join(body) + '</main></body></html>'
    )


def write(outdir: Path, stem: str, stages=None) -> list[Path]:
    """Generate the report in both formats and return the paths."""
    data = collect(outdir, stem, stages=stages)
    md_path = outdir / f'{stem}_report.md'
    html_path = outdir / f'{stem}_report.html'
    md_path.write_text(render_markdown(data), encoding='utf-8')
    html_path.write_text(render_html(data), encoding='utf-8')
    return [md_path, html_path]
