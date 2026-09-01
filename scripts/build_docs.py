"""Generate the documentation site from README.md.

The README is the single source. Keeping a second copy of the same prose under
`docs/` would mean keeping two copies in step, and the one nobody edits is the
one people read.

    python scripts/build_docs.py

It splits the README on its numbered headings, writes one page per section
under `docs/`, and regenerates the navigation in `mkdocs.yml`. Everything it
writes is derived: edit the README, run this, commit both.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / 'README.md'
DOCS = ROOT / 'docs'
MKDOCS = ROOT / 'mkdocs.yml'

SECTION_RE = re.compile(r'^## (\d+)\. (.+)$')


def slug(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    return re.sub(r'[\s-]+', '-', text).strip('-')


def split(markdown: str):
    """The front matter, then one (number, title, body) per section."""
    lines = markdown.splitlines()

    # Everything before the first numbered section is the landing page, minus
    # the table of contents, which the site's navigation replaces.
    first = next(i for i, line in enumerate(lines) if SECTION_RE.match(line))
    front = lines[:first]
    try:
        start = front.index('## Contents')
        end = next(i for i in range(start + 1, len(front))
                   if front[i].startswith('---'))
        front = front[:start] + front[end + 1:]
    except (ValueError, StopIteration):
        pass

    sections, current = [], None
    for line in lines[first:]:
        match = SECTION_RE.match(line)
        if match:
            current = dict(number=int(match.group(1)),
                           title=match.group(2).strip(), body=[])
            sections.append(current)
        elif current is not None:
            current['body'].append(line)

    for section in sections:
        # The horizontal rule that separated sections in one long document is
        # noise once each is a page of its own.
        while section['body'] and section['body'][-1].strip() in ('', '---'):
            section['body'].pop()

    return '\n'.join(front).strip(), sections


def internal_links(text: str, targets: dict) -> str:
    """Rewrite `see §3` and `#3-api-keys` to point at the right page."""
    def by_number(match):
        number = int(match.group(1))
        return f'[§{number}]({targets[number]})' if number in targets else match.group(0)

    text = re.sub(r'§(\d+)', by_number, text)
    for number, path in targets.items():
        text = text.replace(f'](#{number}-', f']({path}#')
    return text


def build() -> int:
    if not README.is_file():
        print(f'{README} not found', file=sys.stderr)
        return 1

    front, sections = split(README.read_text(encoding='utf-8'))
    if not sections:
        print('No numbered section found in the README.', file=sys.stderr)
        return 1

    if DOCS.exists():
        shutil.rmtree(DOCS)
    DOCS.mkdir(parents=True)

    targets = {s['number']: f"{s['number']:02d}-{slug(s['title'])}.md"
               for s in sections}

    (DOCS / 'index.md').write_text(
        internal_links(front, targets) + '\n', encoding='utf-8')

    for section in sections:
        body = '\n'.join(section['body']).strip()
        page = f"# {section['title']}\n\n{internal_links(body, targets)}\n"
        (DOCS / targets[section['number']]).write_text(page, encoding='utf-8')

    # Titles are quoted: "Before analysing: three filters" contains a colon,
    # which YAML would otherwise read as a second mapping key.
    nav = ['nav:', '  - Home: index.md']
    nav += [f'  - "{s["title"]}": {targets[s["number"]]}' for s in sections]

    config = MKDOCS.read_text(encoding='utf-8')
    config = re.sub(r'\nnav:\n(?:  - .*\n)*', '\n' + '\n'.join(nav) + '\n',
                    config)
    MKDOCS.write_text(config, encoding='utf-8')

    print(f'{len(sections) + 1} pages in {DOCS}')
    return 0


if __name__ == '__main__':
    sys.exit(build())
