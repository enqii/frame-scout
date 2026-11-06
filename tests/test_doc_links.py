"""Relative links in the Markdown files of the repository point to existing files (I31).

I31 moved files out of the root folder (requirements/, assets/, docs/): a link that still
names an old place would only show up as a dead link on GitHub. Web links and anchors within
the same page are not checked.
"""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# [text](target) with an optional "title"; images too
LINK = re.compile(r'\]\(\s*<?([^)\s>]+)>?(?:\s+"[^"]*")?\s*\)')
# a reference definition "[label]: target" at the start of a line (review)
REFERENCE = re.compile(r'^ {0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?', re.MULTILINE)
# local folders that are not part of the repository (.gitignore) and git's own folder;
# agent worktrees are whole other checkouts
SKIPPED = {'.git', '.venv', '.python', '.cache', '.tmp', '.pytest_cache', '__pycache__', 'photos', 'references',
           'results'}
WORKTREES = ROOT / '.claude' / 'worktrees'


def markdown_files(root=ROOT):
    """The Markdown files in every folder of the repository, without the SKIPPED local folders (review)."""
    files = []
    for folder, subfolders, names in os.walk(root):
        subfolders[:] = [name for name in subfolders if name not in SKIPPED and Path(folder, name) != WORKTREES]
        files += [Path(folder, name) for name in names if name.lower().endswith('.md')]
    return sorted(files)


def relative_links(text):
    """The link targets of text without web links (scheme:) and anchors of the same page."""
    targets = LINK.findall(text) + REFERENCE.findall(text)
    return [target for target in targets if not re.match(r'[A-Za-z][A-Za-z0-9+.-]*:|#', target)]


def test_relative_links_are_found():
    text = ('[a](docs/BACKLOG.md) [b](https://example.com) [c](#anchor) [d](../x.md#part) '
            '![e](assets/p.png "title") [f](mailto:x@example.com)\n'
            '[g]: requirements/constraints.txt\n  [h]: <docs/x.md> "title"\n[i]: https://example.com\n'
            'text [j]: not/a/definition.md\n')
    assert relative_links(text) == ['docs/BACKLOG.md', '../x.md#part', 'assets/p.png',
                                    'requirements/constraints.txt', 'docs/x.md']


def test_markdown_files_of_every_folder_are_found_but_not_local_ones(tmp_path):
    for path in ('README.md', 'tests/notes.md', 'assets/a.MD', '.venv/lib/x.md', 'results/r.md', 'docs/b.txt'):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text('x', encoding='utf-8')
    found = sorted(path.relative_to(tmp_path).as_posix() for path in markdown_files(tmp_path))
    assert found ==['README.md', 'assets/a.MD', 'tests/notes.md']


def test_every_relative_link_points_to_an_existing_file():
    files = markdown_files()
    assert ROOT / 'README.md' in files and ROOT / 'docs' / 'BACKLOG.md' in files
    assert not any(WORKTREES in path.parents for path in files)
    broken = []
    for path in files:
        for target in relative_links(path.read_text(encoding='utf-8')):
            if not (path.parent / target.split('#', 1)[0]).exists():
                broken.append(f'{path.relative_to(ROOT).as_posix()}: {target}')
    assert broken == []
