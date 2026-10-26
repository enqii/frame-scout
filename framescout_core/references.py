"""Reference image files: a folder per profile, saving uploads, moving them after a rename (A1)."""
import json
import os
import shutil
from pathlib import Path

from ._common import _path_key, _replace_atomically
from .names import slugify
from .profiles import _backup_path


def reference_folder(refs_root, name, others, base):
    """Return the folder for new reference images of the profile name.

    That is refs_root/<slug>, or <slug>-2, <slug>-3, ... if the folder holds a reference
    image of one of the other profiles (dicts with "reference_images", paths relative to
    base), so two profiles never share a folder (A1). Leftover files that no other
    profile references do not block a folder: write_new_file never overwrites them.
    """
    used = {_path_key((base / ref).parent) for profile in others for ref in profile.get('reference_images', [])}
    slug = slugify(name)
    folder, n = refs_root / slug, 2
    while _path_key(folder) in used:
        folder, n = refs_root / f'{slug}-{n}', n + 1
    return folder


def stage_reference_move(refs, folder, refs_root, base, others):
    """First step of moving a renamed profile's reference images into folder (A1).

    refs: the profile's reference paths (relative to base, as in profiles.json); others:
    the other profiles. Every existing file inside refs_root that is not in folder yet and
    that no other profile references gets an additional name in folder: a hard link, or
    a copy where the file system has none. Its file name is kept if free, otherwise the
    next free reference-<n>; nothing is overwritten and nothing is removed here.

    Returns (new_refs, staged): refs with the new paths (relative to base, POSIX) and the
    (old, new) pairs. Save the profiles with new_refs, then call finish_reference_move;
    if the save fails, call undo_reference_move. Until then the old and the new path both
    exist, so a crash at any point leaves profiles.json pointing to existing files. Files
    outside refs_root, missing files and files of other profiles keep their paths. If
    staging fails, the names created so far are removed and the error is raised.
    """
    root = Path(_path_key(refs_root))
    taken = {_path_key(base / ref) for profile in others for ref in profile.get('reference_images', [])}
    moved, staged, new_refs = {}, [], []
    try:
        for ref in refs:
            old = base / ref
            k = _path_key(old)
            if k not in moved:
                inside = Path(k).is_relative_to(root) and Path(k) != root
                if not inside or k in taken or _path_key(old.parent) == _path_key(folder) or not old.is_file():
                    moved[k] = None  # keeps its path, exactly as written
                else:
                    new = _link_new(old.resolve(), folder)
                    staged.append((old.resolve(), new))
                    # lexically, like the paths the app writes: resolving would leave base
                    # if references/ is a junction or symlink to another place (review)
                    moved[k] = Path(os.path.relpath(new, base)).as_posix()
            new_refs.append(moved[k] or ref)
    except BaseException:
        undo_reference_move(staged)
        raise
    return new_refs, staged


def _link_new(src, folder):
    """Give src an additional name in folder (its own name if free, else reference-<n>)."""
    folder.mkdir(parents=True, exist_ok=True)
    names = [src.name] + [f'reference-{n}{src.suffix.lower()}' for n in range(1, 100000)]
    for name in names:
        dst = folder / name
        try:
            os.link(src, dst)
        except FileExistsError:
            continue
        except OSError:  # no hard links on this file system (e.g. FAT32/exFAT)
            try:
                _copy_new(src, dst)
            except FileExistsError:
                continue
        return dst
    raise FileExistsError(f'No free file name in {folder}')


def _copy_new(src, dst):
    """Copy src to the new file dst (FileExistsError if dst exists; no partial dst is left)."""
    try:
        with open(src, 'rb') as source, open(dst, 'xb') as target:
            shutil.copyfileobj(source, target)
    except FileExistsError:
        raise
    except BaseException:
        dst.unlink(missing_ok=True)
        raise


def finish_reference_move(staged, refs_root):
    """Last step after the profiles were saved: remove the old names of the moved files.

    An old name is removed only while its new name still exists with the same size; an
    old folder inside refs_root is removed only if it is empty afterwards. Returns a list
    of messages for old names that could not be removed (the files are then in both
    places; the saved profile uses the new one).
    """
    problems, folders = [], set()
    for old, new in staged:
        try:
            if new.stat().st_size != old.stat().st_size:
                raise OSError('the new copy differs in size')
            old.unlink()
            folders.add(old.parent)
        except OSError as exc:
            problems.append(f'{old}: {exc}')
    root = _path_key(refs_root)
    for folder in folders:
        if _path_key(folder) != root:
            try:
                folder.rmdir()  # only succeeds if the folder is empty
            except OSError:
                pass
    return problems


def undo_reference_move(staged):
    """Undo stage_reference_move after a failed save: remove only the new names."""
    for _, new in staged:
        try:
            new.unlink(missing_ok=True)
        except OSError:
            pass


def update_backup_references(filename, staged, base):
    """After a move was saved, point the moved reference paths in <filename>.bak to the new names.

    Call it between save_profiles (which wrote the backup with the old paths) and
    finish_reference_move (which removes the old names), so restoring the backup keeps
    working after a rename (review). Only the paths of the moved files (staged, from
    stage_reference_move; relative to base) change; everything else, including other
    top-level keys and their order, stays. The backup is replaced via a flushed temporary
    file, so a crash leaves the old or the new backup, and while the old names still
    exist both point to existing files.

    Returns True if the backup now fits the moved files (also if nothing had to change,
    it is missing or in the v3 format without reference paths) and False if it cannot be
    read, so it is left alone. Raises OSError if rewriting fails: the caller should then
    keep the old names (not call finish_reference_move), so the backup still works.
    """
    if not staged:
        return True
    backup = _backup_path(filename)
    try:
        data = backup.read_bytes()
    except FileNotFoundError:
        return True
    try:
        document = json.loads(data.decode('utf-8-sig'))
    except ValueError:
        return False
    if not isinstance(document, dict):
        return False
    profiles = document.get('profiles') if 'profiles' in document else []  # v3: no paths
    new_paths = {_path_key(old): Path(os.path.relpath(new, base)).as_posix() for old, new in staged}
    changed = False
    for profile in profiles if isinstance(profiles, list) else []:
        refs = profile.get('reference_images') if isinstance(profile, dict) else None
        for i, ref in enumerate(refs if isinstance(refs, list) else []):
            if isinstance(ref, str) and ref.strip():
                new = new_paths.get(_path_key(base / ref))
                if new is not None and new != ref:
                    refs[i], changed = new, True
    if changed:
        _replace_atomically(backup, (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    return True


def write_new_file(folder, stem, suffix, data):
    """Write data to folder/<stem>-<n><suffix> with the smallest free n >= 1; return the path.

    Never overwrites an existing file (exclusive create), so leftover reference images
    (e.g. of a deleted profile, or in a folder shared by profiles before A1) are kept.
    Creates the folder if needed.
    """
    folder.mkdir(parents=True, exist_ok=True)
    n = 1
    while True:
        path = folder / f'{stem}-{n}{suffix}'
        try:
            with open(path, 'xb') as handle:
                handle.write(data)
            return path
        except FileExistsError:
            n += 1
