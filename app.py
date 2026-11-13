"""FrameScout: local Streamlit user interface for framescout_engine.py."""
import sys
import time
from pathlib import Path

import streamlit as st

# I35: a script of a version with the packages framescout_core and framescout_scoring, which
# load for it next to an older version's leftover single files (framescout_core.layout); set
# before the first FrameScout import. Streamlit runs this file as the module __main__.
FRAMESCOUT_PACKAGES = True

from framescout_core import (CACHE_CATEGORIES, CACHE_FILE, CLEANUP_CATEGORIES, DEFAULT_YOLO_MODEL,
                             EXAMPLE_PROFILES_FILE, MARKS_FILE, MARK_MATCH, MODELS, QUICK_DIR, QUICK_QUERY_MAX,
                             RESULTS_FILE, ProfilesChangedError, cache_check_current, check_cache, clean_up,
                             cleanup_running, cleanup_summary_text, count_text, create_from_example, delete_marks,
                             distinct_folders, engine_command, feature_signature, finish_reference_move,
                             finishing_minutes, forget_copy_folder, gallery_thumbnails, join_scans, known_throughput,
                             profiles_changed_notice, quick_scope_text, read_profiles_versioned, reference_folder,
                             remembered_scans, rename_copy_folder, rename_marks, save_profiles, scan_cleanup,
                             set_cache_aside, size_text, skipped_lines, stage_reference_move, start_summary,
                             undo_reference_move, update_backup_references, windows_path, write_new_file)
from framescout_ui.common import (BASE, DECODERS, EXAMPLE_PROFILES, MARKS, PROFILES, QUICK_JSON, REFS, RESULTS,
                                  SETTINGS, SUPPORTED, UPLOAD_TYPES, clean_project_folder, file_key,
                                  open_results_folder, plain, version_key)
from framescout_ui.settings import setting_key, show_ai_settings, sync_settings
from framescout_ui.run import (cached_analyzed_photos, engine_alive, low_space_warning, run_state, show_status,
                               start_run, stop_run)
from framescout_ui.marks import load_marks
from framescout_ui.copy_export import cached_copy_folders
from framescout_ui.results import load_results, show_quick_results, show_results



# labels of the profile fields, shared by the edit and the new-profile form (review);
# search terms are English only (E3)
LABEL_NAME = 'Search motif (in English)'
LABEL_CONTEXT = 'Context / origin (optional, in English)'
LABEL_FEATURES = 'Distinctive features (optional, in English)'
LABEL_PROMPTS = 'Custom search texts (optional, in English; one per line)'
# the categories of "Clean up storage" (E7): (label, explanation)
CLEANUP_LABELS = {
    'temp_thumbnails': ('Temporary thumbnail files',
                        'Left behind by a search that was stopped while it wrote the galleries; never used again.'),
    'galleries': ('Galleries of renamed or deleted profiles',
                  'FrameScout HTML galleries in the results folder that belong neither to a current search profile '
                  'nor to the last search, with the thumbnails only they show.'),
    'thumbnails': ('Thumbnails no gallery shows',
                   'Thumbnails that neither the last search nor any HTML gallery in the results folder shows, '
                   'also in the old "vorschaubilder" folder.'),
    'cache_missing': ('Cache entries of unbound photos',
                      'Analyses of photos that no longer exist at their path: deleted, renamed or moved, in any '
                      'folder searched so far (a renamed or moved photo is analyzed again as a new photo). Photos '
                      'on a drive or network share that is not reachable now are not checked. Check the folders '
                      'listed below: if a drive letter now belongs to another disk, the photos of the earlier disk '
                      'look unbound too.'),
    'marks_unbound': ('Marks of unbound photos',
                      'Your match/no-match marks of photos that no longer exist at their path (deleted, renamed or '
                      'moved). They are kept in case the photos come back. Deleting removes only these marks from '
                      'marks.json, never the file or other marks. Photos on a drive or network share that is not '
                      'reachable now are not checked.'),
    'marks_profiles': ('Marks of deleted profiles',
                       'Your match/no-match marks saved under a name that is none of your search profiles now, e.g. '
                       'of a profile deleted before FrameScout deleted the marks together with their profile. A new '
                       'profile of that name would get them. Deleting removes only these marks from marks.json, '
                       'never the file or other marks; the marks of a profile of that name created since the scan '
                       'are kept.'),
    'cache_old': ('Cache entries of older versions or unknown settings',
                  'Analyses made by an earlier FrameScout version, which are never used again, or with settings '
                  'only the command line offers (e.g. another --yolo-model), which are analyzed again when such a '
                  'search runs.'),
    'cache_other': ('Cache entries of other AI settings',
                    'Analyses with other person detection settings of this version. They are used again when you '
                    'switch back to those settings; after deleting them, those photos are analyzed again then.'),
    'cache_models': ('Cache entries of other search models',
                     'Analyses made with another search model (AI settings). They are used again when you switch '
                     'back to that model; after deleting them, every photo is analyzed again then.'),
    'references': ('Reference images no profile uses',
                   'Image files in the references folder that neither profiles.json nor its backup '
                   'profiles.json.bak names, e.g. removed from a profile or of a deleted profile.'),
    'broken_files': ('Damaged files set aside',
                     'The damaged copies FrameScout kept when you restored the marks from their backup '
                     '(marks.json.broken-<date and time>) or set a damaged cache aside (cache.sqlite3.broken-<date '
                     'and time>, with its journal files). FrameScout never reads them again; keep them only if you '
                     'want to try to repair one.'),
}
CLEANUP_NAMES_SHOWN = 20

st.set_page_config(page_title='FrameScout', page_icon='🔎', layout='wide')
st.markdown('''<style>.block-container{padding-top:2rem;max-width:1300px}
.stButton button{border-radius:8px}</style>''', unsafe_allow_html=True)

def store(build, uploads=(), name='', others=(), keep=(), move=False):
    """Save the profile list build(reference_paths) with the profile's reference images.

    reference_paths are the paths in keep (moved into the folder of name if move is set,
    i.e. after a rename) plus copies of the uploads. Returns True on success. On an error
    nothing changes: the message is shown, the new files and names made for this save are
    removed again and the caller keeps its unchanged profile list, which still matches
    the file on disk. The save is refused if profiles.json changed since this page showed
    the profiles the user edited (profiles_shown, A13): then the page is run again with
    emptied edit forms and the message at the top of the profile tab.
    """
    written, staged, refs, new_folder = [], [], list(keep), None
    try:
        if uploads or move:
            # one folder per profile, never one holding references of another profile (A1),
            # named after the profile: a rename moves the profile's files along
            folder = reference_folder(REFS, name, others, BASE)
            new_folder = None if folder.exists() else folder
            if move:
                # old and new names both exist until the save succeeded (crash safety)
                refs, staged = stage_reference_move(refs, folder, REFS, BASE, others)
            # write_new_file never overwrites leftover files in the folder
            for f in uploads:
                suffix = Path(f.name).suffix.lower()
                if suffix in SUPPORTED:
                    written.append(write_new_file(folder, 'reference', suffix, f.getvalue()))
        # keeps the previous file as profiles.json.bak (A2); never overwrites a change made in
        # another tab, session or by hand since the page showed the edited profiles (A13).
        # The next save is based on this saved file, also if the rerun that shows it is
        # interrupted before the forms (review)
        st.session_state.profiles_shown = save_profiles(
            PROFILES, build(refs + [x.relative_to(BASE).as_posix() for x in written]), expected=profiles_shown)
    except (OSError, ValueError) as exc:  # ValueError: e.g. a path that cannot be made relative
        undo_reference_move(staged)
        for x in written:
            try:
                x.unlink()
            except OSError:
                pass
        if new_folder:
            try:
                new_folder.rmdir()  # the folder made for this save; only removed if empty
            except OSError:
                pass
        if isinstance(exc, ProfilesChangedError):
            # the profile at this form's place may now be another one: new widget keys, so
            # that its uploads and "Remove" checkbox are not kept for that profile, and the
            # message at the top of the tab, since the expander of this form may be redrawn
            # closed or no longer exist (review)
            st.session_state.saves = st.session_state.get('saves', 0) + 1
            st.session_state.profile_error = (
                f'Your changes were not saved: {exc}. The page now shows the current search profiles: please '
                'check them and make your changes again. (The input of a new profile is kept.)')
            st.rerun()
        st.error(f'Could not save the search profiles: {exc}. Your changes were not saved.')
        return False
    try:
        # profiles.json.bak still lists the old paths: point it to the new names before the
        # old ones are removed, so restoring the backup keeps working (review)
        update_backup_references(PROFILES, staged, BASE)
    except OSError as exc:
        # keep the old names too, so the backup still points to existing files
        # the next save replaces the backup: the old names are then offered by "Clean up
        # storage" as reference images no profile uses (A43)
        st.session_state.notice = (f'Saved. profiles.json.bak could not be updated ({exc}), so the moved '
                                   'reference images also keep their old names for now. After the next save of '
                                   'the search profiles, "Clean up storage" offers these old files as reference '
                                   'images no profile uses.')
    else:
        problems = finish_reference_move(staged, REFS)
        if problems:
            st.session_state.notice = ('Saved. Some reference images could not be removed from their old folder '
                                       'and now exist twice; the profile uses the new copy: ' + '; '.join(problems))
    # new widget keys for the edit forms: their uploaders would otherwise keep the saved
    # files and add them again on the next save, or pass them to the profile that moves
    # into a deleted profile's place (review)
    st.session_state.saves = st.session_state.get('saves', 0) + 1
    return True







def add_notice(text, first=''):
    """Add text to the one-shot notice at the top of the profile tab; first starts a new notice."""
    # names and error texts (paths) are shown as Markdown: escaped (review)
    st.session_state.notice = (st.session_state.notice + ' ' if 'notice' in st.session_state else first) + plain(text)

def change_name_data(marks_action, folder_action):
    """Run the changes of a renamed or deleted profile's marks and saved copy target folder (A17, A22).

    Both run, also if the first fails. Returns (the result of marks_action or None if it
    failed, the failed parts as text, e.g. "its marks (error)", or '' if none failed).
    """
    results, problems = {}, []
    for what, action in (('marks', marks_action), ('saved copy target folder', folder_action)):
        try:
            results[what] = action()
        except (OSError, ValueError) as exc:
            problems.append(f'its {what} ({exc})')
    return results.get('marks'), ' and '.join(problems)

def carry_over(old, new):
    """Give the marks and the saved target folder of the renamed profile old to its new name (A17)."""
    _, problems = change_name_data(lambda: rename_marks(MARKS, old, new),
                                   lambda: rename_copy_folder(SETTINGS, old, new))
    if problems:
        add_notice(f'The profile was renamed, but {problems} still belong to the old name "{old}".', first='Saved. ')

def deletion_consequences(p):
    """Return the confirmation of deleting the profile p: what happens to its data (A22).

    Returns (its Markdown lines, the number of marks they name, or None if marks.json
    cannot be read).
    """
    name = p['name']
    lines = []
    all_marks, marks_error = load_marks()
    marks = all_marks.get(name, {})
    if marks_error:
        lines.append(f'{MARKS_FILE} cannot be read, so its marks cannot be deleted now: they stay in the file and '
                     f'would pass to a new profile of the same name ({plain(str(marks_error))}).')
    elif marks:
        matches = sum(1 for state in marks.values() if state == MARK_MATCH)
        lines.append(f'Its {count_text(len(marks), "mark", "marks")} ({matches:,} match, {len(marks) - matches:,} '
                     f'no match) in {RESULTS.name}/{MARKS_FILE} {"is" if len(marks) == 1 else "are"} deleted with '
                     'it. This cannot be undone.')
    else:
        lines.append('It has no marks.')
    try:
        saved = cached_copy_folders(*version_key(SETTINGS)).get(name)
    except FileNotFoundError:
        saved = None
    except (OSError, ValueError) as exc:
        lines.append(f'{SETTINGS.name} cannot be read, so a saved copy target folder of it cannot be removed now '
                     f'({plain(str(exc))}).')
        saved = None
    # the folder typed in this session that settings.json could not save is used instead of
    # the saved one (copy_folder_value) and is forgotten as well (review)
    unsaved = st.session_state.get('copy_folders_unsaved', {}).get(name)
    if unsaved is not None:
        lines.append(f'The copy target folder {plain(unsaved) or "(empty)"} typed for it in this session (not saved '
                     f'in {SETTINGS.name}) is forgotten. The folder and the photos copied into it stay where they are.')
    if saved:
        lines.append(f'Its saved copy target folder {plain(saved)} is removed from the settings. The folder and the '
                     'photos copied into it stay where they are.')
    elif unsaved is None:
        lines.append('Photos copied for it stay where they are.')
    refs = p.get('reference_images', [])
    if refs:
        lines.append(f'Its {count_text(len(refs), "reference image", "reference images")} '
                     f'{"stays" if len(refs) == 1 else "stay"} in the references folder, since the backup '
                     'profiles.json.bak still names the profile; "Clean up storage" can delete '
                     f'{"it" if len(refs) == 1 else "them"} later.')
    return lines, None if marks_error else len(marks)

def forget_profile(name, named):
    """Delete the marks and the saved copy target folder of the deleted profile name (A22).

    Called after the deletion is saved; the folder itself and the copies in it are never
    touched. named: the number of marks the confirmation named (None: it could not read
    them). A different number of deleted marks (marked or unmarked since the question)
    and a part that cannot be removed are named in the notice at the top of the tab.
    """
    st.session_state.get('copy_folders_unsaved', {}).pop(name, None)
    deleted, problems = change_name_data(lambda: delete_marks(MARKS, name), lambda: forget_copy_folder(SETTINGS, name))
    if deleted is not None and deleted != (named or 0):
        add_notice(f'The profile "{name}" was deleted with {count_text(deleted, "mark", "marks")}: '
                   + (f'{MARKS_FILE} could not be read when you were asked, but could be read again by then.'
                      if named is None else
                      f'the question named {named:,}, but photos of it were marked or unmarked after it was shown '
                      '(in the gallery, another tab or another window).'))
    if problems:
        add_notice(f'The profile was deleted, but {problems} could not be removed: they still belong to the name '
                   f'"{name}" and would pass to a new profile of that name.')



def cleanup_signature():
    """The cache signature of the current settings: its entries are never offered for deletion (E11)."""
    return feature_signature(settings['person_detection'], settings['max_persons'], settings['person_confidence'],
                             DEFAULT_YOLO_MODEL, model=settings['model'])

def cleanup_inputs():
    """What a cleanup scan was classified for: a scan of other values is out of date (E22 review).

    Not the photo folders: unbound photos are looked for wherever they were (E8/A21).
    """
    return cleanup_signature(), settings['model']

def cleanup_offered(category):
    return not category['problem'] and bool(category['items'])

def scan_storage():
    """Look for what the cleanup can delete and select the default categories (E7)."""
    bar = st.progress(0.0, text='Checking which photos still exist …')

    def progress(done, total):
        # the slow part: one look per folder of the cached and marked photos (E8/A21)
        bar.progress(done / total, text=f'Checking which photos still exist … {done:,} of {total:,} folders')

    try:
        # rows of the other search models are a category of their own, kept by default (E22)
        scan = scan_cleanup(RESULTS, PROFILES, REFS, cleanup_signature(), current_model=settings['model'],
                            progress=progress)
    except OSError as exc:
        st.session_state.cleanup_notice = ('warning', f'The storage could not be scanned: {exc}')
        return
    finally:
        bar.empty()
    st.session_state.cleanup_scan = scan
    st.session_state.cleanup_scan_inputs = cleanup_inputs()
    st.session_state.cleanup_confirm = False
    for key, category in scan.items():
        # set before the checkboxes are drawn, never as their value= (they have keys)
        st.session_state['cleanup_' + key] = bool(category['default'] and cleanup_offered(category))
    st.session_state.cleanup_vacuum = True

def delete_storage(scan, selected):
    """Delete the selected categories of scan after the confirmation; the summary is shown next run (E7)."""
    try:
        with st.spinner('Cleaning up …'):
            summary = clean_up(RESULTS, scan, selected, st.session_state.get('cleanup_vacuum', False), engine_alive,
                               PROFILES, REFS, cleanup_signature(), current_model=settings['model'])
    except Exception as exc:
        # clean_up reports the errors of its steps in the summary; this is e.g. the lock file
        # that cannot be opened. The scan is dropped: some files may be gone (review)
        st.session_state.cleanup_notice = ('warning', f'The cleanup stopped: {exc}. Scan again to see what is left.')
        st.session_state.pop('cleanup_scan', None)
        return
    if summary['refused']:
        st.session_state.cleanup_notice = ('warning', summary['refused'] + ' Nothing was deleted.')
        return
    text = cleanup_summary_text(summary) + '.'
    problems = [f'{name}: {why}' for name, why in summary['failed'][:10]]
    if len(summary['failed']) > 10:
        problems.append('…')
    if problems:
        text += ' Not deleted: ' + '; '.join(problems) + '.'
    if summary['skipped']:
        text += ' ' + ' '.join(summary['skipped'])
    st.session_state.cleanup_notice = ('warning' if problems or summary['skipped'] else 'success', text)
    st.session_state.pop('cleanup_scan', None)

def show_cleanup():
    """The expander "Clean up storage": scan, choose categories, delete permanently after a confirmation (E7)."""
    st.caption('Lists files and cache entries FrameScout no longer needs, and marks of photos that no longer exist '
               'at their path ("unbound": deleted, renamed or moved). Your photos, the marks file (marks.json), '
               'the results of the last search, your profiles and settings are never deleted; single marks only '
               'if you select them. Deleting is permanent: nothing goes to the Recycle Bin.')
    if st.button('Scan', disabled=active,
                 help='Only looks; nothing is deleted yet. Checks whether every cached or marked photo still '
                      'exists, which can take a while for a large cache or a network share.'):
        scan_storage()
    if 'cleanup_notice' in st.session_state:
        kind, text = st.session_state.pop('cleanup_notice')
        (st.success if kind == 'success' else st.warning)(plain(text))
    scan = st.session_state.get('cleanup_scan')
    if scan and st.session_state.get('cleanup_scan_inputs') != cleanup_inputs():
        # e.g. another search model: the scan would offer the rows of the model chosen now
        st.session_state.pop('cleanup_scan', None)
        st.caption('The AI settings changed since the scan. Scan again.')
        return
    if not scan:
        return
    for key in CLEANUP_CATEGORIES:
        category = scan[key]
        label, explanation = CLEANUP_LABELS[key]
        if category['problem']:
            st.caption(f"{label}: {plain(category['problem'])}")
            continue
        # e.g. a drive or network share that is not reachable now, not checked (E8/A21)
        notes = ' '.join(category.get('notes', []))
        if not cleanup_offered(category):
            st.caption(f'{label}: nothing to clean up.' + (f' {plain(notes)}' if notes else ''))
            continue
        if key.startswith('cache_'):
            amount = f"{count_text(category['rows'], 'entry', 'entries')} · about {size_text(category['size'])}"
        elif key.startswith('marks_'):
            amount = count_text(len(category['items']), 'mark', 'marks')
        else:
            amount = f"{count_text(len(category['items']), 'file', 'files')} · {size_text(category['size'])}"
        st.checkbox(f'{label} – {amount}', key='cleanup_' + key, help=explanation, disabled=active)
        if notes:
            st.caption(plain(notes))
        if category.get('thumbnails'):
            # the thumbnails only these galleries show go with them (review)
            st.caption(f"Together with {count_text(len(category['thumbnails']), 'thumbnail', 'thumbnails')} "
                       f"({size_text(category['thumbnails_size'])}) that only these galleries show.")
        if category['names']:
            names = category['names'][:CLEANUP_NAMES_SHOWN]
            more = len(category['names']) - len(names)
            st.caption(plain(', '.join(names)) + (f' and {more:,} more' if more else ''))
    if any(cleanup_offered(scan[key]) for key in CACHE_CATEGORIES):
        st.checkbox(f'Compact {CACHE_FILE} afterwards', key='cleanup_vacuum',
                    help='Without compacting, the file keeps its size and reuses the space for new analyses. '
                         'Compacting can take a while for a large cache.', disabled=active)
    selected = [key for key in CLEANUP_CATEGORIES
                if cleanup_offered(scan[key]) and st.session_state.get('cleanup_' + key)]
    if not st.session_state.get('cleanup_confirm'):
        if st.button('Delete selected', disabled=active or not selected):
            st.session_state.cleanup_confirm = True
            st.rerun()
        return
    st.warning('Delete the selected items permanently? They do not go to the Recycle Bin, and this cannot be '
               'undone. Only what this scan listed and is still unused now is deleted.')
    c1, c2 = st.columns(2)
    yes = c1.button('Yes, delete permanently', type='primary', disabled=active or not selected)
    if c2.button('Cancel'):
        st.session_state.cleanup_confirm = False
        st.rerun()
    if yes:
        st.session_state.cleanup_confirm = False
        delete_storage(scan, selected)
        st.rerun()

def check_cache_now():
    """Run the cache check (F1); its result is shown below the button until a search starts or the file changes."""
    try:
        with st.spinner(f'Checking {CACHE_FILE} …'):
            st.session_state.cache_check = check_cache(RESULTS, engine_alive)
    except Exception as exc:  # e.g. the lock file cannot be created
        st.session_state.pop('cache_check', None)
        st.session_state.cache_notice = ('warning', f'The cache could not be checked: {exc}')

def set_damaged_cache_aside(expected):
    """Rename the damaged cache the check found (F1); the outcome is shown next run."""
    st.session_state.pop('cache_check', None)
    try:
        done = set_cache_aside(RESULTS, engine_alive, expected)
    except Exception as exc:
        st.session_state.cache_notice = ('warning', f'{CACHE_FILE} was not renamed: {exc}')
        return
    if done['refused']:
        st.session_state.cache_notice = ('warning', done['refused'] + ' Nothing was renamed.')
        return
    st.session_state.pop('cleanup_scan', None)  # the scan listed rows of the old cache
    new, *sides = done['renamed']
    st.session_state.cache_notice = (
        'success', f'Renamed {CACHE_FILE} to {new}' + (f" (with {', '.join(sides)})" if sides else '') +
        '. The next search builds a new cache and analyzes all photos again, which takes about as long as the '
        f'first search. Once you no longer need {new}, "Clean up storage" offers it as a damaged file set aside.')

def show_cache_check():
    """"Check cache" in "Clean up storage": SQLite's quick check of the cache, a damaged one set aside (F1)."""
    st.caption(f'Check cache: looks for damage in {CACHE_FILE} (e.g. after a full disk or a power loss), which '
               'otherwise shows only as errors during a search. It reads the whole file, which can take a few '
               'seconds for a large cache, and cannot run while a search runs.')
    if st.button('Check cache', disabled=active):
        check_cache_now()
    if 'cache_notice' in st.session_state:
        kind, text = st.session_state.pop('cache_notice')
        (st.success if kind == 'success' else st.warning)(plain(text))
    result = st.session_state.get('cache_check')
    if not result:
        return
    if not cache_check_current(RESULTS, result):
        # e.g. compacted by a cleanup or written by a search of another tab: the result and
        # its rename offer no longer apply (review)
        st.session_state.pop('cache_check', None)
        st.caption(f'{CACHE_FILE} changed since the check. Check it again.')
        return
    details = plain('; '.join(result['details'][:5]))
    if result['refused']:
        st.warning(plain(result['refused']))
    elif result['state'] == 'missing':
        st.info(f'There is no {CACHE_FILE} yet: the first search creates it.')
    elif result['state'] == 'ok':
        st.success(f"SQLite's quick check found no damage in {CACHE_FILE}.")
    elif result['state'] == 'unchecked':
        st.warning(f'{CACHE_FILE} could not be checked ({details}). Nothing was changed. Try again later, e.g. '
                   'after closing other programs that may have the file open.')
    else:
        rename = plain(f'{CACHE_FILE}.broken-<date and time>: it stays in the results folder until you delete it '
                       'as a damaged file set aside in "Clean up storage", '
                       'and the next search builds a new cache and analyzes all photos again, which takes about as '
                       'long as the first search. Your marks, results, profiles and photos are not affected.')
        if result['state'] == 'unreadable':
            # a disk I/O error: a bad sector, or a drive that is not reachable now (review)
            st.error(f'{CACHE_FILE} could not be read, so a search may fail or stop with an error. SQLite reports: '
                     f'{details}. This can be a damaged spot on the disk, or a drive or network share that is not '
                     f'reachable at the moment.\n\nIf the error stays when you check again, you can rename it to '
                     + rename)
        else:
            st.error(f'{CACHE_FILE} is damaged, so a search may fail or stop with an error. SQLite reports: '
                     f'{details}\n\nYou can rename it to ' + rename)
        st.button(f'Rename the damaged {CACHE_FILE}', on_click=set_damaged_cache_aside, args=(result['file'],),
                  disabled=active, key='cache_set_aside')




st.title('🔎 FrameScout')
st.caption('Local AI search in large photo collections · your images stay on your computer')

# "Find similar" clicked on a result card (F11): its fragment asked this page run to start it.
# Taken at once, so a page run that stops early (e.g. at an unreadable profiles.json) drops it
# instead of leaving it for a later run to start unexpectedly (review); handled under "Start search"
find_similar_request = st.session_state.pop('find_similar', None)

clean_project_folder()
try:
    create_from_example(PROFILES, EXAMPLE_PROFILES)  # first start only; never overwrites
except OSError as exc:  # e.g. a read-only project folder
    st.error(f'Could not create profiles.json from {windows_path(EXAMPLE_PROFILES_FILE)}: {exc}. '
             'Check that the project folder is writable.')
    st.stop()
try:
    profiles, profiles_version = read_profiles_versioned(PROFILES)
except (OSError, ValueError) as exc:
    # never save over a file the app cannot read (A2)
    st.error('profiles.json cannot be read, so FrameScout does not change it. Fix it in a text '
             f'editor, or restore the backup profiles.json.bak if there is one.\n\nDetails: {exc}')
    st.stop()
# A13: the version of profiles.json that the profile forms of the last complete page showed.
# A form submit reruns the page and reads the file again; store() saves only if the file is
# still at this version, so an edit based on what the page showed never overwrites a change
# made in another tab or session or by hand. Updated after the forms are shown (below), so
# a run interrupted before them keeps the older version: a save is then refused, not lost;
# and by this session's own successful save (store), so that it never refuses the next one.
profiles_shown = st.session_state.get('profiles_shown', profiles_version)

# whether a search runs, also after a reload or in another tab (A4)
active, run_status = run_state()
st.session_state.page_run_state = (active, run_status)

# the settings of the widgets, synchronized with settings.json (A8)
settings, seen, shown, settings_taken_over = sync_settings()
# the folders as the image count, the Start check and the engine use them (review: ~ expanded)
photo_folders = [Path(folder).expanduser() for folder in settings['photo_folders']]
# a folder listed twice or inside another listed folder is searched once (A25)
search_folders, dropped_folders = distinct_folders([folder.resolve() for folder in photo_folders])
p_tab, f_tab, settings_tab, run_tab = st.tabs(['Search profiles', 'Photo source', 'AI settings', 'Search & results'])

with p_tab:
    st.subheader('Saved search profiles')
    # first, so that a one-shot save notice is not missed below the static hint (review)
    if 'notice' in st.session_state:
        st.warning(st.session_state.pop('notice'))
    if 'profile_error' in st.session_state:  # a save refused by store() (A13)
        st.error(st.session_state.pop('profile_error'))
    elif profiles_notice := profiles_changed_notice(profiles_shown, profiles_version):
        # A31: the file changed since the last complete page, e.g. a profile was deleted in
        # another session: a click on a form this page no longer draws was dropped by
        # Streamlit, so say so (a click on a form still drawn is refused by store instead).
        # Only this first run after the change can carry such a click: it redraws the forms
        st.warning(profiles_notice)
    # hint only, no check of the input (user decision on E3: English search terms only);
    # one box with the call to action on an empty list (review)
    st.info(('Create a search profile first. ' if not profiles else '') +
            'Enter the search motif, context, features and custom search texts **in English**. The CLIP model '
            'FrameScout uses understands practically only English: a word in another language, e.g. German '
            '"Schwert" instead of "sword", can find completely different photos.')
    saves = st.session_state.get('saves', 0)
    # "Delete profile" asks first (A8, A22): the profile name and the save count of the click.
    # Any save since (also a refused one) or the profile's disappearance ends the question
    if st.session_state.get('delete_pending') not in [(p['name'], saves) for p in profiles]:
        st.session_state.pop('delete_pending', None)
    for index, p in enumerate(profiles):
        with st.expander(f"{p['name']}  ·  {p.get('franchise','')}"):
            with st.form(f'edit_{index}_{saves}'):
                edit_name = st.text_input(LABEL_NAME, value=p['name'])
                franchise = st.text_input(LABEL_CONTEXT, value=p.get('franchise', ''))
                features = st.text_area(LABEL_FEATURES, value=p.get('features', ''))
                prompts = st.text_area(LABEL_PROMPTS, value='\n'.join(p.get('prompts', [])))
                st.caption('Existing reference images: ' + (', '.join(p.get('reference_images', [])) or 'none'))
                refs_new = st.file_uploader('Add reference images', type=UPLOAD_TYPES, accept_multiple_files=True, key=f'edit_refs_{index}_{saves}')
                clear_refs = st.checkbox('Remove the existing reference images from this profile')
                c1,c2 = st.columns(2)
                update = c1.form_submit_button('Save changes', disabled=active)
                delete = c2.form_submit_button('Delete profile', disabled=active)
            if update:
                edit_name = edit_name.strip()
                if not edit_name or any(j != index and q['name'].strip().lower() == edit_name.lower() for j,q in enumerate(profiles)):
                    st.error('The profile name must be unique and must not be empty.')
                else:
                    def edited(refs, index=index, p=p):
                        # {**p, ...} keeps keys the form does not edit (A2)
                        return profiles[:index] + [{**p, 'name': edit_name, 'franchise': franchise.strip(),
                                'features': features.strip(), 'reference_images': refs,
                                'prompts': [x.strip() for x in prompts.splitlines() if x.strip()]}] + profiles[index+1:]
                    others = profiles[:index] + profiles[index+1:]
                    keep = [] if clear_refs else p.get('reference_images', [])
                    # a renamed profile's reference folder follows the new name (A1)
                    if store(edited, refs_new or [], edit_name, others, keep, move=edit_name != p['name']):
                        if edit_name != p['name']:
                            carry_over(p['name'], edit_name)  # its marks and copy folder follow the name (A17)
                        st.rerun()
            if delete:
                # run again before any question is drawn: a question still open for a profile
                # above this one would otherwise be shown too in this run (review)
                st.session_state.delete_pending = (p['name'], saves)
                st.rerun()
            if st.session_state.get('delete_pending') == (p['name'], saves):
                question = st.container()  # filled below the buttons, see there
                c1, c2 = st.columns(2)
                confirmed = c1.button('Delete for good', type='primary', key=f'delete_yes_{index}_{saves}',
                                      disabled=active)
                c2.button('Cancel', key=f'delete_no_{index}_{saves}', on_click=st.session_state.pop,
                          args=('delete_pending', None))
                # new lists instead of changing profiles in place: after a failed save the page
                # keeps showing (and the search uses) exactly what is in profiles.json. A save
                # refused since profiles.json changed (A13) ends the question: the page shows
                # the current profiles, and the user decides again
                if confirmed and store(lambda _, index=index: profiles[:index] + profiles[index+1:]):
                    # its marks and saved copy folder go with it (A22), compared with the number
                    # of marks the question the user answered named (review)
                    forget_profile(p['name'], st.session_state.get('delete_marks_named'))
                    st.rerun()
                # after the click is handled: the number the user saw is the one of the run before
                lines, st.session_state.delete_marks_named = deletion_consequences(p)
                question.warning(f'**Delete the profile "{plain(p["name"])}" for good?**\n\n'
                                 + '\n'.join('- ' + line for line in lines))
    st.divider()
    st.subheader('New search profile')
    # the form is emptied only after a successful save, by giving its widgets new keys;
    # after an error the input stays for another try
    form_id = st.session_state.setdefault('new_profile_form', 0)
    with st.form('new_profile'):
        name = st.text_input(LABEL_NAME + ' *', placeholder='e.g. red car, golden retriever, mountain landscape', key=f'new_name_{form_id}')
        franchise = st.text_input(LABEL_CONTEXT, placeholder='e.g. vehicles, pets, nature', key=f'new_context_{form_id}')
        features = st.text_area(LABEL_FEATURES, placeholder='red bodywork, black roof, parked on a street', key=f'new_features_{form_id}')
        prompts = st.text_area(LABEL_PROMPTS, key=f'new_prompts_{form_id}')
        uploads = st.file_uploader('Reference images (optional)', type=UPLOAD_TYPES, accept_multiple_files=True, key=f'new_refs_{form_id}')
        create = st.form_submit_button('Add profile', disabled=active)
    if create:
        name = name.strip()
        if not name or any(x['name'].strip().lower() == name.lower() for x in profiles):
            st.error('Please enter a unique name.')
        else:
            def added(refs):
                return profiles + [{'name':name, 'franchise':franchise.strip(), 'features':features.strip(),
                                    'prompts':[x.strip() for x in prompts.splitlines() if x.strip()], 'reference_images':refs}]
            if store(added, uploads or [], name, profiles):
                st.session_state.new_profile_form = form_id + 1
                st.rerun()
    st.caption('FrameScout automatically creates several English CLIP search texts from the name, context and features; '
               'it does not translate them. No language model is required.')
    # the forms above show this version now: the next submit is based on it (A13)
    st.session_state.profiles_shown = profiles_version

with f_tab:
    st.subheader('Photo collection')
    st.text_area('Local photo folders (one per line, including subfolders)', key=setting_key('photo_folders'),
                 disabled=active, help='One search covers all listed folders, e.g. event folders on several '
                                       'drives. A folder inside another listed folder is searched as part of it.')
    # per listed folder (A25): its photo count, or why it is not searched on its own. The
    # folders are scanned together, as the engine scans them (E25), so the numbers match its
    # log; a photo reached through a link into another listed folder counts once, for the
    # folder it is really in (A29). The count is remembered for this browser session and
    # repeated only when the existing folders, the readable formats or the output folder
    # change, or on "Recount" (A27): not on every widget click, which walked the whole
    # photo tree each time. Whether a folder exists is checked on every page run.
    existing = [folder for folder in search_folders if folder.is_dir()]
    missing_folders = [folder for folder in search_folders if folder not in existing]
    scans, counted_at = remembered_scans(st.session_state.setdefault('photo_count', {}), existing, SUPPORTED,
                                         RESULTS, recount=st.session_state.pop('recount_photos', False))
    folder_scans = list(zip(existing, scans))
    photo_scan = join_scans(scans)
    if len(search_folders) == 1 and folder_scans:
        st.success(f'{len(photo_scan.paths):,} supported image files found.')
    elif folder_scans:
        st.success(f'{len(photo_scan.paths):,} supported image files found in {len(folder_scans)} folders.')
        for folder, scan in folder_scans:
            st.caption(plain(f"{folder}: {count_text(len(scan.paths), 'supported image file', 'supported image files')}"))
    if folder_scans:
        c1, c2 = st.columns([3, 1])
        c1.caption(f"Counted at {time.strftime('%H:%M:%S', time.localtime(counted_at))}. Photos added or removed "
                   'since are counted after "Recount"; a search always reads the folders again.')
        c2.button('Recount', key='recount_button', on_click=st.session_state.__setitem__,
                  args=('recount_photos', True), help='Count the photos in the listed folders again.')
    for _, note in dropped_folders:  # listed twice or inside another listed folder
        st.caption(plain(note))
    if not photo_folders:
        st.warning('Enter a photo folder.')
    elif len(search_folders) == 1 and missing_folders:
        st.warning('The folder does not exist yet. Create it or choose an existing image folder.')
    else:
        for folder in missing_folders:
            st.warning(plain(f'{folder} does not exist (e.g. a disconnected drive); the search leaves it out.'))
    # a missing decoder is named only if the folders have files of it (review)
    for line in skipped_lines(photo_scan, DECODERS):
        st.caption(line)
    st.caption('Supports JPG, PNG, WebP, BMP, TIFF, AVIF, HEIC/HEIF and camera RAW (DNG, CR2, CR3, NEF, ARW, ORF, '
               'RW2, RAF, PEF, SRW; a RAW file next to a JPEG or HEIC of the same name is skipped). '
               'FrameScout searches local files and does not download images from online services.')
    # F18: "Analyze photos now", filled in the run tab's code below, which knows the AI
    # settings, the analyzed photos and how to start the engine
    analyze_area = st.container()

with settings_tab:
    info, model_missing = show_ai_settings(settings, seen, shown, active)

with run_tab:
    st.subheader('Start search')
    c1,c2 = st.columns([1,1])
    with c1:
        # at least one listed folder must exist (as sorted out in the Photo source tab, without
        # asking the file system again, review); the engine leaves out the others with a note (A25).
        # A search model without its package would only fail in the engine (E22 review)
        start = st.button('▶ Start search', type='primary', width='stretch',
                          disabled=active or not profiles or not folder_scans or bool(model_missing))
    with c2:
        # a cleanup holding the run lock is no search to stop (review)
        stop = st.button('■ Stop search', disabled=not active or cleanup_running(RESULTS), width='stretch',
                         help='Stops the running search, also an analysis started with "Analyze photos now" in the '
                              'tab "Photo source". Photos analyzed so far are kept in the cache.')
    def start_engine(notice='run_notice', **search):
        """Start the engine with the current settings: search is profiles=..., quick_query=... (F10), like=... (F11)
        or analyze_only=True (F18).

        notice: the session key of the note shown where the click was, if the start failed.
        """
        what = 'analysis' if search.get('analyze_only') else 'search'
        if settings_taken_over:
            # the page showed other values until this click: never start with settings the
            # user has not seen (review)
            st.session_state[notice] = (f'The {what} was not started: another tab or window changed these settings '
                                        'meanwhile: ' + ', '.join(settings_taken_over) + '. Check the settings '
                                        'shown now and start again.')
            st.rerun()
        cmd = engine_command(sys.executable, BASE / 'framescout_engine.py', search_folders, RESULTS, settings,
                             st.session_state[setting_key('device')], **search)
        st.session_state.pop('cleanup_scan', None)  # the search changes what a cleanup finds (E7)
        st.session_state.pop('cache_check', None)  # and the cache a check looked at (F1)
        try:
            problem = start_run(cmd, analyze_only=bool(search.get('analyze_only')))
        except Exception as exc:
            problem = f'Start failed: {exc}'
        # kept for the next page run: the state may have changed, which reruns the page
        st.session_state[notice] = problem
        st.rerun()
    if start:
        start_engine(profiles=PROFILES)
    if find_similar_request:
        # the card's button may have been drawn before a search started (its fragment reruns
        # alone): never dropped without a word (review)
        if active:
            st.session_state.run_notice = ('"Find similar" was not started: a search is running already. Try again '
                                           'when it has finished.')
        else:
            start_engine(like=find_similar_request[0], like_part=find_similar_request[1])
    if stop:
        try:
            st.session_state.run_notice = stop_run()
        except Exception as exc:
            st.session_state.run_notice = f'Stop failed: {exc}'
        st.rerun()
    if st.session_state.get('run_notice'):
        st.warning(st.session_state.pop('run_notice'))
    if model_missing and not active:
        st.warning(model_missing)  # why Start is not available
    analyzed = None  # the photos analyzed with these settings: counted only while no search runs
    quick_counts = None  # quick_scope: (analyzed, not analyzed, partners) of a quick search, as the engine counts (E61)
    analysis_text = None  # what "Analyze photos now" would do (F18)
    analysis_space = None  # and its low disk space warning (review)
    if folder_scans and not active:
        try:
            cache_key = file_key(RESULTS / CACHE_FILE)
        except OSError:  # no cache yet
            cache_key = None
        # photos analyzed with these settings need no new cache rows (review: else a large,
        # analyzed collection kept the warning for good)
        quick_counts = cached_analyzed_photos(cache_key, cleanup_signature(),
                                              (tuple(map(str, existing)), counted_at), photo_scan)
        analyzed = quick_counts[0]
        # what the search will do and, if an earlier search with these settings measured its
        # speed on this device, roughly how long its analysis takes (F12). "auto" picks CUDA
        # if PyTorch can use it; without the system details any device's record counts
        chosen_device = st.session_state[setting_key('device')]
        if chosen_device == 'auto':
            chosen_device = ('cuda' if info['cuda'] else 'cpu') if info else None
        # and scoring and the gallery thumbnails at the speeds of earlier searches (F16)
        finishing = finishing_minutes((run_status or {}).get('finishing'), len(photo_scan.paths),
                                      gallery_thumbnails(len(photo_scan.paths), settings['top'], len(profiles)))
        per_minute = known_throughput(run_status, cleanup_signature(), chosen_device)
        st.info(start_summary(len(photo_scan.paths), analyzed, per_minute, finishing))
        # a JPEG/HEIC searched through another file of its shot (its RAW file, E30, or another
        # partner) never gets a row of its own, however often it is analyzed: done for the
        # analysis, as for the quick search (review)
        analysis_done = analyzed + quick_counts[2]
        analysis_text = start_summary(len(photo_scan.paths), analysis_done, per_minute, analysis_only=True)
        space_warning = low_space_warning(len(photo_scan.paths), settings['top'], len(profiles), settings['model'],
                                          settings['person_detection'], analyzed)
        if space_warning:
            st.warning(space_warning)
        # the analysis writes the cache rows without gallery thumbnails (no profile), and is
        # started from the tab "Photo source", where the warning above is not shown (review)
        analysis_space = low_space_warning(len(photo_scan.paths), settings['top'], 0, settings['model'],
                                           settings['person_detection'], analysis_done, analysis=True)
    with analyze_area:
        # F18: the analysis of a search without the search, e.g. overnight before the profiles
        # are written; it runs like a search (run lock, status, stop button, low priority)
        st.subheader('Analyze ahead')
        st.caption('Analyzing the photos is the slow part of a first search. "Analyze photos now" analyzes the photos '
                   'of the listed folders with the current AI settings and keeps the analyses in the cache, without '
                   'searching: no search profile is needed, and the results of the last search stay as they are. '
                   'A later search with the same search model and person detection settings only ranks these photos, '
                   'and the quick search can search them; after a change of these settings, the photos are analyzed '
                   'again. Its progress and the button to stop it are in the tab "Search & results"; "Keep the PC '
                   'responsive" applies to it as to a search.')
        st.caption(f"Current settings: search model {MODELS[settings['model']].label} · person detection "
                   f"{'on' if settings['person_detection'] else 'off'}.")
        if st.session_state.get('analyze_notice'):
            st.warning(st.session_state.pop('analyze_notice'))
        # not gated on the photo count: it is the one remembered for the browser session (A27),
        # while the engine reads the folders again, e.g. for photos added since (review)
        analyze_now = st.button('Analyze photos now', disabled=active or not folder_scans or bool(model_missing))
        if active:
            st.info('Not available while a search or an analysis runs (its progress is shown in the tab "Search & '
                    'results") or the storage is being cleaned up.')
        elif analysis_text:
            st.info(analysis_text)
        if analysis_space and not active:
            st.warning(analysis_space)
        if model_missing and not active:
            st.warning(model_missing)  # why the button is not available
    if analyze_now:
        start_engine(notice='analyze_notice', analyze_only=True)
    show_status(active)
    st.divider()
    # F10: one search text over the photos already analyzed, without a profile and without
    # analyzing; its result goes to results/quick/, the profiles' results and marks stay
    st.subheader('Quick search')
    st.caption('Try a search text without creating a search profile. Only the photos already analyzed with the '
               'current AI settings are searched; nothing new is analyzed, so it is fast. Its result replaces the '
               f'previous quick search (folder {QUICK_DIR} in the results folder); the results and marks of your '
               'search profiles stay as they are. Search texts are in English. "Find similar" on a result card '
               'searches the same way by the image similarity with that photo, and its result appears here too.')
    with st.form('quick_search', border=False):
        c1, c2 = st.columns([4, 1], vertical_alignment='bottom')
        c1.text_input('Search text (in English)', key='quick_query', max_chars=QUICK_QUERY_MAX, disabled=active,
                      placeholder='e.g. a red car in the snow')
        quick_start = c2.form_submit_button('Quick search', width='stretch',
                                            disabled=active or not folder_scans or bool(model_missing)
                                            or (quick_counts is not None and not (quick_counts[0] or quick_counts[2])))
    if quick_counts is not None:
        st.caption(quick_scope_text(len(photo_scan.paths), *quick_counts))
    if quick_start:
        query = ' '.join(str(st.session_state.get('quick_query') or '').split())
        if query:
            start_engine(quick_query=query)
        else:
            st.warning('Type a search text first.')
    quick_results, quick_error = load_results(QUICK_JSON)
    if quick_error:
        st.warning(f'The result file of the last quick search ({QUICK_DIR}/{RESULTS_FILE}) cannot be read, so its '
                   f'results are not shown here. The next quick search writes it anew.\n\n'
                   f'Details: {plain(str(quick_error))}')
    if quick_results:
        with st.expander('Results of the last quick search or "Find similar"', expanded=True):
            show_quick_results(quick_results, search_folders, settings['model'], active or not folder_scans)
    st.divider()
    st.subheader('Results')
    # the galleries of the last complete search, as the engine wrote them (A12)
    last_results, results_error = load_results()
    if results_error:
        st.warning(f'{RESULTS_FILE} cannot be read, so the results of the last search are not shown here. Starting '
                   f'the search again writes it anew.\n\nDetails: {plain(str(results_error))}')
    if last_results:
        # a copy target must not be in a photo folder of this search or of the next one (A17, A25)
        show_results(last_results, [*last_results['photo_folders'], *map(str, photo_folders)], settings['model'],
                     active or not folder_scans)
    elif RESULTS.is_dir() and (old_pages := sorted(RESULTS.glob('*.html'))):
        # galleries of a search before results.json: listed by file name, since the
        # current profile list may no longer match them (A12)
        st.caption('These galleries come from a search by an earlier FrameScout version. Start the search again '
                   'to see its results here.')
        for page in old_pages:
            st.download_button(f'Download {page.name}', page.read_bytes(), file_name=page.name, mime='text/html',
                               key=f'dl_{page.name}')
            st.caption(f'Open the local gallery: {plain(str(page))}')
        st.button('Open results folder', on_click=open_results_folder)
        if st.session_state.get('gallery_notice'):
            st.warning(plain(st.session_state.pop('gallery_notice')))  # paths: no Markdown
    else:
        st.caption('After the first search run, its results appear here.')
    st.caption('The HTML galleries in the results folder link to the local thumbnails and original photos; keep '
               'the results folder together for the complete gallery.')
    with st.expander('Clean up storage'):
        show_cleanup()
        st.divider()
        show_cache_check()
