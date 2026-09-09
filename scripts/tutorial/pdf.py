"""Turn the walk-through into a PDF, for sending to somebody.

The guide lives in the README and is published as a page of the site, which is
where it belongs — it stays true because the same scripts regenerate it. But a
supervisor asked by email for something to read is not going to be sent a URL to
a site that may not be up yet, so the same text also becomes a file.

    python scripts/tutorial/pdf.py --out chatlens-walkthrough.pdf

Markdown to HTML by hand rather than by library: the subset used here is
headings, paragraphs, code fences, images and lists, and a dependency that
converts a hundred things to convert five is a dependency to explain later.
"""

from __future__ import annotations

import argparse
import base64
import html
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STYLE = """
@page { size: A4; margin: 16mm 14mm; }
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  margin: 0; background: #fff; color: #16181d;
  font-family: "IBM Plex Sans", system-ui, -apple-system, sans-serif;
  font-size: 15px; line-height: 1.6;
}
.wrap { max-width: 46rem; margin: 0 auto; padding: 1rem 0 3rem; }
h1 { font-family: Newsreader, Georgia, serif; font-size: 2.3rem;
     font-weight: 600; line-height: 1.15; margin: 0 0 .4rem; }
h2 { font-family: Newsreader, Georgia, serif; font-size: 1.45rem;
     font-weight: 600; margin: 2rem 0 .3rem; break-after: avoid; }
h3 { font-size: 1.02rem; font-weight: 600; margin: 1.6rem 0 .3rem;
     break-after: avoid; }
p { margin: 0 0 .8rem; max-width: 64ch; }
strong { font-weight: 600; }
em { font-style: italic; }
code { font-family: "IBM Plex Mono", ui-monospace, Menlo, monospace;
       font-size: .86em; background: #f3f4f8; border: 1px solid #e1e3ec;
       border-radius: 4px; padding: .05em .32em; }
pre { background: #f3f4f8; border: 1px solid #e1e3ec; border-radius: 8px;
      padding: .7rem .9rem; overflow-x: auto; break-inside: avoid;
      margin: 0 0 1rem; }
pre code { background: none; border: 0; padding: 0; font-size: .84em; }
figure { margin: 1rem 0 1.4rem; break-inside: avoid; }
img { width: 100%; height: auto; border: 1px solid #e1e3ec; border-radius: 8px; }
.lead { font-family: Newsreader, Georgia, serif; font-size: 1.18rem;
        line-height: 1.5; color: #4a5060; margin-bottom: 1.6rem; }
.meta { font-size: .8rem; color: #6b7183; border-top: 1px solid #e1e3ec;
        padding-top: .6rem; margin-bottom: 2rem; }
"""


def section(readme: str, number: int) -> tuple:
    """The numbered section, without its heading line."""
    match = re.search(rf'^## {number}\. (.+?)$', readme, flags=re.M)
    if not match:
        raise SystemExit(f'No section {number} in the README.')
    start = match.end()
    nxt = re.search(r'^## \d+\. ', readme[start:], flags=re.M)
    end = start + (nxt.start() if nxt else len(readme) - start)
    return match.group(1), readme[start:end].strip()


def inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', text)
    return text


def to_html(body: str, images: Path) -> str:
    out, lines, i = [], body.splitlines(), 0
    paragraph = []

    def flush():
        if paragraph:
            out.append(f'<p>{inline(" ".join(paragraph))}</p>')
            paragraph.clear()

    while i < len(lines):
        line = lines[i]
        if line.startswith('```'):
            flush()
            i += 1
            code = []
            while i < len(lines) and not lines[i].startswith('```'):
                code.append(lines[i])
                i += 1
            out.append(f'<pre><code>{html.escape(chr(10).join(code))}'
                       f'</code></pre>')
        elif line.startswith('!['):
            flush()
            match = re.match(r'!\[(.*?)\]\((.*?)\)', line)
            if match:
                path = images / Path(match.group(2)).name
                data = base64.b64encode(path.read_bytes()).decode()
                out.append(f'<figure><img alt="{html.escape(match.group(1))}" '
                           f'src="data:image/png;base64,{data}"></figure>')
        elif line.startswith('### '):
            flush()
            out.append(f'<h3>{inline(line[4:])}</h3>')
        elif line.startswith('## '):
            flush()
            out.append(f'<h2>{inline(line[3:])}</h2>')
        elif not line.strip():
            flush()
        else:
            paragraph.append(line.strip())
        i += 1
    flush()
    return '\n'.join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--section', type=int, default=8)
    parser.add_argument('--out', type=Path,
                        default=Path('chatlens-walkthrough.pdf'))
    args = parser.parse_args(argv)

    title, body = section((ROOT / 'README.md').read_text(encoding='utf-8'),
                          args.section)
    lead, _, rest = body.partition('\n\n')
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,600&amp;family=IBM+Plex+Mono:wght@400&amp;family=IBM+Plex+Sans:wght@400;600&amp;display=swap">
<style>{STYLE}</style></head><body><div class="wrap">
<h1>chatlens — {html.escape(title)}</h1>
<p class="lead">{inline(lead)}</p>
<div class="meta">Every figure is a screenshot of the running tool, on a
synthetic study generated by <code>chatlens demo</code>. Nobody's data.</div>
{to_html(rest, ROOT / 'docs' / 'images')}
</div></body></html>'''

    source = args.out.with_suffix('.html')
    source.write_text(page, encoding='utf-8')
    chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    subprocess.run([chrome, '--headless', '--disable-gpu',
                    '--no-pdf-header-footer', '--virtual-time-budget=20000',
                    f'--print-to-pdf={args.out.resolve()}',
                    f'file://{source.resolve()}'], capture_output=True)
    if not args.out.is_file():
        raise SystemExit('Chrome wrote no PDF.')
    print(f'  {args.out}  {args.out.stat().st_size // 1024} KB')
    return 0


if __name__ == '__main__':
    sys.exit(main())
