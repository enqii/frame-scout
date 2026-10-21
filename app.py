"""FrameScout: local Streamlit user interface for framescout_engine.py."""
import os
import platform
import subprocess
import sys
from pathlib import Path

import streamlit as st

from framescout_core import (EXT, create_from_example, parse_progress, profile_slugs, read_profiles, reference_folder,
                             save_profiles, write_new_file)

BASE = Path(__file__).resolve().parent
PROFILES = BASE / 'profiles.json'  # the user's working file, not in the repository
EXAMPLE_PROFILES = BASE / 'profiles.example.json'
REFS = BASE / 'references'
RESULTS = BASE / 'results'
LOG = BASE / 'run.log'
UPLOAD_TYPES = sorted(x.lstrip('.') for x in EXT)

st.set_page_config(page_title='FrameScout', page_icon='🔎', layout='wide')
st.markdown('''<style>.block-container{padding-top:2rem;max-width:1300px}
.stButton button{border-radius:8px}</style>''', unsafe_allow_html=True)

def persist(profiles):
    # keeps the previous file as profiles.json.bak (A2); returns False if saving failed
    try:
        save_profiles(PROFILES, profiles)
        return True
    except OSError as exc:
        st.error(f'Could not save profiles.json: {exc}. Your changes were not saved.')
        return False

def running():
    proc = st.session_state.get('process')
    return proc is not None and proc.poll() is None

def cache_env():
    env = os.environ.copy()
    paths = {'TORCH_HOME': BASE/'.cache'/'torch', 'HF_HOME': BASE/'.cache'/'huggingface',
             'YOLO_CONFIG_DIR': BASE/'.cache'/'ultralytics', 'XDG_CACHE_HOME': BASE/'.cache',
             'TMP': BASE/'.tmp', 'TEMP': BASE/'.tmp'}
    for k,p in paths.items():
        p.mkdir(parents=True, exist_ok=True)
        env[k] = str(p)
    return env

def add_ref_files(files, name, others):
    # one folder per profile: never one holding references of the other profiles (A1);
    # write_new_file never overwrites leftover files in it
    target_dir = reference_folder(REFS, name, others, BASE)
    paths = []
    for f in files:
        suffix = Path(f.name).suffix.lower()
        if suffix not in EXT:
            continue
        target = write_new_file(target_dir, 'reference', suffix, f.getvalue())
        paths.append(target.relative_to(BASE).as_posix())
    return paths

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

if 'settings' not in st.session_state:
    st.session_state.settings = {'folder': str(BASE/'photos'), 'device': 'auto', 'batch': 8,
        'top': 150, 'detect': True, 'max_persons': 12, 'conf': 0.30, 'weight': 0.35}
settings = st.session_state.settings
p_tab, f_tab, settings_tab, run_tab = st.tabs(['Search profiles', 'Photo source', 'AI settings', 'Search & results'])

with p_tab:
    st.subheader('Saved search profiles')
    if not profiles:
        st.info('Create a search profile first.')
    for index, p in enumerate(profiles):
        with st.expander(f"{p['name']}  ·  {p.get('franchise','')}"):
            with st.form(f'edit_{index}'):
                edit_name = st.text_input('Search motif', value=p['name'])
                franchise = st.text_input('Context / origin (optional)', value=p.get('franchise', ''))
                features = st.text_area('Distinctive features (optional; English works best)', value=p.get('features', ''))
                prompts = st.text_area('Custom search texts (optional; one per line)', value='\n'.join(p.get('prompts', [])))
                st.caption('Existing reference images: ' + (', '.join(p.get('reference_images', [])) or 'none'))
                refs_new = st.file_uploader('Add reference images', type=UPLOAD_TYPES, accept_multiple_files=True, key=f'edit_refs_{index}')
                clear_refs = st.checkbox('Remove the existing reference images from this profile')
                c1,c2 = st.columns(2)
                update = c1.form_submit_button('Save changes', disabled=running())
                delete = c2.form_submit_button('Delete profile', disabled=running())
            if update:
                edit_name = edit_name.strip()
                if not edit_name or any(j != index and q['name'].strip().lower() == edit_name.lower() for j,q in enumerate(profiles)):
                    st.error('The profile name must be unique and must not be empty.')
                else:
                    refs = [] if clear_refs else list(p.get('reference_images', []))
                    if refs_new:
                        others = [q for j, q in enumerate(profiles) if j != index]
                        refs.extend(add_ref_files(refs_new, edit_name, others))
                    # {**p, ...} keeps keys the form does not edit (A2)
                    profiles[index] = {**p, 'name': edit_name, 'franchise': franchise.strip(), 'features': features.strip(),
                                       'prompts': [x.strip() for x in prompts.splitlines() if x.strip()], 'reference_images': refs}
                    if persist(profiles):
                        st.rerun()
            if delete:
                profiles.pop(index)
                if persist(profiles):
                    st.rerun()
    st.divider()
    st.subheader('New search profile')
    with st.form('new_profile', clear_on_submit=True):
        name = st.text_input('Search motif *', placeholder='e.g. red car, golden retriever, mountain landscape')
        franchise = st.text_input('Context / origin (optional)', placeholder='e.g. vehicles, pets, nature')
        features = st.text_area('Distinctive features (optional; English works best)', placeholder='red bodywork, black roof, parked on a street')
        prompts = st.text_area('Custom search texts (optional; one per line)')
        uploads = st.file_uploader('Reference images (optional)', type=UPLOAD_TYPES, accept_multiple_files=True)
        create = st.form_submit_button('Add profile', disabled=running())
    if create:
        name = name.strip()
        if not name or any(x['name'].strip().lower() == name.lower() for x in profiles):
            st.error('Please enter a unique name.')
        else:
            refs = add_ref_files(uploads or [], name, profiles)
            profiles.append({'name':name, 'franchise':franchise.strip(), 'features':features.strip(),
                             'prompts':[x.strip() for x in prompts.splitlines() if x.strip()], 'reference_images':refs})
            if persist(profiles):
                st.rerun()
    st.caption('FrameScout automatically creates several CLIP search texts from the name. No language model is required.')

with f_tab:
    st.subheader('Photo collection')
    settings['folder'] = st.text_input('Local photo folder (including subfolders)', value=settings['folder'], disabled=running())
    folder = Path(settings['folder']).expanduser()
    if folder.is_dir():
        count = sum(1 for x in folder.rglob('*') if x.is_file() and x.suffix.lower() in EXT and RESULTS not in x.parents)
        st.success(f'{count:,} supported image files found.')
    else:
        st.warning('The folder does not exist yet. Create it or choose an existing image folder.')
    st.caption('Supports JPG, PNG, WebP, BMP and TIFF. FrameScout searches local files and does not download images from online services.')

with settings_tab:
    st.subheader('AI processing')
    settings['device'] = st.selectbox('Compute device', ['auto','cpu','cuda'], index=['auto','cpu','cuda'].index(settings['device']), disabled=running(), help='auto uses CUDA if a compatible NVIDIA GPU is available, otherwise the CPU.')
    settings['batch'] = st.number_input('Batch size', min_value=1, max_value=64, value=int(settings['batch']), step=1, disabled=running())
    settings['top'] = st.number_input('Maximum matches per search profile', min_value=1, max_value=5000, value=int(settings['top']), step=25, disabled=running())
    settings['detect'] = st.checkbox('Also detect individual persons in group photos (YOLO)', value=settings['detect'], disabled=running())
    settings['max_persons'] = st.number_input('Maximum detected persons per photo', min_value=1, max_value=50, value=int(settings['max_persons']), disabled=running())
    settings['conf'] = st.slider('Minimum confidence of the person detection', .1, .9, float(settings['conf']), .05, disabled=running())
    settings['weight'] = st.slider('Weight of reference images (if any)', 0., 1., float(settings['weight']), .05, disabled=running(), help='0 = text only; 0.35 = 35 % reference images and 65 % text.')
    @st.cache_data(show_spinner=False)
    def system_info():
        import torch
        data = {'cpu': platform.processor() or platform.machine() or 'Not detected',
                'threads': os.cpu_count() or 1, 'cuda': torch.cuda.is_available(),
                'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}
        try:
            import psutil
            data['ram_gb'] = round(psutil.virtual_memory().total / (1024**3), 1)
        except (ImportError, OSError):
            data['ram_gb'] = None
        return data
    try:
        info = system_info()
        st.caption(f"Detected: {info['cpu']} · {info['threads']} logical CPU cores · " +
                   (f"{info['ram_gb']} GB RAM · " if info['ram_gb'] else 'RAM unknown · ') +
                   (f"CUDA: {info['gpu']}" if info['cuda'] else 'No CUDA GPU detected'))
        st.info('Recommendation: choose auto. A batch size of 8 is a conservative starting point; reduce it if memory runs short. Model weights are downloaded on the first run.')
    except Exception as exc:
        st.caption(f'System details could not be determined ({exc}). Automatic device selection remains available.')

with run_tab:
    st.subheader('Start search')
    is_running = running()
    c1,c2 = st.columns([1,1])
    with c1:
        start = st.button('▶ Start search', type='primary', disabled=is_running or not profiles or not Path(settings['folder']).is_dir(), use_container_width=True)
    with c2:
        stop = st.button('■ Stop search', disabled=not is_running, use_container_width=True)
    if start:
        cmd = [sys.executable, '-u', str(BASE/'framescout_engine.py'), str(Path(settings['folder']).resolve()),
            '--profiles',str(PROFILES),'--output',str(RESULTS),'--device',settings['device'],
            '--batch-size',str(settings['batch']),'--top',str(settings['top']),
            '--max-persons',str(settings['max_persons']),'--person-confidence',str(settings['conf']),
            '--reference-weight',str(settings['weight'])]
        if not settings['detect']:
            cmd.append('--no-person-detection')
        try:
            log_handle = LOG.open('w', encoding='utf-8', buffering=1)
            proc = subprocess.Popen(cmd, cwd=str(BASE), env=cache_env(), stdout=log_handle, stderr=subprocess.STDOUT)
            log_handle.close()
            st.session_state.process = proc
            st.session_state.last_exit = None
            st.rerun()
        except Exception as exc:
            st.error(f'Start failed: {exc}')
    if stop:
        proc = st.session_state.get('process')
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        st.session_state.last_exit = 'stopped'
        st.rerun()
    @st.fragment(run_every='2s')
    def status():
        proc = st.session_state.get('process')
        if proc and proc.poll() is None:
            st.info('Analysis running. Photos that are already processed are kept in the cache.')
        elif proc:
            code = proc.poll()
            if code == 0:
                st.success('The last search run finished successfully.')
            else:
                st.warning(f'The last search run ended (exit code {code}). See the log for details.')
        if LOG.exists():
            contents = LOG.read_text(encoding='utf-8', errors='replace')
            lines = contents.splitlines()
            progress = parse_progress(contents)
            if progress:
                done,total,new,cached,errors = progress
                st.progress(min(done/max(total,1),1.), text=f'{done}/{total} photos · {new} new · {cached} from cache · {errors} errors')
            with st.expander('Live log', expanded=bool(proc and proc.poll() is None)):
                st.code('\n'.join(lines[-35:]) or 'No output yet', language='text')
    status()
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
