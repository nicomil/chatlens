"""The narratives page: who does what to whom, and which of it matters."""

from __future__ import annotations

import html
import threading

from chatlens.core import narratives, optional

_CACHE = {}
_LOCK = threading.Lock()

_WORDS = ['spacy', 'statsmodels']


def _e(text) -> str:
    return html.escape(str(text if text is not None else ''))


def requirements(model: str):
    """Four absences, four commands.

    They are listed separately because they are separately missing and
    separately fixed. `pip install spacy` succeeds and leaves the page just as
    broken, because a language model is a different package from the library
    that loads it, and nothing in the first command hints at the second.

    RELATIO is required rather than optional. The extraction is its method, and
    an approximation of somebody else's published pipeline is not that pipeline
    — results from one could not honestly be attributed to the paper. So the
    page waits for the package instead of substituting anything of ours.
    """
    install = optional.install_command('narratives', ['spacy', 'statsmodels'])
    return [
        optional.Requirement(
            'spacy', 'spaCy', install, size='about 500 MB with the model',
            note='reads the grammar of each sentence'),
        optional.Requirement(
            'statsmodels', 'statsmodels', install, size='included above',
            note='fits the models and clusters the standard errors'),
        optional.Requirement(
            model, f'the {model} language model',
            optional.model_command(model), size='about 40 MB',
            note='the English model spaCy parses with'),
        optional.Requirement(
            'relatio', 'RELATIO', 'chatlens install-relatio',
            size='about 1.6 GB — it brings torch and transformers',
            note='extracts the relations; this page is its method, so it is '
                 'required and not approximated'),
    ]


def _requirements_panel(model: str) -> str:
    state = optional.report(requirements(model))
    if state['ready']:
        return ''
    blocks = []
    seen = set()
    for requirement in state['missing']:
        if requirement.command in seen:
            continue
        seen.add(requirement.command)
        blocks.append(
            f'<p class="muted"><b>{_e(requirement.label)}</b> — '
            f'{_e(requirement.note)}, {_e(requirement.size)}</p>'
            f'<pre class="cmd">{_e(requirement.command)}</pre>')
    return f'''<div class="panel">
  <h3>This page needs something that is not installed</h3>
  <p>Run these in order and then check again. Nothing is installed on your
  behalf: chatlens is four megabytes and this is the part that is not.</p>
  {"".join(blocks)}
  <p class="muted">Each command names this installation's own interpreter. A
  <code>pip install</code> typed into a shell usually reaches a different
  Python, and this page would go on saying the same thing.</p>
  <p><a href="?checked=1">Check again</a></p>
</div>'''


def _entities_panel(name: str, experiment) -> str:
    """The one setting the result depends on."""
    declared = ', '.join(experiment.narrative_entities)
    warning = ''
    if not experiment.narrative_entities:
        warning = ('<p class="formerror">No entities are declared. Without them '
                   'every phrase is kept under its own head word, and the '
                   'people in the experiment are not recognised as people — in '
                   'a study of who does what to whom, that is the whole '
                   'question. Name them below.</p>')
    return f'''{warning}
<form hx-post="/experiment/{_e(name)}/narratives/entities"
      hx-target="#narrativepanel" hx-swap="innerHTML">
  <label class="field"><span class="rolename">Entities</span>
    <input type="text" name="entities" value="{_e(declared)}"
           placeholder="i, you, we, and whatever names the participants"
           size="60">
    <span class="rolehint">comma separated</span></label>
  <button type="submit" class="primary">Save and run</button>
</form>
<p class="muted">These are the words that name someone rather than describe
something. Left to be grouped by similarity, <code>i</code> and
<code>you</code> fall together — they sit in the same positions and mean the
same kind of thing — and the speaker stops being distinguishable from the
person being spoken to.</p>'''


def _result(experiment):
    """Extract and test, reusing the last run when nothing that matters changed.

    Parsing eight thousand messages takes a while and the answer only depends on
    the entities and the model, so it is not repaid on every page load.
    """
    from chatlens.core import config, outcome as outcome_module
    from chatlens.web import views_participation

    declared = experiment.outcome
    key = (tuple(experiment.narrative_entities), experiment.narrative_model,
           declared and declared['column'])
    with _LOCK:
        if _CACHE.get('key') == key:
            return _CACHE['value'], ''

    messages_path = views_participation._latest(config.MERGED_DIR,
                                                '_messages_long.csv')
    if messages_path is None:
        return None, 'no messages'
    messages = views_participation._read(messages_path)

    ready, why = narratives.available()
    if not ready:
        return None, f'relatio unusable: {why}'
    per_unit = narratives.extract_with_relatio(
        messages, experiment.narrative_entities)
    value = {'per_unit': per_unit,
             'frequencies': narratives.frequencies(per_unit), 'tested': None}

    if declared and declared['kind'] == 'binary':
        suffix = f'_{outcome_module.DATASET_OF[declared["unit"]]}_nlp.csv'
        path = views_participation._latest(config.DATASETS_DIR, suffix)
        if path is not None:
            rows = views_participation._read(path)
            text_column = next(
                (c for c in ('sent_transcript_text', 'text', 'body')
                 if rows and c in rows[0]), None)

            def words_of(row):
                from chatlens.core import words as words_module

                return len(words_module.clean(row.get(text_column)).split())

            try:
                value['tested'] = narratives.which_matter(
                    per_unit, rows, declared['column'],
                    key_of=lambda r: (r['group_uid'], r['focal_id_in_group'],
                                      r['partner_id_in_group']),
                    words_of=words_of if text_column else (lambda r: 0),
                    group_of=lambda r: r['group_uid'])
            except ValueError as exc:
                value['problem'] = str(exc)

    with _LOCK:
        _CACHE.clear()
        _CACHE.update(key=key, value=value)
    return value, ''


def panel(name: str) -> str:
    from chatlens.core import config

    experiment = config.EXPERIMENT
    body = _entities_panel(name, experiment)
    if not experiment.narrative_entities:
        return body

    found, problem = _result(experiment)
    if problem == 'no messages':
        return body + ('<p class="muted">No messages table yet. Run the '
                       'analysis once.</p>')
    if problem:
        return body + f'<p class="formerror">{_e(problem)}</p>' 

    common = found['frequencies'].most_common(12)
    rows = ''.join(
        f'<tr><td><code>{_e(a)} | {_e(v)} | {_e(p)}</code></td>'
        f'<td class="num">{n}</td></tr>' for (a, v, p), n in common)
    how = ('Extracted with the <b>RELATIO package</b> (Ash, Gauthier and Widmer, '
           '<i>Political Analysis</i> 2024), which also clusters the phrases '
           'that are not declared entities and chooses how many clusters to '
           'use. The method is theirs; this tool prepares the input and reads '
           'the output.')

    body += f'''<h3>What was said</h3>
<p class="muted">{len(found["per_unit"])} units carry at least one relation, and
{len(found["frequencies"])} distinct relations were found. {how}</p>
<div class="scroll"><table class="grid">
<thead><tr><th>Relation</th><th class="num">Units</th></tr></thead>
<tbody>{rows}</tbody></table></div>'''

    tested = found.get('tested')
    if found.get('problem'):
        body += f'<p class="formerror">{_e(found["problem"])}</p>'
    elif tested is None:
        body += ('<h3>Which of them matter</h3>'
                 '<p class="muted">Declare a binary outcome under Settings and '
                 'this becomes a test rather than a list.</p>')
    else:
        result_rows = ''.join(
            f'<tr><td><code>{_e(r["narrative"][0])} | {_e(r["narrative"][1])} '
            f'| {_e(r["narrative"][2])}</code></td>'
            f'<td class="num">{r["documents"]}</td>'
            f'<td class="num">{r["odds"]:.2f}</td>'
            f'<td class="num">{r["q"]:.4f}</td>'
            f'<td>{"yes" if r["q"] < 0.10 else ""}</td></tr>'
            for r in tested['results'])
        body += f'''<h3>Which of them matter</h3>
<p class="muted">Every relation appearing in {narratives.MIN_DOCUMENTS} or more
units is tested — {tested["tested"]} of {tested["candidates"]} candidates —
holding the length of what was written constant, with standard errors clustered
by group. <b>q</b> carries a Benjamini-Hochberg correction across the whole
family: reporting the one that came out significant, out of dozens tried, is how
a list of nothing becomes a finding. {tested["survivors"]} survive at
q&nbsp;&lt;&nbsp;0.10.</p>
<div class="scroll"><table class="grid">
<thead><tr><th>Relation</th><th class="num">Units</th><th class="num">Odds</th>
<th class="num">q</th><th>Survives</th></tr></thead>
<tbody>{result_rows}</tbody></table></div>
<p class="muted">A relation naming a participant mixes the cases where that
participant is the one being addressed with the cases where they are not, and
those can be opposite moves. Reading direction properly needs the addressee's
identity, which this page does not assume every experiment has.</p>'''
    return body


def page(name: str, query=None) -> str:
    from chatlens.core import config

    experiment = config.EXPERIMENT
    needs = _requirements_panel(experiment.narrative_model)
    body = needs if needs else f'<div id="narrativepanel">{panel(name)}</div>'

    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(experiment.name)} — narratives</title>
<link rel="stylesheet" href="/static/style.css">
<script src="/static/htmx.min.js"></script>
</head><body class="library">
<header>
  <a class="back-link" href="/experiment/{_e(name)}">&larr;
    {_e(experiment.name)}</a>
  <h1>Narratives</h1>
</header>
<main class="single">
<p class="muted">The text read as relations — who does what to whom — rather
than as words. A relation has a direction, which a word count does not: in a
study of who supports whom, "I support you" and "I support the other one" are
opposite moves made of the same words.</p>
{body}
</main>
</body></html>'''
