# Installation

One command, the same on macOS, Windows and Linux:

```bash
uv tool install git+https://github.com/nicomil/chatlens.git
```

Not on PyPI yet, so it installs from the repository — the command is the same
shape and does the same thing.

[uv](https://docs.astral.sh/uv/) is a single binary and installs Python itself
if the machine has none, which is why this works on a Windows laptop with
nothing set up. If uv is not there yet:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell
# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

`pipx` and a plain `pip install` into a virtual environment of your own work the
same way, with the same URL.

This installs what the deterministic measures and the dashboard need — about
four megabytes, one dependency. The optional stages ask for more, and each is
its own extra so that nothing large arrives unasked:

```bash
uv tool install "git+https://github.com/nicomil/chatlens.git#egg=chatlens[all]"
```

| Extra | Adds | Roughly |
|---|---|---|
| `llm` | the validation rubric | small |
| `topics` | TopicGPT (plus `chatlens install-topicgpt`) | small |
| `words` | the word clouds, the coefficient tables and the comparison page | 150 MB |
| `narratives` | the relational analysis | 500 MB with the model |
| `all` | all four | |

Every page that needs one says so, with the command already written out for the
interpreter chatlens is running under. That last part matters: chatlens lives in
an environment of its own, so a `pip install` typed into a shell installs
somewhere else and the page goes on reporting the same thing missing.

Check it arrived:

```bash
chatlens --help
chatlens status        # run inside the folder holding your data
```

### Only if you need the topics

TopicGPT is installed separately, because the prompt files are part of the
method and **are not inside the published package**; release 0.2.7 on PyPI also
imports vLLM at the top level, a dependency that does not install on macOS
without a GPU, whereas the `main` branch has already made it optional.

```bash
chatlens install-topicgpt
```

It clones the official repository into this machine's application data
directory and installs it, then checks that the prompt files really arrived.
With `--repo <path>` you choose where it goes; to point the analysis at a copy
you already have, set `CHATLENS_TOPICGPT_REPO=<path>` or pass
`--topicgpt-repo <path>`.

### Working on the code rather than using it

```bash
git clone https://github.com/nicomil/chatlens.git
cd chatlens
make setup      # editable install in .venv/, every extra included
make test
```

On Windows, where `make` is absent:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -e ".[llm,topics]"
.venv\Scripts\python tests\test_merge.py
```

### Optional extras

The tool itself is about four megabytes and has one dependency. Everything that
needs a large library is an extra, absent until asked for, and the page that
needs it says so with the exact command rather than failing.

| Extra | Adds | Roughly |
|---|---|---|
| `llm` | the validation rubric | small |
| `topics` | TopicGPT (plus `chatlens install-topicgpt`) | small |
| `words` | word clouds and the coefficient tables | 150 MB |

```bash
uv tool install --reinstall "chatlens[words]"
```

**`--reinstall`, not `--force`.** An extra added to an existing installation
needs the environment rebuilt, and `--force` alone will not rebuild one that uv
considers current.

The commands the pages print are built from the interpreter chatlens is actually
running under. That matters more than it sounds: chatlens normally lives in its
own environment, so a `pip install` typed into a shell installs somewhere else
and the page goes on reporting the same thing missing.

### The narratives extra

```bash
uv tool install --reinstall "chatlens[narratives]"
python -m spacy download en_core_web_md
```

Two commands, because a language model is a separate package from the library
that loads it: `pip install spacy` succeeds and leaves the page just as broken.
The page prints both, each naming this installation's own interpreter.

RELATIO comes with it, as a command rather than a dependency:

```bash
chatlens install-relatio
```

A command because it pulls torch and transformers — about 1.6 GB against the
four megabytes chatlens takes — and nobody should download that by opening a
page. It is cloned into this machine's application data directory, not into the
checkout, for the same reason TopicGPT is. From the repository rather than PyPI,
where the release fails to build.

**The narratives page does not work without it, on purpose.** The extraction is
RELATIO's method: it parses the sentences, clusters the phrases that are not
declared entities, and chooses how many clusters to use. Approximating that
would produce numbers nobody could attribute to the paper, so the page waits for
the package instead.

If it is installed but cannot be imported, the page says why rather than
failing quietly. The usual cause is `transformers` refusing to load beside
Keras 3, which `pip install tf-keras` resolves.
