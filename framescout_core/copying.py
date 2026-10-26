"""Copying marked photos to a folder and the saved target folders (A17)."""
import filecmp
import os
import re
import shutil
from pathlib import Path

from ._common import _path_key, _publish_new, _publish_via_temp, _update_locked
from .settings import SETTINGS_LOCK_TIMEOUT, _read_settings_file


# Copying the photos marked as matches (A17): copies only, never moving or deleting an
# original and never overwriting a file in the target folder; flat, one folder per profile.
# The target folders the user typed are saved per profile in settings.json under this key.
COPY_FOLDERS_KEY = 'copy_folders'
# names tried for one copy (name.jpg, name (2).jpg, ...) before it fails
COPY_MAX_NAMES = 10000


def default_copy_folder(pictures, slug):
    """Return the target folder offered for a profile: <Pictures>/FrameScout/<slug>.

    Outside the project folder, so removing FrameScout never removes the copies.
    """
    return Path(pictures) / 'FrameScout' / slug


def _inside(path, folder):
    """Return True if path is folder or inside it (resolved, case-insensitive where the OS is)."""
    a, b = _path_key(Path(path)), _path_key(Path(folder))
    try:
        return os.path.commonpath([a, b]) == b
    except ValueError:  # e.g. different drives
        return False


def copy_target(text, photo_folders, photos=()):
    """Return (target folder, None) for the text of the target field, or (None, why it is refused).

    Refused: an empty field, a path that is not complete (it would depend on the app's
    working directory), a file, and a folder in one of photo_folders (empty entries are
    ignored): the copies would be analyzed again by the next search and appear twice.
    Likewise a folder in the folder of one of photos, the photos to copy: marked in an
    earlier search, they may come from another photo folder (review; its root is unknown,
    so only the photo's own folder is covered).
    """
    text = (text or '').strip()
    if not text:
        return None, 'Enter a target folder.'
    target = Path(text).expanduser()
    if not target.is_absolute():
        return None, f'Enter a complete path for the target folder, e.g. {Path.home() / "Pictures"}.'
    if target.exists() and not target.is_dir():
        return None, f'{target} is a file, not a folder.'
    for folder in photo_folders:
        if folder and _inside(target, Path(folder).expanduser()):
            return None, (f'{target} is inside the photo folder {folder}. FrameScout does not copy there: the next '
                          'search would analyze the copies again and show every photo twice. Choose a folder '
                          'outside the photo folder.')
    for folder in sorted({str(Path(x).parent) for x in photos}):
        if _inside(target, folder):
            return None, (f'{target} is inside {folder}, which holds photos you marked. FrameScout does not copy '
                          'there: a search of that folder would analyze the copies again and show every photo '
                          'twice. Choose a folder outside your photo folders.')
    return target, None


def _copy_candidates(source, target):
    """The names a copy of source may get in target: name.jpg, name (2).jpg, name (3).jpg, ..."""
    yield target / source.name
    n = 2
    while True:
        yield target / f'{source.stem} ({n}){source.suffix}'
        n += 1


def _copy_one(source, target):
    """Copy source into target; return 'copied', 'renamed' or 'already'. Raises OSError."""
    if not source.is_file():
        raise FileNotFoundError('the photo no longer exists')
    # an earlier copy under any of its names, also behind a gap in the numbering (review)
    flags = re.IGNORECASE if os.name == 'nt' else 0
    names = re.compile(re.escape(source.stem) + r'(?: \([0-9]+\))?' + re.escape(source.suffix), flags)
    with os.scandir(target) as entries:
        earlier = [Path(e.path) for e in entries if names.fullmatch(e.name)]
    if any(x.is_file() and filecmp.cmp(source, x, shallow=False) for x in earlier):
        return 'already'
    for index, candidate in enumerate(_copy_candidates(source, target)):
        if index >= COPY_MAX_NAMES:
            raise FileExistsError(f'no free name for {source.name} in {target}')
        if os.path.lexists(candidate):  # also a dangling symbolic link
            continue  # another file or a folder of that name: the next name
        try:
            # a complete file under the final name or none; never replaces anything that
            # took the name meanwhile, and every name is tried once (review: no endless loop)
            _publish_via_temp(candidate, lambda tmp: shutil.copy2(source, tmp), _publish_new)
        except FileExistsError:
            continue
        return 'copied' if index == 0 else 'renamed'


def copy_photos(paths, target, progress=None):
    """Copy the photos paths flat into the folder target (created if needed) and return a summary.

    {'copied': n, 'already': n, 'renamed': n, 'failed': [(path, reason), ...]}. A copy keeps
    the file date (shutil.copy2). A file of the same name and content in target counts as
    already there (also one named "name (n).jpg" by an earlier copy); the same name with
    other content gets the next free "name (n).jpg". A photo that cannot be copied fails
    on its own. progress(done, total) is called after each photo (the app shows it, and a
    rerun of the app stops the copy there, review). Raises OSError if target cannot be
    created.
    """
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    summary = {'copied': 0, 'already': 0, 'renamed': 0, 'failed': []}
    paths = list(paths)
    for done, path in enumerate(paths, 1):
        try:
            summary[_copy_one(Path(path), target)] += 1
        except OSError as exc:
            summary['failed'].append((str(path), exc.strerror or str(exc)))
        if progress:
            progress(done, len(paths))
    return summary


def copy_summary_text(summary):
    """Return e.g. "20 copied · 2 already there · 1 renamed · 0 failed" for a copy_photos summary."""
    return (f"{summary['copied']} copied · {summary['already']} already there · {summary['renamed']} renamed · "
            f"{len(summary['failed'])} failed")


def _copy_folders(data):
    folders = data.get(COPY_FOLDERS_KEY)
    if not isinstance(folders, dict):
        return {}
    return {k: v for k, v in folders.items() if isinstance(k, str) and isinstance(v, str) and v.strip()}


def read_copy_folders(filename, attempts=5, retry_delay=0.05):
    """Return {profile name: target folder} saved in the app's settings file ({} if none).

    Invalid entries are ignored; raises like read_settings for an unreadable file.
    """
    return _copy_folders(_read_settings_file(filename, attempts, retry_delay))


def _update_copy_folders(filename, change, attempts, retry_delay, lock_timeout):
    """Change the saved target folders with change(folders) under the settings lock (see save_settings)."""
    filename = Path(filename)

    def update(document):
        before = _copy_folders(document)
        folders = change(dict(before))
        if folders == before and document.get(COPY_FOLDERS_KEY, {}) == before:
            return None
        if folders:
            document[COPY_FOLDERS_KEY] = folders
        else:
            document.pop(COPY_FOLDERS_KEY, None)
        return document if document or filename.exists() else None

    _update_locked(filename, lambda: _read_settings_file(filename, attempts, retry_delay), update,
                   attempts, retry_delay, lock_timeout)


def save_copy_folder(filename, profile, folder, default, attempts=5, retry_delay=0.05,
                     lock_timeout=SETTINGS_LOCK_TIMEOUT):
    """Save the target folder of profile in the app's settings file; the default folder is not stored.

    Merged into the file as it is now, like save_settings; the other settings are kept.
    Raises ValueError for an unreadable file (never replaced) and OSError like save_settings.
    """
    folder = str(folder).strip()

    def change(folders):
        if not folder or folder == str(default):
            folders.pop(profile, None)
        else:
            folders[profile] = folder
        return folders

    _update_copy_folders(filename, change, attempts, retry_delay, lock_timeout)


def rename_copy_folder(filename, old, new, attempts=5, retry_delay=0.05, lock_timeout=SETTINGS_LOCK_TIMEOUT):
    """Give the saved target folder of the profile old to its new name new (nothing if none is saved)."""
    def change(folders):
        if old != new and old in folders:
            folders[new] = folders.pop(old)
        return folders

    _update_copy_folders(filename, change, attempts, retry_delay, lock_timeout)
