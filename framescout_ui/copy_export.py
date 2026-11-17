"""Copying the marked matches and exporting the result list of a profile.

Both are in the popover "Export and copy" of the results toolbar; each of its buttons
closes it, and the outcome is shown below the toolbar.
"""
from pathlib import Path

import streamlit as st

from framescout_core.cleanup import count_text
from framescout_core.copying import (copy_photos, copy_summary_text, copy_target, default_copy_folder,
                                     read_copy_folders, save_copy_folder)
from framescout_core.exporting import (DEFAULT_EXPORT_SEPARATOR, EXPORTS_DIR, EXPORT_SEPARATORS, export_cards,
                                       export_result_list, unlisted_paths)
from framescout_core.marks import MARKS_FILE, MARK_MATCH, MARK_NO_MATCH, read_marks
from framescout_core.profiles import UnknownProfileError

from .common import (EXPORTS, MARKS, PROFILES, RESULTS, SETTINGS, close_popover, gallery_action, open_path,
                     pictures_folder, plain, version_key, widget_id)
from .settings import setting_key


@st.cache_data(show_spinner=False, max_entries=2)
def cached_copy_folders(path, mtime_ns, size, ino):
    """read_copy_folders, read again only when settings.json changes."""
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
        # like set_mark: never under the name of a deleted or renamed profile
        save_copy_folder(SETTINGS, profile, st.session_state.get(key, ''), default, profiles_file=PROFILES)
    except UnknownProfileError as exc:
        unsaved.pop(profile, None)  # not kept for this session either
        st.session_state.gallery_notice = f'The target folder was not saved: {exc}.'
    except (OSError, ValueError) as exc:
        unsaved[profile] = st.session_state.get(key, '')  # used in this session anyway
        st.session_state.gallery_notice = f'The target folder is used, but could not be saved to {SETTINGS.name}: {exc}'
    else:
        unsaved.pop(profile, None)


def request_copy(profile, key):
    """Ask the next run of the results to copy the matches of profile to the folder typed into the field key (on_click)."""
    st.session_state.copy_request = (profile, st.session_state.get(key, ''))


def run_copy_request(request, profile, photo_folders):
    """Run the copy the button "Copy marked photos" asked for (request, taken by show_results), if it was for profile."""
    if request and request[0] == profile:
        copy_matches(profile, request[1], photo_folders)


def copy_matches(profile, folder, photo_folders):
    """Copy the photos of profile marked as match into folder (the text typed as target folder).

    Runs in the page run (not in a callback) with a progress bar: a reload, closing the tab
    or another click in the gallery stops it between two photos.
    """
    try:
        paths = [photo for photo, state in read_marks(MARKS).get(profile, {}).items() if state == MARK_MATCH]
    except (OSError, ValueError) as exc:
        st.warning(plain(f'Nothing was copied: {exc}'))
        return
    target, problem = copy_target(folder, photo_folders, paths)
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
    """Write the result list of profile to results/exports/ (on_click of the export button).

    gallery and cards are the list the page showed when it was drawn, on purpose: the user
    exports the list in front of them, under its own gallery name, even if a newer search
    finished meanwhile. The marks are read now: they belong to a photo path, not to a
    search, so another tab's later marks are the current ones for these photos too.
    Without readable marks the list of all photos is written with an empty mark column.
    The separator is the one the popover's choice shows now (saved in settings.json).
    """
    try:
        marks = read_marks(MARKS).get(profile, {})
    except (OSError, ValueError) as exc:
        if only_matches:
            st.session_state.export_notice = ('warning', f'Nothing was exported: {MARKS_FILE} cannot be read ({exc}).')
            return
        marks = None
    try:
        separator = EXPORT_SEPARATORS[st.session_state.get(setting_key('export_separator'), DEFAULT_EXPORT_SEPARATOR)]
        table, listing = export_result_list(RESULTS, Path(gallery).stem, cards, marks, only_matches,
                                            separator=separator)
    except (OSError, ValueError) as exc:
        st.session_state.export_notice = ('warning', f'Nothing was exported: {exc}.')
        return
    # a path with a line break (not possible on Windows) is only in the CSV table
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


def show_copy(name, entry, marks, photo_folders, profile_exists, popover):
    """Copying the photos of profile name marked as match to a folder, in the popover "Export and copy".

    The target folder can be changed only for a profile that still exists: it is saved under
    the profile name, which a later profile could take. popover: the key of the popover,
    closed by the buttons; the copy runs below the toolbar (run_copy_request).
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
    # also not in the folder of a photo to copy, which may be from another photo folder
    target, problem = copy_target(st.session_state[key], photo_folders, matches)
    if problem:
        st.warning(plain(problem))
    c1, c2 = st.columns(2)
    c1.button(f"Copy {count_text(len(matches), 'marked photo', 'marked photos')}", on_click=close_popover,
              args=(popover, request_copy, name, key), disabled=not matches or target is None, width='stretch')
    c2.button('Open target folder', on_click=close_popover, args=(popover, open_target_folder, key, photo_folders),
              disabled=target is None or not target.is_dir(), width='stretch')


def show_export(name, entry, marks, marks_error, popover):
    """Exporting the result list of profile name as a CSV table and a file list, in "Export and copy".

    popover: the key of the popover, closed by the buttons; the result of the export is
    shown below the toolbar (export_notice).
    """
    st.markdown('**Export list**')
    # one short line, the rest behind the help icon (a long caption would widen the popover)
    st.caption(f'A CSV table and a file list, in the folder {plain(EXPORTS_DIR)} of the results folder.',
               help=f'Writes the ranked photos of "{plain(name)}" as a CSV table (rank, path, score, crop, mark) and '
                    'as a text file with one path per line, e.g. for a cataloging program. The paths are those of '
                    'this computer; an export never replaces an earlier one.')
    key = 'export_matches_' + widget_id(name)
    # persist_state: kept while the popover is closed, which does not draw the box
    only = st.checkbox('Only photos marked as match', key=key, disabled=marks_error is not None, persist_state='page',
                       help='Only the photos of this list marked as match. Photos marked as match in an earlier '
                            'search that are not in this list are not exported: they have no rank or score here.')
    only = only and marks_error is None
    # a setting (settings.json), synchronized by sync_settings like the AI settings
    st.radio('Separator', list(EXPORT_SEPARATORS), key=setting_key('export_separator'), horizontal=True,
             format_func=lambda name: f'{name} ({EXPORT_SEPARATORS[name]})',
             help='The character between the columns of the CSV table. Excel opens a double-clicked CSV in columns '
                  'only if it uses the list separator of your Windows region: comma in English, semicolon in German '
                  'and other regions with a decimal comma. The scores keep a decimal point either way.')
    count = len(export_cards(entry['cards'], marks, only))
    if marks_error is not None:
        st.caption(f'{MARKS_FILE} cannot be read: the mark column of the list stays empty.')
    c1, c2 = st.columns(2)
    c1.button(f"Export {count:,} photo{'' if count == 1 else 's'}", on_click=close_popover,
              args=(popover, export_list, name, entry['gallery'], entry['cards'], only), disabled=not count,
              width='stretch', key='export_list')
    c2.button('Open exports folder', on_click=close_popover, args=(popover, open_exports_folder),
              disabled=not EXPORTS.is_dir(), width='stretch')
