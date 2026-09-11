"""Photograph a page of the running dashboard.

Headless Chrome against the same server the browser sees, so what lands in the
guide is the page as it renders, not a mock-up of it.

    python scripts/tutorial/capture.py --url .../participation --out shot.png

`--wait` matters for the pages that compute on load: the narratives page parses
every message before it draws, and a screenshot taken too early shows an empty
frame that looks like a bug in the tool.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

CHROME = ('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
          '/usr/bin/google-chrome', '/usr/bin/chromium')


def chrome() -> str:
    for candidate in CHROME:
        if Path(candidate).exists():
            return candidate
    raise SystemExit('Chrome not found. Set one of: ' + ', '.join(CHROME))


def capture(url: str, out: Path, width=1400, height=1000, wait=4000) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        chrome(), '--headless', '--disable-gpu', '--hide-scrollbars',
        f'--window-size={width},{height}',
        f'--virtual-time-budget={wait}',
        f'--screenshot={out}', url,
    ], check=False, capture_output=True)
    if not out.is_file():
        raise SystemExit(f'Nothing was written to {out}')
    return out


def crop(path: Path, out: Path, top: int, bottom: int) -> Path:
    """Take a band out of a tall capture.

    Three of the guide's figures are three parts of the settings page, and
    shooting it three times at three window heights produces three pictures of
    the same thing cropped at the bottom. Cutting bands out of one tall capture
    shows each section where it actually is.
    """
    from PIL import Image

    out.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(path) as image:
        image.crop((0, top, image.width, min(bottom, image.height))).save(out)
    return out


def crop_tail(path: Path, out: Path, height: int, margin: int = 24) -> Path:
    """The last `height` pixels of a page, from a capture taller than it.

    Headless Chrome photographs the top of a page and cannot be told to
    scroll — an anchor in the URL gave an empty frame — so the sections at
    the foot of a long page are out of reach. A capture taller than the page
    ends in background; this finds where the content stops and keeps the band
    just above it. A capture with no background at its foot was cut short by
    the window, and cropping it would photograph the wrong section, so that
    is refused.
    """
    from PIL import Image

    out.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(path) as image:
        rgb = image.convert('RGB')
        ground = rgb.getpixel((rgb.width - 1, rgb.height - 1))
        last = rgb.height - 1
        while last > 0 and all(rgb.getpixel((x, last)) == ground
                               for x in range(0, rgb.width, 7)):
            last -= 1
        if rgb.height - 1 - last < margin:
            raise SystemExit(f'{path.name}: the page is taller than the '
                             f'{rgb.height}px capture; raise the height.')
        bottom = last + margin
        rgb.crop((0, max(0, bottom - height), rgb.width, bottom)).save(out)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--width', type=int, default=1400)
    parser.add_argument('--height', type=int, default=1000)
    parser.add_argument('--wait', type=int, default=4000,
                        help='milliseconds of virtual time before the shot')
    args = parser.parse_args(argv)
    path = capture(args.url, args.out, args.width, args.height, args.wait)
    print(f'{path}  {path.stat().st_size // 1024} KB')
    return 0


if __name__ == '__main__':
    sys.exit(main())
