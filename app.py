"""FrameScout: local Streamlit user interface for framescout_engine.py."""
import functools
import hashlib
import os
import platform
import re
import subprocess
import sys
import threading
from pathlib import Path

import psutil
import streamlit as st

from framescout_core import (CACHE_CATEGORIES, CACHE_FILE, CLEANUP_CATEGORIES, DEFAULT_REFERENCE_WEIGHT, DEFAULT_YOLO_MODEL, DEVICES,
                             FINAL_PHASES, GALLERY_PAGE_SIZE, MARK_MATCH, MARK_NO_MATCH, MARK_OPEN, MARKS_FILE,
                             PHASE_LABELS, RESULTS_FILE, RUN_LOCK, RUN_STATUS, SETTING_RANGES, SETTING_STEPS,
                             SETTINGS_FILE, RunLock, StatusReporter, clean_up, cleanup_running, cleanup_summary_text,
                             copy_photos, copy_summary_text, copy_target, count_text, create_from_example,
                             DEFAULT_MODEL, MODEL_KEYS, MODELS, model_label, model_problem, results_model,
                             cuda_status, default_copy_folder, default_settings, device_choices, feature_signature,
                             finish_reference_move, lock_held, open_command, openable_photo, page_cards, page_count,
                             profile_fingerprints, profile_state, read_copy_folders, read_marks, read_profiles,
                             read_results, read_settings, read_status, reconcile_settings, reference_folder,
                             rename_copy_folder, rename_marks, reveal_command, run_active, save_copy_folder,
                             available_decoders, distinct_folders, folder_lines, join_scans, save_marks,
                             save_profiles, save_settings, scan_cleanup, scan_photos,
                             size_text, skipped_lines, stage_reference_move, started_in_time, status_fraction,
                             status_text, stopped_status, supported_extensions, undo_reference_move,
                             update_backup_references, write_new_file, write_status)

BASE = Path(__file__).resolve().parent
PROFILES = BASE / 'profiles.json'  # the user's working file, not in the repository
SETTINGS = BASE / SETTINGS_FILE  # the user's settings (A8), not in the repository
EXAMPLE_PROFILES = BASE / 'profiles.example.json'
REFS = BASE / 'references'
RESULTS = BASE / 'results'
LOG = BASE / 'run.log'
# held by the engine while it runs, and its phase and progress (A4, A5)
LOCK = RESULTS / RUN_LOCK
STATUS = RESULTS / RUN_STATUS
# what the galleries of the last search show (A12) and their thumbnails
RESULTS_JSON = RESULTS / RESULTS_FILE
THUMBS = RESULTS / 'thumbnails'
# the user's marks of gallery photos (A17): user data, never deleted by FrameScout
MARKS = RESULTS / MARKS_FILE
# the three states of a mark, as the control on each gallery card shows them (A17)
MARK_LABELS = {MARK_OPEN: 'Undecided', MARK_MATCH: 'Match', MARK_NO_MATCH: 'No match'}
MARK_BY_LABEL = {label: state for state, label in MARK_LABELS.items()}
GALLERY_COLUMNS = 4
# Markdown characters, escaped in file names shown with st.markdown/st.caption
MARKDOWN_CHARS = re.compile(r'([\\`*_{}\[\]()#+\-.!|<>~$])')


@st.cache_resource
def decoders():
    """The engine's Decoders (E25): it runs in the same Python environment and checks the same way (review)."""
    return available_decoders()


DECODERS = decoders()
SUPPORTED = supported_extensions(DECODERS)
UPLOAD_TYPES = sorted(x.lstrip('.') for x in SUPPORTED)
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
    'cache_missing': ('Cache entries of deleted photos',
                      'Analyses of photos inside the current photo folders that no longer exist there. A listed '
                      'folder that does not exist (e.g. on a disconnected drive) is left out.'),
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
    the file on disk.
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
        # keeps the previous file as profiles.json.bak (A2)
        save_profiles(PROFILES, build(refs + [x.relative_to(BASE).as_posix() for x in written]))
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
        st.error(f'Could not save the search profiles: {exc}. Your changes were not saved.')
        return False
    try:
        # profiles.json.bak still lists the old paths: point it to the new names before the
        # old ones are removed, so restoring the backup keeps working (review)
        update_backup_references(PROFILES, staged, BASE)
    except OSError as exc:
        # keep the old names too, so the backup still points to existing files
        st.session_state.notice = (f'Saved. profiles.json.bak could not be updated ({exc}), so the moved '
                                   'reference images also keep their old names for now.')
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

def engine_alive(pid, status):
    """Return True if pid is the running FrameScout engine of status.

    Checks the command line and that the process existed when status was written, so a
    process (also another engine, e.g. with another --output) that got the pid of an ended
    run later does not count (review).
    """
    try:
        process = psutil.Process(pid)
        return (any(part.endswith('framescout_engine.py') for part in process.cmdline())
                and started_in_time(status, process.create_time()))
    except psutil.Error:
        return False

def run_state():
    """Return (active, status) of the search in the results folder, whichever tab or session started it (A4)."""
    status = read_status(STATUS)
    return run_active(status, lock_held(LOCK), lambda pid: engine_alive(pid, status)), status

def start_run(cmd):
    """Start the engine with cmd unless a search is running; return None, or why it was not started.

    The app holds the engine's run lock while it starts it, so two tabs or sessions cannot
    start at the same time; the status "starting" shows the run until the engine takes the
    lock over (A4).
    """
    RESULTS.mkdir(parents=True, exist_ok=True)
    lock = RunLock(LOCK)
    # with a timeout: every open tab checks the lock for a moment every two seconds (review)
    if not lock.acquire(timeout=1):
        return 'A search is already running, or the storage is being cleaned up.'
    try:
        current = read_status(STATUS)
        if run_active(current, False, lambda pid: engine_alive(pid, current)):
            return 'Another search is being started.'
        with LOG.open('w', encoding='utf-8', buffering=1) as log_handle:
            proc = subprocess.Popen(cmd, cwd=str(BASE), env=cache_env(), stdout=log_handle, stderr=subprocess.STDOUT)
        st.session_state.process = proc
        if not StatusReporter(STATUS, proc.pid).update('starting'):
            # without "starting", other tabs would see no run until the engine takes the
            # lock and could start a second one (review)
            end_processes([proc.pid])
            proc.poll()
            return (f'The search was not started: {STATUS} cannot be written (it may be open in another '
                    'program). Try again in a moment.')
        return None
    finally:
        lock.release()

def stop_run():
    """End the running engine, also one started in another tab or before a reload (A4).

    Returns None, or a note for the user.
    """
    # read again: the page may have been drawn before the engine replaced the app's
    # "starting" status with its own (review)
    status = read_status(STATUS)
    pids = []
    proc = st.session_state.get('process')
    if proc is not None and proc.poll() is None:
        pids.append(proc.pid)
    if status and isinstance(status.get('pid'), int) and engine_alive(status['pid'], status):
        pids.append(status['pid'])
    ended = end_processes(pids)
    if proc is not None:
        proc.poll()
    if not ended:
        return 'No running search process was found; it may have just ended.'
    # the stopped engine cannot write its final status; mark it under the lock, which
    # Windows may release a moment after the process has ended (review)
    lock = RunLock(LOCK)
    if not lock.acquire(timeout=10):
        return ('The search was stopped, but its lock was not released yet, so it is not marked as stopped; '
                'the page may show it as ended without finishing.')
    try:
        current = read_status(STATUS)
        # only the status of a stopped process: another start may have replaced it meanwhile
        if current and current.get('pid') in ended and current.get('phase') not in FINAL_PHASES:
            if not write_status(STATUS, stopped_status(current), attempts=20):
                return ('The search was stopped, but the status file could not be updated, so the page may show '
                        'it as ended without finishing.')
    finally:
        lock.release()
    return None

def end_processes(pids):
    """Terminate the processes pids with their child processes, kill what is left after 5 s.

    Returns the set of process ids that were found (and ended).
    """
    targets = {}
    for pid in pids:
        try:
            # with child processes: on Windows the venv's python.exe starts the interpreter as one
            process = psutil.Process(pid)
            for x in [process, *process.children(recursive=True)]:
                targets[x.pid] = x
        except psutil.Error:
            pass
    for x in targets.values():
        try:
            x.terminate()
        except psutil.Error:
            pass
    _, remaining = psutil.wait_procs(list(targets.values()), timeout=5)
    for x in remaining:
        try:
            x.kill()
        except psutil.Error:
            pass
    psutil.wait_procs(remaining, timeout=5)
    return set(targets)

def open_path(path):
    """Open the file or folder path with its default program on the computer the app runs on."""
    if os.name == 'nt':
        os.startfile(str(path))
    else:
        start_launcher(open_command(path, platform.system()))

def start_launcher(cmd):
    """Start cmd (open, xdg-open) without waiting; a thread reaps it, so no zombie stays (review)."""
    process = subprocess.Popen(cmd)
    threading.Thread(target=process.wait, daemon=True).start()

def reveal_path(path):
    """Show the file path in the file manager of the computer the app runs on, selected if possible."""
    if os.name != 'nt':
        start_launcher(reveal_command(path, platform.system()))
        return
    # the shell function behind "explorer /select,", which did not select a file with a
    # comma in its name (checked on Windows 11); COM is initialized for this script thread
    import ctypes
    from ctypes import wintypes
    ole32, shell32 = ctypes.windll.ole32, ctypes.windll.shell32
    shell32.ILCreateFromPathW.restype = ctypes.c_void_p
    shell32.ILCreateFromPathW.argtypes = [wintypes.LPCWSTR]
    shell32.ILFree.argtypes = [ctypes.c_void_p]
    shell32.SHOpenFolderAndSelectItems.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p, wintypes.DWORD]
    # S_OK or S_FALSE: this call holds a reference to undo; a thread whose COM was
    # initialized in another mode (RPC_E_CHANGED_MODE, negative) must keep it (review)
    initialized = ole32.CoInitialize(None) >= 0
    try:
        item = shell32.ILCreateFromPathW(str(path))
        if not item:
            raise OSError(f'Windows does not find {path}')
        try:
            result = shell32.SHOpenFolderAndSelectItems(item, 0, None, 0)
        finally:
            shell32.ILFree(item)
    finally:
        if initialized:
            ole32.CoUninitialize()
    if result < 0:  # FAILED(); a success code such as S_FALSE is no error (review)
        raise OSError(f'Explorer reported error {result & 0xFFFFFFFF:#010x}')

def gallery_action(action, path, what):
    """Run action(path) for a gallery button; a failure becomes a note above the gallery."""
    if path is None:
        st.session_state.gallery_notice = f'{what} no longer exists.'
        return
    try:
        action(path)
    except OSError as exc:
        st.session_state.gallery_notice = f'{what} could not be opened: {exc}'

def open_photo(path):
    # only an existing image file: never start a program named in results.json
    gallery_action(open_path, openable_photo(path), f'The photo {path}')

def show_photo(path):
    gallery_action(reveal_path, openable_photo(path), f'The photo {path}')

def open_gallery(name):
    page = RESULTS / name  # a plain file name, checked by read_results
    gallery_action(open_path, page if page.is_file() else None, f'The gallery {page}')

def open_results_folder():
    gallery_action(open_path, RESULTS if RESULTS.is_dir() else None, f'The results folder {RESULTS}')

@functools.lru_cache(maxsize=1)
def pictures_folder():
    """Return the user's Pictures folder (also when Windows has moved it, e.g. to OneDrive)."""
    if os.name == 'nt':
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD), ('Data3', wintypes.WORD),
                        ('Data4', ctypes.c_ubyte * 8)]

        # FOLDERID_Pictures
        folder_id = GUID.from_buffer_copy(uuid.UUID('33E28130-4E1E-4676-835A-98395C3BC3BB').bytes_le)
        found = ctypes.c_void_p()
        shell32 = ctypes.windll.shell32
        shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
                                                 ctypes.POINTER(ctypes.c_void_p)]
        ctypes.windll.ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        try:
            if shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(found)) == 0:
                return Path(ctypes.wstring_at(found.value))
        finally:
            ctypes.windll.ole32.CoTaskMemFree(found)  # also on failure (documented), None is allowed
    return Path.home() / 'Pictures'

def widget_id(*parts):
    """A short stable key part for widgets of a profile or photo (names and paths may hold any character)."""
    return hashlib.sha256('\0'.join(parts).encode('utf-8')).hexdigest()[:16]

def version_key(path):
    """(path, mtime_ns, size, file id) of path: the cache key of the files saved by replacing them.

    With the file id, which changes with every atomic replace, so two saves of the same size
    within the time resolution of the file system (2 s on FAT) still count as a change.
    """
    stat = Path(path).stat()
    return str(path), stat.st_mtime_ns, stat.st_size, stat.st_ino

@st.cache_data(show_spinner=False, max_entries=2)
def cached_marks(path, mtime_ns, size, ino):
    """read_marks, read again only when the file changes (review: not on every gallery click)."""
    return read_marks(Path(path))

@st.cache_data(show_spinner=False, max_entries=2)
def cached_copy_folders(path, mtime_ns, size, ino):
    """read_copy_folders, read again only when settings.json changes (review)."""
    return read_copy_folders(Path(path))

def load_marks():
    """Return (marks of all profiles, error or None) of results/marks.json (A17)."""
    try:
        return cached_marks(*version_key(MARKS)), None
    except FileNotFoundError:
        return {}, None
    except (OSError, ValueError) as exc:
        return {}, exc

def set_mark(profile, photo, key):
    """Save the mark the control key shows for photo of profile (on_change of the control)."""
    # no selection (the selected option clicked again) is "open"
    state = MARK_BY_LABEL.get(st.session_state.get(key), MARK_OPEN)
    try:
        save_marks(MARKS, profile, {photo: state})
    except (OSError, ValueError) as exc:
        # the next run shows the saved mark again
        st.session_state.gallery_notice = f'The mark could not be saved: {exc}'

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
        save_copy_folder(SETTINGS, profile, st.session_state.get(key, ''), default)
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

def open_target_folder(key, photo_folders):
    target, _ = copy_target(st.session_state.get(key, ''), photo_folders)
    gallery_action(open_path, target if target is not None and target.is_dir() else None, f'The folder {target}')

def carry_over(old, new):
    """Give the marks and the saved target folder of the renamed profile old to its new name (A17)."""
    problems = []
    for what, action in (('marks', lambda: rename_marks(MARKS, old, new)),
                         ('saved copy target folder', lambda: rename_copy_folder(SETTINGS, old, new))):
        try:
            action()
        except (OSError, ValueError) as exc:
            problems.append(f'its {what} ({exc})')
    if problems:
        note = f'The profile was renamed, but {" and ".join(problems)} still belong to the old name "{old}".'
        # the name and the error texts (paths) are shown as Markdown: escaped (review)
        st.session_state.notice = ((st.session_state.notice + ' ' if 'notice' in st.session_state else 'Saved. ')
                                   + plain(note))

@st.cache_data(show_spinner=False, max_entries=2)
def cached_results(path, mtime_ns, size):
    """read_results, read again only when the file changes (mtime_ns and size are the cache key)."""
    return read_results(Path(path))

@st.cache_data(show_spinner=False, max_entries=2)
def cached_fingerprints(path, mtime_ns, size):
    """profile_fingerprints, computed again only when profiles.json changes (review: not on every click)."""
    return profile_fingerprints(Path(path))

@st.cache_data(show_spinner=False, max_entries=4)
def cached_bytes(path, mtime_ns, size):
    """The content of a file, read again only when it changes (the gallery's HTML download)."""
    return Path(path).read_bytes()

def file_key(path):
    """(path, mtime_ns, size) of path, the cache key of the functions above."""
    stat = Path(path).stat()
    return str(path), stat.st_mtime_ns, stat.st_size

def load_results():
    """Return (results of the last search or None, error or None) (A12)."""
    try:
        stat = RESULTS_JSON.stat()
        return cached_results(str(RESULTS_JSON), stat.st_mtime_ns, stat.st_size), None
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError) as exc:
        return None, exc

def plain(text):
    """Return text with its Markdown characters escaped, e.g. a file name for st.markdown/st.caption."""
    return MARKDOWN_CHARS.sub(r'\\\1', text)

def run_date(results):
    return str(results.get('finished', '')).replace('T', ' ')[:16]

@st.fragment
def show_results(results, photo_folders):
    """The galleries of the last search as a grid of thumbnails; its buttons rerun only this part (P4).

    With a mark per photo and copying of the matches (A17); photo_folders: the folders a
    copy target must not be in.
    """
    entries = results['profiles']
    if not entries:
        st.caption('The last search wrote no galleries.')
        return
    try:
        fingerprints = cached_fingerprints(*file_key(PROFILES))
    except (OSError, ValueError):
        fingerprints = {}
    states = {e['name']: profile_state(e, fingerprints) for e in entries}
    names = [e['name'] for e in entries]
    if st.session_state.get('results_profile') not in names:
        st.session_state.pop('results_profile', None)  # e.g. a profile of an earlier search
    # the options are the plain names: a state note in them would give the widget a new
    # identity in Streamlit versions that do not use the key as its identity and jump back
    # to the first profile whenever a profile is edited (review); the notes are shown below
    name = st.selectbox('Search profile', names, key='results_profile')
    entry = entries[names.index(name)]
    # the settings of that search, not the app's settings
    run_settings = results.get('settings') if isinstance(results.get('settings'), dict) else {}
    folders = results['photo_folders']  # also for a format 1 file (A25)
    model_key = results_model(run_settings)  # the default for a search before E22
    result_model = MODELS.get(model_key) if model_key else None
    st.caption(f"Search from {run_date(results)} · photo folder{'s' if len(folders) > 1 else ''} "
               f"{plain('; '.join(folders))} · "
               + (f'search model {plain(result_model.label)} · ' if result_model else '') +
               f"{len(entry['cards']):,} photos (at most {run_settings.get('top', '?')}), best first. "
               'A ranking by similarity, not a guaranteed identification.')
    if model_key != settings['model']:
        # E22 review: the gallery must not look like one of the model chosen now
        made_with = f'the search model {plain(result_model.label)}' if result_model else 'another search model'
        st.info(f'These results were made with {made_with}; the AI settings now choose '
                f"{plain(MODELS[settings['model']].label)}. Start the search again for its results.")
    if states[name] == 'changed':
        st.info(f'"{plain(name)}" was changed after this search (search texts or reference images), so these '
                'results may not fit it any more. Start the search again to update them.')
    elif states[name] == 'missing':
        st.info(f'"{plain(name)}" is no longer one of your search profiles (renamed or deleted). These are its '
                f'results from the search of {run_date(results)}. Its photos cannot be marked here: a renamed '
                "profile took its marks along, and they appear with the next search's results.")
    others = {state: [plain(n) for n in names if n != name and states[n] == state] for state in ('changed', 'missing')}
    if others['changed'] or others['missing']:
        st.caption(' · '.join(text + ', '.join(found) for text, found in (
            ('Changed since this search: ', others['changed']),
            ('No longer search profiles: ', others['missing'])) if found))
    c1, c2, c3 = st.columns(3)
    c1.button('Open gallery in browser', on_click=open_gallery, args=(entry['gallery'],), use_container_width=True,
              help=f"Opens {entry['gallery']} from the results folder in your web browser.")
    c2.button('Open results folder', on_click=open_results_folder, use_container_width=True)
    page_file = RESULTS / entry['gallery']
    try:
        # cached: a click on Open or Folder reruns this fragment (review)
        c3.download_button('Download HTML (without thumbnails)', cached_bytes(*file_key(page_file)), file_name=page_file.name,
                           mime='text/html', use_container_width=True, key='dl_results_gallery')
    except OSError:
        pass  # deleted or in use: the other buttons still work
    if st.session_state.get('gallery_notice'):
        st.warning(plain(st.session_state.pop('gallery_notice')))  # paths: no Markdown
    # read on every run of this part: another tab or session may have marked photos (A17)
    all_marks, marks_error = load_marks()
    if marks_error:
        st.warning(f'{MARKS_FILE} cannot be read, so marks are not shown and cannot be changed; FrameScout does not '
                   f'change the file. Fix or remove it in the results folder.\n\nDetails: {plain(str(marks_error))}')
    marks = all_marks.get(name, {})
    can_mark = marks_error is None and states[name] != 'missing'
    hide = st.checkbox('Hide photos marked as no match', key='hide_rejected')
    cards = [c for c in entry['cards'] if not (hide and marks.get(c['path']) == MARK_NO_MATCH)]
    if hide and len(cards) < len(entry['cards']):
        st.caption(f"{len(entry['cards']) - len(cards):,} photos marked as no match are hidden.")
    pages = page_count(len(cards), GALLERY_PAGE_SIZE)
    page = 1
    if pages > 1:
        key = 'results_page_' + name
        if st.session_state.get(key, 1) not in range(1, pages + 1):
            st.session_state.pop(key, None)  # a page of a longer list of an earlier search
        page = st.selectbox(f'Page (of {pages})', range(1, pages + 1), key=key)
    shown = page_cards(cards, page, GALLERY_PAGE_SIZE)
    st.caption('"Open" and "Folder" use the programs of the computer FrameScout runs on. Mark each photo you have '
               'checked as Match or No match; marks are kept for this profile across searches.')
    mark_keys = {}
    for card in shown:
        # the saved mark, set before the control is drawn (never as its default): the file
        # is the truth, also for marks made in another tab
        mark_keys[card['rank']] = key = 'mark_' + widget_id(name, card['path'])
        st.session_state[key] = MARK_LABELS[marks.get(card['path'], MARK_OPEN)]
    # a new container for every profile, page and card count: in a fragment rerun with fewer
    # cards (the shorter last page) the rows of the previous page stayed in the browser
    # (checked in Edge with Streamlit 1.66; a st.empty placeholder did not help)
    with st.container(key=f'gallery_{names.index(name)}_{page}_{len(shown)}'):
        for start in range(0, len(shown), GALLERY_COLUMNS):
            for column, card in zip(st.columns(GALLERY_COLUMNS), shown[start:start + GALLERY_COLUMNS]):
                with column:
                    thumb = THUMBS / card['thumbnail']  # a plain file name, checked by read_results
                    if thumb.is_file():
                        st.image(str(thumb))
                    else:
                        st.caption('No thumbnail')
                    st.markdown(f"**#{card['rank']}** · {plain(card['caption'])} · {plain(card['label'])}")
                    st.caption(f"{plain(card['detail'])}  \n{plain(card['relative'])}")
                    b1, b2 = st.columns(2)
                    b1.button('Open', key=f"open_{card['rank']}", on_click=open_photo, args=(card['path'],),
                              use_container_width=True, help='Opens the photo in your image viewer.')
                    b2.button('Folder', key=f"reveal_{card['rank']}", on_click=show_photo, args=(card['path'],),
                              use_container_width=True, help='Shows the photo in its folder.')
                    key = mark_keys[card['rank']]
                    st.segmented_control('Mark', list(MARK_LABELS.values()), key=key, on_change=set_mark,
                                         args=(name, card['path'], key), disabled=not can_mark,
                                         label_visibility='collapsed')
    show_copy(name, entry, marks, photo_folders)

def show_copy(name, entry, marks, photo_folders):
    """Copying the photos of profile name marked as match to a folder, below its gallery (A17)."""
    st.markdown('**Copy marked matches**')
    matches = [photo for photo, state in marks.items() if state == MARK_MATCH]
    rejected = sum(1 for state in marks.values() if state == MARK_NO_MATCH)
    in_results = {card['path'] for card in entry['cards']}
    elsewhere = sum(1 for photo in matches if photo not in in_results)
    st.caption(f'Marked: {len(matches):,} photos of "{plain(name)}" as match · {rejected:,} as no match.'
               + (f' {elsewhere:,} of the matches are not among the results of this search (marked earlier); they '
                  'are copied too.' if elsewhere else ''))
    default = str(default_copy_folder(pictures_folder(), Path(entry['gallery']).stem))
    key = 'copy_folder_' + widget_id(name)
    st.session_state[key] = copy_folder_value(name, default)
    st.text_input('Copy to folder', key=key, on_change=set_copy_folder, args=(name, key, default),
                  help='Copies only: the originals stay where they are. Files in this folder are never overwritten; '
                       'a different photo with the same name is saved as "name (2)".')
    # also not in the folder of a photo to copy, which may be from another photo folder (review)
    target, problem = copy_target(st.session_state[key], photo_folders, matches)
    if problem:
        st.warning(plain(problem))
    c1, c2 = st.columns(2)
    copy = c1.button(f'Copy {len(matches):,} marked photos', disabled=not matches or target is None,
                     use_container_width=True)
    c2.button('Open target folder', on_click=open_target_folder, args=(key, photo_folders),
              disabled=target is None or not target.is_dir(), use_container_width=True)
    if copy:
        copy_matches(name, key, photo_folders)

def cleanup_signature():
    """The cache signature of the current settings: its entries are never offered for deletion (E11)."""
    return feature_signature(settings['person_detection'], settings['max_persons'], settings['person_confidence'],
                             DEFAULT_YOLO_MODEL, model=settings['model'])

def cleanup_inputs():
    """What a cleanup scan was classified for: a scan of other values is out of date (E22 review)."""
    return cleanup_signature(), settings['model'], tuple(map(str, search_folders))

def cleanup_offered(category):
    return not category['problem'] and bool(category['items'])

def scan_storage():
    """Look for what the cleanup can delete and select the default categories (E7)."""
    try:
        # rows of the other search models are a category of their own, kept by default (E22)
        scan = scan_cleanup(RESULTS, PROFILES, REFS, search_folders, cleanup_signature(),
                            current_model=settings['model'])
    except OSError as exc:
        st.session_state.cleanup_notice = ('warning', f'The storage could not be scanned: {exc}')
        return
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
                               PROFILES, REFS, search_folders, cleanup_signature(), current_model=settings['model'])
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
    st.caption('Lists files and cache entries FrameScout no longer needs. Your photos, your marks (marks.json), '
               'the results of the last search, your profiles and settings are never deleted. Deleting is '
               'permanent: nothing goes to the Recycle Bin.')
    if st.button('Scan', disabled=active, help='Only looks; nothing is deleted yet.'):
        scan_storage()
    if 'cleanup_notice' in st.session_state:
        kind, text = st.session_state.pop('cleanup_notice')
        (st.success if kind == 'success' else st.warning)(plain(text))
    scan = st.session_state.get('cleanup_scan')
    if scan and st.session_state.get('cleanup_scan_inputs') != cleanup_inputs():
        # e.g. another search model: the scan would offer the rows of the model chosen now
        st.session_state.pop('cleanup_scan', None)
        st.caption('The AI settings or photo folders changed since the scan. Scan again.')
        return
    if not scan:
        return
    for key in CLEANUP_CATEGORIES:
        category = scan[key]
        label, explanation = CLEANUP_LABELS[key]
        if category['problem']:
            st.caption(f"{label}: {plain(category['problem'])}")
            continue
        # e.g. a listed photo folder on a disconnected drive, left out (A25)
        notes = ' '.join(category.get('notes', []))
        if not cleanup_offered(category):
            st.caption(f'{label}: nothing to clean up.' + (f' {plain(notes)}' if notes else ''))
            continue
        if key.startswith('cache_'):
            amount = f"{count_text(category['rows'], 'entry', 'entries')} · about {size_text(category['size'])}"
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

def cache_env():
    env = os.environ.copy()
    paths = {'TORCH_HOME': BASE/'.cache'/'torch', 'HF_HOME': BASE/'.cache'/'huggingface',
             'YOLO_CONFIG_DIR': BASE/'.cache'/'ultralytics', 'XDG_CACHE_HOME': BASE/'.cache',
             'TMP': BASE/'.tmp', 'TEMP': BASE/'.tmp'}
    for k,p in paths.items():
        p.mkdir(parents=True, exist_ok=True)
        env[k] = str(p)
    # run.log is written and read as UTF-8; without this the engine writes the ANSI code
    # page of Windows, which garbles e.g. "·" or "ä" in the log (E22 review)
    env['PYTHONIOENCODING'] = 'utf-8'
    return env

st.title('🔎 FrameScout')
st.caption('Local AI search in large photo collections · your images stay on your computer')

try:
    create_from_example(PROFILES, EXAMPLE_PROFILES)  # first start only; never overwrites
except OSError as exc:  # e.g. a read-only project folder
    st.error(f'Could not create profiles.json from profiles.example.json: {exc}. '
             'Check that the project folder is writable.')
    st.stop()
try:
    profiles = read_profiles(PROFILES)
except (OSError, ValueError) as exc:
    # never save over a file the app cannot read (A2)
    st.error('profiles.json cannot be read, so FrameScout does not change it. Fix it in a text '
             f'editor, or restore the backup profiles.json.bak if there is one.\n\nDetails: {exc}')
    st.stop()

# whether a search runs, also after a reload or in another tab (A4)
active, run_status = run_state()
st.session_state.page_run_state = (active, run_status)

@st.cache_data(show_spinner=False)
def system_info():
    import torch
    data = {'cpu': platform.processor() or platform.machine() or 'Not detected',
            'threads': os.cpu_count() or 1, 'cuda': torch.cuda.is_available(),
            'cuda_build': torch.version.cuda,
            'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}
    try:
        data['ram_gb'] = round(psutil.virtual_memory().total / (1024**3), 1)
    except OSError:
        data['ram_gb'] = None
    return data

DEFAULT_SETTINGS = default_settings(BASE)

def setting_key(name):
    """Return the session-state key of the widget of setting name (A8)."""
    return 'setting_' + name

def number_range(name):
    """Return the min_value/max_value arguments of the widget of setting name (review: one table)."""
    low, high = SETTING_RANGES[name]
    return {'min_value': low, 'max_value': high}

# Settings (A8): settings.json is read on every rerun, so a reload, a restart, another tab
# or session shows the saved settings. The widgets have keys and get the saved values
# through their session state; passing them as value= would give a widget a new identity
# after every save and drop the next change (review). framescout_core.reconcile_settings
# tells a change made in this session (saved; the latest action wins) from a value another
# session saved (shown here).
try:
    saved_settings, settings_problems = read_settings(SETTINGS, DEFAULT_SETTINGS)
except OSError as exc:
    # e.g. a virus scanner or another program holding the file for longer (review)
    saved_settings, settings_problems = None, []
    st.warning(f'{SETTINGS.name} is in use by another program right now, so the settings shown are kept and '
               f'saving a change is tried again the next time this page updates.\n\nDetails: {exc}')
except ValueError as exc:
    # never save over a file the app cannot read, like profiles.json (A2); the widgets keep
    # what they show (the defaults in a new page)
    saved_settings, settings_problems = None, []
    st.warning(f'{SETTINGS.name} cannot be read, so FrameScout does not change it and keeps the settings shown '
               f'(the defaults in a new page). Fix it in a text editor or delete it to save settings again.'
               f'\n\nDetails: {exc}')
if settings_problems:
    st.warning(f'Some values in {SETTINGS.name} are not allowed and were replaced by their defaults: '
               + '; '.join(settings_problems) + '. The next saved change removes them from the file.')
def setting_of_widget(name, value):
    """Return the setting value of the widget value of setting name.

    The photo folder field is a text area with one folder per line, and the setting is the
    list of its lines (A25): reconcile_settings and save_settings work on the lists.
    """
    return folder_lines(value) if name == 'photo_folders' else value

def widget_of_setting(name, value):
    """Return the widget value that shows the setting value of setting name (see setting_of_widget)."""
    return '\n'.join(value) if name == 'photo_folders' else value

seen = st.session_state.setdefault('settings_seen', {})
shown = st.session_state.setdefault('settings_shown', {})
widget_values = {name: setting_of_widget(name, st.session_state[setting_key(name)]) for name in DEFAULT_SETTINGS
                 if setting_key(name) in st.session_state}
setting_updates, changed_settings, settings_taken_over = reconcile_settings(
    widget_values, seen, shown, saved_settings, DEFAULT_SETTINGS)
for name, value in setting_updates.items():
    st.session_state[setting_key(name)] = widget_of_setting(name, value)
if changed_settings:
    if saved_settings is None:
        st.warning(f'The changed settings are used, but not saved yet, since {SETTINGS.name} cannot be read.')
    else:
        try:
            written = save_settings(SETTINGS, changed_settings, DEFAULT_SETTINGS)
        except (OSError, ValueError) as exc:
            # tried again on the next rerun: the widget still differs from settings_shown
            st.warning(f'The settings could not be saved to {SETTINGS.name}: {exc}. They are used for now, and '
                       'saving is tried again the next time this page updates.')
        else:
            shown.update(changed_settings)
            seen.update(written)  # as stored, e.g. rounded (review)
settings = {name: setting_of_widget(name, st.session_state[setting_key(name)]) for name in DEFAULT_SETTINGS}
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
    # hint only, no check of the input (user decision on E3: English search terms only);
    # one box with the call to action on an empty list (review)
    st.info(('Create a search profile first. ' if not profiles else '') +
            'Enter the search motif, context, features and custom search texts **in English**. The CLIP model '
            'FrameScout uses understands practically only English: a word in another language, e.g. German '
            '"Schwert" instead of "sword", can find completely different photos.')
    saves = st.session_state.get('saves', 0)
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
            # new lists instead of changing profiles in place: after a failed save the page
            # keeps showing (and the search uses) exactly what is in profiles.json
            if delete and store(lambda _, index=index: profiles[:index] + profiles[index+1:]):
                st.rerun()
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

with f_tab:
    st.subheader('Photo collection')
    st.text_area('Local photo folders (one per line, including subfolders)', key=setting_key('photo_folders'),
                 disabled=active, help='One search covers all listed folders, e.g. event folders on several '
                                       'drives. A folder inside another listed folder is searched as part of it.')
    # per listed folder (A25): its photo count, or why it is not searched on its own. Each
    # folder is scanned once per page run, as the engine scans it (E25), so the numbers
    # match its log.
    folder_scans, missing_folders = [], []
    for folder in search_folders:
        if folder.is_dir():
            folder_scans.append((folder, scan_photos(folder, SUPPORTED, exclude=RESULTS)))
        else:
            missing_folders.append(folder)
    photo_scan = join_scans([scan for _, scan in folder_scans])
    if len(search_folders) == 1 and folder_scans:
        st.success(f'{len(photo_scan.paths):,} supported image files found.')
    elif folder_scans:
        st.success(f'{len(photo_scan.paths):,} supported image files found in {len(folder_scans)} folders.')
        for folder, scan in folder_scans:
            st.caption(plain(f"{folder}: {count_text(len(scan.paths), 'supported image file', 'supported image files')}"))
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

with settings_tab:
    st.subheader('AI processing')
    # imports torch: here rather than at the top, so the profile tab is drawn first (review)
    try:
        info, info_error = system_info(), None
    except Exception as exc:
        info, info_error = None, exc
    # E22: the registry keys, the default first; the labels name the CPU factor, the download
    # and whether the model is evaluated
    st.selectbox('Search model', MODEL_KEYS, format_func=model_label, key=setting_key('model'), disabled=active,
                 help='The AI model that compares your search texts and reference images with the photos.')
    chosen_model = MODELS[settings['model']]
    if settings['model'] == DEFAULT_MODEL:
        st.caption("The default search model: the fastest one, and the one FrameScout's settings were tuned for.")
    else:
        st.caption(f'{chosen_model.label} takes about {chosen_model.cpu_factor.lstrip("~")} as long as the default '
                   'to analyze a photo on a CPU (not measured on a GPU) and downloads '
                   f'{chosen_model.download} the first time it is used. '
                   + ('' if chosen_model.evaluated else
                      "It is not evaluated on FrameScout's searches yet: its results may be better or worse than "
                      "the default's, and the default weight of reference images was tuned for the default."))
    st.caption('A new search model analyzes every photo once more. The cache keeps the analyses of each model '
               'side by side (about 10–15 MB per model for 5,000 photos), so switching back needs no new analysis.')
    model_missing = model_problem(settings['model'])
    if model_missing:
        st.warning(model_missing)
    # "cuda" only if PyTorch can use it (A7); if detection failed, the engine still checks
    devices = device_choices(info['cuda']) if info else list(DEVICES)
    if st.session_state[setting_key('device')] not in devices:
        # the only substitute (review): a saved device this PyTorch cannot use (e.g. "cuda"
        # after switching to the CPU build) is shown and used as "auto" but stays saved
        st.session_state[setting_key('device')] = shown['device'] = 'auto'
    st.selectbox('Compute device', devices, key=setting_key('device'), disabled=active, help='auto uses CUDA if a compatible NVIDIA GPU is available, otherwise the CPU.')
    if seen.get('device', 'auto') not in devices:
        # a saved device this PyTorch cannot use (e.g. "cuda" after switching to the CPU
        # build) is shown and used as "auto", but stays saved, so it applies again once
        # PyTorch can use it; choosing "auto" is no change, hence the button (review)
        st.caption(f"The saved device \"{seen['device']}\" is not available, so auto is used. "
                   'It is used again once PyTorch can use it.')
        if st.button('Use auto from now on', disabled=active):
            try:
                save_settings(SETTINGS, {'device': 'auto'}, DEFAULT_SETTINGS)
            except (OSError, ValueError) as exc:
                st.warning(f'The settings could not be saved to {SETTINGS.name}: {exc}.')
            else:
                seen['device'] = 'auto'
                st.rerun()
    st.number_input('Batch size', **number_range('batch_size'), step=1, key=setting_key('batch_size'), disabled=active)
    st.number_input('Maximum matches per search profile', **number_range('top'), step=25, key=setting_key('top'), disabled=active)
    st.checkbox('Also detect individual persons in group photos (YOLO)', key=setting_key('person_detection'), disabled=active)
    st.number_input('Maximum detected persons per photo', **number_range('max_persons'), key=setting_key('max_persons'), disabled=active)
    st.slider('Minimum confidence of the person detection', **number_range('person_confidence'), step=SETTING_STEPS['person_confidence'], key=setting_key('person_confidence'), disabled=active)
    st.slider('Weight of reference images (if any)', **number_range('reference_weight'), step=SETTING_STEPS['reference_weight'], key=setting_key('reference_weight'), disabled=active, help=f'0 = text only; {DEFAULT_REFERENCE_WEIGHT:g} (default) = {DEFAULT_REFERENCE_WEIGHT:.0%} reference images '
              f'and {1 - DEFAULT_REFERENCE_WEIGHT:.0%} text. Text and reference scores are scaled to the photos of '
              'the search before they are weighted.')
    if info:
        st.caption(f"Detected: {info['cpu']} · {info['threads']} logical CPU cores · " +
                   (f"{info['ram_gb']} GB RAM · " if info['ram_gb'] else 'RAM unknown · ') +
                   cuda_status(info['cuda'], info['cuda_build'], info['gpu']))
        st.info('Recommendation: choose auto. A batch size of 8 is a conservative starting point; reduce it if memory runs short. Model weights are downloaded on the first run.')
    else:
        st.caption(f'System details could not be determined ({info_error}). Automatic device selection remains available.')

with run_tab:
    st.subheader('Start search')
    c1,c2 = st.columns([1,1])
    with c1:
        # at least one listed folder must exist (as sorted out in the Photo source tab, without
        # asking the file system again, review); the engine leaves out the others with a note (A25).
        # A search model without its package would only fail in the engine (E22 review)
        start = st.button('▶ Start search', type='primary', use_container_width=True,
                          disabled=active or not profiles or not folder_scans or bool(model_missing))
    with c2:
        # a cleanup holding the run lock is no search to stop (review)
        stop = st.button('■ Stop search', disabled=not active or cleanup_running(RESULTS), use_container_width=True)
    if start and settings_taken_over:
        # the page showed other values until this click: never start with settings the
        # user has not seen (review)
        st.session_state.run_notice = ('The search was not started: another tab or window changed these settings '
                                       'meanwhile: ' + ', '.join(settings_taken_over) + '. Check the settings '
                                       'shown now and start again.')
        st.rerun()
    if start:
        cmd = [sys.executable, '-u', str(BASE/'framescout_engine.py'), *map(str, search_folders),
            '--profiles',str(PROFILES),'--output',str(RESULTS),'--device',st.session_state[setting_key('device')],
            '--batch-size',str(settings['batch_size']),'--top',str(settings['top']),
            '--max-persons',str(settings['max_persons']),'--person-confidence',str(settings['person_confidence']),
            '--reference-weight',str(settings['reference_weight']),'--model',settings['model']]
        if not settings['person_detection']:
            cmd.append('--no-person-detection')
        st.session_state.pop('cleanup_scan', None)  # the search changes what a cleanup finds (E7)
        try:
            problem = start_run(cmd)
        except Exception as exc:
            problem = f'Start failed: {exc}'
        # kept for the next page run: the state may have changed, which reruns the page
        st.session_state.run_notice = problem
        st.rerun()
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
    @st.fragment(run_every='2s')
    def show_status():
        # the state of this page run, read once at its top; fragment-only reruns read it again (review)
        fresh = st.session_state.pop('page_run_state', None)
        now_active, status = fresh if fresh else run_state()
        if now_active != active:
            st.rerun()  # a search started or ended, also in another tab: update the whole page
        if now_active and cleanup_running(RESULTS):
            # "Clean up storage" of another tab holds the run lock, no search runs (review)
            st.info('The storage is being cleaned up in another tab or window. You can start a search again '
                    'when it is done.')
        elif now_active:
            st.info('Search running. You can reload this page or close the tab: the search continues and '
                    'is shown again when you come back. Photos that are already analyzed are kept in the cache.')
        elif status:
            phase = status.get('phase')
            message = status.get('message')
            if phase == 'finished':
                finished_at = str(status.get('updated', '')).replace('T', ' ')[:19]
                st.success(f'The last search run finished successfully ({finished_at}).')
            elif phase == 'interrupted':
                st.warning(f"The last search run was interrupted{': ' + message if message else '.'} "
                           'Photos analyzed so far are in the cache; start again to resume.')
            elif phase in FINAL_PHASES:
                st.warning(f"The last search run failed (exit code {status.get('exit_code')})"
                           f"{': ' + message if message else ''}. See the log for details.")
            else:
                st.warning(f"The last search run ended during the phase \"{PHASE_LABELS.get(phase, phase)}\" "
                           'without finishing (stopped or crashed). Photos analyzed so far are in the cache; '
                           'see the log for details.')
        if status and status.get('phase') != 'finished':
            # the phase and its progress: analysis, scoring and gallery export (A5)
            fraction = status_fraction(status)
            if fraction is None:
                st.caption(status_text(status) + (' …' if now_active else ''))
            else:
                st.progress(fraction, text=status_text(status))
        if LOG.exists():
            lines = LOG.read_text(encoding='utf-8', errors='replace').splitlines()
            with st.expander('Live log', expanded=now_active):
                st.code('\n'.join(lines[-35:]) or 'No output yet', language='text')
    show_status()
    st.divider()
    st.subheader('Results')
    # the galleries of the last complete search, as the engine wrote them (A12)
    last_results, results_error = load_results()
    if results_error:
        st.warning(f'{RESULTS_FILE} cannot be read, so the results of the last search are not shown here. Starting '
                   f'the search again writes it anew.\n\nDetails: {plain(str(results_error))}')
    if last_results:
        # a copy target must not be in a photo folder of this search or of the next one (A17, A25)
        show_results(last_results, [*last_results['photo_folders'], *map(str, photo_folders)])
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
