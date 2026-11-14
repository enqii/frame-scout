"""The settings: settings.json synchronized with the widgets, and the AI settings in the tab "Settings" (A8, A46)."""
import os
import platform
import time

import psutil
import streamlit as st

from framescout_core import (AI_DETAIL_SETTINGS, AI_SETTINGS, DEFAULT_MODEL, DEFAULT_REFERENCE_WEIGHT, DEVICES, MODELS, MODEL_KEYS,
                             SETTING_RANGES, SETTING_STEPS, changed_from_defaults, check_installation, cuda_status,
                             default_settings, device_choices, downloaded_models, folder_lines, model_label,
                             model_problem, read_settings, reconcile_settings, save_settings, setting_text)

from .common import BASE, LOW_SPACE_TTL, SETTINGS, plain


@st.cache_data(show_spinner=False, max_entries=1, ttl=LOW_SPACE_TTL)
def models_downloaded():
    """The keys of the search models whose files are downloaded already (A39), asked again after LOW_SPACE_TTL."""
    try:
        return downloaded_models(BASE, dict(os.environ))
    except (OSError, ValueError):
        return set()


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


def setting_of_widget(name, value):
    """Return the setting value of the widget value of setting name.

    The photo folder field is a text area with one folder per line, and the setting is the
    list of its lines (A25): reconcile_settings and save_settings work on the lists.
    """
    return folder_lines(value) if name == 'photo_folders' else value


def widget_of_setting(name, value):
    """Return the widget value that shows the setting value of setting name (see setting_of_widget)."""
    return '\n'.join(value) if name == 'photo_folders' else value


# the labels of the AI settings' widgets, also used in the list of changed settings (A26)
AI_LABELS = {'model': 'Search model', 'device': 'Compute device', 'batch_size': 'Batch size',
             'low_priority': 'Keep the PC responsive during a search',
             'top': 'Maximum matches per search profile',
             'person_detection': 'Also detect individual persons in group photos (YOLO)',
             'max_persons': 'Maximum detected persons per photo',
             'person_confidence': 'Minimum confidence of the person detection',
             'reference_weight': 'Weight of reference images (if any)'}


def default_help(name, text=''):
    """Return the help text of the widget of setting name: text and its default (A26)."""
    return (text + ' ' if text else '') + f'Default: {setting_text(name, DEFAULT_SETTINGS[name])}.'


def reset_ai_settings():
    """Put the defaults into the AI settings' widgets (on_click, so before they are drawn; A26).

    Never as value= (A8 review); the next run saves them as a change of this session.
    """
    for name in AI_SETTINGS:
        st.session_state[setting_key(name)] = widget_of_setting(name, DEFAULT_SETTINGS[name])
    st.session_state.settings_reset = list(AI_SETTINGS)


# Settings (A8): settings.json is read on every rerun, so a reload, a restart, another tab
# or session shows the saved settings. The widgets have keys and get the saved values
# through their session state; passing them as value= would give a widget a new identity
# after every save and drop the next change (review). framescout_core.reconcile_settings
# tells a change made in this session (saved; the latest action wins) from a value another
# session saved (shown here).
def sync_settings():
    """Synchronize the settings widgets with settings.json in this page run (A8); warnings are shown here.

    Returns (settings, seen, shown, settings_taken_over): the settings the widgets show now,
    the session's settings_seen and settings_shown (changed in place by the AI settings tab)
    and the names of the settings another tab or session changed meanwhile.
    """
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
    widget_values = {name: setting_of_widget(name, st.session_state[setting_key(name)]) for name in DEFAULT_SETTINGS
                     if setting_key(name) in st.session_state}
    # the settings "Reset to defaults" reset (A26): saved as a change of this session even where
    # the widget showed the default before, and kept until the save succeeded
    settings_reset = st.session_state.get('settings_reset', ())
    setting_updates, changed_settings, settings_taken_over = reconcile_settings(
        widget_values, seen, shown, saved_settings, DEFAULT_SETTINGS, reset=settings_reset)
    for name, value in setting_updates.items():
        st.session_state[setting_key(name)] = widget_of_setting(name, value)
    if not changed_settings:
        st.session_state.pop('settings_reset', None)
    else:
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
                st.session_state.pop('settings_reset', None)
    settings = {name: setting_of_widget(name, st.session_state[setting_key(name)]) for name in DEFAULT_SETTINGS}
    return settings, seen, shown, settings_taken_over


def show_ai_settings(settings, seen, shown, active):
    """The AI settings of the tab "Settings"; returns (system_info() or None, model_problem of the chosen model or None)."""
    st.subheader('AI processing')
    # imports torch: here rather than at the top, so the profile tab is drawn first (review)
    try:
        info, info_error = system_info(), None
    except Exception as exc:
        info, info_error = None, exc
    # E22: the registry keys, the default first; the labels name the CPU factor, the download
    # and whether the model is evaluated
    # A39: a model already in the cache shows "downloaded" instead of its download size
    downloaded = models_downloaded()
    st.selectbox(AI_LABELS['model'], MODEL_KEYS, format_func=lambda key: model_label(key, key in downloaded),
                 key=setting_key('model'), disabled=active,
                 help=default_help('model', 'The AI model that compares your search texts and reference images '
                                            'with the photos.'))
    chosen_model = MODELS[settings['model']]
    if settings['model'] == DEFAULT_MODEL:
        st.caption("The default search model: the fastest one, and the one FrameScout's settings were tuned for.")
    else:
        st.caption(f'{chosen_model.label} takes about {chosen_model.cpu_factor.lstrip("~")} as long as the default '
                   'to analyze a photo on a CPU (not measured on a GPU) and '
                   + ('is downloaded already. ' if settings['model'] in downloaded else
                      f'downloads {chosen_model.download} the first time it is used. ')
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
    st.selectbox(AI_LABELS['device'], devices, key=setting_key('device'), disabled=active,
                 help=default_help('device', 'auto uses CUDA if a compatible NVIDIA GPU is available, otherwise '
                                             'the CPU.'))
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
    st.number_input(AI_LABELS['batch_size'], **number_range('batch_size'), step=1, key=setting_key('batch_size'),
                    disabled=active, help=default_help('batch_size'))
    # F4: the engine's --low-priority; its effect on the search time is not measured yet
    st.checkbox(AI_LABELS['low_priority'], key=setting_key('low_priority'), disabled=active,
                help=default_help('low_priority', 'Runs the search at a lower priority, so other programs get the '
                                                  'CPU first, and with fewer CPU threads for the AI models. The '
                                                  'search may take longer while you use the PC. Helps little when '
                                                  'the GPU does the work; how much it helps is not measured yet.'))
    st.number_input(AI_LABELS['top'], **number_range('top'), step=25, key=setting_key('top'), disabled=active,
                    help=default_help('top'))
    # F32: the settings changed less often in an expander, open while one of them differs from
    # its default, so a changed value is never hidden. `expanded` only ever turns True in a
    # browser session: Streamlit closes an open expander when it turns False on a rerun, e.g.
    # after a value is set back to its default (review)
    if changed_from_defaults({name: st.session_state[setting_key(name)] for name in AI_DETAIL_SETTINGS},
                             DEFAULT_SETTINGS, AI_DETAIL_SETTINGS):
        st.session_state['ai_details_open'] = True
    with st.expander('Person detection and reference images', expanded=st.session_state.get('ai_details_open', False)):
        st.checkbox(AI_LABELS['person_detection'], key=setting_key('person_detection'), disabled=active,
                    help=default_help('person_detection'))
        # the checkbox value of this page run: its sub-settings apply only while it is on
        detecting = st.session_state[setting_key('person_detection')]
        st.number_input(AI_LABELS['max_persons'], **number_range('max_persons'), key=setting_key('max_persons'),
                        disabled=active or not detecting, help=default_help('max_persons'))
        st.slider(AI_LABELS['person_confidence'], **number_range('person_confidence'),
                  step=SETTING_STEPS['person_confidence'], key=setting_key('person_confidence'),
                  disabled=active or not detecting, help=default_help('person_confidence'))
        if not detecting:
            st.caption('The two person settings apply only while the person detection is on.')
        st.slider(AI_LABELS['reference_weight'], **number_range('reference_weight'),
                  step=SETTING_STEPS['reference_weight'], key=setting_key('reference_weight'), disabled=active,
                  help=default_help('reference_weight', f'0 = text only; {DEFAULT_REFERENCE_WEIGHT:g} = '
                                    f'{DEFAULT_REFERENCE_WEIGHT:.0%} reference images and '
                                    f'{1 - DEFAULT_REFERENCE_WEIGHT:.0%} text. Text and reference scores are scaled '
                                    'to the photos of the search before they are weighted.'))
    # what differs from the defaults, as the widgets show it now (a substituted device is
    # shown as "auto"), and the way back to them (A26)
    not_default = changed_from_defaults({name: st.session_state[setting_key(name)] for name in AI_SETTINGS},
                                        DEFAULT_SETTINGS, AI_SETTINGS)
    c1, c2 = st.columns([3, 1], vertical_alignment='center')
    if not_default:
        c1.caption('Changed from the default: ' + ' · '.join(
            f'{AI_LABELS[name]} (default {setting_text(name, DEFAULT_SETTINGS[name])})' for name in not_default) + '.')
    else:
        c1.caption('All AI settings have their default values.')
    c2.button('Reset to defaults', on_click=reset_ai_settings, disabled=active or not not_default, width='stretch',
              help='Sets every AI setting on this tab back to its default and saves that. The photo folders stay '
                   'as they are.')
    if info:
        st.caption(f"Detected: {info['cpu']} · {info['threads']} logical CPU cores · " +
                   (f"{info['ram_gb']} GB RAM · " if info['ram_gb'] else 'RAM unknown · ') +
                   cuda_status(info['cuda'], info['cuda_build'], info['gpu']))
        st.info('Recommendation: choose auto. A batch size of 8 is a conservative starting point; reduce it if memory runs short. Model weights are downloaded on the first run.')
    else:
        st.caption(f'System details could not be determined ({info_error}). Automatic device selection remains available.')
    # F15: the read-only self-test of Check-FrameScout.bat; importing PyTorch in a subprocess
    # takes a few seconds, so it runs only on the button
    with st.expander('Check installation'):
        st.caption('Checks the Python environment, the package versions, PyTorch (and the GPU for a CUDA build), '
                   'whether .cache and results can be written, the downloaded model files and the free disk space. '
                   'It changes nothing. Check-FrameScout.bat runs the same check when the app does not start.')
        if st.button('Check installation'):
            with st.spinner('Checking the installation ...'):
                st.session_state['install_check'] = check_installation(BASE, dict(os.environ))
                st.session_state['install_check_at'] = time.time()
        if 'install_check' in st.session_state:
            # the results are kept until the next click: say when they were found (review)
            st.caption(f"Checked at {time.strftime('%H:%M:%S', time.localtime(st.session_state['install_check_at']))}"
                       '. After you fix something, click the button again.')
        for result in st.session_state.get('install_check', []):
            text = plain(f'{result.name}: {result.text}')
            if result.ok is False:
                st.error(text + (f'  \n**Fix:** {plain(result.fix)}' if result.fix else ''))
            elif result.ok:
                st.success(text)
            else:
                st.info(text)
    return info, model_missing
