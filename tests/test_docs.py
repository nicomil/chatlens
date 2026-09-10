"""The documentation is read in two places, and has to work in both.

On GitHub the README sits above a `handbook/` folder and a `docs/images/`
folder. On the site every page is a sibling and neither folder exists, because
`scripts/build_docs.py` flattens them. A link is correct in one rendering and
broken in the other unless something checks both — and for a while nothing
did: the guide's thirteen screenshots resolved on the site and were thirteen
empty boxes on GitHub for as long as the repository was public.

Nothing here needs the network. A link to an address on the internet is not
this suite's business; a link to a file in this repository is.

    python tests/test_docs.py
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import build_docs  # noqa: E402

# `](target)` or `](target#anchor)`, which covers images too — `![alt](path)`
# ends the same way, and a missing screenshot is a broken link.
LINK = re.compile(r'\]\(([^)#\s]*)(#[^)\s]*)?\)')

# Headings, for the anchors that point at them.
HEADING = re.compile(r'^#{1,6}\s+(.*?)\s*$', re.MULTILINE)


def sources() -> list:
    """The files a person edits."""
    found = [ROOT / 'README.md', ROOT / 'GUIDE.md', ROOT / 'CONTRIBUTING.md']
    return [p for p in found if p.is_file()] + sorted(
        (ROOT / 'handbook').glob('*.md'))


def generated() -> list:
    return sorted((ROOT / 'docs').glob('*.md'))


def anchor(heading: str) -> str:
    """What GitHub and mkdocs both make of a heading.

    They agree on everything this repository does: lowercase, punctuation
    dropped, spaces to hyphens. Where they would disagree — HTML in a heading,
    two headings with the same text — the answer here is to not write that.
    """
    text = heading.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    return re.sub(r'[\s_]+', '-', text).strip('-')


def anchors_of(path: Path) -> set:
    return {anchor(h) for h in HEADING.findall(path.read_text(encoding='utf-8'))}


def links_of(path: Path):
    """(target, anchor) for every link that points inside the repository."""
    for match in LINK.finditer(path.read_text(encoding='utf-8')):
        target, fragment = match.group(1), (match.group(2) or '')[1:]
        if target.startswith(('http://', 'https://', 'mailto:')):
            continue
        yield target, fragment


class LinksResolveTests(unittest.TestCase):
    """Both renderings, because a link can only be checked against one."""

    def assert_links_resolve(self, paths):
        broken = []
        for path in paths:
            for target, fragment in links_of(path):
                where = path.relative_to(ROOT)
                if not target:
                    # `](#anchor)` — a heading on this same page.
                    if fragment and fragment not in anchors_of(path):
                        broken.append(f'{where} -> #{fragment}')
                    continue
                destination = (path.parent / target).resolve()
                if not destination.exists():
                    broken.append(f'{where} -> {target}')
                elif fragment and destination.suffix == '.md':
                    if fragment not in anchors_of(destination):
                        broken.append(f'{where} -> {target}#{fragment}')
        self.assertEqual(broken, [], f'{len(broken)} broken: {broken}')

    def test_on_github_where_the_handbook_is_a_folder(self):
        self.assert_links_resolve(sources())

    def test_on_the_site_where_every_page_is_a_sibling(self):
        """`scripts/build_docs.py` flattens the paths; this is the check that
        it flattened all of them."""
        self.assert_links_resolve(generated())


class ImagesTests(unittest.TestCase):
    def test_every_screenshot_the_guide_shows_is_there(self):
        """They were written as if the guide lived beside them. It does on the
        site and does not on GitHub, and nothing said so."""
        guide = ROOT / 'GUIDE.md'
        shown = [t for t, _f in links_of(guide) if t.endswith('.png')]
        self.assertTrue(shown, 'the guide shows no screenshots at all')
        for target in shown:
            self.assertTrue((guide.parent / target).is_file(), target)

    def test_the_site_keeps_them_too(self):
        page = ROOT / 'docs' / 'guide.md'
        if not page.is_file():
            self.skipTest('the site has not been built')
        for target, _fragment in links_of(page):
            if target.endswith('.png'):
                self.assertTrue((page.parent / target).is_file(), target)


class EveryPageReachableTests(unittest.TestCase):
    """A page nobody links to and the navigation does not list is a page that
    exists and is never read."""

    def test_the_builder_knows_every_handbook_page(self):
        on_disk = {p.stem for p in (ROOT / 'handbook').glob('*.md')}
        declared = {name for name, _title in build_docs.PAGES}
        self.assertEqual(on_disk, declared)

    def test_the_readme_links_to_every_handbook_page(self):
        readme = ROOT / 'README.md'
        linked = {Path(t).stem for t, _f in links_of(readme)
                  if t.startswith('handbook/')}
        self.assertEqual({p.stem for p in (ROOT / 'handbook').glob('*.md')},
                         linked)

    def test_the_navigation_lists_what_was_built(self):
        config = (ROOT / 'mkdocs.yml').read_text(encoding='utf-8')
        listed = set(re.findall(r'^  - .*: ([a-z0-9-]+\.md)$', config,
                                re.MULTILINE))
        self.assertEqual({p.name for p in generated()}, listed)


class GeneratedIsCurrentTests(unittest.TestCase):
    """`docs/` is committed, so it can be stale. CI regenerates and diffs;
    this catches it before the push rather than after."""

    def test_every_source_has_a_page(self):
        expected = {'index.md', 'guide.md'} | {
            f'{name}.md' for name, _title in build_docs.PAGES}
        self.assertEqual({p.name for p in generated()}, expected)

    def test_the_pages_match_the_sources(self):
        pairs = [(ROOT / 'README.md', ROOT / 'docs' / 'index.md'),
                 (ROOT / 'GUIDE.md', ROOT / 'docs' / 'guide.md')]
        pairs += [(ROOT / 'handbook' / f'{name}.md',
                   ROOT / 'docs' / f'{name}.md')
                  for name, _title in build_docs.PAGES]
        stale = [str(page.relative_to(ROOT)) for source, page in pairs
                 if page.is_file()
                 and page.read_text(encoding='utf-8')
                 != build_docs.flatten_links(source.read_text(encoding='utf-8'))]
        self.assertEqual(stale, [],
                         'run scripts/build_docs.py and commit: ' + str(stale))


if __name__ == '__main__':
    unittest.main(verbosity=2)
