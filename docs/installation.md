# Installation

### The two commands

```bash
uv tool install git+https://github.com/nicomil/chatlens.git
chatlens dashboard
```

The second one opens your browser on the dashboard and prints the address it is
serving. That is the whole of it: no database, no server to configure, nothing
listening to the outside world.

Identical on macOS, Windows and Linux. Not on PyPI yet, so it installs from the
repository — the command is the same shape and does the same thing.

### If uv is not there yet

[uv](https://docs.astral.sh/uv/) is a single binary, and it **installs Python
itself** if the machine has none. That is why the two commands above work on a
laptop with nothing set up.

```bash
# macOS and Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell
# Windows, in PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

If `chatlens` is not found afterwards, uv has put it somewhere not on your
PATH; it says so when it installs, and `uv tool update-shell` fixes it. Open a
new terminal after that.

`pipx`, or a plain `pip install` into a virtual environment of your own, work
the same way with the same URL.

### What works straight away, and what asks for more

The base install is about four megabytes and one dependency. With it you get
the conversations, who wrote to whom, the language measures and the report —
everything that does not fit a model.

Three findings ask for more, and **each one tells you on its own screen exactly
what to run**, with the command already written for the environment chatlens is
installed in. That last part matters: chatlens lives in an environment of its
own, so a `pip install` typed into a shell installs somewhere else and the
screen goes on reporting the same thing missing. Copy the command from the
screen and it will be right.

| Finding | Needs | Roughly |
|---|---|---|
| The words, Which representation to trust | scikit-learn, matplotlib, wordcloud | 150 MB |
| The relations | spaCy + a language model + statsmodels + RELATIO | 1.6 GB |
| The emotions | the NRC Emotion Lexicon | 4 MB |
| The topics (paid) | the `topics` extra + TopicGPT + an OpenAI key | small |
| The validation rubric (paid) | the `llm` extra + an OpenAI or Anthropic key | small |
| The `.dta` files of `chatlens tables` | the `stata` extra (pandas) | 130 MB |

For reference, here is every one of them written out. Replace the URL with
wherever you installed from; if you used pip rather than uv, the shape is
`pip install "chatlens[words]"` and the rest is the same.

```bash
# ── the words, and the comparison between representations ──
uv tool install --reinstall "chatlens[words] @ git+https://github.com/nicomil/chatlens.git"

# ── the relations: three steps, and all three are needed ──
uv tool install --reinstall "chatlens[narratives] @ git+https://github.com/nicomil/chatlens.git"
chatlens install-model                 # the spaCy language model, 33 MB
chatlens install-relatio               # clones and installs RELATIO, 1.6 GB

# ── the topics: two steps, then a key ──
uv tool install --reinstall "chatlens[topics] @ git+https://github.com/nicomil/chatlens.git"
chatlens install-topicgpt              # clones TopicGPT for its prompt files
chatlens keys                          # OPENAI_API_KEY, guided

# ── the validation rubric: an extra and a key ──
uv tool install --reinstall "chatlens[llm] @ git+https://github.com/nicomil/chatlens.git"
chatlens keys                          # OpenAI or Anthropic, either will do

# ── a Stata .dta beside each CSV of `chatlens tables` ──
uv tool install --reinstall "chatlens[stata] @ git+https://github.com/nicomil/chatlens.git"

# ── every library at once, if you would rather not choose ──
# still leaves the three that are not libraries: the model, RELATIO, TopicGPT
uv tool install --reinstall "chatlens[all] @ git+https://github.com/nicomil/chatlens.git"
```

**The `chatlens install-…` commands exist because these three are not
libraries.** `install-model` fetches the spaCy language model, which is a
package but is published outside PyPI and has to match the spaCy installed
beside it. `install-relatio` clones RELATIO and installs it from source,
because its published release cannot build under a modern setuptools, and
because torch and transformers should not arrive on anyone's laptop for opening
a page. `install-topicgpt` clones TopicGPT for the prompt files, which are part
of the method and are not inside its published package. The two clones go to
this machine's application data directory, and the commands find them there
without being told.

Each one is safe to run twice: it says what is already present and stops.

The two paid findings also want a key, and only those two. See
[[api keys, and what they cost](keys-and-costs.md), API keys](keys-and-costs.md) — `chatlens keys` asks for them, verifies them with
one real call rather than a listing, and writes them outside any repository.

### The emotion lexicon

The NRC Emotion Lexicon is free for research and distributed through a request
form, so it cannot be shipped with anything. The emotions screen says where to
get it and where to put it; there are three ways in, and any of them works:

- **ask for it** at [saifmohammad.com](https://saifmohammad.com/WebPages/NRC-Emotion-Lexicon.htm)
  — the word-level file;
- **export it from R**, if you have R: `textdata` downloads the same lexicon
  under the same licence, and the two-column table `tidytext::get_sentiments("nrc")`
  writes is read as it is;
- **point at a copy you already have** with `CHATLENS_NRC_LEXICON`.

The distributed form, the wide form with a column per category, and a
`tidytext` export are all read without conversion.

### It does not matter where you run it from

Neither command cares about the folder you are standing in. `uv tool install`
puts chatlens in an environment of its own and on your PATH, and `chatlens
dashboard` opens the library of studies, which lives in the application data
directory below — not in the current directory. Run both from wherever your
terminal happens to open.

The current directory matters only for the command-line pipeline —
`chatlens all` and its siblings — which treats it as the workspace and expects
an `input/` folder in it. The dashboard does not use it: a study created there
gets its own folder in the library, and `--workspace <path>` points the command
line at one of those, or at any folder of your own.

### Where things end up

Nothing is written beside the package. The studies, the lexicon and the cloned
repositories live in this machine's application data directory:

| | |
|---|---|
| macOS | `~/Library/Application Support/chatlens/` |
| Windows | `%LOCALAPPDATA%\chatlens\` |
| Linux | `~/.local/share/chatlens/` |

The API keys are the exception and are kept apart, in the configuration
directory (`%APPDATA%\chatlens\` on Windows), so that copying a study to a
colleague cannot carry them along. `--library <path>` moves the studies
somewhere else; the dashboard prints where it is reading from when it starts.

### Check it arrived

```bash
chatlens --help
chatlens status        # run inside a folder holding your data
chatlens demo my-first-study   # writes a synthetic study and analyses it
```

The demo needs no key, costs nothing, and belongs to nobody: it is the fastest
way to see whether the installation works and what the output looks like.

### Working on the code rather than using it

```bash
git clone https://github.com/nicomil/chatlens.git
cd chatlens
make setup      # editable install in .venv/, every extra included
make test
```
