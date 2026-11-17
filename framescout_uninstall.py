"""FrameScout uninstall (P5): deletes what the installer and FrameScout create again.

Uninstall-FrameScout.bat runs it with the installer's private Python (.python), never with
the environment's own Python (.venv), which could not delete itself while it runs. The
private Python cannot delete itself either: when it runs the script, the script deletes
everything else and ends with PRIVATE_PYTHON_EXIT_CODE, and the .bat deletes .python (I20).

Deleted after a confirmation: the Python environment (.venv), the private Python (.python),
downloaded model weights and
the pip cache (.cache), temporary files (.tmp, except the evaluation tool's .tmp/eval),
the person detection model and compiled Python files. Never deleted: your photos, reference
images, results (galleries, cache, marks), profiles, settings and run.log, and nothing
outside this folder. Afterwards the folder holds the program files and your data: delete it
yourself to remove FrameScout completely.

  python framescout_uninstall.py             lists, asks, deletes
  python framescout_uninstall.py --dry-run   only lists

Exit code 0 done, cancelled or only listed; 1 refused or failed; PRIVATE_PYTHON_EXIT_CODE
done except the private Python that runs the script.
"""
import argparse
import os
import sys
from pathlib import Path

from framescout_core.app_instance import stale_lock_hint
from framescout_core.cleanup import size_text
from framescout_core.paths import script
from framescout_core.uninstall import (PRIVATE_PYTHON_EXIT_CODE, app_running, protected_folders, remove_items,
                                       running_python, search_running, uninstall_plan, user_data)

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
    """Print (path, label, size) rows; size None leaves the size column out."""
    width = max(len(_name(path, root)) for path, _, _ in rows)
    for path, label, size in rows:
        size = '' if size is None else f'{size_text(size):>8}  '
        out(f'  {_name(path, root):<{width}}  {size}{label}')


def _blocked(root, out):
    """Print why nothing may be deleted now and return True, or return False.

    A program that holds a file open without these locks shows up in the failure list of
    remove_items instead (I44).
    """
    if search_running(root):
        out('A search is running. Stop it (or wait for its end), close FrameScout and run the uninstall again.')
        return True
    if app_running(root):
        out(f'FrameScout is still running. Close the window of {script("Start")}, then run the uninstall again. '
            + stale_lock_hint('run the uninstall again'))
        return True
    return False


def main(argv=None, root=ROOT, ask=input, out=print, interpreter=sys.executable):
    """Run the dialog; interpreter is the Python that runs the script."""
    parser = argparse.ArgumentParser(description='Delete what the FrameScout installer and FrameScout created '
                                     'again (environment, model weights, temporary files); never your data.')
    parser.add_argument('--dry-run', action='store_true', help='only list what would be deleted and kept')
    args = parser.parse_args(argv)
    root = Path(root)
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
    # the private Python that runs this script: deleted by Uninstall-FrameScout.bat afterwards
    last = running_python(items, root, interpreter)
    if items:
        out('Deleted (a new installation downloads or creates them again):')
        _rows([(item.path, f'{item.label} (deleted last, when this script has ended)' if item is last else item.label,
                item.size) for item in items], root, out)
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
        _rows([(path, label, None) for path, label in kept], root, out)
    out('  Also kept: the program files of this folder, your photo folders and copy folders anywhere else.')
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
    if _blocked(root, out):  # FrameScout may have been started while the question waited
        return 1
    now = [item for item in items if item is not last]
    failures = remove_items(now)
    if failures:
        # the private Python stays, so the uninstall can run again
        out(f'{len(failures)} files or folders could not be deleted:')
        for path, exc in failures[:MAX_FAILURES_SHOWN]:
            out(f'  {path}: {exc}')
        if len(failures) > MAX_FAILURES_SHOWN:
            out(f'  … and {len(failures) - MAX_FAILURES_SHOWN} more')
        out('Close FrameScout and other programs that use these files and make sure you may change them '
            '(on Windows: clear a read-only attribute), then run the uninstall again.')
        return 1
    out(f'Done: {size_text(sum(item.size for item in now))} deleted.')
    if last:
        out(f'The private Python ({_name(last.path, root)}, {size_text(last.size)}) runs this script: '
            f'{script("Uninstall")} deletes it when this script has ended.')
    out(f'To remove FrameScout completely, back up the data you want to keep and delete the folder {root}.')
    return PRIVATE_PYTHON_EXIT_CODE if last else 0


if __name__ == '__main__':
    sys.exit(main())
