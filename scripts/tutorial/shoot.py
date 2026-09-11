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
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capture import capture, crop_tail  # noqa: E402

# (file, path, height, wait in ms, caption). The paths are the interface's
# own: five steps and a findings area, not the flat pages this list used to
# name.
SHOTS = [
    ('01-library', '/__library__', 620, 2500,
     'the studies on this machine'),
    ('02-step-data', '/step/data', 780, 2500,
     'step 1 — the export, and what each file is'),
    ('03-step-columns', '/step/columns', 900, 2500,
     'step 2 — which column plays which part'),
    ('04-step-outcome', '/step/outcome', 900, 3000,
     'step 3 — what to explain, and what that column holds'),
    ('05-step-run', '/step/run', 1000, 3000,
     'step 4 — what to run, and what the last run produced'),
    ('10-findings', '/findings/compare', 800, 30000,
     'the register, and which representation is worth using'),
    ('11-corpus', '/findings/corpus', 900, 8000,
     'the conversations themselves'),
    ('12-participation', '/findings/participation', 900, 10000,
     'who wrote to whom, including the directions nobody used'),
    ('13-words', '/findings/words?penalty=1.0&min_df=10&ngrams=both', 1100,
     40000, 'the terms, with the penalty as a control'),
    ('14-words-strict', '/findings/words?penalty=0.1&min_df=10&ngrams=both',
     700, 40000, 'the same page with the penalty tightened'),
    ('15-narratives', '/findings/narratives', 1100, 180000,
     'the relations, and which of them survive the correction'),
    ('16-emotions', '/findings/emotions', 760, 6000,
     'the categories, and how much of the corpus could be measured at all'),
    ('17-export', '/findings/export', 1000, 60000,
     'every finding, put together as one page'),
]

# The foot of a long page, which a capture of the window never reaches: shot
# taller than the page, then cropped to the band where the content ends. The
# findings summary of the demo study is about 11,700 pixels.
TAILS = [
    ('18-take-away', '/findings/export', 900, 60000,
     'the tables for Stata and R, and the study itself, to download'),
]
TALL = 24000


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--token', required=True)
    # The study the walkthrough makes on synthetic data; a real one would put
    # participants' words into every copy of the guide.
    parser.add_argument('--experiment', default='ultimatum-with-pre-play-chat')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--out', type=Path, default=Path('docs/images'))
    parser.add_argument('--width', type=int, default=1400)
    args = parser.parse_args(argv)

    base = f'http://127.0.0.1:{args.port}'

    def url_of(page: str) -> str:
        if page == '/__library__':
            return f'{base}/?t={args.token}'
        joiner = '&' if '?' in page else '?'
        return (f'{base}/experiment/{args.experiment}{page}'
                f'{joiner}t={args.token}')

    # Ask for the slow panels once before photographing anything. Each of them
    # answers at once and fills in, and each caches its result — so a shot
    # taken while the first one is still computing photographs a spinner, which
    # in a guide reads as the tool being broken. On the real corpus the
    # relations take about a minute and a half.
    warm = ['/findings/compare/panel', '/findings/narratives/panel',
            '/findings/words/panel?penalty=1.0&min_df=10&ngrams=both',
            '/findings/words/panel?penalty=0.1&min_df=10&ngrams=both']
    print('Warming the slow findings, so that nothing is photographed mid-thought.')
    for path_part in warm:
        started = time.monotonic()
        with urllib.request.urlopen(url_of(path_part), timeout=1800) as answer:
            answer.read()
        print(f'  {path_part.split("?")[0]:38s} '
              f'{time.monotonic() - started:5.1f} s')

    # The settings page used to be one tall capture cut into four bands. It is
    # four screens now, so each is photographed as itself.
    for name, page, height, wait, caption in SHOTS:
        out = args.out / f'{name}.png'
        capture(url_of(page), out, args.width, height, wait)
        print(f'  {name:22s} {out.stat().st_size // 1024:4d} KB   {caption}')

    with tempfile.TemporaryDirectory() as tmp:
        for name, page, height, wait, caption in TAILS:
            tall = capture(url_of(page), Path(tmp) / f'{name}-tall.png',
                           args.width, TALL, wait)
            out = crop_tail(tall, args.out / f'{name}.png', height)
            print(f'  {name:22s} {out.stat().st_size // 1024:4d} KB   '
                  f'{caption}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
