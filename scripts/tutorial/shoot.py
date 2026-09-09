"""Photograph every page of the walkthrough, in order.

The guide is only worth having if its pictures are of the tool as it is, so
they are taken from a running dashboard rather than drawn. Re-running this after
a change to the interface refreshes every figure at once, which is the whole
reason it is a script and not a morning of screenshots.

    python scripts/tutorial/shoot.py --token abc123 --out docs/images

The dashboard has to be up, on a library prepared by `prepare.py` and then
taken through the setup in the browser. `--token` is the key printed when it
started.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capture import capture, crop  # noqa: E402

# (file, page, height, wait in ms, band, caption). A band crops the capture,
# for pages where one section is the subject and the rest is context.
SHOTS = [
    ('02-library-created', '/__library__', 760, 2500, None,
     'the experiment made, saying what is still missing'),
    ('11-run-done', '', 1000, 3000, None,
     'the run finished, archived, with the report beside it'),
    ('12-report', '/report.html', 1200, 3000, None,
     'the readable summary the run produces'),
    ('20-participation', '/participation', 880, 6000, None,
     'the whole grid, including the pairs that never spoke'),
    ('30-words', '/words?penalty=0.1&min_df=10&ngrams=both', 1300, 20000, None,
     'the clouds, with length beside the model'),
    ('31-words-strict', '/words?penalty=0.02&min_df=10&ngrams=both', 900,
     20000, None, 'the same page with the penalty tightened'),
    ('32-words-loose', '/words?penalty=1.0&min_df=10&ngrams=both', 900, 20000,
     None, 'and loosened'),
    ('40-narratives', '/narratives', 1400, 40000, None,
     'the relations, and which of them matter'),
    ('50-emotions', '/emotions', 1150, 5000, None,
     'the coverage, and what a zero means'),
    ('60-compare', '/compare', 980, 25000, None,
     'every representation against the same outcome'),
]

# Bands of the settings page, cut from one tall capture of it.
# The empty library cannot be photographed from this instance — by the time the
# walk is done there is an experiment in it. `capture.py` takes that one against
# a throwaway library on another port.
SETTINGS = [
    ('03-settings-files', 60, 470, 'the uploaded files and their roles'),
    ('04-settings-columns', 440, 950,
     'the column mapping, read from the file header'),
    ('05-settings-treatments', 930, 1180,
     'the treatments, named from the values found'),
    ('06-settings-outcome', 1180, 1620,
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
        if page == '/__library__' or page == '/__empty__':
            url = f'{base}/?t={args.token}'
        elif page:
            joiner = '&' if '?' in page else '?'
            url = (f'{base}/experiment/{args.experiment}{page}'
                   f'{joiner}t={args.token}')
        else:
            url = f'{base}/experiment/{args.experiment}?t={args.token}'
        out = args.out / f'{name}.png'
        capture(url, out, args.width, height, wait)
        print(f'  {name:22s} {out.stat().st_size // 1024:4d} KB   {caption}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
