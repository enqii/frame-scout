"""FrameScout: local Streamlit user interface for framescout_engine.py."""
import os
import platform
import subprocess
import sys
from pathlib import Path

import psutil
import streamlit as st

from framescout_core import (DEVICES, EXT, FINAL_PHASES, PHASE_LABELS, RUN_LOCK, RUN_STATUS, SETTING_RANGES,
                             SETTINGS_FILE, RunLock, StatusReporter, create_from_example, cuda_status,
                             default_settings, device_choices, finish_reference_move, lock_held, profile_slugs,
                             read_profiles, read_settings, read_status, reconcile_settings, reference_folder,
                             run_active, save_profiles, save_settings,
                             stage_reference_move, started_in_time, status_fraction, status_text, stopped_status,
                             undo_reference_move, update_backup_references, write_new_file, write_status)

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
UPLOAD_TYPES = sorted(x.lstrip('.') for x in EXT)

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
                if suffix in EXT:
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
        return 'A search is already running.'
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

def cache_env():
    env = os.environ.copy()
    paths = {'TORCH_HOME': BASE/'.cache'/'torch', 'HF_HOME': BASE/'.cache'/'huggingface',
             'YOLO_CONFIG_DIR': BASE/'.cache'/'ultralytics', 'XDG_CACHE_HOME': BASE/'.cache',
             'TMP': BASE/'.tmp', 'TEMP': BASE/'.tmp'}
    for k,p in paths.items():
        p.mkdir(parents=True, exist_ok=True)
        env[k] = str(p)
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
seen = st.session_state.setdefault('settings_seen', {})
shown = st.session_state.setdefault('settings_shown', {})
widget_values = {name: st.session_state[setting_key(name)] for name in DEFAULT_SETTINGS
                 if setting_key(name) in st.session_state}
setting_updates, changed_settings, settings_taken_over = reconcile_settings(
    widget_values, seen, shown, saved_settings, DEFAULT_SETTINGS)
for name, value in setting_updates.items():
    st.session_state[setting_key(name)] = value
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
settings = {name: st.session_state[setting_key(name)] for name in DEFAULT_SETTINGS}
# the folder as the image count, the Start check and the engine use it (review: ~ expanded)
photo_folder = Path(settings['photo_folder']).expanduser()
p_tab, f_tab, settings_tab, run_tab = st.tabs(['Search profiles', 'Photo source', 'AI settings', 'Search & results'])

with p_tab:
    st.subheader('Saved search profiles')
    if 'notice' in st.session_state:
        st.warning(st.session_state.pop('notice'))
    if not profiles:
        st.info('Create a search profile first.')
    saves = st.session_state.get('saves', 0)
    for index, p in enumerate(profiles):
        with st.expander(f"{p['name']}  ·  {p.get('franchise','')}"):
            with st.form(f'edit_{index}_{saves}'):
                edit_name = st.text_input('Search motif', value=p['name'])
                franchise = st.text_input('Context / origin (optional)', value=p.get('franchise', ''))
                features = st.text_area('Distinctive features (optional; English works best)', value=p.get('features', ''))
                prompts = st.text_area('Custom search texts (optional; one per line)', value='\n'.join(p.get('prompts', [])))
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
        name = st.text_input('Search motif *', placeholder='e.g. red car, golden retriever, mountain landscape', key=f'new_name_{form_id}')
        franchise = st.text_input('Context / origin (optional)', placeholder='e.g. vehicles, pets, nature', key=f'new_context_{form_id}')
        features = st.text_area('Distinctive features (optional; English works best)', placeholder='red bodywork, black roof, parked on a street', key=f'new_features_{form_id}')
        prompts = st.text_area('Custom search texts (optional; one per line)', key=f'new_prompts_{form_id}')
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
    st.caption('FrameScout automatically creates several CLIP search texts from the name. No language model is required.')

with f_tab:
    st.subheader('Photo collection')
    st.text_input('Local photo folder (including subfolders)', key=setting_key('photo_folder'), disabled=active)
    if photo_folder.is_dir():
        count = sum(1 for x in photo_folder.rglob('*') if x.is_file() and x.suffix.lower() in EXT and RESULTS not in x.parents)
        st.success(f'{count:,} supported image files found.')
    else:
        st.warning('The folder does not exist yet. Create it or choose an existing image folder.')
    st.caption('Supports JPG, PNG, WebP, BMP and TIFF. FrameScout searches local files and does not download images from online services.')

with settings_tab:
    st.subheader('AI processing')
    # imports torch: here rather than at the top, so the profile tab is drawn first (review)
    try:
        info, info_error = system_info(), None
    except Exception as exc:
        info, info_error = None, exc
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
    st.slider('Minimum confidence of the person detection', **number_range('person_confidence'), step=.05, key=setting_key('person_confidence'), disabled=active)
    st.slider('Weight of reference images (if any)', **number_range('reference_weight'), step=.05, key=setting_key('reference_weight'), disabled=active, help='0 = text only; 0.35 = 35 % reference images and 65 % text.')
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
        start = st.button('▶ Start search', type='primary', disabled=active or not profiles or not photo_folder.is_dir(), use_container_width=True)
    with c2:
        stop = st.button('■ Stop search', disabled=not active, use_container_width=True)
    if start and settings_taken_over:
        # the page showed other values until this click: never start with settings the
        # user has not seen (review)
        st.session_state.run_notice = ('The search was not started: another tab or window changed these settings '
                                       'meanwhile: ' + ', '.join(settings_taken_over) + '. Check the settings '
                                       'shown now and start again.')
        st.rerun()
    if start:
        cmd = [sys.executable, '-u', str(BASE/'framescout_engine.py'), str(photo_folder.resolve()),
            '--profiles',str(PROFILES),'--output',str(RESULTS),'--device',st.session_state[setting_key('device')],
            '--batch-size',str(settings['batch_size']),'--top',str(settings['top']),
            '--max-persons',str(settings['max_persons']),'--person-confidence',str(settings['person_confidence']),
            '--reference-weight',str(settings['reference_weight'])]
        if not settings['person_detection']:
            cmd.append('--no-person-detection')
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
    @st.fragment(run_every='2s')
    def show_status():
        # the state of this page run, read once at its top; fragment-only reruns read it again (review)
        fresh = st.session_state.pop('page_run_state', None)
        now_active, status = fresh if fresh else run_state()
        if now_active != active:
            st.rerun()  # a search started or ended, also in another tab: update the whole page
        if now_active:
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
    st.subheader('Result galleries')
    if RESULTS.exists():
        # same file names as the engine: unique slugs in profile order
        for p, slug in zip(profiles, profile_slugs([q['name'].strip() for q in profiles])):
            page = RESULTS/(slug+'.html')
            if page.exists():
                st.download_button(f"Export HTML: {p['name']}", page.read_bytes(), file_name=page.name, mime='text/html', key=f'dl_{p["name"]}')
                st.caption(f'Open the local gallery: {page}')
        st.caption('Open the HTML files in your file manager. They link to the local thumbnails and original photos; keep the results folder together for the complete gallery.')
    else:
        st.caption('After the first search run, the HTML galleries appear in the results folder.')
