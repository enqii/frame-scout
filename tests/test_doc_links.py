"""Relative links in the Markdown files of the repository point to existing files (I31).

I31 moved files out of the root folder (requirements/, assets/, docs/): a link that still
names an old place would only show up as a dead link on GitHub. Web links and anchors within
the same page are not checked.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# [text](target) with an optional "title"; images too
LINK = re.compile(r'\]\(\s*<?([^)\s>]+)>?(?:\s+"[^"]*")?\s*\)')


def markdown_files():
    """The Markdown files of the repository: no .venv, .tmp, agent worktrees or other local folders."""
    files = list(ROOT.glob('*.md'))
    for folder in (ROOT / 'docs', ROOT / '.github', ROOT / '.claude' / 'skills'):
        files += folder.rglob('*.md')
    return sorted(files)


def relative_links(text):
    """The link targets of text without web links (scheme:) and anchors of the same page."""
    return [target for target in LINK.findall(text) if not re.match(r'[A-Za-z][A-Za-z0-9+.-]*:|#', target)]


def test_relative_links_are_found():
    text = ('[a](docs/BACKLOG.md) [b](https://example.com) [c](#anchor) [d](../x.md#part) '
            '![e](assets/p.png "title") [f](mailto:x@example.com)')
    assert relative_links(text) == ['docs/BACKLOG.md', '../x.md#part', 'assets/p.png']


def test_every_relative_link_points_to_an_existing_file():
    files = markdown_files()
    assert ROOT / 'README.md' in files and ROOT / 'docs' / 'BACKLOG.md' in files
    broken = []
    for path in files:
        for target in relative_links(path.read_text(encoding='utf-8')):
            if not (path.parent / target.split('#', 1)[0]).exists():
                broken.append(f'{path.relative_to(ROOT).as_posix()}: {target}')
    assert broken == []
