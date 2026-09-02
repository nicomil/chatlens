# Your own experiment

### From the interface, without touching a file

```bash
chatlens dashboard
```

opens the library: the experiments this machine holds, and a form to make
another. Then, on the new experiment's **Settings** page:

1. **Drop the CSVs in.** Any name will do — each file gets a menu saying which
   role it plays, so an export called `chat_log.csv` is as good as one called
   `messages.csv`.
2. **Confirm the columns.** The page reads the file's header and offers a menu
   per role — group, sender, recipient, text, time, treatment — filled with the
   columns your file actually has, and pre-selected by a guess from their
   names. Usually the guess is right and there is nothing to do but agree.
3. **Name the treatments.** Choosing the treatment column makes its own values
   appear, one box each: what you type is what the report prints.

Then **Start run**. No editor, no paths, nothing to remember.

The experiments live in a folder the application owns — the interface shows the
path, and each one is an ordinary directory that can be copied to a colleague
or included in a backup. It is not somewhere you would come across by accident,
so if these are participant data, check that your backup covers it.

Everything below describes the file that produces, `experiment.toml`. Reading it
is worthwhile — it is what makes an experiment portable and reviewable — but
writing it by hand is now optional.

### How the pieces fit

The project is split where the reusable part ends and the experiment-specific
part begins.

```
your export
     │
     ▼
  ADAPTER          knows your columns, your group size, your game
     │
     ▼
  THREE TABLES     messages_long · chat_by_partner · chat_aggregated
     │             the contract, written down in core/schema.py
     ▼
  CORE             measures · rubric · topics · aggregation · report
```

The core never reads a raw export. It reads the three tables and nothing else,
which is what lets it run on a study it has never seen.

### The file behind it

If your export is already one message per row — a group, a sender, a recipient,
a text — no code is needed. This is what the interface writes, and what you
would write by hand for an experiment kept outside the library:

```toml
[experiment]
name       = "Ultimatum with pre-play chat"
adapter    = "generic_chat"
group_noun = "team"          # what the report calls a group; default "group"

[input]
messages     = "chat_log*.csv"
participants = "roster*.csv"       # optional: joined onto the participant table

[columns]
group     = "team"
sender    = "from_seat"
receiver  = "to_seat"
body      = "text"
timestamp = "sent_at"              # epoch seconds or ISO 8601, either works
treatment = "condition"

[treatments]                       # how the report names them, and their order
anonymous = "Anonymous offers"
named     = "Named offers"
```

Then the usual `chatlens all`. `chatlens status` shows which adapter is active
and which files it is looking for.

Group size is whatever your data says: nothing in the core counts the members,
so three or nine aggregate the same way. The one real assumption is that a
message has **one sender and one recipient** — a message to the whole group has
no directed pair to belong to. Those rows are counted and reported rather than
attributed to somebody; if your chat is group-wide, write one row per recipient
before running.

### Measuring something else

The rubric's dimensions are declared, not hard-coded, and the prompt, the
output schema and the column names are all generated from that one declaration.
To measure something your experiment cares about:

```toml
[rubric]
context = "Two participants bargain over how to divide a sum of money."

[[rubric.dimensions]]
name    = "aggression"
label   = "AGGRESSIVENESS"
kind    = "scale"                  # 0-100; "flag" for true/false
summary = "How forcefully the writer pushes their own claim, 0-100"
high    = "ultimatums, threats to walk away, refusal to move"
low     = "concessions, hedging, invitations to find a middle ground"
```

Declaring any dimension replaces the default four, so list every one you want.
`insufficient_text` is always added: without it an empty transcript scores 50
across the board and reads like a real measurement.

One dictionary can be replaced the same way — `commitment`, the only word list
in the project that belongs to a particular game rather than to English:

```toml
[lexicons]
commitment = ["offer", "accept", "reject", "deadline", "final"]
```

### When the export is not that shape

Some exports need real reconstruction — who was in which group, what a channel
name means, what a choice was relative to a seating order. That is a Python
module in `adapters/`, and `adapters/otree_coalition.py` is the worked example:
it does all of the above for a three-player coalition game in oTree. An adapter
needs `INPUTS`, `OPTIONS`, `run()` and `print_summary()`; `core/schema.py`
states exactly what `run()` has to produce, and says so in an error message
naming the missing column if it does not.

### A limitation worth knowing before you start

The dictionary-based measures are **English only**. The tokeniser matches a-z
and the word lists are English. On a conversation in another language the
volume measures still mean something, while analytic, clout, authenticity and
tone read near zero and mean nothing at all. There is no partial credit: another
language needs its own lexicons. The rubric and the topics, being model-based,
do not have this limitation.
