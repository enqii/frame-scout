"""FrameScout: lokale Streamlit-Oberflaeche fuer framescout_engine.py."""
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

import streamlit as st

from framescout_core import EXT, profile_slugs, slugify

BASE = Path(__file__).resolve().parent
PROFILES = BASE / 'profiles.json'
REFS = BASE / 'references'
RESULTS = BASE / 'results'
LOG = BASE / 'run.log'
UPLOAD_TYPES = sorted(x.lstrip('.') for x in EXT)

st.set_page_config(page_title='FrameScout', page_icon='🔎', layout='wide')
st.markdown('''<style>.block-container{padding-top:2rem;max-width:1300px}
.stButton button{border-radius:8px}</style>''', unsafe_allow_html=True)

def read_profiles():
    if not PROFILES.exists():
        return []
    data = json.loads(PROFILES.read_text(encoding='utf-8-sig'))
    return data.get('profiles', [])

def save_profiles(data):
    tmp = PROFILES.with_suffix('.tmp')
    tmp.write_text(json.dumps({'profiles': data}, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(PROFILES)

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

def add_ref_files(files, name):
    target_dir = REFS / slugify(name)
    target_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, f in enumerate(files):
        suffix = Path(f.name).suffix.lower()
        if suffix not in EXT:
            continue
        target = target_dir / f'reference-{i+1}{suffix}'
        target.write_bytes(f.getvalue())
        paths.append(target.relative_to(BASE).as_posix())
    return paths

st.title('🔎 FrameScout')
st.caption('Lokale KI-Suche in großen Fotosammlungen · Bilder bleiben auf deinem Rechner')

try:
    profiles = read_profiles()
except (OSError, ValueError) as exc:
    st.error(f'profiles.json ist ungültig: {exc}')
    st.stop()

if 'settings' not in st.session_state:
    st.session_state.settings = {'folder': str(BASE/'photos'), 'device': 'auto', 'batch': 8,
        'top': 150, 'detect': True, 'max_persons': 12, 'conf': 0.30, 'weight': 0.35}
settings = st.session_state.settings
p_tab, f_tab, settings_tab, run_tab = st.tabs(['Suchprofile', 'Fotoquelle', 'KI-Einstellungen', 'Suche & Ergebnisse'])

with p_tab:
    st.subheader('Gespeicherte Suchprofile')
    if not profiles:
        st.info('Lege zunächst ein Suchprofil an.')
    for index, p in enumerate(profiles):
        with st.expander(f"{p['name']}  ·  {p.get('franchise','')}"):
            with st.form(f'edit_{index}'):
                edit_name = st.text_input('Suchmotiv', value=p['name'])
                franchise = st.text_input('Kontext / Herkunft (optional)', value=p.get('franchise', ''))
                features = st.text_area('Zusätzliche Merkmale (am besten Englisch)', value=p.get('features', ''))
                prompts = st.text_area('Zusätzliche Suchtexte: eine Zeile pro Text (optional)', value='\n'.join(p.get('prompts', [])))
                st.caption('Vorhandene Referenzen: ' + (', '.join(p.get('reference_images', [])) or 'keine'))
                refs_new = st.file_uploader('Referenzbilder hinzufügen', type=UPLOAD_TYPES, accept_multiple_files=True, key=f'edit_refs_{index}')
                clear_refs = st.checkbox('Vorhandene Referenzbilder aus Profil entfernen')
                c1,c2 = st.columns(2)
                update = c1.form_submit_button('Änderungen speichern', disabled=running())
                delete = c2.form_submit_button('Profil entfernen', disabled=running())
            if update:
                edit_name = edit_name.strip()
                if not edit_name or any(j != index and q['name'].lower() == edit_name.lower() for j,q in enumerate(profiles)):
                    st.error('Der Profilname muss eindeutig und nicht leer sein.')
                else:
                    refs = [] if clear_refs else list(p.get('reference_images', []))
                    if refs_new:
                        refs.extend(add_ref_files(refs_new, edit_name))
                    profiles[index] = {'name': edit_name, 'franchise': franchise.strip(), 'features': features.strip(),
                                       'prompts': [x.strip() for x in prompts.splitlines() if x.strip()], 'reference_images': refs}
                    save_profiles(profiles)
                    st.rerun()
            if delete:
                profiles.pop(index)
                save_profiles(profiles)
                st.rerun()
    st.divider()
    st.subheader('Neues Suchprofil')
    with st.form('new_profile', clear_on_submit=True):
        name = st.text_input('Suchmotiv *', placeholder='z. B. rotes Auto, Golden Retriever, Berglandschaft')
        franchise = st.text_input('Kontext / Herkunft (optional)', placeholder='z. B. Batman / DC Comics')
        features = st.text_area('Erkennungsmerkmale (optional)', placeholder='red bodywork, black roof, parked on a street')
        prompts = st.text_area('Eigene Suchformulierungen (optional; eine pro Zeile)')
        uploads = st.file_uploader('Referenzbilder (optional)', type=UPLOAD_TYPES, accept_multiple_files=True)
        create = st.form_submit_button('Profil hinzufügen', disabled=running())
    if create:
        name = name.strip()
        if not name or any(x['name'].lower() == name.lower() for x in profiles):
            st.error('Bitte einen eindeutigen Namen eingeben.')
        else:
            refs = add_ref_files(uploads or [], name)
            profiles.append({'name':name, 'franchise':franchise.strip(), 'features':features.strip(),
                             'prompts':[x.strip() for x in prompts.splitlines() if x.strip()], 'reference_images':refs})
            save_profiles(profiles)
            st.rerun()
    st.caption('FrameScout erzeugt aus dem Namen automatisch mehrere CLIP-Suchtexte. Ein LLM ist nicht erforderlich.')

with f_tab:
    st.subheader('Fotosammlung')
    settings['folder'] = st.text_input('Lokaler Fotoordner (inklusive Unterordner)', value=settings['folder'], disabled=running())
    folder = Path(settings['folder']).expanduser()
    if folder.is_dir():
        count = sum(1 for x in folder.rglob('*') if x.is_file() and x.suffix.lower() in EXT and RESULTS not in x.parents)
        st.success(f'{count:,} unterstützte Bilddateien gefunden.'.replace(',', '.'))
    else:
        st.warning('Ordner noch nicht vorhanden. Lege ihn an oder wähle einen existierenden Bildordner.')
    st.caption('Unterstützt JPG, PNG, WebP, BMP und TIFF. FrameScout durchsucht lokale Dateien und lädt keine Bilder von Online-Diensten herunter.')

with settings_tab:
    st.subheader('KI-Verarbeitung')
    settings['device'] = st.selectbox('Rechengerät', ['auto','cpu','cuda'], index=['auto','cpu','cuda'].index(settings['device']), disabled=running(), help='Automatisch verwendet CUDA, wenn eine kompatible NVIDIA-GPU verfügbar ist; sonst CPU.')
    settings['batch'] = st.number_input('Batchgröße', min_value=1, max_value=64, value=int(settings['batch']), step=1, disabled=running())
    settings['top'] = st.number_input('Maximale Treffer je Suchprofil', min_value=1, max_value=5000, value=int(settings['top']), step=25, disabled=running())
    settings['detect'] = st.checkbox('Personen in Gruppenfotos zusätzlich erkennen (YOLO)', value=settings['detect'], disabled=running())
    settings['max_persons'] = st.number_input('Maximal erkannte Personen je Foto', min_value=1, max_value=50, value=int(settings['max_persons']), disabled=running())
    settings['conf'] = st.slider('Mindest-Konfidenz der Personenerkennung', .1, .9, float(settings['conf']), .05, disabled=running())
    settings['weight'] = st.slider('Gewichtung Referenzbilder (falls vorhanden)', 0., 1., float(settings['weight']), .05, disabled=running(), help='0 = nur Text; 0,35 = 35 % Referenzbild und 65 % Text.')
    @st.cache_data(show_spinner=False)
    def system_info():
        import torch
        data = {'cpu': platform.processor() or platform.machine() or 'Nicht erkannt',
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
        st.caption(f"Erkannt: {info['cpu']} · {info['threads']} logische CPU-Kerne · " +
                   (f"{info['ram_gb']} GB RAM · " if info['ram_gb'] else 'RAM unbekannt · ') +
                   (f"CUDA: {info['gpu']}" if info['cuda'] else 'Keine CUDA-GPU erkannt'))
        st.info('Empfehlung: Automatisch wählen. Batchgröße 8 ist ein konservativer Ausgangspunkt; bei Speicherproblemen reduzieren. Beim ersten Lauf werden Modellgewichte heruntergeladen.')
    except Exception as exc:
        st.caption(f'Systemdetails konnten nicht ermittelt werden ({exc}). Automatische Gerätewahl bleibt verfügbar.')

with run_tab:
    st.subheader('Suche starten')
    is_running = running()
    c1,c2 = st.columns([1,1])
    with c1:
        start = st.button('▶ Suche starten', type='primary', disabled=is_running or not profiles or not Path(settings['folder']).is_dir(), use_container_width=True)
    with c2:
        stop = st.button('■ Suche stoppen', disabled=not is_running, use_container_width=True)
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
            st.error(f'Start fehlgeschlagen: {exc}')
    if stop:
        proc = st.session_state.get('process')
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        st.session_state.last_exit = 'angehalten'
        st.rerun()
    @st.fragment(run_every='2s')
    def status():
        proc = st.session_state.get('process')
        if proc and proc.poll() is None:
            st.info('Analyse läuft. Bereits fertig verarbeitete Fotos werden zwischengespeichert.')
        elif proc:
            code = proc.poll()
            if code == 0:
                st.success('Letzter Suchlauf erfolgreich beendet.')
            else:
                st.warning(f'Letzter Suchlauf beendet (Exitcode {code}). Einzelheiten stehen im Protokoll.')
        if LOG.exists():
            contents = LOG.read_text(encoding='utf-8', errors='replace')
            lines = contents.splitlines()
            progress = re.findall(r'(\d+)/(\d+) \| Neu: (\d+) \| Cache: (\d+) \| Fehler: (\d+)',contents)
            if progress:
                done,total,new,cached,errors = map(int,progress[-1])
                st.progress(min(done/max(total,1),1.), text=f'{done}/{total} Fotos · {new} neu · {cached} aus Cache · {errors} Fehler')
            with st.expander('Live-Protokoll', expanded=bool(proc and proc.poll() is None)):
                st.code('\n'.join(lines[-35:]) or 'Noch keine Ausgabe', language='text')
    status()
    st.divider()
    st.subheader('Ergebnisgalerien')
    if RESULTS.exists():
        # same file names as the engine: unique slugs in profile order
        for p, slug in zip(profiles, profile_slugs([q['name'].strip() for q in profiles])):
            page = RESULTS/(slug+'.html')
            if page.exists():
                st.download_button(f"HTML exportieren: {p['name']}", page.read_bytes(), file_name=page.name, mime='text/html', key=f'dl_{p["name"]}')
                st.caption(f'Lokale Galerie öffnen: {page}')
        st.caption('Öffne die HTML-Dateien im Dateimanager. Sie verlinken auf die lokalen Vorschaubilder und Originalfotos; für die vollständige Galerie den Ergebnisordner zusammenhalten.')
    else:
        st.caption('Nach dem ersten Suchlauf erscheinen die HTML-Galerien im Ordner results.')
