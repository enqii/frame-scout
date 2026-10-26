"""The app's settings.json (A8): defaults, validation, saving and the widget sync."""
from pathlib import Path

from ._common import _read_json_object, _update_locked


# The app's settings (A8): kept in settings.json in the project folder, so they survive a
# browser reload and a restart. Only values that differ from the defaults are written, so
# the default photo folder follows the project folder when it is moved.
SETTINGS_FILE = 'settings.json'
# the engine's --device choices
DEVICES = ('auto', 'cpu', 'cuda')
# (minimum, maximum) of each number setting; the app builds its widgets from them (Streamlit
# raises for a value outside a widget's range), so both always agree (review). Float
# bounds mark a float setting.
SETTING_RANGES = {'batch_size': (1, 64), 'top': (1, 5000), 'max_persons': (1, 50),
                  'person_confidence': (0.1, 0.9), 'reference_weight': (0.0, 1.0)}
# step of the app's sliders; known_signatures computes the cache signatures they lead to (E11)
SETTING_STEPS = {'person_confidence': 0.05, 'reference_weight': 0.05}
# default weight of the reference images: 0.35 before the scores were normalized (E5);
# 0.3 did best on the local evaluation set (user decision in PR #11). A value saved in
# settings.json is kept as it is, also the old default.
DEFAULT_REFERENCE_WEIGHT = 0.3
# seconds save_settings waits for the lock around its read-merge-write
SETTINGS_LOCK_TIMEOUT = 5.0


def default_settings(base):
    """Return the app's default settings; base is the project folder (photos/ is the default input)."""
    return {'photo_folder': str(Path(base) / 'photos'), 'device': 'auto', 'batch_size': 8, 'top': 150,
            'person_detection': True, 'max_persons': 12, 'person_confidence': 0.30,
            'reference_weight': DEFAULT_REFERENCE_WEIGHT}


def _setting_value(key, value):
    """Return value as the setting key uses it, or None if it is not allowed."""
    if key == 'photo_folder':
        return value if isinstance(value, str) else None
    if key == 'device':
        return value if isinstance(value, str) and value in DEVICES else None
    if key == 'person_detection':
        return value if isinstance(value, bool) else None
    if key not in SETTING_RANGES:
        return None
    low, high = SETTING_RANGES[key]
    number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(low, float):
        # rounded: a slider computes min + n * step, e.g. 0.30000000000000004 (review)
        return round(float(value), 4) if number and low <= value <= high else None  # NaN is never in range
    return value if number and isinstance(value, int) and low <= value <= high else None


def _read_settings_file(filename, attempts=5, retry_delay=0.05):
    """Return the JSON object of a settings file ({} if it is missing); ValueError if unreadable.

    On Windows, reading fails for a moment while another session replaces the file, so an
    OSError is retried up to attempts times, retry_delay seconds apart (review).
    """
    return _read_json_object(filename, 'settings file', attempts, retry_delay)


def read_settings(filename, defaults, attempts=5, retry_delay=0.05):
    """Return (settings, problems) of the app's settings file.

    settings has the keys of defaults: a saved value replaces its default if it is allowed
    (the same range as the app's widget); a missing file gives the defaults. problems lists
    the saved values that are not allowed and were replaced by their defaults. Unknown keys
    are ignored (save_settings keeps them). Raises ValueError (including JSON and Unicode
    decoding errors) for a file that is not a JSON object, and OSError if it still cannot
    be read after attempts tries.
    """
    data = _read_settings_file(filename, attempts, retry_delay)
    settings, problems = dict(defaults), []
    for key in defaults:
        if key not in data:
            continue
        value = _setting_value(key, data[key])
        if value is None:
            problems.append(f'{key}: {data[key]!r} is not allowed, the default {defaults[key]!r} is used')
        else:
            settings[key] = value
    return settings, problems


def save_settings(filename, changes, defaults, attempts=5, retry_delay=0.05, lock_timeout=SETTINGS_LOCK_TIMEOUT):
    """Write the changed settings into the app's settings file; return them as written.

    changes are merged into the file as it is now (another tab or session may have saved
    other settings in between). The read-merge-write holds a RunLock on <filename>.lock
    (app sessions are threads of one process, and two RunLocks conflict there too), so two
    sessions saving at the same moment cannot lose a change (review); the lock file stays
    (empty). Saved values that are not allowed (read_settings replaced them by their
    defaults and reported them) and values equal to their default are removed; unknown
    keys are kept. No file is created if there is nothing to write. The file is replaced
    atomically; on Windows that fails while another session reads it at that moment, so
    reading and replacing are tried up to attempts times. The returned dict holds the
    changes as stored, e.g. rounded floats. Raises ValueError for a change that is not
    allowed and for an unreadable file, which is never replaced, and OSError if the lock is
    not free within lock_timeout seconds or reading or writing keeps failing.
    """
    filename = Path(filename)
    normalized = {}
    for key, value in changes.items():
        allowed = _setting_value(key, value) if key in defaults else value
        if allowed is None:
            raise ValueError(f'{key}: {value!r} is not allowed')
        normalized[key] = allowed

    def update(current):
        document = {}
        for key, value in {**current, **normalized}.items():
            if key in defaults:
                # after normalizing, a known setting has the type of its default (no True == 1)
                value = _setting_value(key, value)
                if value is None or value == defaults[key]:
                    continue
            document[key] = value
        return document if document or filename.exists() else None

    _update_locked(filename, lambda: _read_settings_file(filename, attempts, retry_delay), update,
                   attempts, retry_delay, lock_timeout)
    return normalized


def reconcile_settings(widgets, seen, shown, saved, defaults):
    """Bring the app's settings widgets and the saved settings together (A8 review).

    Called at the start of every page run, before the widgets are drawn. widgets maps a
    setting to its widget's current value (missing: a new page, or the widget was not drawn
    in the last run). seen and shown are this session's records per setting: seen is the
    saved value it last took from or wrote to the file, shown is the value its widget showed
    then. They differ for a substitute (e.g. "auto" shown for a saved device PyTorch cannot
    use) and for slider noise (0.30000000000000004 shown, 0.3 saved). saved is the result of
    read_settings, or None if the file cannot be read.

    Returns (updates, changed, taken_over). updates are the values to put into the widgets
    now. changed are the widgets changed in this session, to be saved; after a successful
    save the caller stores the widget values in shown and the result of save_settings in
    seen, and after a failed one neither, so the save is tried again on the next run.
    taken_over lists the settings another session saved, now shown here. A change in this
    session wins over another session's save, since it is the later action. seen and shown
    are updated for the updates.
    """
    updates, changed, taken_over = {}, {}, []
    for name, default in defaults.items():
        file_value = default if saved is None else saved[name]
        if name not in widgets:
            updates[name] = seen[name] = shown[name] = file_value
        elif widgets[name] != shown.get(name, widgets[name]):
            changed[name] = widgets[name]
        elif saved is not None and file_value != seen.get(name, file_value):
            updates[name] = seen[name] = shown[name] = file_value
            taken_over.append(name)
    return updates, changed, taken_over
