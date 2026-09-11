# The pages in the dashboard

Everything below runs in the browser, on a local server that opens with
`chatlens dashboard`. This is how the tool is meant to be used; the commands
exist for scripting and for the stages that take minutes.

Each page answers one question, and they are ordered so the cheap and certain
ones come first.

### Participation — who spoke to whom

Every other page measures text, so it can only see the pairs that produced some.
This one shows the **whole grid**: for every group, every ordered pair of its
members, whether or not anything passed between them.

That matters more than it sounds. A row in a chat dataset is built from a
message, so a pair who never exchanged one leaves no row — and every text
measure is therefore computed on a sample **conditional on having spoken**, a
selection that is easy to forget precisely because it never appears anywhere.

On the coalition experiment this page held the strongest result in the dataset:
holding the receiver fixed, where exactly one of their possible partners had
written to them, the outcome went to the one who wrote 357 times against 35.

Needs no extra and no key. Start here.

### Words — the look before the statistics

A penalised regression over unigrams and bigrams against the declared outcome,
drawn as two clouds — the terms that go with it and the terms that go against —
and listed as a table. Downloads as PNG, SVG and CSV.

The **penalty** is a control rather than a constant, and moving it is the point
of the page: watching terms appear and disappear says how fragile the selection
is, which a single table hides.

A term being kept says it carries signal; its size says how much the penalty let
it keep. None of it is an estimate.

Needs the `words` extra.

### Narratives — who does what to whom

The same text read as (agent, verb, patient) relations rather than as words. Two
properties make that worth having. A relation comes out of a **sentence**, so
nothing has to be generalisable at the level of a whole document — which is
where topic modelling gives up on short conversations. And a relation has a
**direction**, which a word count cannot represent: in a study of who supports
whom, "I support you" and "I support the other one" are opposite moves made of
the same words.

The page will not run until you name the entities, and that is deliberate. Left
to be grouped by similarity, `i` and `you` fall together — they sit in the same
positions and mean the same kind of thing — and the speaker stops being
distinguishable from the person being spoken to. Nothing but the experiment can
know which words are its participants.

Needs the `narratives` extra, a language model, and the RELATIO package —
`chatlens install-relatio`. The package is required rather than optional, and
that is deliberate: the extraction is its method, and an approximation of
somebody else's published pipeline is not that pipeline. A result from one could
not honestly be attributed to the paper, so the page waits for the package
instead of substituting anything of ours.

**Reading an extraction needs none of that.** A study imported from somebody
who has already opened this page carries RELATIO's output, and the page shows
it without the extra, the model or the package — as long as the entities stay
as they arrived. What cannot be done without installing them is a new
extraction, which is what changing the entities asks for. Testing which
relations matter against the outcome still needs statsmodels, and the page
says so when it is missing.

**It is slow the first time and only the first time.** Parsing eight thousand
messages took a hundred and thirteen seconds on the study this was built for,
and the comparison page needed the same extraction again. The result is now
written to `output/cache/narratives/`, keyed by the corpus, the entities, the
unit and the language model — so the second page costs nothing, a dashboard
restarted tomorrow costs ten seconds rather than two minutes, and an exported
study carries it, which means the colleague who opens it does not pay either.
Change any of those four things and it is extracted again, because the answer
would be a different answer.

### Emotions — eight categories from a word list

Counts from the NRC Emotion Lexicon, which is free for research and distributed
through a form. The page says where to request it and where to put it.

Half the page is about coverage, and that is not padding: a document containing
none of the listed words scores zero on every category, which is an absence of
measurement rather than an absence of feeling, and the output column cannot tell
the two apart.

### Compare — which representation to use

All of them against the same outcome, on the same rows and the same folds. This
is the page that answers the practical question, and the one to read before
building anything on a set of columns.

Length is always the first row, because it is the null hypothesis of text
analysis: longer documents contain more of everything, and a representation that
does not beat "how much was written" has not shown that content matters.

### Settings — everything about one experiment

Files and their roles, the column mapping, the treatment labels, the outcome and
the narrative entities. All of it is written into that experiment's own
`experiment.toml`, so the folder can be copied to a colleague complete.

**What to explain** is the one to set first. Until an experiment declares an
outcome — which column holds what the analysis should explain, and at which unit
— the tool can only describe the text. With one declared, the pages above turn
from descriptions into answers.
