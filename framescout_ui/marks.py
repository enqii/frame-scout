"""The marks of gallery photos: reading them, the backup offer, saving a mark (A17, F1, A40, A46)."""
import time
from pathlib import Path

import streamlit as st

from framescout_core import (MARKS_BACKUP, MARKS_FILE, MARK_MATCH, MARK_NO_MATCH, MARK_OPEN, count_text,
                             marks_restore_offer, read_marks, restore_marks, save_marks)

from .common import MARKS, PROFILES, version_key


# the three states of a mark, as the control on each gallery card shows them (A17)
MARK_LABELS = {MARK_OPEN: 'Undecided', MARK_MATCH: 'Match', MARK_NO_MATCH: 'No match'}
MARK_BY_LABEL = {label: state for state, label in MARK_LABELS.items()}


@st.cache_data(show_spinner=False, max_entries=2)
def cached_marks(path, mtime_ns, size, ino):
    """read_marks, read again only when the file changes (review: not on every gallery click)."""
    return read_marks(Path(path))


def load_marks():
    """Return (marks of all profiles, error or None) of results/marks.json (A17)."""
    try:
        return cached_marks(*version_key(MARKS)), None
    except FileNotFoundError:
        return {}, None
    except (OSError, ValueError) as exc:
        return {}, exc


def marks_backup_offer(error):
    """The text offering to restore marks.json.bak, or None if there is nothing to offer (F1, A40).

    error: the error of load_marks, or None. For a damaged marks.json and for a missing one
    whose backup holds marks (marks_restore_offer). This runs on every gallery rerun, so the
    backup is read through cached_marks: again only when it changes (review).
    """
    offer = marks_restore_offer(MARKS, error, read=lambda backup: cached_marks(*version_key(backup)))
    if offer is None:
        return None
    count, saved = offer
    text = (f"The backup {MARKS_BACKUP} of {time.strftime('%Y-%m-%d %H:%M', time.localtime(saved))} holds "
            f"{count_text(count, 'mark', 'marks')}: the marks as they were before the last change that was saved.")
    if error is None:
        return (f'{MARKS_FILE} does not exist (e.g. it was removed by hand), so no photo is marked. {text} '
                'Restoring it brings these marks back. FrameScout never restores it on its own; your next mark '
                f'starts a new {MARKS_FILE} instead.')
    return (f'{text} Restoring it replaces {MARKS_FILE} and keeps the damaged file next to it as '
            f'{MARKS_FILE}.broken-<date and time>. FrameScout never restores it on its own.')


def restore_marks_backup():
    """Replace the damaged or missing marks.json by its backup (on_click of "Restore marks from backup", F1, A40)."""
    try:
        restored, kept = restore_marks(MARKS)
    except (OSError, ValueError) as exc:
        st.session_state.marks_notice = ('warning', f'The marks were not restored: {exc}')
        return
    text = f"Restored {count_text(restored, 'mark', 'marks')} from {MARKS_BACKUP}."
    if kept:
        text += (f' The damaged file is kept as {kept.name} in the results folder; "Clean up storage" offers it as a '
                 'damaged file set aside once you no longer need it.')
    st.session_state.marks_notice = ('success', text)


def set_mark(profile, photo, key):
    """Save the mark the control key shows for photo of profile (on_change of the control)."""
    # no selection (the selected option clicked again) is "open"
    state = MARK_BY_LABEL.get(st.session_state.get(key), MARK_OPEN)
    try:
        # only for a profile that still exists: this gallery may have been drawn before it
        # was deleted or renamed in another tab (review of A22); the run after this
        # callback then shows it as no longer a search profile
        save_marks(MARKS, profile, {photo: state}, profiles_file=PROFILES)
    except (OSError, ValueError) as exc:
        # the next run shows the saved mark again
        st.session_state.gallery_notice = f'The mark could not be saved: {exc}'
