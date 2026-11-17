"""The uninstall script (P5): what Uninstall-FrameScout.bat deletes and keeps.

It deletes what the installer and FrameScout create again on their own (the Python
environment, downloaded model weights, temporary and compiled files) and never the
user's data: photos, reference images, results, profiles and settings stay, and so does
everything outside the project folder. The private Python of the installer (P5 part C) is
deleted too; when it runs the uninstall, Uninstall-FrameScout.bat deletes it after the
script has ended (I20).
"""
import errno
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .app_instance import AppInstance
from .copying import COPY_FOLDERS_KEY, _inside
from .locks import lock_held
from .portable_python import PRIVATE_PYTHON
from .run_status import RUN_LOCK
from .settings import (LEGACY_PHOTO_FOLDER, SETTINGS_FILE, _read_settings_file, _setting_value, _with_folder_list,
                       default_settings)
from .signature import DEFAULT_YOLO_MODEL


# What a new installation and the next search create again: (path relative to the project
# folder, what it is). Deleted after a confirmation.
UNINSTALL_ITEMS = (
    ('.venv', 'Python environment with PyTorch and the other packages'),
    (PRIVATE_PYTHON, 'private Python'),
    ('.cache', 'downloaded model weights and the pip cache'),
    ('.tmp', 'temporary files'),
    (DEFAULT_YOLO_MODEL, 'person detection model'),
    ('__pycache__', 'compiled Python files'),
    ('framescout_core/__pycache__', 'compiled Python files'),
    ('framescout_scoring/__pycache__', 'compiled Python files'),
    ('framescout_ui/__pycache__', 'compiled Python files'),
    ('tests/__pycache__', 'compiled Python files'),
    ('.pytest_cache', 'test cache'),
)
# entries inside an item that stay: the evaluation tool's collections hold labels the user made
UNINSTALL_KEEP = {'.tmp': ('eval',)}
# the user's data in the project folder: listed as kept, never deleted
USER_DATA = (
    ('photos', 'default photo folder'),
    ('references', 'reference images of your profiles'),
    ('results', 'galleries, the analysis cache and your marks'),
    ('profiles.json', 'your search profiles'),
    ('profiles.json.bak', 'backup of your search profiles'),
    (SETTINGS_FILE, 'your settings'),
    ('run.log', 'log of the last search'),
    ('.tmp/eval', 'collections of the evaluation tool with your labels'),
)
# files deleted before the rest of their folder: without its python.exe (on Linux bin/python
# and bin/python3, F47), an environment or private Python whose removal stopped halfway never
# looks complete, and the installer creates a new one
UNINSTALL_FIRST = {'.venv': ('Scripts/python.exe', 'Scripts/pythonw.exe', 'bin/python'),
                   PRIVATE_PYTHON: ('python.exe', 'pythonw.exe', 'bin/python3')}
# exit code of framescout_uninstall.py when it deleted everything but the private Python it
# runs with: Uninstall-FrameScout.bat deletes that one after the script has ended (I20).
# 0 and 1 are the script's other results, 2 is argparse's usage error.
PRIVATE_PYTHON_EXIT_CODE = 3
# Windows error of removing a folder that is not empty
_ERROR_DIR_NOT_EMPTY = 145


@dataclass(frozen=True)
class UninstallItem:
    """One file or folder to delete. keep: names of entries inside path that stay; first:
    paths inside it deleted before the rest; link: path is a symbolic link or junction, of
    which only the link is removed, never what it points to."""
    path: Path
    label: str
    size: int
    keep: tuple = ()
    first: tuple = ()
    link: bool = False


def _is_link(path):
    return os.path.islink(path) or os.path.isjunction(path)


def _kept(entry, folder, keep):
    """Return True if the directory entry of folder is one of the names in keep.

    Case-insensitive where the file system is (review): a kept name must match the same
    entries as _inside, which decides whether a protected folder is inside a kept entry.
    """
    for name in keep:
        if os.path.normcase(entry.name) == os.path.normcase(name):
            return True
        try:
            if os.path.samefile(entry.path, os.path.join(folder, name)):
                return True
        except OSError:
            continue
    return False


def _entries(folder, keep=()):
    """Return the directory entries of folder that are not in keep; raises OSError."""
    with os.scandir(folder) as listing:
        return [entry for entry in listing if not _kept(entry, folder, keep)]


def _tree_size(path, keep=()):
    """Bytes of the files below path; links and junctions are not followed, keep is skipped."""
    total = 0
    try:
        entries = _entries(path, keep)
    except OSError:
        return 0
    for entry in entries:
        try:
            if entry.is_symlink() or entry.is_junction():
                continue
            if entry.is_dir(follow_symlinks=False):
                total += _tree_size(entry.path)
            else:
                total += entry.stat(follow_symlinks=False).st_size
        except OSError:
            continue
    return total


def _size(path, keep=()):
    if _is_link(path):
        return 0
    if path.is_dir():
        return _tree_size(path, keep)
    try:
        return path.stat().st_size
    except OSError:
        return 0


def protected_folders(root):
    """Return the folders the uninstall must never delete, delete into or delete from: the
    photo folders and the copy target folders of settings.json (the default photo folder
    without one). Relative ones count from root.

    The file is read once, so both lists come from the same version of it (review). Raises
    ValueError or OSError like read_settings if settings.json cannot be read, and ValueError
    if its photo or copy folders are not allowed values (the app would use the default photo
    folder instead, review): the folders are unknown then, so nothing may be deleted.
    """
    root = Path(root)
    data = _with_folder_list(_read_settings_file(root / SETTINGS_FILE))
    if LEGACY_PHOTO_FOLDER in data:  # not a string
        raise ValueError(f'"{LEGACY_PHOTO_FOLDER}" is not a folder: {data[LEGACY_PHOTO_FOLDER]!r}')
    photo_folders = default_settings(root)['photo_folders']
    if 'photo_folders' in data:
        photo_folders = _setting_value('photo_folders', data['photo_folders'])
        if photo_folders is None:
            raise ValueError(f'"photo_folders" is not a list of folders: {data["photo_folders"]!r}')
    copy_folders = data.get(COPY_FOLDERS_KEY, {})
    if not isinstance(copy_folders, dict) or not all(isinstance(x, str) for x in copy_folders.values()):
        raise ValueError(f'"{COPY_FOLDERS_KEY}" is not a list of folders per profile: {copy_folders!r}')
    folders = [Path(x).expanduser() for x in photo_folders]
    folders += [Path(x.strip()).expanduser() for x in copy_folders.values() if x.strip()]
    return [root / x if not x.is_absolute() else x for x in folders]


def uninstall_plan(root, protected):
    """Return (items, skipped): the UninstallItems that exist below root, and (path, reason)
    for each that is not deleted because one of the protected folders is inside it (outside
    its kept entries) or holds it (e.g. a photo folder that is root or a folder above it)."""
    root = Path(root)
    items, skipped = [], []
    for relative, label in UNINSTALL_ITEMS:
        path = root / relative
        if not os.path.lexists(path):
            continue
        link = _is_link(path)
        keep = () if link else UNINSTALL_KEEP.get(relative, ())
        # the folder the item is in: for a link, never what it points to
        around = [folder for folder in protected if _inside(path.parent, folder)]
        if around:
            skipped.append((path, f'is inside the folder {around[0]} of your settings'))
            continue
        if keep and path.is_dir():
            try:
                rest = _entries(path, keep)
            except OSError as exc:  # what it holds besides the kept entries is unknown (review)
                skipped.append((path, f'cannot be listed ({exc})'))
                continue
            if not rest:
                continue  # only kept entries: nothing to delete
        if not link:
            inside = [folder for folder in protected if _inside(folder, path)
                      and not any(_inside(folder, path / name) for name in keep)]
            if inside:
                skipped.append((path, f'contains the folder {inside[0]} of your settings'))
                continue
        if keep:
            label = f'{label} (except {", ".join(str(Path(relative, name)) for name in keep)})'
        if link:
            label = f'{label} (a link: only the link is removed, not what it points to)'
        first = () if link else UNINSTALL_FIRST.get(relative, ())
        items.append(UninstallItem(path, label, _size(path, keep), keep, first, link))
    return items, skipped


def running_python(items, root, interpreter):
    """Return the item of the private Python (PRIVATE_PYTHON) if interpreter, the Python
    that runs the uninstall, is inside it; else None.

    Windows does not delete a running program, so the uninstall leaves it to
    Uninstall-FrameScout.bat, which deletes it after the script has ended (I20). A link is
    removed by the script itself: that leaves the running Python where the link points to.
    """
    folder = Path(root) / PRIVATE_PYTHON
    for item in items:
        if item.path == folder and not item.link and _inside(interpreter, folder):
            return item
    return None


def user_data(root):
    """Return (path, what it is) of the user's data that exists below root.

    Without sizes: photos/ and results/ may hold many thousands of files, and walking them
    would delay the question for what is never deleted anyway (review).
    """
    root = Path(root)
    return [(root / relative, label) for relative, label in USER_DATA if os.path.lexists(root / relative)]


def search_running(root):
    """Return True if a search holds the run lock of the app's results folder."""
    return lock_held(Path(root) / 'results' / RUN_LOCK)


def app_running(root):
    """Return True if an app started with the start script of root holds its start lock (F47)."""
    return AppInstance(root).running()


def _not_empty(exc):
    return exc.errno == errno.ENOTEMPTY or getattr(exc, 'winerror', None) == _ERROR_DIR_NOT_EMPTY


def _remove_file(path, failures):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError as exc:  # e.g. in use or read-only: reported, not retried (I44)
        failures.append((Path(path), exc))


def _remove_tree(path, failures):
    start = len(failures)

    def handle(function, name, exc):
        if isinstance(exc, FileNotFoundError):
            return
        if function is os.rmdir and _not_empty(exc) and any(
                Path(name) in failed.parents for failed, _ in failures[start:]):
            return  # what is left inside it failed and is reported already (review)
        failures.append((Path(name), exc))
    # shutil.rmtree removes links and junctions inside the tree without following them
    shutil.rmtree(path, onexc=handle)


def _remove_link(path, failures):
    try:
        if os.path.isjunction(path) or (os.path.islink(path) and os.path.isdir(path)):
            os.rmdir(path)
        else:
            os.unlink(path)
    except OSError as exc:
        failures.append((Path(path), exc))


def remove_items(items):
    """Delete the items; return a list of (path, error) of what could not be deleted.

    Deleting goes on after a failure. An item's first entries go before the rest of it.
    """
    failures = []
    for item in items:
        path = item.path
        if item.link:
            _remove_link(path, failures)
        elif not path.is_dir():
            _remove_file(path, failures)
        elif item.keep:
            try:
                entries = _entries(path, item.keep)
            except OSError as exc:  # the other items are still deleted (review)
                failures.append((path, exc))
                continue
            for entry in entries:
                try:
                    link = entry.is_symlink() or entry.is_junction()
                    folder = not link and entry.is_dir(follow_symlinks=False)
                except OSError as exc:
                    failures.append((Path(entry.path), exc))
                    continue
                if link:
                    _remove_link(entry.path, failures)
                elif folder:
                    _remove_tree(entry.path, failures)
                else:
                    _remove_file(entry.path, failures)
            try:
                path.rmdir()  # only if nothing was kept
            except OSError:
                pass
        else:
            for relative in item.first:
                if (path / relative).is_file():
                    _remove_file(path / relative, failures)
            _remove_tree(path, failures)
    return failures
