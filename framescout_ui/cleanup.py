"""The expander "Clean up storage": the storage cleanup and the cache check (E7, E11, F1, A46)."""
import streamlit as st

from framescout_core import (CACHE_CATEGORIES, CACHE_FILE, CLEANUP_CATEGORIES, DEFAULT_YOLO_MODEL,
                             cache_check_current, check_cache, clean_up, cleanup_summary_text, count_text,
                             feature_signature, scan_cleanup, set_cache_aside, size_text)

from .common import PROFILES, REFS, RESULTS, plain
from .run import engine_alive


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


def cleanup_signature(settings):
    """The cache signature of the current settings: its entries are never offered for deletion (E11)."""
    return feature_signature(settings['person_detection'], settings['max_persons'], settings['person_confidence'],
                             DEFAULT_YOLO_MODEL, model=settings['model'])


def cleanup_inputs(settings):
    """What a cleanup scan was classified for: a scan of other values is out of date (E22 review).

    Not the photo folders: unbound photos are looked for wherever they were (E8/A21).
    """
    return cleanup_signature(settings), settings['model']


def cleanup_offered(category):
    return not category['problem'] and bool(category['items'])


def scan_storage(settings):
    """Look for what the cleanup can delete and select the default categories (E7)."""
    bar = st.progress(0.0, text='Checking which photos still exist …')

    def progress(done, total):
        # the slow part: one look per folder of the cached and marked photos (E8/A21)
        bar.progress(done / total, text=f'Checking which photos still exist … {done:,} of {total:,} folders')

    try:
        # rows of the other search models are a category of their own, kept by default (E22)
        scan = scan_cleanup(RESULTS, PROFILES, REFS, cleanup_signature(settings), current_model=settings['model'],
                            progress=progress)
    except OSError as exc:
        st.session_state.cleanup_notice = ('warning', f'The storage could not be scanned: {exc}')
        return
    finally:
        bar.empty()
    st.session_state.cleanup_scan = scan
    st.session_state.cleanup_scan_inputs = cleanup_inputs(settings)
    st.session_state.cleanup_confirm = False
    for key, category in scan.items():
        # set before the checkboxes are drawn, never as their value= (they have keys)
        st.session_state['cleanup_' + key] = bool(category['default'] and cleanup_offered(category))
    st.session_state.cleanup_vacuum = True


def delete_storage(scan, selected, settings):
    """Delete the selected categories of scan after the confirmation; the summary is shown next run (E7)."""
    try:
        with st.spinner('Cleaning up …'):
            summary = clean_up(RESULTS, scan, selected, st.session_state.get('cleanup_vacuum', False), engine_alive,
                               PROFILES, REFS, cleanup_signature(settings), current_model=settings['model'])
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


def show_cleanup(settings, active):
    """The expander "Clean up storage": scan, choose categories, delete permanently after a confirmation (E7).

    settings: the settings of this page run; active: whether a search runs (nothing can be deleted then).
    """
    st.caption('Lists files and cache entries FrameScout no longer needs, and marks of photos that no longer exist '
               'at their path ("unbound": deleted, renamed or moved). Your photos, the marks file (marks.json), '
               'the results of the last search, your profiles and settings are never deleted; single marks only '
               'if you select them. Deleting is permanent: nothing goes to the Recycle Bin.')
    if st.button('Scan', disabled=active,
                 help='Only looks; nothing is deleted yet. Checks whether every cached or marked photo still '
                      'exists, which can take a while for a large cache or a network share.'):
        scan_storage(settings)
    if 'cleanup_notice' in st.session_state:
        kind, text = st.session_state.pop('cleanup_notice')
        (st.success if kind == 'success' else st.warning)(plain(text))
    scan = st.session_state.get('cleanup_scan')
    if scan and st.session_state.get('cleanup_scan_inputs') != cleanup_inputs(settings):
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
        delete_storage(scan, selected, settings)
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


def show_cache_check(active):
    """"Check cache" in "Clean up storage": SQLite's quick check of the cache, a damaged one set aside (F1).

    active: whether a search runs (no check then).
    """
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
