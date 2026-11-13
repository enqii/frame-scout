"""Copying the marked matches and exporting the result list of a profile, below its gallery (A17, F5, A46)."""
from pathlib import Path

import streamlit as st

from framescout_core import (EXPORTS_DIR, MARKS_FILE, MARK_MATCH, MARK_NO_MATCH, UnknownProfileError, copy_photos,
                             copy_summary_text, copy_target, count_text, default_copy_folder, export_cards,
                             export_result_list, read_copy_folders, read_marks, save_copy_folder, unlisted_paths)

from .common import (EXPORTS, MARKS, PROFILES, RESULTS, SETTINGS, gallery_action, open_path, pictures_folder, plain,
                     version_key, widget_id)


@st.cache_data(show_spinner=False, max_entries=2)
def cached_copy_folders(path, mtime_ns, size, ino):
    """read_copy_folders, read again only when settings.json changes (review)."""
    return read_copy_folders(Path(path))


def copy_folder_value(profile, default):
    """Return the target folder of profile: typed but not saved in this session, saved, or the default."""
    unsaved = st.session_state.get('copy_folders_unsaved', {})
    if profile in unsaved:
        return unsaved[profile]
    try:
        return cached_copy_folders(*version_key(SETTINGS)).get(profile) or default
    except (OSError, ValueError):  # also FileNotFoundError: nothing saved
        return default


def set_copy_folder(profile, key, default):
    """Save the target folder typed into the field key in settings.json (on_change of the field)."""
    unsaved = st.session_state.setdefault('copy_folders_unsaved', {})
    try:
        # like set_mark: never under the name of a deleted or renamed profile (A22, A33)
        save_copy_folder(SETTINGS, profile, st.session_state.get(key, ''), default, profiles_file=PROFILES)
    except UnknownProfileError as exc:
        unsaved.pop(profile, None)  # not kept for this session either
        st.session_state.gallery_notice = f'The target folder was not saved: {exc}.'
    except (OSError, ValueError) as exc:
        unsaved[profile] = st.session_state.get(key, '')  # used in this session anyway
        st.session_state.gallery_notice = f'The target folder is used, but could not be saved to {SETTINGS.name}: {exc}'
    else:
        unsaved.pop(profile, None)


def copy_matches(profile, key, photo_folders):
    """Copy the photos of profile marked as match into the folder typed into the field key (A17).

    Runs in the page run (not in a callback) with a progress bar: a reload, closing the tab
    or another click in the gallery stops it between two photos (review).
    """
    try:
        paths = [photo for photo, state in read_marks(MARKS).get(profile, {}).items() if state == MARK_MATCH]
    except (OSError, ValueError) as exc:
        st.warning(plain(f'Nothing was copied: {exc}'))
        return
    target, problem = copy_target(st.session_state.get(key, ''), photo_folders, paths)
    if problem:
        st.warning(plain(problem))
        return
    bar = st.progress(0.0, text=f'Copying {len(paths):,} photos …')

    def progress(done, total):
        bar.progress(done / total, text=f'Copied {done:,} of {total:,} photos …')

    try:
        summary = copy_photos(paths, target, progress)
    except OSError as exc:
        bar.empty()
        st.warning(plain(f'Nothing was copied: {exc}'))
        return
    bar.empty()
    text = f'{copy_summary_text(summary)} (to {target})'
    if summary['failed']:
        st.warning(plain(text + '. Not copied: ' + '; '.join(f'{p}: {why}' for p, why in summary['failed'][:10])
                         + (' …' if len(summary['failed']) > 10 else '')))
    else:
        st.success(plain(text))


def export_list(profile, gallery, cards, only_matches):
    """Write the result list of profile to results/exports/ (on_click of the export button, F5).

    gallery and cards are the list the page showed when it was drawn, on purpose: the user
    exports the list in front of them, under its own gallery name, even if a newer search
    finished meanwhile. The marks are read now: they belong to a photo path, not to a
    search, so another tab's later marks are the current ones for these photos too.
    Without readable marks the list of all photos is written with an empty mark column.
    """
    try:
        marks = read_marks(MARKS).get(profile, {})
    except (OSError, ValueError) as exc:
        if only_matches:
            st.session_state.export_notice = ('warning', f'Nothing was exported: {MARKS_FILE} cannot be read ({exc}).')
            return
        marks = None
    try:
        table, listing = export_result_list(RESULTS, Path(gallery).stem, cards, marks, only_matches)
    except (OSError, ValueError) as exc:
        st.session_state.export_notice = ('warning', f'Nothing was exported: {exc}.')
        return
    # a path with a line break (not possible on Windows) is only in the CSV table (A42)
    unlisted = len(unlisted_paths(export_cards(cards, marks, only_matches)))
    st.session_state.export_notice = (
        'success', f'Exported to {table.name} and {listing.name} in {EXPORTS}.'
                   + (f' The mark column is empty: {MARKS_FILE} cannot be read.' if marks is None else '')
                   + (f" {count_text(unlisted, 'path contains', 'paths contain')} a line break, which one line of "
                      f'{listing.name} cannot hold: only {table.name} lists it.' if unlisted else ''))


def open_exports_folder():
    gallery_action(open_path, EXPORTS if EXPORTS.is_dir() else None, f'The folder {EXPORTS}')


def open_target_folder(key, photo_folders):
    target, _ = copy_target(st.session_state.get(key, ''), photo_folders)
    gallery_action(open_path, target if target is not None and target.is_dir() else None, f'The folder {target}')


def show_copy(name, entry, marks, photo_folders, profile_exists):
    """Copying the photos of profile name marked as match to a folder, below its gallery (A17).

    The target folder can be changed only for a profile that still exists: it is saved under
    the profile name, which a later profile could take (A33).
    """
    st.markdown('**Copy marked matches**')
    matches = [photo for photo, state in marks.items() if state == MARK_MATCH]
    rejected = sum(1 for state in marks.values() if state == MARK_NO_MATCH)
    in_results = {card['path'] for card in entry['cards']}
    elsewhere = sum(1 for photo in matches if photo not in in_results)
    st.caption(f'Marked: {count_text(len(matches), "photo", "photos")} of "{plain(name)}" as match · '
               f'{rejected:,} as no match.'
               +(f' {elsewhere:,} of the matches are not among the results of this search (marked earlier); they '
                  'are copied too.' if elsewhere else ''))
    default = str(default_copy_folder(pictures_folder(), Path(entry['gallery']).stem))
    key = 'copy_folder_' + widget_id(name)
    st.session_state[key] = copy_folder_value(name, default)
    st.text_input('Copy to folder', key=key, on_change=set_copy_folder, args=(name, key, default),
                  disabled=not profile_exists,
                  help='Copies only: the originals stay where they are. Files in this folder are never overwritten; '
                       'a different photo with the same name is saved as "name (2)".'
                       + ('' if profile_exists else ' It cannot be changed for a profile that is no longer one of '
                          'your search profiles.'))
    # also not in the folder of a photo to copy, which may be from another photo folder (review)
    target, problem = copy_target(st.session_state[key], photo_folders, matches)
    if problem:
        st.warning(plain(problem))
    c1, c2 = st.columns(2)
    copy = c1.button(f"Copy {count_text(len(matches), 'marked photo', 'marked photos')}",
                     disabled=not matches or target is None, width='stretch')
    c2.button('Open target folder', on_click=open_target_folder, args=(key, photo_folders),
              disabled=target is None or not target.is_dir(), width='stretch')
    if copy:
        copy_matches(name, key, photo_folders)


def show_export(name, entry, marks, marks_error):
    """Exporting the result list of profile name as a CSV table and a file list, below its gallery (F5)."""
    st.markdown('**Export list**')
    st.caption(f'Writes the ranked photos of "{plain(name)}" as a CSV table (rank, path, score, crop, mark) and as a '
               'text file with one path per line, e.g. for a cataloging program, to the folder '
               f'{plain(EXPORTS_DIR)} in the results folder. The paths are those of this computer; an export never '
               'replaces an earlier one.')
    key = 'export_matches_' + widget_id(name)
    only = st.checkbox('Only photos marked as match', key=key, disabled=marks_error is not None,
                       help='Only the photos of this list marked as match. Photos marked as match in an earlier '
                            'search that are not in this list are not exported: they have no rank or score here.')
    only = only and marks_error is None
    count = len(export_cards(entry['cards'], marks, only))
    if marks_error is not None:
        st.caption(f'{MARKS_FILE} cannot be read: the mark column of the list stays empty.')
    if 'export_notice' in st.session_state:
        kind, text = st.session_state.pop('export_notice')
        (st.success if kind == 'success' else st.warning)(plain(text))
    c1, c2 = st.columns(2)
    c1.button(f"Export {count:,} photo{'' if count == 1 else 's'}", on_click=export_list, args=(name, entry['gallery'], entry['cards'], only),
              disabled=not count, width='stretch', key='export_list')
    c2.button('Open exports folder', on_click=open_exports_folder, disabled=not EXPORTS.is_dir(), width='stretch')
