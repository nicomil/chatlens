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
| The rubric and the topics (paid) | the `llm` and `topics` extras | small |

For reference, the commands are these. Replace the URL with wherever you
installed from.

```bash
# the words and the comparison
uv tool install --reinstall "chatlens[words] @ git+https://github.com/nicomil/chatlens.git"

# the relations: three steps, and all three are needed
uv tool install --reinstall "chatlens[narratives] @ git+https://github.com/nicomil/chatlens.git"
chatlens install-relatio                       # clones and installs RELATIO
# then the language model, into the same environment — the command is on the screen

# everything at once
uv tool install --reinstall "chatlens[all] @ git+https://github.com/nicomil/chatlens.git"
```

`chatlens install-relatio` and `chatlens install-topicgpt` clone their
repositories into this machine's application data directory and install them.
Neither is a dependency, because neither should arrive because somebody opened
a page: RELATIO brings torch and transformers, and TopicGPT's prompt files are
part of its method and are not inside its published package.

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
