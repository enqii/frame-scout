"""Marks of gallery photos in results/marks.json (A17)."""
from pathlib import Path

from ._common import _read_json_object, _update_locked
from .profiles import require_profile


# Marks (A17, P4 (B)): FrameScout ranks candidates, not certain hits; a mark records what the
# user decided about a photo of a profile's gallery: a match, no match, or still open. Kept
# in MARKS_FILE in the results folder (user decision), per profile name and photo path,
# across later searches; "open" is the absence of a mark. The file is user data: the engine
# never writes it, and a cleanup of the results folder (E7) must never delete it.
MARKS_FILE = 'marks.json'
MARKS_FORMAT = 1
MARK_OPEN, MARK_MATCH, MARK_NO_MATCH = 'open', 'match', 'no-match'
MARK_STATES = (MARK_OPEN, MARK_MATCH, MARK_NO_MATCH)
# seconds save_marks and rename_marks wait for the lock around their read-change-write
MARKS_LOCK_TIMEOUT = 5.0


def _read_marks_document(path, attempts=5, retry_delay=0.05):
    """Return the checked JSON object of the marks file ({'format': ..., 'profiles': {}} if missing)."""
    data = _read_json_object(path, 'marks file', attempts, retry_delay)
    if not data:
        return {'format': MARKS_FORMAT, 'profiles': {}}
    if data.get('format') != MARKS_FORMAT:
        raise ValueError(f'{Path(path).name} is not a FrameScout marks file of format {MARKS_FORMAT}')
    profiles = data.get('profiles')
    if not isinstance(profiles, dict):
        raise ValueError('"profiles" must be a JSON object')
    for name, marks in profiles.items():
        if not isinstance(marks, dict) or any(
                not isinstance(photo, str) or state not in (MARK_MATCH, MARK_NO_MATCH) for photo, state in marks.items()):
            raise ValueError(f'invalid marks of {name!r}: {marks!r}'[:300])
    return data


def read_marks(path, attempts=5, retry_delay=0.05):
    """Return {profile name: {photo path: MARK_MATCH or MARK_NO_MATCH}} of the marks file.

    {} if the file is missing. Raises ValueError for a file that is not a marks file of
    this format or holds an unknown state (such a file is never replaced), and OSError if
    it still cannot be read after attempts tries.
    """
    return _read_marks_document(path, attempts, retry_delay)['profiles']


def save_marks(path, profile, changes, attempts=5, retry_delay=0.05, lock_timeout=MARKS_LOCK_TIMEOUT,
               profiles_file=None):
    """Apply changes ({photo path: state of MARK_STATES}) to the marks of profile; return its marks now.

    MARK_OPEN removes a mark, and a profile without marks is removed from the file. The
    changes are merged into the file as it is now (another tab or session may have marked
    other photos), under a lock like save_settings; the file is replaced atomically and its
    folder is created if needed. Nothing is written if nothing changes. With profiles_file,
    profile must be a profile of that file at the time of the write (require_profile,
    checked under the lock), else UnknownProfileError is raised and nothing is written.
    Raises ValueError for an unknown state and for an unreadable file (never replaced),
    OSError if the lock is not free within lock_timeout seconds or writing keeps failing.
    """
    for photo, state in changes.items():
        if not isinstance(photo, str) or state not in MARK_STATES:
            raise ValueError(f'{photo!r}: {state!r} is not a mark')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)  # for the lock file
    result = {}

    def update(document):
        if profiles_file is not None:
            require_profile(profiles_file, profile)
        profiles = document['profiles']
        marks = dict(profiles.get(profile, {}))
        for photo, state in changes.items():
            if state == MARK_OPEN:
                marks.pop(photo, None)
            else:
                marks[photo] = state
        result.update(marks)
        if marks == profiles.get(profile, {}):
            return None
        if marks:
            profiles[profile] = marks
        else:
            profiles.pop(profile, None)
        return document

    _update_locked(path, lambda: _read_marks_document(path, attempts, retry_delay), update,
                   attempts, retry_delay, lock_timeout)
    return result


def rename_marks(path, old, new, attempts=5, retry_delay=0.05, lock_timeout=MARKS_LOCK_TIMEOUT):
    """Give the marks of the profile old to its new name new; return True if the file changed.

    Marks the name new already has (e.g. of a deleted profile of that name) are kept unless
    old has a mark for the same photo, which wins. Nothing happens without a marks file.
    Raises like save_marks.
    """
    path = Path(path)
    if not path.parent.is_dir():
        return False
    changed = []

    def update(document):
        profiles = document['profiles']
        if old == new or old not in profiles:
            return None
        profiles[new] = {**profiles.get(new, {}), **profiles.pop(old)}
        changed.append(True)
        return document

    _update_locked(path, lambda: _read_marks_document(path, attempts, retry_delay), update,
                   attempts, retry_delay, lock_timeout)
    return bool(changed)


def delete_marks(path, profile, attempts=5, retry_delay=0.05, lock_timeout=MARKS_LOCK_TIMEOUT):
    """Delete all marks of the profile profile; return how many there were.

    For a profile the user deleted after a confirmation that names the marks (A22): marks
    are keyed by the profile name, so a later profile of that name would otherwise get them.
    Merged into the file as it is now, under the lock of save_marks; nothing happens without
    a marks file or marks of profile. Raises like save_marks.
    """
    path = Path(path)
    if not path.parent.is_dir():
        return 0
    removed = 0

    def update(document):
        nonlocal removed
        marks = document['profiles'].pop(profile, None)
        if marks is None:
            return None
        removed = len(marks)
        return document

    _update_locked(path, lambda: _read_marks_document(path, attempts, retry_delay), update,
                   attempts, retry_delay, lock_timeout)
    return removed


def remove_marks(path, entries, attempts=5, retry_delay=0.05, lock_timeout=MARKS_LOCK_TIMEOUT):
    """Remove the marks entries ((profile name, photo path) pairs) names; return how many were removed.

    For the cleanup of marks of photos that no longer exist (unbound, E8/A21): only these
    entries go, never the file or other marks; a profile left without marks is removed from
    the file, as by save_marks. Merged into the file as it is now, under the lock of
    save_marks; nothing happens without a marks file or without one of the entries. Raises
    like save_marks.
    """
    path = Path(path)
    entries = set(entries)
    if not entries or not path.parent.is_dir():
        return 0
    removed = 0

    def update(document):
        nonlocal removed
        profiles = document['profiles']
        for profile, photo in entries:
            marks = profiles.get(profile)
            if marks is not None and photo in marks:
                del marks[photo]
                removed += 1
                if not marks:
                    del profiles[profile]
        return document if removed else None

    _update_locked(path, lambda: _read_marks_document(path, attempts, retry_delay), update,
                   attempts, retry_delay, lock_timeout)
    return removed
