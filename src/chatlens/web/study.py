"""What state a study is in: which steps are done, which questions can be asked.

The interface used to leave both of these to the reader. Whether the setup was
finished could only be learnt by scrolling four sections; which of the five
analysis pages had anything to say could only be learnt by opening all five.
Both are computable, and this is where they are computed.

Nothing here renders anything. `web/ui.py` draws what this returns.
"""

from __future__ import annotations

from chatlens.web import ui


def _dataset_exists() -> bool:
    """True once a run has produced something to analyse."""
    from chatlens.core import config

    try:
        return any(config.DATASETS_DIR.glob('*_nlp.csv'))
    except OSError:
        return False


def _merged_exists() -> bool:
    from chatlens.core import config

    try:
        return any(config.MERGED_DIR.glob('*_messages_long.csv'))
    except OSError:
        return False


def step_state(experiment) -> dict:
    """Each step of the study's life, in the state it is really in.

    A step is `done` when the thing it is for has been decided, not when it has
    been visited: visiting is not a decision and the reader knows it.
    """
    from chatlens.core import config
    from chatlens.web import views_library

    declared = experiment.declared
    ready, missing = views_library.readiness(
        config.WORKSPACE, experiment.adapter, declared.get('input'))
    columns = declared.get('columns') or {}
    has_columns = all(columns.get(role)
                      for role in views_library.REQUIRED_ROLES)
    # The oTree adapter reads its export directly; there is nothing to map, so
    # the step is satisfied by the adapter rather than by the user.
    if experiment.adapter != 'generic_chat':
        has_columns = ready
    has_outcome = bool((declared.get('outcome') or {}).get('column'))
    has_run = _dataset_exists() or _merged_exists()

    state = {
        'data': ui.DONE if ready else ui.TODO,
        'columns': ui.DONE if has_columns else ui.TODO,
        'outcome': ui.DONE if has_outcome else ui.TODO,
        'run': ui.DONE if has_run else ui.TODO,
        'findings': ui.DONE if has_run else ui.TODO,
    }
    if not ready:
        because = f'{missing} still missing'
        state['columns'] = (ui.BLOCKED, 'the files come first')
        state['run'] = (ui.BLOCKED, because)
        state['findings'] = (ui.BLOCKED, because)
    elif not has_run:
        state['findings'] = (ui.BLOCKED, 'nothing has been run yet')
    return state


# The questions this tool can answer, in the order they make sense: what was
# said, who said it, then the four ways of turning it into numbers. `order`
# breaks ties inside a verdict group so the list does not reshuffle itself
# between runs.
CATALOGUE = (
    ('corpus', 'What was said', 0),
    ('participation', 'Who spoke to whom', 1),
    ('compare', 'Which representation to trust', 2),
    ('words', 'The words', 3),
    ('narratives', 'The relations', 4),
    ('emotions', 'The emotions', 5),
)

# Which entries need a declared outcome before they are even a question.
NEEDS_OUTCOME = {'compare', 'words', 'narratives'}

# Entries answerable from the merge alone, with no analysis run behind them.
NEEDS_NO_RUN = {'corpus', 'participation'}


def findings(experiment, verdicts=None) -> list[dict]:
    """The register: one entry per question, with the state it is in.

    `verdicts` is what the analysis actually found, when it has been computed —
    a mapping of entry id to `(verdict, note)`. Without it every answerable
    entry is `open`, which is what the register shows while the numbers are
    still being worked out.
    """
    verdicts = verdicts or {}
    blocked = ui.unavailable_reasons()
    has_outcome = bool((experiment.declared.get('outcome') or {}).get('column'))
    has_run = _dataset_exists()

    entries = []
    for key, name, order in CATALOGUE:
        verdict, note = verdicts.get(key, (ui.OPEN, ''))
        if key in blocked:
            verdict, note = ui.UNAVAILABLE, blocked[key]
        elif key in NEEDS_OUTCOME and not has_outcome:
            verdict, note = ui.UNAVAILABLE, 'no outcome declared yet'
        elif key not in NEEDS_NO_RUN and not has_run:
            verdict, note = ui.UNAVAILABLE, 'needs a run first'
        entries.append({'id': key, 'name': name, 'order': order,
                        'verdict': verdict, 'note': note})
    return entries


def verdicts() -> dict:
    """What the analysis actually found, per entry of the register.

    Every number here is already computed by the core; this only reads the
    decisions out and says them in one line each. The heavy one — the
    comparison — is cached by `views_compare`, so the second reader pays
    nothing.
    """
    from chatlens.web import views_compare

    found = {}
    found.update(_corpus_verdict())
    found.update(_participation_verdict())
    found.update(_emotions_verdict())

    scored, problem = views_compare._scored()
    if problem or not scored:
        return found

    volume = scored.get('volume')
    by_kind = {row['kind']: row for row in scored['results']}
    for key, kind in (('words', 'words'), ('narratives', 'narratives')):
        row = by_kind.get(kind)
        if row is None:
            continue
        if row['auc'] is None:
            # Unavailable is for what could not be computed here. A row the
            # data answered — relations found, none frequent enough to use —
            # is open, with the reason as its note.
            found[key] = (ui.OPEN if row.get('answered') else ui.UNAVAILABLE,
                          row.get('why', ''))
        elif row['beats_volume']:
            found[key] = (ui.YES, f'{row["auc"]:.3f} against {volume:.3f}')
        else:
            found[key] = (ui.NO, f'{row["auc"]:.3f} against {volume:.3f} '
                                 f'for length')

    winners = [r for r in scored['results']
               if r['kind'] != 'volume' and r.get('beats_volume')]
    scorable = [r for r in scored['results'] if r['auc'] is not None]
    if scorable:
        best = max(scorable, key=lambda r: r['auc'])
        found['compare'] = (
            (ui.YES, f'{best["name"].lower()} does best at {best["auc"]:.3f}')
            if winners else
            (ui.NO, f'nothing beats length at {volume:.3f}'))
    return found


def _corpus_verdict() -> dict:
    """Not a verdict: a size. The corpus is the thing, not a claim about it."""
    from chatlens.core import config, corpus

    found = sorted(config.MERGED_DIR.glob('*_messages_long.csv'))
    if not found:
        return {}
    try:
        messages = corpus.load(found[0])
    except OSError:
        return {}
    groups = len({str(m.get('group_uid') or '') for m in messages})
    return {'corpus': (ui.OPEN,
                       f'{len(messages)} messages in {groups} conversations')}


def _participation_verdict() -> dict:
    """Whether writing at all went with the outcome.

    On the study this grew out of it was the strongest result of the lot, and
    it is not about the text: it is about the pairs where there was none.
    """
    from chatlens.core import participation
    from chatlens.web import views_participation

    messages_path, roster_path, by_partner_path = views_participation._sources()
    if messages_path is None:
        return {}
    try:
        messages = views_participation._read(messages_path)
        roster = (views_participation._read(roster_path)
                  if roster_path else None)
        members, _source = participation.membership(messages, roster=roster)
        cover = participation.coverage(
            participation.grid(messages, members), members)
    except (OSError, ValueError):
        return {}

    empty = cover['cells'] - cover['used']
    share = empty / cover['cells'] if cover['cells'] else 0
    return {'participation': (ui.OPEN,
                              f'{empty} of {cover["cells"]} directions silent '
                              f'({100 * share:.0f}%)')}


def _emotions_verdict() -> dict:
    """How much of the corpus a word list can say anything about at all."""
    from chatlens.core import nrc
    from chatlens.web import views_emotions

    try:
        if not nrc.available():
            return {}
        marked = nrc.load()
        texts, _source = views_emotions._texts_and_source()
        if not texts:
            return {}
        cover = nrc.coverage(texts, marked)
    except (OSError, ValueError):
        return {}
    share = cover['share_measured']
    return {'emotions': (ui.OPEN,
                         f'{100 * share:.0f}% of documents could be measured')}


def entry_name(key: str) -> str:
    for candidate, name, _order in CATALOGUE:
        if candidate == key:
            return name
    return key
