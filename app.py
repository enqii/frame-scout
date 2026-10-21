"""FrameScout: local Streamlit user interface for framescout_engine.py."""
import os
import platform
import subprocess
import sys
from pathlib import Path

import psutil
import streamlit as st

from framescout_core import (EXT, FINAL_PHASES, PHASE_LABELS, RUN_LOCK, RUN_STATUS, RunLock, StatusReporter,
                             create_from_example, cuda_status, device_choices, finish_reference_move, lock_held,
                             profile_slugs, read_profiles, read_status, reference_folder, run_active, same_run,
                             save_profiles, stage_reference_move, status_fraction, status_text, stopped_status,
                             undo_reference_move, update_backup_references, write_new_file, write_status)

BASE = Path(__file__).resolve().parent
PROFILES = BASE / 'profiles.json'  # the user's working file, not in the repository
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

def engine_alive(pid):
    """Return True if pid is a running FrameScout engine (not another process that got its id)."""
    try:
        return any(part.endswith('framescout_engine.py') for part in psutil.Process(pid).cmdline())
    except psutil.Error:
        return False

def run_state():
    """Return (active, status) of the search in the results folder, whichever tab or session started it (A4)."""
    status = read_status(STATUS)
    return run_active(status, lock_held(LOCK), engine_alive), status

def start_run(cmd):
    """Start the engine with cmd unless a search is running; return None, or why it was not started.

    The app holds the engine's run lock while it starts it, so two tabs or sessions cannot
    start at the same time; the status "starting" shows the run until the engine takes the
    lock over (A4).
    """
    RESULTS.mkdir(parents=True, exist_ok=True)
    lock = RunLock(LOCK)
    if not lock.acquire():
        return 'A search is already running.'
    try:
        if run_active(read_status(STATUS), False, engine_alive):
            return 'Another search is being started.'
        with LOG.open('w', encoding='utf-8', buffering=1) as log_handle:
            proc = subprocess.Popen(cmd, cwd=str(BASE), env=cache_env(), stdout=log_handle, stderr=subprocess.STDOUT)
        StatusReporter(STATUS, proc.pid).update('starting')
        st.session_state.process = proc
        return None
    finally:
        lock.release()

def stop_run(status):
    """End the running engine, also one started in another tab or before a reload (A4).

    Returns True if a process was found to stop.
    """
    pids = []
    proc = st.session_state.get('process')
    if proc is not None and proc.poll() is None:
        pids.append(proc.pid)
    if status and isinstance(status.get('pid'), int) and engine_alive(status['pid']):
        pids.append(status['pid'])
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
    if proc is not None:
        proc.poll()
    # the stopped engine cannot write its final status; mark it under the lock, unless
    # another start has replaced the status in the meantime
    lock = RunLock(LOCK)
    if status and lock.acquire(timeout=2):
        try:
            current = read_status(STATUS)
            if same_run(current, status) and current.get('phase') not in FINAL_PHASES:
                write_status(STATUS, stopped_status(current), attempts=20)
        finally:
            lock.release()
    return bool(targets)

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

if 'settings' not in st.session_state:
    st.session_state.settings = {'folder': str(BASE/'photos'), 'device': 'auto', 'batch': 8,
        'top': 150, 'detect': True, 'max_persons': 12, 'conf': 0.30, 'weight': 0.35}
settings = st.session_state.settings
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
    settings['folder'] = st.text_input('Local photo folder (including subfolders)', value=settings['folder'], disabled=active)
    folder = Path(settings['folder']).expanduser()
    if folder.is_dir():
        count = sum(1 for x in folder.rglob('*') if x.is_file() and x.suffix.lower() in EXT and RESULTS not in x.parents)
        st.success(f'{count:,} supported image files found.')
    else:
        st.warning('The folder does not exist yet. Create it or choose an existing image folder.')
    st.caption('Supports JPG, PNG, WebP, BMP and TIFF. FrameScout searches local files and does not download images from online services.')

with settings_tab:
    st.subheader('AI processing')
    @st.cache_data(show_spinner=False)
    def system_info():
        import torch
        data = {'cpu': platform.processor() or platform.machine() or 'Not detected',
                'threads': os.cpu_count() or 1, 'cuda': torch.cuda.is_available(),
                'cuda_build': torch.version.cuda,
                'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}
        try:
            import psutil
            data['ram_gb'] = round(psutil.virtual_memory().total / (1024**3), 1)
        except (ImportError, OSError):
            data['ram_gb'] = None
        return data
    try:
        info, info_error = system_info(), None
    except Exception as exc:
        info, info_error = None, exc
    # "cuda" only if PyTorch can use it (A7); if detection failed, the engine still checks
    devices = device_choices(info['cuda']) if info else ['auto', 'cpu', 'cuda']
    if settings['device'] not in devices:
        settings['device'] = 'auto'
    settings['device'] = st.selectbox('Compute device', devices, index=devices.index(settings['device']), disabled=active, help='auto uses CUDA if a compatible NVIDIA GPU is available, otherwise the CPU.')
    settings['batch'] = st.number_input('Batch size', min_value=1, max_value=64, value=int(settings['batch']), step=1, disabled=active)
    settings['top'] = st.number_input('Maximum matches per search profile', min_value=1, max_value=5000, value=int(settings['top']), step=25, disabled=active)
    settings['detect'] = st.checkbox('Also detect individual persons in group photos (YOLO)', value=settings['detect'], disabled=active)
    settings['max_persons'] = st.number_input('Maximum detected persons per photo', min_value=1, max_value=50, value=int(settings['max_persons']), disabled=active)
    settings['conf'] = st.slider('Minimum confidence of the person detection', .1, .9, float(settings['conf']), .05, disabled=active)
    settings['weight'] = st.slider('Weight of reference images (if any)', 0., 1., float(settings['weight']), .05, disabled=active, help='0 = text only; 0.35 = 35 % reference images and 65 % text.')
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
        start = st.button('▶ Start search', type='primary', disabled=active or not profiles or not Path(settings['folder']).is_dir(), use_container_width=True)
    with c2:
        stop = st.button('■ Stop search', disabled=not active, use_container_width=True)
    if start:
        cmd = [sys.executable, '-u', str(BASE/'framescout_engine.py'), str(Path(settings['folder']).resolve()),
            '--profiles',str(PROFILES),'--output',str(RESULTS),'--device',settings['device'],
            '--batch-size',str(settings['batch']),'--top',str(settings['top']),
            '--max-persons',str(settings['max_persons']),'--person-confidence',str(settings['conf']),
            '--reference-weight',str(settings['weight'])]
        if not settings['detect']:
            cmd.append('--no-person-detection')
        try:
            problem = start_run(cmd)
        except Exception as exc:
            st.error(f'Start failed: {exc}')
        else:
            if problem:
                st.warning(problem)
            else:
                st.rerun()
    if stop:
        try:
            if not stop_run(run_status):
                st.warning('No running search process was found; it may have just ended.')
        except Exception as exc:
            st.error(f'Stop failed: {exc}')
        else:
            st.rerun()
    @st.fragment(run_every='2s')
    def show_status():
        now_active, status = run_state()
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
