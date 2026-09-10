"""Packing an experiment into one file, and unpacking it again.

An experiment is already a folder that stands on its own — the configuration,
the input, and everything the analysis produced, including the two things that
cost money: the rubric cache under ``output/cache/`` and TopicGPT's output
under ``output/topicgpt/``. So sharing one is, at bottom, sending a folder.

What this module adds is the judgement about *which* folder, because three
kinds of file in there must not travel and one must not travel silently.

**The pseudonym key never goes.** ``output/.pseudonym_key`` is the one file
that turns the pseudonyms back into Prolific ids. Sending it alongside the data
it protects would undo the protection, and it would be undone by accident, in a
file nobody thought about. It is excluded, and the exclusion is not optional.

**Nor do the keys.** A workspace may hold a ``.env`` with API credentials.

**Nor the archived datasets.** ``output/runs/`` holds a copy of each previous
run, and almost all of its weight is in the datasets: on the study this was
written for, 77 MB of which 77 are the two ``datasets/`` folders. What is left
after those — ``run.json`` and the report — is a few kilobytes and is the part
worth having, because it says what was run and with which options. So the
datasets are left behind and the history is not, and ``--with-runs`` sends the
lot for anyone who wants to re-read an old run's tables.

**And the identifiers travel unless told otherwise.** They are in the input
export: Prolific ids, participant labels, session ids. Between co-authors that
is right — the recipient may need to join the chat back to the payoffs. Outside
that circle it is not, so ``pseudonymise`` rewrites those columns on the way
out, using a key generated for the bundle and then thrown away. Not reversible
by us either, afterwards: that is what makes it worth doing.

The manifest at the root of the archive records what was decided, so that the
person opening it can see whether identifiers were kept, whether the paid
stages are inside, and what the figures were when it left.

Unpacking
---------
A tar archive can name any path it likes, including ``../../.ssh/authorized_keys``
and symlinks pointing outside the tree. Python's own extraction grew a filter
for this in 3.12, which is later than the version this tool supports, so every
member is checked here before anything is written: relative paths only, no
traversal, regular files and directories only. An archive that fails the check
is refused whole rather than partially unpacked.
"""

from __future__ import annotations

import json
import secrets
import tarfile
from datetime import datetime, timezone
from pathlib import Path

MANIFEST = 'chatlens-bundle.json'
SUFFIX = '.chatlens.tar.gz'

# The format the manifest is written in. Read by `inspect` before anything is
# unpacked, so that a future change can be refused with a sentence rather than
# a traceback from the middle of an extraction.
FORMAT = 1

# Never packed, whatever the options. See the module docstring.
NEVER = (
    'output/.pseudonym_key',
    '.env',
    '.pseudonym_key',
)

# Where the archive of previous runs lives, and the part of it that is heavy.
HISTORY = 'output/runs'
HISTORY_BULK = 'datasets'


class BundleError(RuntimeError):
    """The bundle could not be made, or could not be trusted."""


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _excluded(relative: str, with_runs: bool) -> bool:
    if relative in NEVER:
        return True
    # A backup somebody made by hand before replacing the input. Theirs, not
    # part of the experiment, and it doubles the largest folder in it.
    if relative.startswith('input.') and '.bak' in relative:
        return True
    if not with_runs and relative.startswith(HISTORY + '/'):
        # `output/runs/<when>/datasets/...`: the copy of the tables, which the
        # current run has a newer version of at a fixed path.
        parts = relative.split('/')
        return len(parts) > 3 and parts[3] == HISTORY_BULK
    return False


def members_of(folder: Path, with_runs: bool = False) -> list[Path]:
    """Every file that belongs in the bundle, in a stable order."""
    folder = Path(folder)
    found = []
    for path in sorted(folder.rglob('*')):
        if not path.is_file() or path.is_symlink():
            continue
        relative = _relative(path, folder)
        if _excluded(relative, with_runs):
            continue
        found.append(path)
    return found


def _has(folder: Path, relative: str) -> bool:
    path = folder / relative
    return path.is_dir() and any(path.iterdir())


def describe(folder: Path, with_runs: bool = False,
             pseudonymised: bool = False) -> dict:
    """The manifest: what is inside, and what was decided about it."""
    from . import experiment as experiment_module

    folder = Path(folder)
    try:
        loaded = experiment_module.load(folder)
        name, adapter = loaded.name, loaded.adapter
    except Exception:                                  # noqa: BLE001
        name, adapter = folder.name, ''

    files = members_of(folder, with_runs)
    return dict(
        format=FORMAT,
        packed=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        slug=folder.name,
        name=name or folder.name,
        adapter=adapter,
        n_files=len(files),
        bytes=sum(f.stat().st_size for f in files),
        # The two that cost money, named rather than implied: whoever opens
        # this wants to know before deciding whether to re-run anything.
        has_rubric=_has(folder, 'output/cache'),
        has_topics=_has(folder, 'output/topicgpt'),
        has_runs=_has(folder, HISTORY),
        pseudonymised=bool(pseudonymised),
    )


# --- packing ---------------------------------------------------------------


def _pseudonymise_into(folder: Path, staging: Path) -> None:
    """Copy the folder to `staging`, identifier columns rewritten.

    The key is made here and never written down, so the mapping cannot be
    undone afterwards — not by the recipient and not by us. A pseudonym is
    still consistent across every table in the bundle, which is what the
    analysis needs from it.
    """
    import shutil

    from . import privacy, tables

    key = secrets.token_bytes(32)
    for source in members_of(folder, with_runs=True):
        relative = _relative(source, folder)
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() != '.csv':
            shutil.copy2(source, target)
            continue
        rows = tables.read(source)
        if not rows or not any(privacy.is_identifier(c) for c in rows[0]):
            shutil.copy2(source, target)
            continue
        # Rewrites the rows in place and hands back the columns it touched.
        privacy.pseudonymise_rows(rows, key)
        tables.write(target, rows)


def pack(folder, destination=None, with_runs: bool = False,
         pseudonymise: bool = False) -> Path:
    """Write the experiment at `folder` to a single archive. Returns its path."""
    import tempfile

    folder = Path(folder).resolve()
    if not (folder / 'experiment.toml').is_file():
        raise BundleError(
            f'{folder} does not look like an experiment: no experiment.toml.')

    destination = (Path(destination).expanduser() if destination
                   else Path.cwd() / f'{folder.name}{SUFFIX}')
    if destination.is_dir():
        destination = destination / f'{folder.name}{SUFFIX}'
    destination.parent.mkdir(parents=True, exist_ok=True)

    manifest = describe(folder, with_runs, pseudonymise)

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / folder.name
        if pseudonymise:
            _pseudonymise_into(folder, staging)
            source = staging
        else:
            source = folder

        manifest_file = Path(tmp) / MANIFEST
        manifest_file.write_text(json.dumps(manifest, indent=2) + '\n',
                                 encoding='utf-8')

        with tarfile.open(destination, 'w:gz') as archive:
            archive.add(manifest_file, arcname=MANIFEST)
            for path in members_of(source, with_runs):
                archive.add(path,
                            arcname=f'{folder.name}/{_relative(path, source)}')
    return destination


# --- unpacking -------------------------------------------------------------


def _safe_name(name: str) -> bool:
    """Is this member name one we are willing to write to disk?

    Rejects what an attacker would use and what a careless `tar -c /abs/path`
    produces by accident, which look the same from here.
    """
    if not name or name.startswith('/') or name.startswith('\\'):
        return False
    if ':' in name.split('/')[0]:          # a Windows drive letter
        return False
    parts = Path(name).parts
    return '..' not in parts and not any(p.startswith('/') for p in parts)


def inspect(archive_path) -> dict:
    """Read the manifest without unpacking anything."""
    archive_path = Path(archive_path).expanduser()
    if not archive_path.is_file():
        raise BundleError(f'No such file: {archive_path}')
    try:
        with tarfile.open(archive_path, 'r:*') as archive:
            member = archive.extractfile(MANIFEST)
            if member is None:
                raise BundleError(
                    f'{archive_path.name} carries no {MANIFEST}: it was not '
                    f'made by chatlens export.')
            manifest = json.loads(member.read().decode('utf-8'))
    except tarfile.TarError as exc:
        raise BundleError(f'{archive_path.name} is not readable as an '
                          f'archive: {exc}') from None
    except (KeyError, ValueError) as exc:
        raise BundleError(f'{archive_path.name} has an unreadable '
                          f'{MANIFEST}: {exc}') from None

    if int(manifest.get('format', 0)) > FORMAT:
        raise BundleError(
            f'{archive_path.name} was written by a later chatlens '
            f'(format {manifest.get("format")}, this one reads {FORMAT}). '
            f'Upgrade chatlens and open it again.')
    return manifest


def _checked_members(archive: tarfile.TarFile, slug: str) -> list:
    """Every member, verified, or nothing at all."""
    keep = []
    for member in archive.getmembers():
        if member.name == MANIFEST:
            continue
        if not (member.isfile() or member.isdir()):
            raise BundleError(
                f'{member.name} is not a regular file or folder. An experiment '
                f'is made of files; refusing the whole archive.')
        if not _safe_name(member.name):
            raise BundleError(
                f'{member.name} names a path outside the folder it claims to '
                f'be. Refusing the whole archive.')
        parts = Path(member.name).parts
        if not parts or parts[0] != slug:
            raise BundleError(
                f'{member.name} is outside {slug}/, which is the only folder '
                f'this archive says it contains. Refusing it.')
        keep.append(member)
    return keep


def unpack(archive_path, root, name=None) -> Path:
    """Unpack the archive into the library at `root`. Returns the folder.

    Refuses to write over an experiment that is already there: a bundle is
    usually a colleague's copy of work you also have, and the useful failure
    is being told so, not losing yours.
    """
    from . import library

    manifest = inspect(archive_path)
    slug = str(manifest.get('slug') or '')
    if slug != library.slug(slug):
        raise BundleError(f'The archive names a folder chatlens would not '
                          f'make: {slug!r}.')

    wanted = library.slug(name) if name else slug
    if not wanted:
        raise BundleError(f'{name!r} has no letters or digits to name a '
                          f'folder with.')

    root = Path(root).expanduser().resolve()
    target = (root / wanted).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise BundleError(f'Outside the library: {wanted!r}') from None
    if target.exists():
        raise BundleError(
            f'"{wanted}" is already in this library. Rename it, or import '
            f'this one under another name with --name.')

    root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(Path(archive_path).expanduser(), 'r:*') as archive:
        members = _checked_members(archive, slug)
        staging = root / f'.incoming-{wanted}'
        if staging.exists():
            raise BundleError(f'{staging} is in the way: an earlier import '
                              f'stopped half-way. Remove it and try again.')
        try:
            for member in members:
                archive.extract(member, path=staging)
            (staging / slug).rename(target)
        finally:
            _remove(staging)

    if name:
        _rename(target, name)
    return target


def _rename(folder: Path, display: str) -> None:
    """Give the imported study the name it was asked to arrive under.

    Renaming only the folder leaves the library showing two cards with the
    same title, which is the situation `--name` exists to avoid: the name in
    `experiment.toml` is what the interface prints, not the folder.
    """
    from . import experiment as experiment_module

    try:
        loaded = experiment_module.load(folder)
    except Exception:                                  # noqa: BLE001
        return
    loaded.set('experiment', {**loaded.declared.get('experiment', {}),
                              'name': ' '.join(str(display).split())})
    loaded.save(folder / experiment_module.FILENAME)


def _remove(path: Path) -> None:
    import shutil
    shutil.rmtree(path, ignore_errors=True)
