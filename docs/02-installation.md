# Installation

One command, the same on macOS, Windows and Linux:

```bash
uv tool install chatlens
```

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

`pipx install chatlens` works just as well if you already use pipx, and so does
`pip install chatlens` inside a virtual environment of your own.

This installs what the deterministic measures and the dashboard need. The
optional stages ask for more:

```bash
uv tool install "chatlens[llm]"      # + the validation rubric
uv tool install "chatlens[all]"      # + everything
```

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
