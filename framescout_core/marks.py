"""Marks of gallery photos in results/marks.json, with a backup and its restore."""
import json
import re
from pathlib import Path
from typing import NamedTuple, Optional

from ._common import (_backup_path, _broken_names, _file_lock, _previous_content, _publish_new, _publish_via_temp,
                      _replace_with_retry, _update_locked)
from .profiles import read_profiles, require_profile


# Marks: FrameScout ranks candidates, not certain hits; a mark records what the
# user decided about a photo of a profile's gallery: a match, no match, or still open. Kept
# in MARKS_FILE in the results folder, per profile name and photo path,
# across later searches; "open" is the absence of a mark. The file is user data: the engine
# never writes it, and a cleanup of the results folder must never delete it.
MARKS_FILE = 'marks.json'
# the marks file before its latest change: written by every change, restored only on the
# user's request (restore_marks) when marks.json cannot be read; user data like MARKS_FILE
MARKS_BACKUP = MARKS_FILE + '.bak'
MARKS_FORMAT = 1
MARK_OPEN, MARK_MATCH, MARK_NO_MATCH = 'open', 'match', 'no-match'
MARK_STATES = (MARK_OPEN, MARK_MATCH, MARK_NO_MATCH)
# seconds save_marks and rename_marks wait for the lock around their read-change-write
MARKS_LOCK_TIMEOUT = 5.0
# the color of a mark in the app's gallery: (background, border) per state, for
# the selected button of a card's mark control and (the border color) the card's frame;
# Undecided keeps Streamlit's look. Blue and orange of the Okabe-Ito palette, told apart
# without red and green. Translucent backgrounds and the theme's text
# color keep the label readable in the light and the dark theme.
MARK_COLORS = {MARK_MATCH: ('rgba(0, 114, 178, 0.25)', 'rgb(0, 114, 178)'),
               MARK_NO_MATCH: ('rgba(230, 159, 0, 0.25)', 'rgb(230, 159, 0)')}
# how much of the photo of a card marked as no match shows: dimmed, so the two states
# differ by more than their color
MARK_NO_MATCH_OPACITY = 0.4
# the key of a gallery card's container in the app starts with this; CARD_STYLE and
# mark_style find the cards by it
CARD_KEY_PREFIX = 'fscard-'
# the photo of a card sits in a container whose key starts with PHOTO_KEY_PREFIX, with the
# button that opens the review dialog laid over it, whose key starts with
# PREVIEW_KEY_PREFIX: Streamlit has no clickable image, so a click on the photo reaches the
# invisible button; it shows when it has the keyboard focus. Neither prefix contains
# CARD_KEY_PREFIX, whose selector would match them too
PHOTO_KEY_PREFIX = 'fsphoto-'
PREVIEW_KEY_PREFIX = 'fspreview-'
# equal cells: the photo of every card is fitted whole into a square box (as in the
# HTML gallery), so portrait and landscape photos give cards of one height; CSS, so the
# thumbnails and the cache signature stay as they are. Streamlit sizes the elements around an
# image to its natural width, also with width='stretch' (checked with 1.66.1), so they are
# stretched too: Streamlit internals (their data-testid), see MARK_STYLE_STREAMLIT
_CARD = f'[class*="st-key-{CARD_KEY_PREFIX}"]'
CARD_STYLE = (f'<style>{_CARD} :is(div:has(> [data-testid="stImage"]), [data-testid="stImage"], '
              '[data-testid="stImageContainer"]){width:100%!important}'
              f'{_CARD} img{{width:100%!important;height:auto!important;aspect-ratio:1/1;object-fit:contain;'
              'background:rgba(128, 128, 128, 0.12);border-radius:4px}'
              f'[class*="st-key-{PHOTO_KEY_PREFIX}"]{{position:relative}}'
              f'[class*="st-key-{PREVIEW_KEY_PREFIX}"]{{position:absolute;inset:0;width:auto!important;z-index:1}}'
              f'[class*="st-key-{PREVIEW_KEY_PREFIX}"] :is(div, button){{width:100%!important;height:100%!important}}'
              f'[class*="st-key-{PREVIEW_KEY_PREFIX}"] button{{opacity:0;cursor:zoom-in}}'
              f'[class*="st-key-{PREVIEW_KEY_PREFIX}"] button:focus-visible{{opacity:0.85}}</style>')
# the Streamlit version whose internals mark_style was checked against (its frontend bundle:
# the key class st-key-<key>, data-variant="segmented_control" on the buttons and the
# data-selected attribute of the selected one);
# a test fails once constraints.txt pins another version
MARK_STYLE_STREAMLIT = '1.66.1'


def marks_backup(path):
    """Return the backup of the marks file path: <path>.bak, the file before its latest change."""
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
    previous content goes to marks_backup(path) first (_update_locked with backup): only
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

    For a profile the user deleted after a confirmation that names the marks: marks
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


def remove_marks(path, entries, attempts=5, retry_delay=0.05, lock_timeout=MARKS_LOCK_TIMEOUT,
                 unless_profile_of=None):
    """Remove the marks entries ((profile name, photo path) pairs) names; return how many were removed.

    For the cleanup of marks of photos that no longer exist (unbound) and of names
    that are no profile: only these entries go, never the file or other marks; a
    profile left without marks is removed from the file, as by save_marks. With
    unless_profile_of (the app's profiles JSON file), the entries of a name that is a profile
    of that file at the time of the write are kept (read under the lock, like
    require_profile; ValueError naming the file if it is missing or cannot be read). Merged into the file
    as it is now, under the lock of save_marks; nothing happens without a marks file or
    without one of the entries. Raises like save_marks.
    """
    path = Path(path)
    entries = set(entries)
    if not entries or not path.parent.is_dir():
        return 0
    removed = 0

    def update(document):
        nonlocal removed
        profiles = document['profiles']
        current = set()
        if unless_profile_of is not None:
            if not Path(unless_profile_of).is_file():  # read_profiles would give no profile
                raise ValueError(f'{Path(unless_profile_of).name} does not exist')
            try:
                current = {p.get('name') for p in read_profiles(unless_profile_of)}
            except ValueError as exc:
                raise ValueError(f'{Path(unless_profile_of).name} cannot be read: {exc}') from exc
        for profile, photo in entries:
            if profile in current:
                continue
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
    """Replace the unreadable marks file path by its backup; return (marks restored, damaged copy or None).

    Only on the user's request, never automatically. Under the lock of save_marks, the file
    is read again: if it can be read now (fixed by hand, or restored in another tab),
    ValueError is raised and nothing changes. The backup (marks_backup) must be a readable
    marks file, else ValueError naming it. The damaged file is first copied byte for byte
    to <path>.broken-<YYYYMMDD-HHMMSS> (of now, a time.time() value; -2, -3, ... if that
    name exists), which is returned; then the file is replaced atomically by the backup's
    content, which stays as the backup. A missing file (removed meanwhile) just gets the
    backup (None is returned). Any error leaves the file as it was, without a copy; OSError
    if the lock is not free within lock_timeout seconds or a write keeps failing.
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
        try:
            _replace_with_retry(path, content, attempts, retry_delay)
        except OSError:
            # the damaged file is still there: no copy of it per failed try
            if kept is not None:
                kept.unlink(missing_ok=True)
            raise
    return sum(len(marks) for marks in restored.values()), kept


def marks_restore_offer(path, error, read=read_marks):
    """Return (marks in the backup, its mtime) if restoring marks_backup(path) can be offered, else None.

    error: what read_marks(path) raised, or None if it read the file or found none. Offered
    for a damaged file (a ValueError; an OSError may pass, e.g. a file another program has
    open) and for a missing file whose backup holds at least one mark (e.g. removed by
    hand), in both cases only with a backup that can be read. read(backup) reads the
    backup like read_marks (e.g. a cached read_marks of the app). Nothing is changed.
    """
    path = Path(path)
    if error is None:
        if path.exists():
            return None
    elif not isinstance(error, ValueError):
        return None
    backup = marks_backup(path)
    try:
        saved = backup.stat().st_mtime
        count = sum(len(marks) for marks in read(backup).values())
    except (OSError, ValueError):
        return None
    if error is None and not count:
        return None
    return count, saved


def _keep_copy(path, content, now):
    """Write content to a new file <path>.broken-<date>[-n] next to path (never replacing one); return it."""
    for candidate in _broken_names(path, now):
        try:
            _publish_via_temp(candidate, lambda tmp: tmp.write_bytes(content), _publish_new)
        except FileExistsError:
            continue
        return candidate


def hide_no_match(cards, marks):
    """Return (the cards not marked as no match, how many were left out).

    cards are result cards with a "path", marks one profile's marks of read_marks. The app
    applies it to the cards of one gallery page, after paginating the whole ranked list, so
    hiding the rejects of a page never pulls photos of the following pages up into it.
    """
    kept = [card for card in cards if marks.get(card['path']) != MARK_NO_MATCH]
    return kept, len(cards) - len(kept)


class ReviewProgress(NamedTuple):
    """How far the user got marking one profile's result list, of review_progress."""
    matches: int
    no_matches: int
    open: int
    first_open_rank: Optional[int]  # the rank of the first unmarked photo of the list, or None
    first_open_page: Optional[int]  # the gallery page (1-based) holding it, or None


def review_progress(cards, marks, size):
    """Return the ReviewProgress of a profile's ranked cards under its marks.

    cards are the result cards in the order the gallery pages them, marks one profile's
    marks of read_marks, size the gallery's page size. Only the photos of cards count; a
    state other than match or no match counts as open, as the gallery shows it. The page
    follows page_cards; hide_no_match never hides an open photo, so that page shows it.
    """
    counts = {MARK_MATCH: 0, MARK_NO_MATCH: 0, MARK_OPEN: 0}
    first = None
    for index, card in enumerate(cards):
        state = marks.get(card['path'])
        state = state if state in (MARK_MATCH, MARK_NO_MATCH) else MARK_OPEN
        counts[state] += 1
        if state == MARK_OPEN and first is None:
            first = index
    return ReviewProgress(counts[MARK_MATCH], counts[MARK_NO_MATCH], counts[MARK_OPEN],
                          None if first is None else cards[first]['rank'],
                          None if first is None else first // size + 1)


def progress_text(progress, paged):
    """Return the caption of a profile's ReviewProgress, or '' for an empty list.

    paged says whether the gallery has more than one page: only then the page is named.
    """
    total = progress.matches + progress.no_matches + progress.open
    if not total:
        return ''
    text = (f"{total:,} photo{'s' if total != 1 else ''}: {progress.matches:,} match, "
            f'{progress.no_matches:,} no match, {progress.open:,} undecided.')
    if progress.first_open_rank is None:
        return text + ' Every photo is marked.'
    return (text + f' The first undecided photo is #{progress.first_open_rank}'
            + (f' on page {progress.first_open_page}.' if paged else '.'))


def mark_counts_text(progress):
    """Return the short counts of a profile's ReviewProgress for the results toolbar, or ''.

    Only the three counts: progress_text, below the grid, names the first undecided photo.
    """
    if not progress.matches + progress.no_matches + progress.open:
        return ''
    return f'{progress.matches:,} match · {progress.no_matches:,} no match · {progress.open:,} undecided'


def mark_style(states):
    """Return a <style> block showing the saved mark of each gallery card, or ''.

    states maps the key of a card's container (CARD_KEY_PREFIX) to its saved state. A
    marked card gets a frame in its state's color, the photo of one marked as no match is
    dimmed, and the selected option of the card's mark control takes the color too
    (st.segmented_control has no colors per option). The style targets each card by its
    key class and the selected button by its attributes: Streamlit internals, see
    MARK_STYLE_STREAMLIT.
    """
    rules = []
    for state, (background, border) in MARK_COLORS.items():
        # the class Streamlit gives the element of a container with a key; a disabled
        # control (its profile is no longer searched) keeps the color of its saved mark on purpose
        cards = [f'.st-key-{re.sub(r"[^a-zA-Z0-9_-]", "-", key.strip())}'
                 for key, saved in states.items() if saved == state]
        if not cards:
            continue
        # a box-shadow, not a border: it follows the rounded corners and changes no size;
        # inset, inside the card's padding, so no parent that clips its overflow
        # can cut the frame of a card at the edge of a row
        rules.extend(f'{card}{{box-shadow:inset 0 0 0 3px {border}!important}}' for card in cards)
        if state == MARK_NO_MATCH:
            rules.extend(f'{card} img{{opacity:{MARK_NO_MATCH_OPACITY}!important}}' for card in cards)
        selectors = ', '.join(f'{card} button[data-variant="segmented_control"][data-selected]' for card in cards)
        # !important: Streamlit's own rules for the selected button (its class with
        # [data-selected]:not([data-disabled]), plus hover and focus states) must not win
        rules.append(f'{selectors}{{background-color:{background}!important;border-color:{border}!important;'
                     'color:inherit!important}')
    return f'<style>{"".join(rules)}</style>' if rules else ''


def hidden_text(hidden, kept, more_pages):
    """Return the caption of a gallery page's photos hidden by hide_no_match, or ''.

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
