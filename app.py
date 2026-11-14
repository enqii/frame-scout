"""FrameScout: local Streamlit user interface for framescout_engine.py.

This file is the page Streamlit runs: its five tabs (F28), the photo source tab, the search tab and the
results tab.
The other areas are modules of the package framescout_ui (A46).
"""
import sys
import time
from pathlib import Path

import streamlit as st

# I35: a script of a version with the packages framescout_core and framescout_scoring, which
# load for it next to an older version's leftover single files (framescout_core.layout); set
# before the first FrameScout import. Streamlit runs this file as the module __main__.
FRAMESCOUT_PACKAGES = True

from framescout_core import (APP_TABS, CACHE_FILE, EXAMPLE_PROFILES_FILE, MODELS, QUICK_DIR, QUICK_QUERY_MAX,
                             RESULTS_FILE, RESULTS_TAB, cleanup_running, count_text, create_from_example, distinct_folders,
                             engine_command, finishing_minutes, gallery_thumbnails, join_scans, known_throughput,
                             quick_scope_text, read_profiles_versioned, remembered_scans, results_running_text,
                             skipped_lines, start_blocked_text, start_needs, start_needs_line, start_summary,
                             windows_path)
from framescout_ui.cleanup import cleanup_signature, show_cache_check, show_cleanup
from framescout_ui.common import (BASE, EXAMPLE_PROFILES, PROFILES, QUICK_JSON, RESULTS, clean_project_folder,
                                  decoders, file_key, keep_value, open_results_folder, plain, restore_value,
                                  supported)
from framescout_ui.profiles import show_profiles
from framescout_ui.results import load_results, show_results
from framescout_ui.run import (cached_analyzed_photos, low_space_warning, run_state, show_state_line, show_status,
                               start_run, stop_run)
from framescout_ui.settings import setting_key, show_ai_settings, sync_settings

# the readable formats, in every page run: clearing the cache of decoders() refreshes them (review)
DECODERS = decoders()
SUPPORTED = supported()

st.set_page_config(page_title='FrameScout', page_icon='🔎', layout='wide')
st.markdown('''<style>.block-container{padding-top:2rem;max-width:1300px}
.stButton button{border-radius:8px}</style>''', unsafe_allow_html=True)

title_col, state_col = st.columns([1, 2], vertical_alignment='bottom')
title_col.title('🔎 FrameScout')
# F27: the run state on every tab, filled once the photos are counted (below)
state_area = state_col.container()
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
st.session_state.state_line_state = (active, run_status)  # for the state line next to the title (F27)

# the settings of the widgets, synchronized with settings.json (A8)
settings, seen, shown, settings_taken_over = sync_settings()
# the folders as the image count, the Start check and the engine use them (review: ~ expanded)
photo_folders = [Path(folder).expanduser() for folder in settings['photo_folders']]
# a folder listed twice or inside another listed folder is searched once (A25)
search_folders, dropped_folders = distinct_folders([folder.resolve() for folder in photo_folders])
# F28: five tabs; start, analysis, progress and Stop in "Search", the results on their own,
# storage maintenance with the settings
p_tab, f_tab, settings_tab, search_tab, results_tab = st.tabs(list(APP_TABS))

with p_tab:
    show_profiles(profiles, profiles_version, profiles_shown, active)

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
    # the photos counted in the existing folders, None without one: the state line and Start's needs (F27)
    photo_count = len(photo_scan.paths) if folder_scans else None
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

with state_area:
    show_state_line(active, photo_count)

with settings_tab:
    info, model_missing = show_ai_settings(settings, seen, shown, active)
    # F28: storage maintenance is rarely used and neither search nor results; disabled during a run
    st.divider()
    st.subheader('Storage')
    with st.expander('Clean up storage'):
        show_cleanup(settings, active)
        st.divider()
        show_cache_check(active)

with search_tab:
    st.subheader('Start search')
    # F27: what a search needs, with what is missing and the tab to fix it in. At least one
    # listed folder must exist (as sorted out in the Photo source tab, without asking the file
    # system again, review); the engine leaves out the others with a note (A25). A search
    # model without its package would only fail in the engine (E22 review); how to install it is
    # shown in the tab "Settings", which the blocked line names (review)
    needs = start_needs(len(profiles), photo_count, bool(photo_folders), MODELS[settings['model']].label,
                        model_missing)
    cleaning = active and cleanup_running(RESULTS)  # a cleanup holding the run lock is no search (review)
    start_blocked = start_blocked_text(needs, active, cleaning)
    c1,c2 = st.columns([1,1])
    with c1:
        start = st.button('▶ Start search', type='primary', width='stretch', disabled=bool(start_blocked))
    with c2:
        # a cleanup holding the run lock is no search to stop (review)
        stop = st.button('■ Stop search', disabled=not active or cleaning, width='stretch',
                         help='Stops the running search, also an analysis started with "Analyze photos now" or a '
                              'quick search. Photos analyzed so far are kept in the cache.')
    st.caption(plain(start_needs_line(needs)))
    if start_blocked and active:
        st.caption(plain(start_blocked))  # show_status below shows what runs
    elif start_blocked:
        st.warning(plain(start_blocked))
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
        # alone): never dropped without a word (review). Its notes are shown in the tab
        # "Results", where the click was (F28)
        if active:
            st.session_state.like_notice = ('"Find similar" was not started: a search is running already. Try again '
                                            'when it has finished.')
        else:
            start_engine(notice='like_notice', like=find_similar_request[0], like_part=find_similar_request[1])
    if stop:
        try:
            st.session_state.run_notice = stop_run()
        except Exception as exc:
            st.session_state.run_notice = f'Stop failed: {exc}'
        st.rerun()
    if st.session_state.get('run_notice'):
        st.warning(st.session_state.pop('run_notice'))
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
        quick_counts = cached_analyzed_photos(cache_key, cleanup_signature(settings),
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
        per_minute = known_throughput(run_status, cleanup_signature(settings), chosen_device)
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
        # the analysis writes the cache rows without gallery thumbnails (no profile): its own
        # warning, next to its button (review)
        analysis_space = low_space_warning(len(photo_scan.paths), settings['top'], 0, settings['model'],
                                           settings['person_detection'], analysis_done, analysis=True)
    # F18: the analysis of a search without the search, e.g. overnight before the profiles
    # are written; it runs like a search (run lock, status, stop button, low priority). Next
    # to Start since F28, so that start, progress and Stop are in one place
    st.subheader('Analyze ahead')
    st.caption('Analyzing the photos is the slow part of a first search. "Analyze photos now" analyzes the photos '
               'of the listed folders with the current AI settings and keeps the analyses in the cache, without '
               'searching: no search profile is needed, and the results of the last search stay as they are. '
               'A later search with the same search model and person detection settings only ranks these photos, '
               'and the quick search can search them; after a change of these settings, the photos are analyzed '
               'again. Its progress is shown below and "■ Stop search" stops it; "Keep the PC responsive" applies '
               'to it as to a search.')
    st.caption(f"Current settings: search model {MODELS[settings['model']].label} · person detection "
               f"{'on' if settings['person_detection'] else 'off'}.")
    if st.session_state.get('analyze_notice'):
        st.warning(st.session_state.pop('analyze_notice'))
    # not gated on the photo count: it is the one remembered for the browser session (A27),
    # while the engine reads the folders again, e.g. for photos added since (review)
    analyze_now = st.button('Analyze photos now', disabled=active or not folder_scans or bool(model_missing))
    if active:
        st.caption('Not available while a search or an analysis runs or the storage is being cleaned up.')
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
               f'search profiles stay as they are. Search texts are in English. Its result appears in the tab '
               f'"{RESULTS_TAB}", as an entry next to your search profiles; "Find similar" on a result card searches the same way by the image similarity with '
               'that photo, and its result appears there too.')
    # F34: the text stays in the field; Streamlit emptied it in the run after the click, in
    # which the field is disabled while the search runs
    restore_value('quick_query')
    with st.form('quick_search', border=False):
        c1, c2 = st.columns([4, 1], vertical_alignment='bottom')
        c1.text_input('Search text (in English)', key='quick_query', max_chars=QUICK_QUERY_MAX, disabled=active,
                      placeholder='e.g. a red car in the snow')
        quick_start = c2.form_submit_button('Quick search', width='stretch', on_click=keep_value,
                                            args=('quick_query',),
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

with results_tab:
    # F28: the results on their own, without the start and status area; while a run is
    # active, e.g. one "Find similar" started here, the tab says so (review)
    running_note = results_running_text(active, run_status, cleaning)
    if running_note:
        st.info(running_note)
    if st.session_state.get('like_notice'):
        st.warning(st.session_state.pop('like_notice'))  # a "Find similar" that could not start
    st.subheader('Results')
    # the galleries of the last complete search, as the engine wrote them (A12), and the last
    # quick search or "Find similar" as an entry of the same selector (F34)
    last_results, results_error = load_results()
    if results_error:
        st.warning(f'{RESULTS_FILE} cannot be read, so the results of the last search are not shown here. Starting '
                   f'the search again writes it anew.\n\nDetails: {plain(str(results_error))}')
    quick_results, quick_error = load_results(QUICK_JSON)
    if quick_error:
        st.warning(f'The result file of the last quick search ({QUICK_DIR}/{RESULTS_FILE}) cannot be read, so its '
                   f'results are not shown here. The next quick search writes it anew.\n\n'
                   f'Details: {plain(str(quick_error))}')
    if last_results or quick_results:
        # a copy target must not be in a photo folder of this search or of the next one (A17, A25)
        show_results(last_results, quick_results,
                     [*(last_results['photo_folders'] if last_results else []), *map(str, photo_folders)],
                     search_folders, settings['model'], active or not folder_scans)
    if not last_results:
        if RESULTS.is_dir() and (old_pages := sorted(RESULTS.glob('*.html'))):
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
            st.caption('After the first search with your search profiles, its results appear here'
                       + (' too.' if quick_results else '.'))
    st.caption('The HTML galleries in the results folder link to the local thumbnails and original photos; keep '
               'the results folder together for the complete gallery.')
