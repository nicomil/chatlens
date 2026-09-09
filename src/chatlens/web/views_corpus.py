"""Reading the conversations, and looking behind a number.

This is the screen the tool did not have. Everything else here measures text;
nothing showed it. A reader who wanted to know what a coefficient of +1.409 on
«not enough» was made of had no way to find out, which makes every figure in
the interface something to be taken on trust.
"""

from __future__ import annotations

from chatlens.web import ui

# Enough to read; the whole corpus in one page is a download, not a screen.
GROUPS_SHOWN = 12
MESSAGES_PER_GROUP = 40


def _messages():
    """The merged message table, or nothing if the merge has not run."""
    from chatlens.core import config, corpus

    found = sorted(config.MERGED_DIR.glob('*_messages_long.csv'))
    if not found:
        return None, None
    return corpus.load(found[0]), found[0]


def _seconds(value) -> str:
    if value is None:
        return '—'
    if value < 90:
        return f'{value:.0f} s'
    if value < 5400:
        return f'{value / 60:.0f} min'
    return f'{value / 3600:.1f} h'


def _thread(entry, term: str = '') -> str:
    """One group's conversation, in the order it happened."""
    from chatlens.core import corpus

    lines = []
    for message in entry['messages'][:MESSAGES_PER_GROUP]:
        sender = message.get('sender_color') or message.get('sender_id_in_group')
        receiver = (message.get('receiver_color')
                    or message.get('receiver_id_in_group'))
        runs = corpus.highlight(str(message.get('body') or ''), term)
        body = ''.join(
            f'<mark>{ui.esc(text)}</mark>' if hit else ui.esc(text)
            for text, hit in runs)
        lines.append(
            f'<li class="turn"><span class="who">{ui.esc(sender)}'
            f'<span class="arrow">→</span>{ui.esc(receiver)}</span>'
            f'<span class="said">{body}</span></li>')

    left = len(entry['messages']) - MESSAGES_PER_GROUP
    more = (f'<li class="turn more">and {left} more in this conversation</li>'
            if left > 0 else '')
    shape = entry['shape']
    return f'''<article class="thread">
  <header>
    <h3>{ui.esc(entry['group'])}</h3>
    <span class="threadmeta">{shape['messages']} messages ·
      {shape['speakers']} speakers · {ui.esc(_seconds(shape['duration_seconds']))}
      {f"· {ui.esc(entry['treatment'])}" if entry['treatment'] else ''}</span>
  </header>
  <ol class="turns">{''.join(lines)}{more}</ol>
</article>'''


def body(name: str, query=None) -> str:
    """The finding: what these conversations are, and all of them to read."""
    from chatlens.core import corpus

    query = query or {}
    messages, path = _messages()
    if not messages:
        return ui.finding(
            'What was said?',
            'Nothing has been merged yet, so there are no conversations to '
            'read.',
            evidence=ui.empty(
                'Run the merge once — it costs nothing and needs no key — and '
                'the conversations appear here.'))

    wanted = (query.get('q') or [''])[0].strip()
    entries = corpus.conversations(messages)
    overall = corpus.shape(messages)

    if wanted:
        hit = corpus.find(messages, wanted)
        groups = {str(m.get('group_uid') or '') for m in hit['messages']}
        entries = [e for e in entries if e['group'] in groups]
        found = (f'<b>{hit["n_messages"]}</b> messages in '
                 f'<b>{len(groups)}</b> conversations contain '
                 f'“{ui.esc(wanted)}”.')
    else:
        found = ''

    answer = (f'<span class="figure">{len(entries) if wanted else overall["messages"]}</span> '
              f'{"conversations match" if wanted else "messages"}'
              if wanted else
              f'<span class="figure">{overall["messages"]}</span> messages in '
              f'<span class="figure">{len(entries)}</span> conversations.')

    search = f'''<form class="searchform" method="get">
  <label class="field"><span>Find a word or phrase</span>
    <input type="search" name="q" value="{ui.attr(wanted)}"
           placeholder="not enough">
  </label>
  <button type="submit" class="btn quiet">Search</button>
</form>'''

    tiles = ui.stat_tiles([
        (overall['messages'], 'messages'),
        (len(corpus.conversations(messages)), 'conversations'),
        (overall['mean_words'], 'words per message'),
        (_seconds(overall['median_gap_seconds']), 'median gap between turns'),
    ])

    threads = ''.join(_thread(entry, wanted)
                      for entry in entries[:GROUPS_SHOWN])
    left = len(entries) - GROUPS_SHOWN
    tail = (f'<p class="muted">{left} more conversations are in '
            f'<code>{ui.esc(path.name)}</code>.</p>' if left > 0 else '')

    return ui.finding(
        'What was said?',
        answer,
        controls=search,
        evidence=tiles + (f'<p>{found}</p>' if found else ''),
        detail=f'<h2>The conversations</h2>{threads}{tail}',
        how_to_read='''<p>These are the messages as the merge wrote them: one
        row per message, with the sender and the recipient as they were shown
        to the participants where the export carries that. The shape figures —
        how long a conversation lasted, how fast the turns came — are computed
        for every unit of analysis and used to appear nowhere.</p>
        <p>Searching here matches whole words, so "ok" does not match
        "broken". A phrase matches across the whitespace it happens to have,
        because the models are fitted on documents that were collapsed and
        these messages are not.</p>''')


def inspector(name: str, query=None) -> str:
    """The messages behind one number.

    Opened from a term in the words table or a relation in the narratives one.
    It reports the two counts separately and says which is which: a term's
    "documents" are units at the outcome's level, and showing the message count
    under that heading would overstate the evidence by however many messages a
    unit holds.
    """
    from chatlens.core import corpus

    query = query or {}
    term = (query.get('term') or [''])[0].strip()
    unit = (query.get('unit') or ['group'])[0]
    if not term:
        return ui.empty('Nothing to look at.')

    messages, _path = _messages()
    if not messages:
        return ui.empty('The messages have not been merged yet.')

    hit = corpus.find(messages, term, unit=unit)
    if not hit['n_messages']:
        return ui.empty(
            f'No message contains “{ui.esc(term)}” as a whole word. The model '
            f'was fitted on documents that had been collapsed and lower-cased, '
            f'so a term can survive there in a form no single message carries.')

    label = unit.replace('_', ' ')
    rows = []
    for message in hit['messages']:
        runs = corpus.highlight(str(message.get('body') or ''), term)
        said = ''.join(f'<mark>{ui.esc(text)}</mark>' if h else ui.esc(text)
                       for text, h in runs)
        rows.append(
            f'<li class="turn"><span class="who">'
            f'{ui.esc(message.get("group_uid"))} · '
            f'{ui.esc(message.get("sender_id_in_group"))}'
            f'<span class="arrow">→</span>'
            f'{ui.esc(message.get("receiver_id_in_group"))}</span>'
            f'<span class="said">{said}</span></li>')

    more = (f'<li class="turn more">and {hit["truncated"]} more</li>'
            if hit['truncated'] else '')

    return f'''<div class="inspector">
  <header>
    <h3>“{ui.esc(term)}”</h3>
    <span class="threadmeta">
      <b>{hit['n_units']}</b> {ui.esc(label)} units ·
      <b>{hit['n_messages']}</b> messages</span>
    <button class="btn quiet" hx-get="/experiment/{ui.esc(name)}/inspect"
            hx-target="#inspector" hx-swap="innerHTML">Close</button>
  </header>
  <p class="muted">The count in the table is the first of these: the model was
  fitted on {ui.esc(label)} units, not on messages.</p>
  <ol class="turns">{''.join(rows)}{more}</ol>
</div>'''
