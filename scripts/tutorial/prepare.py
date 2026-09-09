"""Set up a clean library with synthetic data, ready for the walkthrough.

Everything the tutorial shows has to be reproducible, which means the starting
state cannot be somebody's laptop. This writes a fresh library, generates the
demo study into it, and stops — the tutorial's whole point is that the next
steps happen in the browser.

**Synthetic data, always.** A guide is a document that gets forwarded, and
screenshots of a real study would carry participant identifiers and the things
people actually said to each other into every copy of it. The demo study is
generated from a fixed seed and belongs to nobody.

    python scripts/tutorial/prepare.py --library /tmp/chatlens-tutorial
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))


def main(argv=None) -> int:
    from chatlens.core import demo, library

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--library', type=Path,
                        default=Path('/tmp/chatlens-tutorial'))
    parser.add_argument('--name', default='Ultimatum with pre-play chat')
    args = parser.parse_args(argv)

    if args.library.exists():
        shutil.rmtree(args.library)
    args.library.mkdir(parents=True)

    # Beside the library, never inside it. `demo.create` writes a workspace, and
    # a workspace inside the library *is* an experiment — the guide would open
    # on one already made, and the first thing it means to show is making one.
    source = args.library.parent / f'{args.library.name}-source'
    if source.exists():
        shutil.rmtree(source)
    made = demo.create(source)

    library.use_library(args.library)
    print(f'Library     {args.library}')
    print(f'Study       {made["n_groups"]} groups, {made["n_participants"]} '
          f'participants, {made["n_messages"]} messages — generated from a '
          f'fixed seed, nobody real')
    print(f'Files to upload:')
    for path in sorted((source / 'input').glob('*.csv')):
        print(f'  {path}')
    print()
    print('Nothing else is set up: the experiment is created, the files are')
    print('uploaded and the columns are mapped through the interface, because')
    print('that is what the guide is about.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
