"""The emotions page: NRC categories, and how much of the corpus they reach."""

from __future__ import annotations


from chatlens.web import active, ui
from chatlens.core import nrc


_e = ui.esc


def _missing_panel() -> str:
    """The lexicon is free, and still cannot be shipped.

    Three ways in, because the file reaches people three ways and the loader
    already reads all three shapes — the screen used to name only the first,
    which left the reader waiting on a form when they had a route open.
    """
    path = nrc.lexicon_path()
    return ui.blocked(
        'This finding needs the NRC Emotion Lexicon',
        f'''<p>About fourteen thousand English words marked for eight emotions
        and two sentiments (Mohammad and Turney). It is free for research and
        distributed through a request form, so it cannot be shipped with a
        tool. Any one of these gets it here.</p>
        <p><b>Ask for it.</b> The form is at
        <a href="{nrc.FORM_URL}" rel="noreferrer">saifmohammad.com</a> — the
        word-level file, currently <code>{_e(nrc.FILENAME)}</code>. Put it at
        the path below, with that name.</p>
        <p><b>Or export it from R</b>, if you have it: <code>textdata</code>
        downloads the same lexicon and asks you to accept the same licence,
        and the two-column CSV it writes is read as it is.</p>
        <p><b>Or point at a copy you already have.</b> Set
        <code>CHATLENS_NRC_LEXICON</code> to it. The distributed
        one-row-per-word-and-category form, the wide form with a column per
        category, and a <code>tidytext</code> export are all read without
        conversion.</p>
        <pre class="cmd">{_e(path)}</pre>''',
        commands=[(
            'From R',
            'install.packages("textdata")\n'
            'write.csv(tidytext::get_sentiments("nrc"),\n'
            f'          "{path}", row.names = FALSE)',
            'about 4 MB')],
        retry='?checked=1')


def _texts_and_source():
    """The documents to score, at the unit the datasets are built on."""
    from chatlens.core import config
    from chatlens.web import views_participation

    path = views_participation._latest(active.datasets_dir(),
                                       '_chat_by_partner_nlp.csv')
    if path is None:
        path = views_participation._latest(config.MERGED_DIR,
                                           '_messages_long.csv')
        if path is None:
            return [], None
        # The merged messages are one table for every treatment, so the chosen
        # study has to be applied here; the built datasets above are already
        # that study's own.
        rows = active.within(views_participation._read(path))
        return [r.get('body') or '' for r in rows], path

    rows = views_participation._read(path)
    column = next((c for c in ('sent_transcript_text', 'text', 'body')
                   if rows and c in rows[0]), None)
    if column is None:
        return [], path
    from chatlens.core import words as words_module

    return [words_module.clean(r.get(column)) for r in rows], path


def language_notice(texts) -> str:
    """Said on the page when the corpus is not the language the lists are in.

    Every dictionary in this tool — the NRC lexicon here, the LIWC-style
    categories next door — is an English word list. On a corpus in another
    language they match almost nothing, so every index built on them reads near
    zero, and a column of zeros is indistinguishable from a measurement that
    found no emotion. Until now the tool said this only in a code comment.
    """
    from chatlens.core import tokens

    found = tokens.looks_like_english(texts)
    if found['english'] is not False:
        return ''
    return ui.notice(
        f'<b>This corpus does not look like English.</b> Only '
        f'{100 * found["share"]:.0f}% of its words are English function words, '
        f'where conversational English runs above 40%. Every word list in this '
        f'tool is English, so these categories — and the analytic, clout, '
        f'authenticity and tone indices — will read near zero whatever the '
        f'conversations actually contain. That is not a measurement of calm: '
        f'it is the absence of one. Another language needs its own lexicons.',
        'bad')


def _bars(rows) -> str:
    """The categories as a chart rather than a second table.

    Eight emotions and two sentiments, each a share of the same denominator:
    a column of percentages makes the reader do the comparison the bars do for
    them. The numbers stay, on the right, because the shares are the finding.
    """
    if not rows:
        return ui.empty('No category was found in any document.')
    top = max(r['share'] for r in rows) or 1
    bars = ''.join(
        f'<tr><th>{_e(r["category"])}</th>'
        f'<td class="barcell"><span class="bar {_e(r["kind"])}" '
        f'style="width:{100 * r["share"] / top:.1f}%"></span></td>'
        f'<td class="num">{r["documents"]}</td>'
        f'<td class="num">{100 * r["share"]:.0f}%</td></tr>'
        for r in rows)
    return (f'<div class="scroll"><table class="hist emotions">'
            f'<thead><tr><th>Category</th><th></th>'
            f'<th class="num">Documents</th><th class="num">Share</th>'
            f'</tr></thead><tbody>{bars}</tbody></table></div>')


QUESTION = 'What emotional content is in these conversations?'

# See `ui.finding`'s `method` parameter.
METHOD = 'NRC Emotion Lexicon'


def panel() -> str:
    if not nrc.available():
        return ui.finding(
            QUESTION, 'Not without the word list.', method=METHOD,
            evidence=_missing_panel())
    try:
        marked = nrc.load()
    except (OSError, ValueError) as exc:
        return ui.finding(QUESTION, 'The word list could not be read.',
                          method=METHOD, evidence=ui.notice(_e(exc), 'bad'))

    texts, source = _texts_and_source()
    if not texts:
        return ui.finding(
            QUESTION, 'Not yet: there are no documents to score.',
            method=METHOD,
            evidence=ui.blocked(
                'This finding needs a run',
                'It scores the documents the measures stage writes. That '
                'stage is free and needs no key.'))

    cover = nrc.coverage(texts, marked)
    rows = nrc.totals(texts, marked)

    buckets = ''.join(
        f'<tr><td>{b["low"]}–{b["high"]}</td><td class="num">{b["n"]}</td>'
        f'<td class="num">{b["unmeasured"]}</td>'
        f'<td class="num">{100 * b["share"]:.0f}%</td></tr>'
        for b in cover['buckets'])

    totals = _bars(rows)

    unmeasured = 100 - 100 * cover['share_measured']
    caveat = ui.notice(
        f'{unmeasured:.0f}% of the documents contain no word from the lexicon '
        f'at all, so they score zero on every category. That is a correct '
        f'reading and not a gap — but those rows are overwhelmingly the short '
        f'ones, which is why length belongs in any model built on these '
        f'columns.', 'warn')
    zeros = ui.disclosure(
        'Why the zeros stay in',
        '''<p>A zero is a real value: a message with no frightening word in it
        did not frighten anyone, and those rows belong in the analysis. What
        the figures above are for is that the all-zero rows are <b>the short
        ones</b>, so these columns carry a signal about length as well as one
        about emotion. Keep the zeros and put length in the model, the same way
        every other page here does.</p>''')

    # The answer is the coverage, not the categories. A word list can only
    # speak about the documents that contain one of its words, and on short
    # messages that is a minority — read without that figure, the category
    # shares look like a measurement where there is mostly a zero.
    share = cover['share_measured']
    answer = (f'On <span class="figure">{100 * share:.0f}%</span> of the '
              f'documents. The rest contain no word from the list at all.')

    provenance = (f'<p class="muted">{len(marked)} words in the lexicon, read '
                  f'from <b>{_e(nrc.lexicon_path().name)}</b>. Scored on '
                  f'{_e(source.name if source else "the documents")}.</p>'
                  + language_notice(texts))

    tiles = ui.stat_tiles([
        (cover['documents'], 'documents with any text'),
        (cover['measured'], 'contain at least one listed word'),
        (f'{100 * share:.0f}%', 'could be measured at all'),
    ])

    where = f'''<h2>Where nothing could be measured</h2>
<div class="scroll"><table class="grid">
<thead><tr><th>Words</th><th class="num">Documents</th>
<th class="num">No emotion word</th><th class="num">Share</th></tr></thead>
<tbody>{buckets}</tbody></table></div>
<p class="muted">{_e(cover["note"])}</p>
{zeros}'''

    contain = f'''<h2>What the measured documents contain</h2>
{totals}
<p class="muted">Shares are of the {cover["measured"]} documents that could be
measured, not of all {cover["documents"]}. Over all of them every category would
be divided by the same inflated denominator, and a corpus that cannot be
measured would look uniformly unemotional.</p>'''

    return ui.finding(
        QUESTION,
        answer,
        method=METHOD,
        evidence=provenance + tiles + caveat + contain,
        detail=where,
        how_to_read='''<p>Eight emotions and two sentiments, from a word list.
        A document containing none of its words scores zero everywhere, which
        is a correct reading and not a gap — but those rows are overwhelmingly
        the short ones, so these columns carry a signal about length as well as
        one about emotion.</p>''')


