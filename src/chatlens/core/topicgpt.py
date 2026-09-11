"""
Adapter for TopicGPT (Pham et al., NAACL 2024).

The experimenter asked that the paper's code be used strictly: this module does
**not** rewrite the algorithm. It prepares the input in the format TopicGPT
expects, calls the package's official functions in the prescribed order, and
maps the output back onto the experiment's keys. Topic generation, refinement,
assignment and correction remain entirely the authors' code.

Official repository: https://github.com/chtmp223/topicGPT

Installation
------------
The PyPI package (0.2.7) imports vLLM at top level, a heavy dependency that
cannot be installed on macOS without a GPU; the ``main`` branch on GitHub has
already made it an optional extra. Install from the repository, which is needed
anyway because **the prompt files are not inside the package**: they live in
`prompt/` in the repository and are an integral part of the method.

    git clone https://github.com/chtmp223/topicGPT.git
    pip install ./topicGPT           # without the [vllm] extra

Unit of analysis
----------------
TopicGPT induces topics from documents, and a chat turn of a few words is not a
document. Topics are therefore induced on the group's whole conversation and
assigned to the **directed pair** — everything i wrote to j — which is the unit
where persuasion happens. The topics are then aggregated to participant and
group level.

Backend
-------
TopicGPT talks to OpenAI, Azure, Vertex, Gemini, Ollama or vLLM. The paper uses
OpenAI, which remains the most faithful choice. Two routes reach Claude without
modifying the authors' code: the ``vertex`` backend, which in the repository
builds an ``AnthropicVertex`` client, or the ``openai`` backend pointed at a
compatible gateway through ``OPENAI_BASE_URL``.
"""

from __future__ import annotations

import contextlib
import io
import json
import random
import re
import sys
from pathlib import Path

from . import schema

# TopicGPT's assignment response format: "[1] Name: description".
#
# The name stops at the end of its line. It used to be matched with `\s` in
# the character class, which includes the newline, so a label ran on into
# whatever followed — and what follows, when the model declines to classify a
# document, is a bulleted list of the topics it considered:
#
#     Unfortunately, it cannot be assigned to any topic in the hierarchy:
#     - [1] Coalition Proposal
#     - [1] Commitment
#     - [1] Payoff Reasoning
#
# That refusal was read as three assignments, and the document came out
# belonging to all three topics. A blemish in the label was the visible part
# of it; the false positives were not visible at all.
#
# So an assignment is anchored to the start of its line. A well-formed answer
# opens with it — 1 738 of the 2 438 on this study do, and the only response
# carrying a bulleted list was the refusal above. `\s` before the bracket
# allows indentation and nothing else: a `- ` does not match, which is what
# separates a topic that was assigned from a topic that was merely named.
TOPIC_RE = re.compile(r"^[ \t]*\[(\d)\]\s*([^\n:]+)", re.MULTILINE)

# The tally the induction appends to each name: "Name (Count: 271)".
COUNT_RE = re.compile(r"\s*\(Count\b[^)]*\)?\s*$")

PROMPT_FILES = {
    'generation': 'prompt/generation_1.txt',
    'seed': 'prompt/seed_1.md',
    'refinement': 'prompt/refinement.txt',
    'assignment': 'prompt/assignment.txt',
    'correction': 'prompt/correction.txt',
}

# Second-level topics are optional, so the file is checked only when they are
# asked for: an older clone that lacks it should not stop an ordinary run.
SUBTOPIC_PROMPT = 'prompt/generation_2.txt'

# TopicGPT comments on every document with print() to stdout, while the progress
# bar lives on stderr: each message pushes the bar onto a new line, and instead
# of one advancing line you get hundreds. Repetitive messages are therefore
# collected and summarised at the end of each phase; unexpected ones pass
# through unchanged, because hiding an unknown message is worse than the mess.
NOISY_LINES = [
    ('Invalid topic format', 'documents with no recognised topic'),
    ('Lower level topics are not allowed', 'lower-level topics discarded'),
    ('Error: Row', 'rows with no topic'),
    ('Hallucinated:', 'topics invented by the model'),
    ('Document is too long', 'documents truncated'),
    ('Too many topics', 'topic lists pruned'),
]

# Refinement is the one phase that leaves no trace in its output file when a
# call fails: it catches the exception, prints this line and carries on with the
# topic tree unmerged. Counting the line is the only way to know it happened.
API_FAILURE_LINES = (
    'Error when calling API!',
)

# Banner lines repeating parameters the caller already knows.
BANNER_LINES = (
    '---', 'Initializing', 'Model:', 'Data file:', 'Prompt file:',
    'Seed file:', 'Output file:', 'Topic file:', 'Generation file:',
    'Refined file:', 'Updated file:', 'Mapping file:', 'Prompt token usage',
    'Response token usage',
)


class _Digest(io.TextIOBase):
    """Collect TopicGPT's stdout, counting the repetitive messages."""

    def __init__(self):
        self.counts = {}
        self.passthrough = []
        self.api_failures = 0
        self._partial = ''

    def write(self, text):
        self._partial += text
        while '\n' in self._partial:
            line, self._partial = self._partial.split('\n', 1)
            self._handle(line.strip())
        return len(text)

    def _handle(self, line):
        if not line or line.startswith(BANNER_LINES):
            return
        # Checked before the noisy lines: a failure must never be filed away as
        # one of the benign repetitive messages.
        if any(needle in line for needle in API_FAILURE_LINES):
            self.api_failures += 1
            return
        for needle, label in NOISY_LINES:
            if needle in line:
                self.counts[label] = self.counts.get(label, 0) + 1
                return
        self.passthrough.append(line)

    def flush(self):
        if self._partial.strip():
            self._handle(self._partial.strip())
            self._partial = ''

    def report(self, prefix='    '):
        """Print the summary: unexpected messages first, then the counts."""
        self.flush()
        for line in self.passthrough:
            print(f'{prefix}{line}')
        for label, count in sorted(self.counts.items(), key=lambda kv: -kv[1]):
            print(f'{prefix}{count} {label}')
        if self.api_failures:
            print(f'{prefix}{self.api_failures} API CALLS FAILED')


@contextlib.contextmanager
def _quiet(verbose: bool):
    """Silence TopicGPT's stdout, leaving the bar on stderr intact."""
    if verbose:
        yield None
        return
    digest = _Digest()
    try:
        with contextlib.redirect_stdout(digest):
            yield digest
    finally:
        sys.stdout.flush()


UNIT_KEYS = {
    'dyad_directed': ('group_uid', 'sender_id_in_group', 'receiver_id_in_group'),
    'dyad': ('group_uid', 'dyad_key'),
    'sender_group': ('group_uid', 'sender_id_in_group'),
    'group': ('group_uid',),
}


class TopicGPTUnavailable(RuntimeError):
    """TopicGPT or its prompt files are unavailable."""


class TopicGPTIncomplete(RuntimeError):
    """A phase answered fewer documents than it was given, or answered "Error".

    Raised by :func:`verify_phase`. It is a separate exception from
    ``TopicGPTUnavailable`` because it means something different to the caller:
    the run started correctly and then lost documents part-way through, so
    there is paid-for work on disk worth resuming from.
    """




def check_installation(repo_path: Path) -> None:
    """Check the package and the prompt files, with actionable messages."""
    # Check the package exists without importing it: the import drags in torch
    # and transformers and costs several seconds, which a preflight check — run
    # at every start — has no business spending.
    import importlib.util

    if importlib.util.find_spec('topicgpt_python') is None:
        raise TopicGPTUnavailable(
            'The topicgpt_python package is not installed.\n'
            '  chatlens install-topicgpt'
        )

    missing = [name for name in PROMPT_FILES.values() if not (repo_path / name).is_file()]
    if missing:
        raise TopicGPTUnavailable(
            f'Prompt files missing under {repo_path}: {", ".join(missing)}.\n'
            'The prompts are part of the method and live in the repository, not '
            'in the installed package: run "chatlens install-topicgpt", or '
            'pass --topicgpt-repo if you already have a clone.'
        )


def check_model_compatibility(api: str, model: str) -> None:
    """Check that the model accepts the parameters TopicGPT sends.

    TopicGPT fixes `temperature` and `top_p` in every phase. Some recent models
    reject them with a 400, and the library responds by retrying three times
    with sixty seconds between attempts: without this check the incompatibility
    would surface after two minutes of nothing, on every document.

    We probe with a minimal call rather than keeping a list of incompatible
    models, which would be out of date next month.
    """
    if api != 'openai':
        return
    try:
        from openai import OpenAI
    except ImportError:
        return

    try:
        OpenAI().chat.completions.create(
            model=model,
            messages=[{'role': 'user', 'content': 'ok'}],
            temperature=0.0,
            top_p=1.0,
            max_completion_tokens=5,
        )
    except Exception as exc:  # noqa: BLE001 - any refusal is informative
        message = str(exc)
        if 'temperature' in message or 'top_p' in message:
            raise TopicGPTUnavailable(
                f'Model {model} does not accept the parameters TopicGPT sends '
                f"(temperature and top_p are fixed in the authors' code).\n"
                f'  Use a model that supports them, for example gpt-4o, which is '
                f"also the paper's.\n"
                f'  Recent models remain usable for the rubric: '
                f'--llm-models {model}'
            ) from None
        # Any other error (key, network, non-existent model) is reported as
        # it is: it is not a compatibility problem.
        raise TopicGPTUnavailable(
            f'Model {model} does not answer: {message[:200]}'
        ) from None


def build_documents(messages, unit: str = 'dyad_directed') -> list[dict]:
    """Build the documents for TopicGPT from the messages.

    Every document carries an ``id`` that lets the assigned topics be rejoined
    to the experiment's units: TopicGPT preserves the JSONL's extra columns in
    the output file.
    """
    from collections import defaultdict

    keys = UNIT_KEYS[unit]
    buckets = defaultdict(list)
    for message in messages:
        buckets[tuple(str(message.get(k, '')) for k in keys)].append(message)

    documents = []
    for key, bucket in sorted(buckets.items()):
        bucket.sort(key=lambda m: schema.parse_timestamp(m.get('timestamp')) or 0.0)
        lines = [
            f"{m.get('sender_color', '?')} to {m.get('receiver_color', '?')}: "
            f"{m.get('body', '')}"
            for m in bucket
        ]
        text = '\n'.join(lines).strip()
        if not text:
            continue
        documents.append(
            dict(
                id='|'.join(key),
                text=text,
                unit=unit,
                treatment=bucket[0].get('treatment', ''),
                n_messages=len(bucket),
            )
        )
    return documents


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


# The string TopicGPT writes into a document's response field when the API call
# raised. It is the only trace an API failure leaves in the output.
API_ERROR = 'Error'


def already_done(phase: str, path: Path, expected: int,
                 allow_short: bool = False):
    """What this phase produced last time, if it finished. Otherwise None.

    `verify_phase` already knows what a complete output looks like, down to
    the `"Error"` rows TopicGPT writes instead of raising, so it is what
    decides. Anything it rejects — absent, truncated, carrying failures — is
    treated here as absent: a half-finished phase is paid for again rather
    than half-reused.
    """
    if not path.is_file():
        return None
    try:
        return verify_phase(phase, path, expected, allow_short=allow_short)
    except TopicGPTIncomplete:
        return None


def verify_phase(phase: str, path: Path, expected: int,
                 allow_short: bool = False) -> int:
    """Check a phase answered every document it was given; raise if it did not.

    TopicGPT does not propagate API failures. When a call raises it records the
    string ``"Error"`` as that document's response and carries on — and in
    generation it breaks out of the loop and truncates the output file to the
    answers it managed to collect (``df.iloc[: len(responses)]``). Either way
    the function returns normally. Without this check the caller sees a clean
    return, the pipeline builds its datasets from whatever arrived, the report
    is written and the archive records the run as complete.

    That is not hypothetical: a run of 1,333 documents stopped at 806 when the
    credit balance ran out, and produced a full set of output files that gave
    no sign 527 documents were missing. It was caught by counting the lines in
    the input and the output by hand.

    Nothing is deleted when this fails. The answers already paid for stay where
    they are, and the message says how many there are, because the sensible
    next step is to resume from them rather than buy them again.

    ``allow_short`` is for generation only, where stopping early is a documented
    feature of the method: once ``early_stop`` documents in a row have produced
    no new topic, induction has converged and returns. A short file with no
    ``"Error"`` in it is therefore that convergence, and is reported rather than
    raised.
    """
    if not path.is_file():
        raise TopicGPTIncomplete(
            f'{phase}: {path.name} was not written at all.\n'
            f'  Expected {expected} answers. Check the messages above for the '
            f'cause.')

    rows = read_jsonl(path)
    failed = sum(1 for r in rows
                 if str(r.get('responses') or '').strip() == API_ERROR)

    if failed:
        raise TopicGPTIncomplete(
            f'{phase}: {failed} of {len(rows)} documents came back as an API '
            f'error, and {expected - len(rows)} were never sent.\n'
            f'  The usual cause is an exhausted credit balance or a revoked '
            f'key; the traceback above says which.\n'
            f'  {len(rows) - failed} answers are already on disk in '
            f'{path.name} and are not affected. Fix the key and resume from '
            f'them rather than paying for them twice.')

    if len(rows) < expected:
        if allow_short:
            print(f'    induction converged early: {len(rows)} of {expected} '
                  f'documents read before the topic list stopped growing',
                  flush=True)
            return len(rows)
        raise TopicGPTIncomplete(
            f'{phase}: {len(rows)} answers for {expected} documents — '
            f'{expected - len(rows)} are missing, with no error recorded '
            f'against them.\n'
            f'  {path.name} holds what arrived.')

    return len(rows)


def generation_order(documents, shuffle_seed=1) -> list:
    """The order induction will read the documents in.

    Its own function because the dry run has to write exactly what the real run
    would send. Writing the documents in one order and sending them in another
    would make the dry run a check on something that never happens.

    `shuffle_seed=None` or 0 keeps the order they came in.
    """
    ordered = list(documents)
    if shuffle_seed:
        random.Random(shuffle_seed).shuffle(ordered)
    return ordered


def run_topicgpt(
    documents,
    outdir: Path,
    repo_path: Path,
    api: str = 'openai',
    model: str = 'gpt-4o',
    refine: bool = True,
    verbose: bool = True,
    seed_file: Path | None = None,
    unsupervised: bool = False,
    induce_only: bool = False,
    shuffle_seed: int | None = None,
    assignment_documents=None,
    reuse: bool = False,
) -> Path:
    """Run the official pipeline and return the assignments file.

    The four phases are the paper's: generation of first-level topics,
    refinement (merging similar topics and removing rare ones), assignment to
    documents, correction of invalid assignments.
    """
    check_installation(repo_path)
    from topicgpt_python import (
        assign_topics,
        correct_topics,
        generate_topic_lvl1,
        refine_topics,
    )

    outdir.mkdir(parents=True, exist_ok=True)

    # Topic induction is order-dependent by construction: the list accumulates
    # as documents are read, and each document is shown the list so far with an
    # instruction to reuse an existing topic where one fits. What comes first
    # therefore shapes the vocabulary, and what comes last is nudged into it.
    #
    # Left in their natural order the documents arrive sorted by group_uid,
    # which begins with the session code, and each session is one treatment. On
    # the coalition data that means one whole condition is read only after the
    # taxonomy has already settled on the other two.
    #
    # (Generation also stops once `early_stop` consecutive documents add
    # nothing, but `generate_topic_lvl1` defaults that to 1000 and there are
    # 501 documents, so it cannot fire here. The ordering matters on its own.)
    #
    # The shuffle is seeded, so a run is reproducible and the seed can be
    # reported alongside the topic list.
    generation_documents = generation_order(documents, shuffle_seed)

    data_file = outdir / 'topicgpt_input.jsonl'
    write_jsonl(data_file, generation_documents)

    # The seed is a parameter of the method, not code. Three cases:
    #
    # unsupervised   an empty list. The model invents every topic from the
    #                documents, which is what TopicGPT is for; the file is
    #                still written so the archive records what was used.
    # a file         a starting list, which steers the induction.
    # neither        the repository's own seed, which belongs to another corpus
    #                (US legislation). The paper's prompt tells the model to
    #                answer "None" where a document has no recognisable topic,
    #                and with the wrong seed that is the answer for every chat.
    if unsupervised:
        seed_path = outdir / 'seed_unsupervised.md'
        seed_path.write_text('', encoding='utf-8')
    else:
        seed_path = (Path(seed_file) if seed_file
                     else repo_path / PROMPT_FILES['seed'])
        if not seed_path.is_file():
            raise TopicGPTUnavailable(f'Seed file not found: {seed_path}')

    generation_out = outdir / 'generation_1.jsonl'
    topics_lvl1 = outdir / 'generation_1.md'

    total = 2 if induce_only else 4
    induced = (already_done('topic generation', generation_out,
                            len(documents), allow_short=True)
               if reuse else None)
    if induced is not None:
        print(f'  [1/{total}] topic generation — '
              f'{generation_out.name} is complete, not run again',
              flush=True)
    else:
        print(f'  [1/{total}] topic generation', flush=True)
        with _quiet(verbose) as digest:
            generate_topic_lvl1(
                api=api,
                model=model,
                data=str(data_file),
                prompt_file=str(repo_path / PROMPT_FILES['generation']),
                seed_file=str(seed_path),
                out_file=str(generation_out),
                topic_file=str(topics_lvl1),
                verbose=verbose,
            )
        if digest:
            digest.report()
        # Before anything downstream reads this file. Generation is the one phase
        # allowed to stop early, because the method says so.
        induced = verify_phase('topic generation', generation_out, len(documents),
                               allow_short=True)

    topics_for_assignment = topics_lvl1
    # Topics can be induced on a broad unit and assigned to a finer one:
    # induction needs substantial documents, assignment does not.
    if assignment_documents is not None:
        data_for_assignment = outdir / 'topicgpt_assignment_input.jsonl'
        write_jsonl(data_for_assignment, assignment_documents)
    else:
        data_for_assignment = data_file

    if refine:
        refined_topics = outdir / 'generation_1_refined.md'
        refined_generation = outdir / 'generation_1_updated.jsonl'
        # Both files: the taxonomy is what assignment reads, the updated
        # generation is what says the phase finished.
        done = (already_done('refinement', refined_generation, induced)
                if reuse and refined_topics.is_file() else None)
        if done is not None:
            print(f'  [2/{total}] refinement — {refined_topics.name} is '
                  f'complete, not run again', flush=True)
        else:
            print(f'  [2/{total}] refinement', flush=True)
            with _quiet(verbose) as digest:
                refine_topics(
                    api=api,
                    model=model,
                    prompt_file=str(repo_path / PROMPT_FILES['refinement']),
                    generation_file=str(generation_out),
                    topic_file=str(topics_lvl1),
                    out_file=str(refined_topics),
                    updated_file=str(refined_generation),
                    verbose=verbose,
                    remove=True,
                    mapping_file=str(outdir / 'refiner_mapping.json'),
                )
            if digest:
                digest.report()
                # Refinement writes nothing into its output to mark a failed call,
                # so the count of the line it prints is the only evidence. With
                # verbose=True there is no digest to count it and the lines reach
                # the terminal instead, where the caller sees them directly.
                if digest.api_failures:
                    raise TopicGPTIncomplete(
                        f'refinement: {digest.api_failures} API calls failed.\n'
                        f'  Refinement merges and prunes the induced topics, and a '
                        f'failed call silently leaves that merge undone, so the '
                        f'topic list would be neither the raw one nor the refined '
                        f'one.\n'
                        f'  The raw topics are in {topics_lvl1.name} and are '
                        f'unaffected.')
            verify_phase('refinement', refined_generation, induced)
        topics_for_assignment = refined_topics

    if induce_only:
        # Assignment costs about four times what induction does, and the
        # taxonomy is the thing there is to judge: a list of one broad topic is
        # not worth attributing to two thousand documents. Stopping here puts
        # that judgement before the spending; the assignment run afterwards
        # reads this same topic file.
        print(f'  stopping after induction: '
              f'{topics_for_assignment.name} holds the topics', flush=True)
        return None

    n_assigned = len(assignment_documents if assignment_documents is not None
                     else documents)
    assignment_out = outdir / 'assignment.jsonl'
    if reuse and already_done('assignment', assignment_out,
                              n_assigned) is not None:
        print(f'  [3/4] assignment — {assignment_out.name} is complete, '
              f'not run again', flush=True)
    else:
        print('  [3/4] assignment to documents', flush=True)
        with _quiet(verbose) as digest:
            assign_topics(
                api=api,
                model=model,
                data=str(data_for_assignment),
                prompt_file=str(repo_path / PROMPT_FILES['assignment']),
                out_file=str(assignment_out),
                topic_file=str(topics_for_assignment),
                verbose=verbose,
            )
        if digest:
            digest.report()
        verify_phase('assignment', assignment_out, n_assigned)

    corrected_out = outdir / 'assignment_corrected.jsonl'
    if reuse and already_done('correction', corrected_out,
                              n_assigned) is not None:
        print(f'  [4/4] correction — {corrected_out.name} is complete, '
              f'not run again', flush=True)
    else:
        print('  [4/4] correction of assignments', flush=True)
        with _quiet(verbose) as digest:
            correct_topics(
                api=api,
                model=model,
                data_path=str(assignment_out),
                prompt_path=str(repo_path / PROMPT_FILES['correction']),
                topic_path=str(topics_for_assignment),
                output_path=str(corrected_out),
                verbose=verbose,
            )
        if digest:
            digest.report()
        verify_phase('correction', corrected_out, n_assigned)

    return corrected_out


def subtopics(
    run_dir: Path,
    repo_path: Path,
    api: str = 'openai',
    model: str = 'gpt-4o',
    prompt_file: Path | None = None,
    verbose: bool = False,
) -> Path:
    """Second-level topics, following Appendix A of the paper.

    The topics that survive refinement become parents, and the model is asked
    what themes run through the documents assigned to each. Documents are
    batched into the prompt rather than sent one per call, so a parent holding a
    thousand conversations costs one call and not a thousand — this is by far
    the cheapest phase, and the only one that can be run as an experiment.

    Two things to know before reading the result, both observed on the corpus
    this tool was built for.

    **The examples decide the answer.** The prompt carries example subtopics, and
    Appendix D of the paper shows they control the granularity of what comes
    back. Passing ``prompt_file`` with different examples and comparing is the
    honest way to use this; taking one run as the taxonomy is not.

    **The grounding may not hold.** The method asks the model to cite the
    documents supporting each subtopic, so that subtopics are grounded rather
    than invented. On a parent holding 1,383 documents both variants tried cited
    documents 1-10; on one holding 136 they cited all 136. At that scale the
    citation is either the first handful or a blanket, and the subtopics
    therefore carry no usable prevalence. Check what came back before believing
    the labels.
    """
    check_installation(repo_path)
    prompt = Path(prompt_file) if prompt_file else repo_path / SUBTOPIC_PROMPT
    if not prompt.is_file():
        raise TopicGPTUnavailable(
            f'The second-level prompt is not at {prompt}.\n'
            f'  It ships with the repository; pull the clone, or pass a prompt '
            f'file of your own.')

    parents = run_dir / 'generation_1_refined.md'
    if not parents.is_file():
        parents = run_dir / 'generation_1.md'
    assignments = run_dir / 'assignment_corrected.jsonl'
    for path in (parents, assignments):
        if not path.is_file():
            raise TopicGPTIncomplete(
                f'{path.name} is missing: second-level topics start from the '
                f'first level, so that run has to have completed its '
                f'assignment.')

    from topicgpt_python import generate_topic_lvl2

    out_file = run_dir / 'generation_2.jsonl'
    topic_file = run_dir / 'generation_2.md'
    print('  second-level topics', flush=True)
    with _quiet(verbose) as digest:
        generate_topic_lvl2(
            api=api,
            model=model,
            seed_file=str(parents),
            data=str(assignments),
            prompt_file=str(prompt),
            out_file=str(out_file),
            topic_file=str(topic_file),
            verbose=verbose,
        )
    if digest:
        digest.report()

    # generate_topic_lvl2 records "Error" and returns normally, exactly as the
    # other phases do.
    rows = read_jsonl(out_file) if out_file.is_file() else []
    failed = sum(1 for r in rows
                 if str(r.get('topics') or '').strip() == API_ERROR)
    if failed or not rows:
        raise TopicGPTIncomplete(
            f'second-level generation: {failed} of {len(rows)} prompts failed. '
            f'Nothing usable was produced.')
    return topic_file


def subtopic_grounding(run_dir: Path) -> list:
    """How many documents each subtopic actually cited, against how many it saw.

    The paper's safeguard is that a subtopic must name the documents supporting
    it. Whether that happened is checkable from the output, and is worth
    checking: a subtopic citing the first ten of a thousand documents is not
    grounded in them, and nothing else in the output says so.
    """
    import re

    out_file = run_dir / 'generation_2.jsonl'
    if not out_file.is_file():
        return []
    found = []
    for row in read_jsonl(out_file):
        shown = str(row.get('text') or '').count('Document ')
        for line in str(row.get('topics') or '').splitlines():
            match = re.match(r"\s*\[2\]\s*([\w\s&'-]+?)\s*\(Documents?:\s*"
                             r"([^)]*)\)", line)
            if not match:
                continue
            cited = match.group(2)
            if '-' in cited and ',' not in cited:
                parts = cited.split('-')
                try:
                    n_cited = int(parts[-1]) - int(parts[0]) + 1
                except ValueError:
                    n_cited = 0
            else:
                n_cited = len([c for c in cited.split(',') if c.strip()])
            found.append({'name': match.group(1).strip(), 'cited': n_cited,
                          'shown': shown,
                          'share': n_cited / shown if shown else 0.0})
    return found


def induced_topics(path: Path) -> set:
    """The topic names the induction settled on, from its own file.

    The list the assignment was given, which is the only list an assignment
    may draw from. Anything else in a response is the model writing prose or
    inventing a label — on this project, `[1] No suitable topic:`, which is
    a refusal wearing the shape of an answer.
    """
    names = set()
    if not path or not Path(path).is_file():
        return names
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        found = TOPIC_RE.match(line.strip())
        if not found:
            continue
        # The induction writes "[1] Name (Count: 271): description", so the
        # tally has to come off before the name is one the assignment could
        # have answered with.
        name = COUNT_RE.sub('', found.group(2)).strip()
        if name:
            names.add(' '.join(name.split()))
    return names


def parse_assignments(path: Path, known=None) -> dict:
    """Extract the assigned topics, indexed by the document's ``id``.

    `known` is the induced taxonomy. Given it, a name that is not in it is
    dropped: the assignment prompt offers a fixed list, so a label outside it
    is not a finding about the document but an artefact of the response.
    Without it every name is kept, because filtering against a list we do not
    have would silently empty the column.
    """
    result = {}
    for row in read_jsonl(path):
        response = row.get('responses') or ''
        topics = []
        for _level, name in TOPIC_RE.findall(response):
            cleaned = ' '.join(name.split())
            if not cleaned or cleaned in topics:
                continue
            if known and cleaned not in known:
                continue
            topics.append(cleaned)
        result[row.get('id', '')] = dict(
            topics='|'.join(topics),
            topic_primary=topics[0] if topics else '',
            n_topics=len(topics),
        )
    return result


def topics_by_key(assignments: dict, unit: str) -> dict:
    """Map the assignments onto the tuple keys the merge uses."""
    return {tuple(doc_id.split('|')): value for doc_id, value in assignments.items()}


def rollup_topics(assignments: dict, unit: str, target: str) -> dict:
    """Roll topics up from a fine unit to a coarser one.

    Needed when topics are assigned to directed pairs but are also wanted at
    participant or group level: the topic set of the higher unit is the union of
    those of the units composing it.
    """
    from collections import defaultdict

    source_keys = UNIT_KEYS[unit]
    target_keys = UNIT_KEYS[target]
    positions = [source_keys.index(k) for k in target_keys if k in source_keys]
    if len(positions) != len(target_keys):
        raise ValueError(f'{target} cannot be rolled up from {unit}')

    buckets = defaultdict(list)
    for doc_id, value in assignments.items():
        parts = doc_id.split('|')
        key = tuple(parts[p] for p in positions)
        buckets[key].extend(t for t in value['topics'].split('|') if t)

    rolled = {}
    for key, topics in buckets.items():
        unique = []
        for topic in topics:
            if topic not in unique:
                unique.append(topic)
        rolled[key] = dict(
            topics='|'.join(unique),
            topic_primary=unique[0] if unique else '',
            n_topics=len(unique),
        )
    return rolled
