"""Marks of gallery photos in results/marks.json (A17), with a backup and its restore (F1)."""
import json
import re
from pathlib import Path

from ._common import (_backup_path, _broken_names, _file_lock, _previous_content, _publish_new, _publish_via_temp,
                      _replace_with_retry, _update_locked)
from .profiles import require_profile


# Marks (A17, P4 (B)): FrameScout ranks candidates, not certain hits; a mark records what the
# user decided about a photo of a profile's gallery: a match, no match, or still open. Kept
# in MARKS_FILE in the results folder (user decision), per profile name and photo path,
# across later searches; "open" is the absence of a mark. The file is user data: the engine
# never writes it, and a cleanup of the results folder (E7) must never delete it.
MARKS_FILE = 'marks.json'
# the marks file before its latest change (F1): written by every change, restored only on the
# user's request (restore_marks) when marks.json cannot be read; user data like MARKS_FILE
MARKS_BACKUP = MARKS_FILE + '.bak'
MARKS_FORMAT = 1
MARK_OPEN, MARK_MATCH, MARK_NO_MATCH = 'open', 'match', 'no-match'
MARK_STATES = (MARK_OPEN, MARK_MATCH, MARK_NO_MATCH)
# seconds save_marks and rename_marks wait for the lock around their read-change-write
MARKS_LOCK_TIMEOUT = 5.0
# the color of the selected option of a mark in the app's gallery (A24): (background, border)
# per state; Undecided keeps Streamlit's look. Translucent backgrounds and the theme's text
# color keep the label readable in the light and the dark theme.
MARK_COLORS = {MARK_MATCH: ('rgba(33, 195, 84, 0.25)', 'rgb(33, 195, 84)'),
               MARK_NO_MATCH: ('rgba(255, 75, 75, 0.25)', 'rgb(255, 75, 75)')}
# the Streamlit version whose internals mark_style was checked against (its frontend bundle:
# the key class st-key-<key> and the kind "segmented_controlActive" of the selected button);
# a test fails once constraints.txt pins another version (review)
MARK_STYLE_STREAMLIT = '1.66.1'


def marks_backup(path):
    """Return the backup of the marks file path: <path>.bak, the file before its latest change (F1)."""
    return _backup_path(path)


def _parse_marks(content, name):
    """Return the checked JSON object of a marks file's content (bytes; None: a missing file).

    {'format': ..., 'profiles': {}} for a missing or empty-object file; ValueError for one
    that is not a marks file of this format (name names it).
    """
    data = {} if content is None else json.loads(content.decode('utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('The marks file must be a JSON object.')
    if not data:
        return {'format': MARKS_FORMAT, 'profiles': {}}
    if data.get('format') != MARKS_FORMAT:
        raise ValueError(f'{name} is not a FrameScout marks file of format {MARKS_FORMAT}')
    profiles = data.get('profiles')
    if not isinstance(profiles, dict):
        raise ValueError('"profiles" must be a JSON object')
    for profile, marks in profiles.items():
        if not isinstance(marks, dict) or any(
                not isinstance(photo, str) or state not in (MARK_MATCH, MARK_NO_MATCH) for photo, state in marks.items()):
            raise ValueError(f'invalid marks of {profile!r}: {marks!r}'[:300])
    return data


def _read_marks_document(path, attempts=5, retry_delay=0.05):
    """Return the checked JSON object of the marks file ({'format': ..., 'profiles': {}} if missing)."""
    return _parse_marks(_previous_content(path, attempts, retry_delay), Path(path).name)


def _update_marks(path, update, attempts, retry_delay, lock_timeout):
    """Read, change and replace the marks file path under its lock, keeping the previous file as backup.

    update(document) returns the new document, or None to leave the file as it is. The
    previous content goes to marks_backup(path) first (F1; _update_locked with backup): only
    content that was just read as a valid marks file, so an unreadable file (ValueError,
    never replaced) never replaces the backup. Raises like _update_locked.
    """
    _update_locked(path, lambda content: _parse_marks(content, path.name), update, attempts, retry_delay,
                   lock_timeout, backup=True)


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

    _update_marks(path, update, attempts, retry_delay, lock_timeout)
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

    _update_marks(path, update, attempts, retry_delay, lock_timeout)
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

    _update_marks(path, update, attempts, retry_delay, lock_timeout)
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

    _update_marks(path, update, attempts, retry_delay, lock_timeout)
    return removed


def restore_marks(path, now=None, attempts=5, retry_delay=0.05, lock_timeout=MARKS_LOCK_TIMEOUT):
    """Replace the unreadable marks file path by its backup; return (marks restored, damaged copy or None) (F1).

    Only on the user's request, never automatically. Under the lock of save_marks, the file
    is read again: if it can be read now (fixed by hand, or restored in another tab),
    ValueError is raised and nothing changes. The backup (marks_backup) must be a readable
    marks file, else ValueError naming it. The damaged file is first copied byte for byte
    to <path>.broken-<YYYYMMDD-HHMMSS> (of now, a time.time() value; -2, -3, ... if that
    name exists), which is returned; then the file is replaced atomically by the backup's
    content, which stays as the backup. A missing file (removed meanwhile) just gets the
    backup (None is returned). Any error leaves the file as it was; OSError if the lock is
    not free within lock_timeout seconds or a write keeps failing.
    """
    path = Path(path)
    backup = marks_backup(path)
    with _file_lock(path, lock_timeout):
        current = _previous_content(path, attempts, retry_delay)
        if current is not None:
            try:
                _parse_marks(current, path.name)
            except ValueError:
                pass
            else:
                raise ValueError(f'{path.name} can be read again, so it was not replaced by {backup.name}')
        content = _previous_content(backup, attempts, retry_delay)
        if content is None:
            raise ValueError(f'There is no backup {backup.name}')
        try:
            restored = _parse_marks(content, backup.name)['profiles']
        except ValueError as exc:
            raise ValueError(f'{backup.name} cannot be read either ({exc})') from None
        kept = None if current is None else _keep_copy(path, current, now)
        _replace_with_retry(path, content, attempts, retry_delay)
    return sum(len(marks) for marks in restored.values()), kept


def _keep_copy(path, content, now):
    """Write content to a new file <path>.broken-<date>[-n] next to path (never replacing one); return it."""
    for candidate in _broken_names(path, now):
        try:
            _publish_via_temp(candidate, lambda tmp: tmp.write_bytes(content), _publish_new)
        except FileExistsError:
            continue
        return candidate


def hide_no_match(cards, marks):
    """Return (the cards not marked as no match, how many were left out) (A24).

    cards are result cards with a "path", marks one profile's marks of read_marks. The app
    applies it to the cards of one gallery page, after paginating the whole ranked list, so
    hiding the rejects of a page never pulls photos of the following pages up into it.
    """
    kept = [card for card in cards if marks.get(card['path']) != MARK_NO_MATCH]
    return kept, len(cards) - len(kept)


def mark_style(states):
    """Return a <style> block coloring the selected option of each mark control, or '' (A24).

    states maps the widget key of a mark control to its saved state. st.segmented_control
    has no colors per option, so the style targets the element of each control by its key
    class and its selected button: Streamlit internals, see MARK_STYLE_STREAMLIT.
    """
    rules = []
    for state, (background, border) in MARK_COLORS.items():
        # the class Streamlit gives the element of a widget with a key
        selectors = ', '.join(f'.st-key-{re.sub(r"[^a-zA-Z0-9_-]", "-", key.strip())} '
                              'button[kind="segmented_controlActive"]'
                              for key, saved in states.items() if saved == state)
        if selectors:
            # !important: Streamlit's own rule for the selected button ([kind=…]:not(:disabled)
            # on its class) is more specific than this selector
            rules.append(f'{selectors}{{background-color:{background}!important;border-color:{border}!important;'
                         'color:inherit!important}')
    return f'<style>{"".join(rules)}</style>' if rules else ''


def hidden_text(hidden, kept, more_pages):
    """Return the caption of a gallery page's photos hidden by hide_no_match, or '' (A24).

    hidden and kept are the counts hide_no_match left out and kept; more_pages says whether
    a page follows this one.
    """
    if not hidden:
        return ''
    if kept:
        return (f"{hidden:,} photo{'s' if hidden != 1 else ''} of this page marked as no match "
                f"{'are' if hidden != 1 else 'is'} hidden.")
    text = ('The only photo of this page is' if hidden == 1 else f'All {hidden:,} photos of this page are')
    return (f'{text} marked as no match and hidden.'
            + (' The next page may hold photos still to check.' if more_pages else ''))
