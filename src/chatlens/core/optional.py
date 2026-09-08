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


def install_command(extra: str, packages) -> str:
    """The command that installs into *this* interpreter, whatever it is.

    Two shapes, because the two installations are not the same operation. A uv
    tool owns its environment and is changed by reinstalling it with the extra
    named — and `--force` alone is not enough, since it will not rebuild an
    environment it considers current. Anywhere else, pip and the package names.
    """
    if 'uv/tools/chatlens' in sys.executable.replace('\\', '/'):
        tool = shutil.which('uv') or 'uv'
        return f'{tool} tool install --reinstall "chatlens[{extra}]"'
    return f'{sys.executable} -m pip install {" ".join(packages)}'


def model_command(name: str) -> str:
    return f'{sys.executable} -m spacy download {name}'


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
