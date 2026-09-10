"""Features that need dependencies the tool does not install by itself.

chatlens has one dependency and takes about four megabytes. Word clouds need
scikit-learn and matplotlib; the relational analysis needs spaCy, a language
model and possibly sentence-transformers. Those are between a hundred and
sixteen hundred megabytes, and nobody should download them because they opened
a page.

So they are declared as extras, absent until asked for, and the pages that need
them say so instead of failing. What the page shows has to be enough to act on,
which means three things this module supplies.

**The command names the right interpreter.** This is the trap worth the most
care. chatlens is normally installed as a `uv` tool, so it lives in its own
environment; a user who reads "pip install scikit-learn" and runs it in their
shell installs into a different Python entirely, and the page goes on saying the
dependency is missing with no clue why. Every command here is built from
``sys.executable``.

**Each missing piece is named separately.** A language model is not the library
that loads it, and `pip install spacy` succeeds while leaving the page just as
broken. Three absences, three commands.

**The size is stated.** Not to discourage anyone, but because starting a 1.6 GB
download unknowingly, on conference wifi, is a bad afternoon.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path


def have(module: str) -> bool:
    """Is the module importable, without paying to import it?

    `find_spec` answers from the filesystem. Actually importing scikit-learn
    costs a second or more, and a page that checks four dependencies to decide
    what to render would spend that on every load.
    """
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def have_spacy_model(name: str) -> bool:
    """A spaCy language model is a package, so the same check applies."""
    return have(name)


def _is_uv_tool() -> bool:
    """True when this copy lives in an environment uv manages as a tool.

    uv writes `uv-receipt.toml` at the root of one, which is a fact about the
    environment rather than a guess about its path — the path can be moved with
    `UV_TOOL_DIR`, and on a machine where it has been, matching on the default
    layout tells the reader to run the wrong command.
    """
    # `sys.prefix`, not the executable's folder: the interpreter inside a
    # uv environment is a symlink to the one uv keeps elsewhere, and
    # resolving it walks straight out of the environment being asked about.
    return (Path(sys.prefix) / 'uv-receipt.toml').is_file()


def installed_from() -> str:
    """Where this copy was installed from, as pip and uv record it.

    PEP 610 has the installer write `direct_url.json` beside the metadata when
    a package came from anywhere but an index. It is the only place that knows,
    and it has to be asked: chatlens is not on PyPI, so a reinstall command
    naming the project alone resolves against an index that has never heard of
    it and fails with "no versions of chatlens".
    """
    import json
    from importlib.metadata import PackageNotFoundError, distribution

    try:
        raw = distribution('chatlens').read_text('direct_url.json')
    except (PackageNotFoundError, OSError):
        return ''
    try:
        info = json.loads(raw or '')
    except ValueError:
        return ''

    url = info.get('url') or ''
    vcs_info = info.get('vcs_info') or {}
    if vcs_info.get('vcs'):
        source = f'{vcs_info["vcs"]}+{url}'
        revision = vcs_info.get('requested_revision')
        return f'{source}@{revision}' if revision else source
    return url


def install_command(extra: str, packages) -> str:
    """The command that installs into *this* interpreter, whatever it is.

    Two shapes, because the two installations are not the same operation. A uv
    tool owns its environment and is changed by reinstalling it with the extra
    named — and `--force` alone is not enough, since it will not rebuild an
    environment it considers current. Anywhere else, pip and the package names.
    """
    if _is_uv_tool():
        tool = shutil.which('uv') or 'uv'
        source = installed_from()
        spec = f'chatlens[{extra}] @ {source}' if source else f'chatlens[{extra}]'
        return f'{tool} tool install --reinstall "{spec}"'
    return f'{sys.executable} -m pip install {" ".join(packages)}'


def pip_argv(*arguments) -> list[str]:
    """How to install something into *this* environment, as a command to run.

    Not always `-m pip`. A uv tool environment is a virtual environment like
    any other, but uv does not put pip in it — `python -m pip install` there
    answers *No module named pip*, and so does anything that shells out to pip,
    which is how a spaCy model arrives. uv installs into it perfectly well when
    told which interpreter to use, so that is the route when uv is what put
    this environment here.
    """
    if _is_uv_tool():
        tool = shutil.which('uv')
        if tool:
            return [tool, 'pip', 'install', '--python', sys.executable,
                    *arguments]
    return [sys.executable, '-m', 'pip', 'install', *arguments]


def model_command(name: str) -> str:
    """The command that puts a spaCy language model in this environment.

    Ours rather than spaCy's, which is the exception to the rule above. The
    others are one call to an installer and can be written out in full;
    `spacy download` reads spaCy's compatibility table to pick the build that
    matches the spaCy actually installed — worth keeping — but it does the
    fetching through pip, which a uv tool environment has not got. Getting one
    in first is a second command, and a second command is a thing to get wrong
    on a page whose whole purpose is to be copied without thinking.
    """
    return f'chatlens install-model {name}'


class Requirement:
    """One thing that may be missing, and exactly how to get it."""

    def __init__(self, module, label, command, size='', note=''):
        self.module = module
        self.label = label
        self.command = command
        self.size = size
        self.note = note

    @property
    def present(self) -> bool:
        return have(self.module)


def report(requirements) -> dict:
    """What is here, what is not, and what to run for each thing that is not."""
    missing = [r for r in requirements if not r.present]
    return {
        'ready': not missing,
        'missing': missing,
        'present': [r for r in requirements if r.present],
    }
