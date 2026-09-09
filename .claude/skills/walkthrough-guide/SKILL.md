---
name: walkthrough-guide
description: "Rebuild the chatlens walk-through guide: run the whole procedure in a real browser on synthetic data, screenshot each step, and regenerate the illustrated section of the README and its PDF. Use when the interface has changed, when a figure is stale, or when asked for a tutorial with screenshots."
risk: low
source: local
---

# Rebuilding the walk-through

The guide is section 8 of `README.md`, published as a page of the docs site, and
also as a PDF for sending to somebody. Its figures are screenshots of the tool
actually running, which is the only kind worth having and the only kind that
goes stale — a guide with pictures of an interface that has since changed is
worse than one with none.

So the whole thing is rebuilt by running it again. Four steps, three scripts.

## The rules that make it worth doing

**Synthetic data, always.** A guide is a document that gets forwarded.
Screenshots of a real study carry participant identifiers and the things people
said to each other into every copy of it. `chatlens demo` writes a study from a
fixed seed that belongs to nobody, and `prepare.py` uses only that.

**Walk it, do not stage it.** The point is that the procedure works. Create the
experiment, upload the files, map the columns, declare the outcome, press run —
in the interface, in that order. Every time this has been done it has found
something that the tests could not: a missing text column, an outcome column
that read as non-binary, a page that assumed the wrong unit.

**Photograph what is there.** Including the screens that report something
missing. The emotions page without its lexicon is what a new installation shows,
and a guide that hides it leaves the reader to meet it alone.

## The four steps

### 1. Prepare a clean library

```bash
python scripts/tutorial/prepare.py --library /tmp/chatlens-tutorial
```

Writes the demo study *beside* the library, not inside it — a workspace inside
the library is already an experiment, and the guide opens by making one.

### 2. Walk the procedure

Start the dashboard on that library and go through it:

```bash
chatlens dashboard --library /tmp/chatlens-tutorial
```

Create *Ultimatum with pre-play chat*, one message per row. Then, under
Settings: upload `messages.csv` and `roster.csv`, give them the roles `messages`
and `participants`, confirm the column mapping, name the treatments, and set the
outcome to `accepted`, binary, one row per person. Then run **Measures only**.

Finally set the narrative entities to `i, you, we` on the Narratives page.

Clicks on native `<select>` elements are unreliable under automation. Driving the
same forms with `curl` against the running server reaches the same state, and
what matters is that the screenshot is of the real page. The cookie is
`chatlens_session`, and a write also needs `Origin` and `Sec-Fetch-Site:
same-origin`.

### 3. Photograph every page

```bash
python scripts/tutorial/shoot.py --token <the key the dashboard printed> \
    --out docs/images
```

Headless Chrome against the same server, so what lands in the guide is the page
as it renders. Heights are per page and the settings figures are bands cut from
one tall capture — three shots of the same page at three window heights are
three pictures of the same thing.

`--wait` matters: the narratives page parses every message before it draws, and
a shot taken too early shows an empty frame that reads as a bug.

### 4. Regenerate the text and the PDF

The prose lives in `README.md` under `## 8. A walk through, with pictures`. Edit
it there, never in `docs/` — that folder is cleared and rebuilt from the README.
Then:

```bash
make docs
python scripts/tutorial/pdf.py --out chatlens-walkthrough.pdf
```

`docs/images/` survives `make docs`; everything else in `docs/` does not.

## When a step fails

That is the useful part. Three defects have been found this way and none of them
had a failing test, because each sat in a seam the tests exercise separately.
Fix the tool rather than working around it in the guide: a walk-through that has
to avoid a broken step is documenting a broken tool.
