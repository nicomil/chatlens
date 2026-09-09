"""Photograph every page of the walkthrough, in order.

The guide is only worth having if its pictures are of the tool as it is, so
they are taken from a running dashboard rather than drawn. Re-running this after
a change to the interface refreshes every figure at once, which is the whole
reason it is a script and not a morning of screenshots.

    python scripts/tutorial/shoot.py --token abc123 --out docs/images

The dashboard has to be up, on a library prepared by `prepare.py` and walked
through by `walk.py`. `--token` is the key printed when it started.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capture import capture, crop  # noqa: E402

# (file, page, height, wait in ms, caption). A `band` crops the capture, for
# the pages where one section is the subject and the rest is context.
SHOTS = [
    ('01-library', '', 880, 3000, None,
     'the library, with the experiment made'),
    ('05-run', '', 900, 3000, None,
     'the run finished, with the report beside it'),
    ('06-participation', '/participation', 860, 5000, None,
     'who spoke to whom, including the pairs that never did'),
    ('07-words', '/words', 1280, 15000, None,
     'the clouds and the coefficient table'),
    ('08-narratives', '/narratives', 1360, 30000, None,
     'the relations, and which of them matter'),
    ('09-emotions', '/emotions', 700, 4000, None,
     'the lexicon notice, which is what a new install shows'),
    ('10-compare', '/compare', 940, 20000, None,
     'every representation against the same outcome'),
]

# Bands of the settings page, cut from one tall capture of it.
SETTINGS = [
    ('02-settings-files', 60, 470, 'the uploaded files and their roles'),
    ('03-settings-columns', 440, 940,
     'the column mapping, guessed from the file'),
    ('04-settings-outcome', 1180, 1620,
     'the outcome: which column, of what kind, at which unit'),
]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--token', required=True)
    parser.add_argument('--experiment', default='ultimatum-with-pre-play-chat')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--out', type=Path, default=Path('docs/images'))
    parser.add_argument('--width', type=int, default=1400)
    args = parser.parse_args(argv)

    base = f'http://127.0.0.1:{args.port}'
    settings_url = (f'{base}/experiment/{args.experiment}/settings'
                    f'?t={args.token}')
    tall = capture(settings_url, args.out / '_settings-full.png',
                   args.width, 1700, 4000)
    for name, top, bottom, caption in SETTINGS:
        out = crop(tall, args.out / f'{name}.png', top, bottom)
        print(f'  {name:22s} {out.stat().st_size // 1024:4d} KB   {caption}')
    tall.unlink()

    for name, page, height, wait, _band, caption in SHOTS:
        url = (f'{base}/experiment/{args.experiment}{page}?t={args.token}'
               if page else
               f'{base}/experiment/{args.experiment}?t={args.token}')
        if name == '01-library':
            url = f'{base}/?t={args.token}'
        out = args.out / f'{name}.png'
        capture(url, out, args.width, height, wait)
        print(f'  {name:22s} {out.stat().st_size // 1024:4d} KB   {caption}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
