# Participant data

The files this produces are **personal data**, and treating them as anything
else is the mistake worth avoiding at the start rather than explaining later.
Two things are in them.

**Identifiers.** The oTree export carries the recruitment platform's
participant id — on Prolific, a value that follows the same person across every
study they have ever taken part in — and it passes straight through into the
output. The analysis never uses it: what it needs is to tell participants
apart, not to know who they are.

```bash
chatlens merge --pseudonymise
```

replaces every identifier with a keyed hash. The pseudonyms are stable within a
workspace, so the same person is the same code across the three tables and
across a re-run months later; they are not reversible without the key, which
lives in `output/.pseudonym_key` and must never travel with the data —
`chatlens export` never packs it, for that reason. Delete
the key and the link is gone for good — which is the point, and also the thing
to be sure about before you delete it. The flag changes nothing else: every
number is identical either way.

**The conversations themselves.** These are untouched, and no option changes
that: they are the object of the analysis. People write their names, their
towns and their jobs into chat windows, so a pseudonymised dataset is
pseudonymised, not anonymous. What follows from that:

- `input/` and `output/` are excluded from version control, and should stay so
  in any workspace you create;
- the paid stages send the conversations to a third party — OpenAI or Anthropic
  — which is a disclosure your ethics approval and your participant information
  sheet have to cover. `--topicgpt-api ollama` runs the topics on a local model
  instead, and the rubric takes `--llm-provider ollama` for the same reason;
- the API keys are kept in this machine's configuration directory rather than
  beside the code, so a key cannot be committed by accident;
- the dashboard listens on 127.0.0.1 and refuses anything else. It executes
  processes and has no user accounts: anyone who could reach it could spend
  your API credit. To drive it from another machine, forward the port over SSH
  rather than opening it up.

None of this is legal advice, and the obligations depend on where you and your
participants are. It is the list of what the tool does with the data, so that
the assessment can be made on facts.
