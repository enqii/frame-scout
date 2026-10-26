"""FrameScout uninstall (P5): deletes what the installer and FrameScout create again.

Uninstall-FrameScout.bat runs it with the Python that created the environment, never with
the environment's own Python (.venv), which could not delete itself while it runs.

Deleted after a confirmation: the Python environment (.venv), downloaded model weights and
the pip cache (.cache), temporary files (.tmp, except the evaluation tool's .tmp/eval),
the person detection model and compiled Python files. Never deleted: your photos, reference
images, results (galleries, cache, marks), profiles, settings and run.log, and nothing
outside this folder; caches that model downloads may have left in your user profile are
only listed. Afterwards the folder holds the program files and your data: delete it
yourself to remove FrameScout completely.

  python framescout_uninstall.py             lists, asks, deletes
  python framescout_uninstall.py --dry-run   only lists
"""
import argparse
import os
import sys
from pathlib import Path

from framescout_core import (outside_leftovers, programs_in_use, protected_folders, remove_items, search_running,
                             size_text, uninstall_plan, user_data)

ROOT = Path(__file__).resolve().parent
# failed paths shown; the rest is counted
MAX_FAILURES_SHOWN = 10
CONFIRMATION = 'yes'


def _name(path, root):
    """The path relative to root (absolute outside it), a folder with a trailing separator."""
    try:
        name = str(path.relative_to(root))
    except ValueError:
        return str(path)
    return name + os.sep if path.is_dir() and not path.is_symlink() else name


def _rows(rows, root, out):
    width = max(len(_name(path, root)) for path, _, _ in rows)
    for path, label, size in rows:
        out(f'  {_name(path, root):<{width}}  {size_text(size):>8}  {label}')


def _blocked(root, out, confirmed=False):
    """Print why nothing may be deleted now and return True, or return False. confirmed: the
    user agreed to the deletion, so a read-only environment Python may be made writable to
    check it."""
    if search_running(root):
        out('A search is running. Stop it (or wait for its end), close FrameScout and run the uninstall again.')
        return True
    busy = programs_in_use(root, clear_read_only=confirmed)
    if busy:
        out(f'FrameScout is still running ({busy[0]} is in use). Close the Start-FrameScout window and any '
            'other program that uses this Python environment, then run the uninstall again. If FrameScout is '
            'closed, another program (e.g. a virus scanner) has the file open: try again in a moment.')
        return True
    return False


def main(argv=None, root=ROOT, environ=os.environ, home=None, ask=input, out=print):
    parser = argparse.ArgumentParser(description='Delete what the FrameScout installer and FrameScout created '
                                     'again (environment, model weights, temporary files); never your data.')
    parser.add_argument('--dry-run', action='store_true', help='only list what would be deleted and kept')
    args = parser.parse_args(argv)
    root = Path(root)
    home = Path.home() if home is None else Path(home)
    out(f'FrameScout uninstall: {root}')
    out('')
    if _blocked(root, out):
        return 1
    try:
        protected = protected_folders(root)
    except (OSError, ValueError) as exc:
        out(f'settings.json cannot be read ({exc}), so your photo folders are unknown and nothing is deleted. '
            'Fix the file or move it out of this folder, then run the uninstall again.')
        return 1
    items, skipped = uninstall_plan(root, protected)
    if items:
        out('Deleted (a new installation downloads or creates them again):')
        _rows([(item.path, item.label, item.size) for item in items], root, out)
        out(f'  Total: {size_text(sum(item.size for item in items))}')
    elif not skipped:
        out('Nothing to delete: the environment, model weights and temporary files are gone already.')
    for path, reason in skipped:
        out(f'Not deleted: {_name(path, root)} {reason}.')
    if skipped:
        out('The uninstall never deletes a folder that holds one of your photo or copy folders, nor anything '
            'inside one. To delete these '
            'items, remove that folder from the photo folders (or the copy folder of the profile) in the app, or '
            'delete the items yourself.')
    out('')
    kept = user_data(root)
    out('Kept (your data, never deleted by the uninstall):')
    if kept:
        _rows(kept, root, out)
    out('  Also kept: the program files of this folder, your photo folders and copy folders anywhere else.')
    leftovers = outside_leftovers(root, environ, home)
    if leftovers:
        out('')
        out('Outside this folder, not deleted: runs without the FrameScout .bat files may have stored model '
            'weights or settings here. Other programs may use them too; delete them yourself if nothing else '
            'needs them:')
        _rows(leftovers, root, out)
    out('')
    if not items:
        out(f'To remove FrameScout completely, back up the data you want to keep and delete the folder {root}.')
        return 1 if skipped else 0
    if args.dry_run:
        out('Dry run: nothing was deleted.')
        return 0
    try:
        answer = ask(f'Delete the items listed under "Deleted"? Type {CONFIRMATION} and press Enter '
                     '(anything else cancels): ')
    except EOFError:
        answer = ''
    if answer.strip().lower() != CONFIRMATION:
        out('Cancelled: nothing was deleted.')
        return 0
    if _blocked(root, out, confirmed=True):  # FrameScout may have been started while the question waited
        return 1
    failures = remove_items(items)
    if failures:
        out(f'{len(failures)} files or folders could not be deleted:')
        for path, exc in failures[:MAX_FAILURES_SHOWN]:
            out(f'  {path}: {exc}')
        if len(failures) > MAX_FAILURES_SHOWN:
            out(f'  … and {len(failures) - MAX_FAILURES_SHOWN} more')
        out('Close FrameScout and other programs that use these files, then run the uninstall again.')
        return 1
    out(f'Done: {size_text(sum(item.size for item in items))} deleted.')
    out(f'To remove FrameScout completely, back up the data you want to keep and delete the folder {root}. '
        'Python itself was installed separately and stays.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
