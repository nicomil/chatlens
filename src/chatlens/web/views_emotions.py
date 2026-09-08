"""The emotions page: NRC categories, and how much of the corpus they reach."""

from __future__ import annotations

import html

from chatlens.core import nrc


def _e(text) -> str:
    return html.escape(str(text if text is not None else ''))


def _missing_panel() -> str:
    """The lexicon is free, and still cannot be shipped."""
    path = nrc.lexicon_path()
    return f'''<div class="panel">
  <h3>The lexicon is not here</h3>
  <p>The NRC Emotion Lexicon is free for research and distributed through a
  request form, so it cannot be included. Getting it is two steps and then this
  page works.</p>
  <ol>
    <li>Request it at <a href="{nrc.FORM_URL}" rel="noreferrer">
      saifmohammad.com</a> — the word-level file, currently
      <code>{_e(nrc.FILENAME)}</code>.</li>
    <li>Put it here, with that name:
      <pre class="cmd">{_e(path)}</pre></li>
  </ol>
  <p class="muted">Either the one-row-per-word-and-category form or the wide
  one will do; both are read. If you keep it somewhere else, point
  <code>CHATLENS_NRC_LEXICON</code> at it.</p>
  <p><a href="?checked=1">Check again</a></p>
</div>'''


def _texts_and_source():
    """The documents to score, at the unit the datasets are built on."""
    from chatlens.core import config
    from chatlens.web import views_participation

    path = views_participation._latest(config.DATASETS_DIR,
                                       '_chat_by_partner_nlp.csv')
    if path is None:
        path = views_participation._latest(config.MERGED_DIR,
                                           '_messages_long.csv')
        if path is None:
            return [], None
        rows = views_participation._read(path)
        return [r.get('body') or '' for r in rows], path

    rows = views_participation._read(path)
    column = next((c for c in ('sent_transcript_text', 'text', 'body')
                   if rows and c in rows[0]), None)
    if column is None:
        return [], path
    from chatlens.core import words as words_module

    return [words_module.clean(r.get(column)) for r in rows], path


def panel() -> str:
    if not nrc.available():
        return _missing_panel()
    try:
        marked = nrc.load()
    except (OSError, ValueError) as exc:
        return f'<p class="formerror">{_e(exc)}</p>'

    texts, source = _texts_and_source()
    if not texts:
        return ('<p class="muted">Nothing to score yet: run the analysis once '
                'so there are documents to read.</p>')

    cover = nrc.coverage(texts, marked)
    rows = nrc.totals(texts, marked)

    buckets = ''.join(
        f'<tr><td>{b["low"]}–{b["high"]}</td><td class="num">{b["n"]}</td>'
        f'<td class="num">{b["unmeasured"]}</td>'
        f'<td class="num">{100 * b["share"]:.0f}%</td></tr>'
        for b in cover['buckets'])

    totals = ''.join(
        f'<tr><td>{_e(r["category"])}</td><td>{_e(r["kind"])}</td>'
        f'<td class="num">{r["documents"]}</td>'
        f'<td class="num">{100 * r["share"]:.0f}%</td></tr>' for r in rows)

    return f'''<p class="muted">{len(marked)} words in the lexicon, read from
<b>{_e(nrc.lexicon_path().name)}</b>. Scored on
{_e(source.name if source else "the documents")}.</p>

<div class="stats">
  <div class="stat"><div class="v">{cover["documents"]}</div>
    <div class="l">documents with any text</div></div>
  <div class="stat"><div class="v">{cover["measured"]}</div>
    <div class="l">contain at least one listed word</div></div>
  <div class="stat"><div class="v">{100 * cover["share_measured"]:.0f}%</div>
    <div class="l">could be measured at all</div></div>
</div>

<h3>Where nothing could be measured</h3>
<div class="scroll"><table class="grid">
<thead><tr><th>Words</th><th class="num">Documents</th>
<th class="num">No emotion word</th><th class="num">Share</th></tr></thead>
<tbody>{buckets}</tbody></table></div>
<p class="muted">{_e(cover["note"])}</p>
<p class="muted">A document with no listed word scores zero on every category,
and that is not the same as a neutral one — it is an absence of measurement
wearing the same number. Anything built on these columns should carry the
unmeasured rows as missing rather than as zeros.</p>

<h3>What the measured documents contain</h3>
<div class="scroll"><table class="grid">
<thead><tr><th>Category</th><th>Kind</th><th class="num">Documents</th>
<th class="num">Share</th></tr></thead>
<tbody>{totals}</tbody></table></div>
<p class="muted">Shares are of the {cover["measured"]} documents that could be
measured, not of all {cover["documents"]}. Over all of them every category would
be divided by the same inflated denominator, and a corpus that cannot be
measured would look uniformly unemotional.</p>'''


def page(name: str, query=None) -> str:
    from chatlens.core import config

    experiment = config.EXPERIMENT
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(experiment.name)} — emotions</title>
<link rel="stylesheet" href="/static/style.css">
</head><body class="library">
<header>
  <a class="back-link" href="/experiment/{_e(name)}">&larr;
    {_e(experiment.name)}</a>
  <h1>Emotions</h1>
</header>
<main class="single">
<p class="muted">Eight emotions and two sentiments, from a word list. It counts
words that are on the list, so a document containing none scores zero
everywhere — which is an absence of measurement rather than an absence of
feeling, and the tables below keep the two apart.</p>
{panel()}
</main>
</body></html>'''
