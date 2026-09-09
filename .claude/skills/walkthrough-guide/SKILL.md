---
name: walkthrough-guide
description: "Rebuild GUIDE.md, the illustrated chatlens manual: run the whole procedure in a real browser on synthetic data, screenshot every page, and regenerate the docs page and the PDF. Use when the interface has changed, when a figure is stale, or when asked for a tutorial or manual with screenshots."
risk: low
source: local
---

# Rebuilding the guide

The guide is `GUIDE.md` at the repository root — its own document, not a section
of the README, because it has its own structure and its own figures and the
README's numbered-section machinery would cut it into pieces that mean nothing
apart. `make docs` copies it into `docs/` and puts it in the navigation, and
`scripts/tutorial/pdf.py` turns it into a PDF for sending to somebody.

It has eight parts, and the order is the point: what the tool is for, what it
can do, installing it, setting up a study, running it, each page in detail, one
complete session from empty library to answer, and where the files live. Its figures are screenshots of the tool
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

**Say when a figure is not the real thing.** The emotions page needs a lexicon
that cannot be shipped; the figure uses a stand-in word list so the page has
something to draw, and the caption says so. A screenshot that quietly shows
invented numbers is worse than no screenshot.

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

Fifteen figures: the empty library, the experiment made, four bands of the
settings page, the finished run, the report, and each analysis page — with the
words page shot three times at three penalties, because the point of that
control is what changes when it moves.

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

### 4. Regenerate the page and the PDF

Edit `GUIDE.md`, never `docs/guide.md` — that is a copy, and `make docs` clears
the folder and remakes it. Then:

```bash
make docs
python scripts/tutorial/pdf.py --out chatlens-guide.pdf
```

`docs/images/` survives `make docs`; everything else in `docs/` does not.

The PDF is built by a small converter in `pdf.py` rather than a markdown
library: it handles headings, paragraphs, code, images, tables, lists, links and
block quotes, which is the whole of what the guide uses. If a construct comes
out as raw pipes or brackets in the PDF, that is the converter missing a case
and not something to work around in the prose.

The contents list is dropped on the way to PDF — anchor links do nothing in a
printed document.

## When a step fails

That is the useful part. Three defects have been found this way and none of them
had a failing test, because each sat in a seam the tests exercise separately.
Fix the tool rather than working around it in the guide: a walk-through that has
to avoid a broken step is documenting a broken tool.
