"""The app's settings.json: defaults, validation and saving without losing data (framescout_core, A8)."""
import json
import threading
from pathlib import Path

import pytest

from framescout_core import (DEFAULT_REFERENCE_WEIGHT, DEVICES, SETTING_RANGES, SETTINGS_FILE, default_settings,
                             read_settings, reconcile_settings, save_settings)


@pytest.fixture
def defaults(tmp_path):
    return default_settings(tmp_path)


def write(path, data):
    path.write_text(json.dumps(data), encoding='utf-8')
    return path


def stored(path):
    return json.loads(path.read_text(encoding='utf-8'))


def test_the_defaults_are_the_previous_session_defaults(tmp_path):
    assert SETTINGS_FILE == 'settings.json'
    assert default_settings(tmp_path) == {
        'photo_folder': str(tmp_path / 'photos'), 'device': 'auto', 'batch_size': 8, 'top': 150,
        'person_detection': True, 'max_persons': 12, 'person_confidence': 0.30, 'reference_weight': 0.3}


def test_the_default_reference_weight_is_the_evaluated_one():
    # 0.35 before E4/E5; 0.3 did best with the normalized scores on the local evaluation
    # set (user decision in PR #11); a saved 0.35 in settings.json stays as it is
    assert DEFAULT_REFERENCE_WEIGHT == 0.3


def test_a_missing_file_gives_the_defaults(tmp_path, defaults):
    settings, problems = read_settings(tmp_path / 'settings.json', defaults)
    assert settings == defaults and problems == []
    assert settings is not defaults  # the caller may change it


def test_saved_values_replace_the_defaults_and_missing_keys_keep_them(tmp_path, defaults):
    path = write(tmp_path / 'settings.json', {'photo_folder': 'D:\\Fotos', 'device': 'cpu', 'batch_size': 16,
                                              'person_detection': False, 'reference_weight': 0})
    settings, problems = read_settings(path, defaults)
    assert problems == []
    assert settings == {**defaults, 'photo_folder': 'D:\\Fotos', 'device': 'cpu', 'batch_size': 16,
                        'person_detection': False, 'reference_weight': 0.0}
    assert isinstance(settings['reference_weight'], float)


def test_a_byte_order_mark_is_accepted(tmp_path, defaults):
    # e.g. a file saved with Windows Notepad as "UTF-8 with BOM"
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps({'top': 300}), encoding='utf-8-sig')
    assert read_settings(path, defaults) == ({**defaults, 'top': 300}, [])


@pytest.mark.parametrize('key, value', [
    ('photo_folder', 5), ('device', 'gpu'), ('device', None),
    ('batch_size', 0), ('batch_size', 65), ('batch_size', 8.0), ('batch_size', True), ('batch_size', '8'),
    ('top', 5001), ('max_persons', 51), ('person_detection', 1), ('person_detection', 'yes'),
    ('person_confidence', 0.05), ('person_confidence', 0.95), ('person_confidence', True),
    ('reference_weight', -0.1), ('reference_weight', 1.5), ('reference_weight', float('nan')),
])
def test_an_invalid_value_falls_back_to_its_default_and_is_reported(tmp_path, defaults, key, value):
    # the widgets raise for values outside their range, so these must never reach them
    other = {'batch_size': 16} if key == 'top' else {'top': 300}  # a valid value is still used
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps({key: value, **other}), encoding='utf-8')
    settings, problems = read_settings(path, defaults)
    assert settings == {**defaults, **other}
    assert len(problems) == 1 and key in problems[0]


def test_unknown_keys_are_ignored(tmp_path, defaults):
    path = write(tmp_path / 'settings.json', {'theme': 'dark', 'top': 300})
    assert read_settings(path, defaults) == ({**defaults, 'top': 300}, [])


@pytest.mark.parametrize('content', ['{"top": 300', '[1, 2]', '"text"', ''])
def test_an_unreadable_file_raises_value_error(tmp_path, defaults, content):
    path = tmp_path / 'settings.json'
    path.write_text(content, encoding='utf-8')
    with pytest.raises(ValueError):
        read_settings(path, defaults)


def test_invalid_utf8_raises_value_error(tmp_path, defaults):
    path = tmp_path / 'settings.json'
    path.write_bytes(b'{"photo_folder": "\xff"}')
    with pytest.raises(ValueError):
        read_settings(path, defaults)


def test_saving_creates_the_file_with_only_the_values_that_differ_from_the_defaults(tmp_path, defaults):
    path = tmp_path / 'settings.json'
    save_settings(path, {'batch_size': 16, 'top': 150}, defaults)
    # the default photo folder is not written: it follows the project folder when it is moved
    assert stored(path) == {'batch_size': 16}
    assert read_settings(path, defaults) == ({**defaults, 'batch_size': 16}, [])


def test_saving_only_defaults_writes_no_file(tmp_path, defaults):
    path = tmp_path / 'settings.json'
    save_settings(path, {'top': 150}, defaults)
    assert not path.exists()


def test_saving_merges_the_changes_into_the_current_file(tmp_path, defaults):
    # another tab or session may have saved other settings since this one read the file
    path = write(tmp_path / 'settings.json', {'device': 'cpu', 'top': 300, 'theme': 'dark'})
    save_settings(path, {'batch_size': 4}, defaults)
    assert stored(path) == {'device': 'cpu', 'top': 300, 'theme': 'dark', 'batch_size': 4}


def test_a_value_set_back_to_its_default_is_removed(tmp_path, defaults):
    path = write(tmp_path / 'settings.json', {'device': 'cpu', 'person_detection': False, 'top': 300})
    save_settings(path, {'device': 'auto', 'person_detection': True}, defaults)
    assert stored(path) == {'top': 300}


def test_saving_never_replaces_an_unreadable_file(tmp_path, defaults):
    path = tmp_path / 'settings.json'
    path.write_text('{"top": 300', encoding='utf-8')
    with pytest.raises(ValueError):
        save_settings(path, {'batch_size': 4}, defaults)
    assert path.read_text(encoding='utf-8') == '{"top": 300'


def test_saving_leaves_no_temporary_file(tmp_path, defaults):
    path = tmp_path / 'settings.json'
    save_settings(path, {'batch_size': 4}, defaults)
    save_settings(path, {'batch_size': 8}, defaults)
    # the lock file of save_settings stays (empty), like the run lock
    assert sorted(x.name for x in tmp_path.iterdir()) == ['settings.json', 'settings.json.lock']
    assert stored(path) == {}


def test_a_failed_replace_is_retried(tmp_path, defaults, monkeypatch):
    # on Windows, replacing fails while another session reads the file at that moment
    import framescout_core
    calls = []
    real_replace = framescout_core.os.replace

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) == 1:
            raise PermissionError('in use')
        real_replace(src, dst)

    monkeypatch.setattr(framescout_core.os, 'replace', flaky)
    path = tmp_path / 'settings.json'
    save_settings(path, {'top': 300}, defaults, retry_delay=0)
    assert len(calls) == 2 and stored(path) == {'top': 300}


def test_a_replace_that_keeps_failing_raises_os_error(tmp_path, defaults, monkeypatch):
    import framescout_core

    def failing(src, dst):
        raise PermissionError('in use')

    monkeypatch.setattr(framescout_core.os, 'replace', failing)
    path = write(tmp_path / 'settings.json', {'top': 300})
    with pytest.raises(OSError):
        save_settings(path, {'top': 400}, defaults, attempts=3, retry_delay=0)
    assert stored(path) == {'top': 300}
    # the lock file of save_settings stays (empty), like the run lock
    assert sorted(x.name for x in tmp_path.iterdir()) == ['settings.json', 'settings.json.lock']


def test_a_transient_read_error_is_retried(tmp_path, defaults, monkeypatch):
    # on Windows, reading fails for a moment while another session replaces the file (review)
    path = write(tmp_path / 'settings.json', {'top': 300})
    real_read = Path.read_text
    calls = []

    def flaky(self, *args, **kwargs):
        calls.append(self)
        if len(calls) == 1:
            raise PermissionError('being replaced')
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', flaky)
    assert read_settings(path, defaults, retry_delay=0) == ({**defaults, 'top': 300}, [])
    assert len(calls) == 2


def test_a_read_error_that_persists_raises_os_error(tmp_path, defaults, monkeypatch):
    path = write(tmp_path / 'settings.json', {'top': 300})

    def failing(self, *args, **kwargs):
        raise PermissionError('in use')

    monkeypatch.setattr(Path, 'read_text', failing)
    with pytest.raises(OSError):
        read_settings(path, defaults, attempts=3, retry_delay=0)


def test_float_noise_of_a_slider_is_rounded(tmp_path, defaults):
    # a slider computes min + n * step, e.g. 0.1 + 4 * 0.05 = 0.30000000000000004 (review)
    noisy = 0.1 + 4 * 0.05
    assert noisy != 0.30
    path = tmp_path / 'settings.json'
    save_settings(path, {'person_confidence': noisy}, defaults)
    assert not path.exists()  # equal to the default once rounded
    save_settings(path, {'reference_weight': 0.15 + 0.2}, defaults)
    assert stored(path) == {'reference_weight': 0.35}
    write(path, {'person_confidence': noisy})
    assert read_settings(path, defaults)[0]['person_confidence'] == 0.30


def test_saving_removes_invalid_values_that_were_replaced_by_their_defaults(tmp_path, defaults):
    # otherwise the warning about them would come back on every page run (review)
    path = write(tmp_path / 'settings.json', {'batch_size': 0, 'device': 'gpu', 'theme': 'dark'})
    save_settings(path, {'top': 300}, defaults)
    assert stored(path) == {'theme': 'dark', 'top': 300}


@pytest.mark.parametrize('changes', [{'batch_size': 0}, {'device': 'gpu'}, {'reference_weight': 2.0},
                                     # True == 1 in Python: a bool is never taken for a number, or the reverse
                                     {'batch_size': True}, {'person_detection': 1}])
def test_an_invalid_change_raises_value_error_and_changes_nothing(tmp_path, defaults, changes):
    path = write(tmp_path / 'settings.json', {'top': 300})
    with pytest.raises(ValueError):
        save_settings(path, changes, defaults)
    assert stored(path) == {'top': 300}


def test_saving_returns_the_values_as_written(tmp_path, defaults):
    # the app remembers these, not the raw widget values (review: rounded floats)
    path = tmp_path / 'settings.json'
    written = save_settings(path, {'person_confidence': 0.1 + 4 * 0.05, 'reference_weight': 0, 'top': 300}, defaults)
    assert written == {'person_confidence': 0.3, 'reference_weight': 0.0, 'top': 300}
    assert isinstance(written['reference_weight'], float)


def test_concurrent_saves_of_different_settings_keep_every_change(tmp_path, defaults):
    # app sessions are threads of one process; without a lock around read-merge-write,
    # two saves at the same moment lose one change (review)
    path = tmp_path / 'settings.json'
    names = ['batch_size', 'top', 'max_persons']
    values = {'batch_size': range(9, 30), 'top': range(200, 221), 'max_persons': range(13, 34)}
    errors = []
    start = threading.Barrier(len(names))

    def worker(name):
        start.wait()
        try:
            for value in values[name]:
                save_settings(path, {name: value}, defaults, retry_delay=0.01)
        except Exception as exc:  # reported below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in names]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert stored(path) == {name: values[name][-1] for name in names}


def test_the_ranges_are_the_ones_of_the_widgets():
    # the app builds its widgets from SETTING_RANGES, so both always agree (review)
    assert SETTING_RANGES == {'batch_size': (1, 64), 'top': (1, 5000), 'max_persons': (1, 50),
                              'person_confidence': (0.1, 0.9), 'reference_weight': (0.0, 1.0)}
    assert DEVICES == ('auto', 'cpu', 'cuda')


# --- reconcile_settings: widget state, the session's view and settings.json (A8 review) ---

def test_a_new_page_shows_the_saved_values(defaults):
    seen, shown = {}, {}
    saved = {**defaults, 'top': 300}
    updates, changed, taken_over = reconcile_settings({}, seen, shown, saved, defaults)
    assert updates == saved and changed == {} and taken_over == []
    assert seen == saved and shown == saved


def test_a_widget_changed_in_this_session_is_reported_as_changed(defaults):
    seen, shown = dict(defaults), dict(defaults)
    widgets = {**defaults, 'batch_size': 16}
    updates, changed, taken_over = reconcile_settings(widgets, seen, shown, dict(defaults), defaults)
    assert updates == {} and changed == {'batch_size': 16} and taken_over == []
    assert seen == defaults and shown == defaults  # updated by the caller after a successful save


def test_a_value_saved_by_another_session_is_taken_over(defaults):
    seen, shown = dict(defaults), dict(defaults)
    saved = {**defaults, 'top': 300}
    updates, changed, taken_over = reconcile_settings(dict(defaults), seen, shown, saved, defaults)
    assert updates == {'top': 300} and changed == {} and taken_over == ['top']
    assert seen['top'] == 300 and shown['top'] == 300


def test_a_change_in_this_session_wins_over_another_sessions_save(defaults):
    # the latest action wins: the widget change happened after this session last looked
    seen, shown = dict(defaults), dict(defaults)
    saved = {**defaults, 'top': 300}
    updates, changed, taken_over = reconcile_settings({**defaults, 'top': 400}, seen, shown, saved, defaults)
    assert updates == {} and changed == {'top': 400} and taken_over == []


def test_a_widget_showing_a_substitute_is_not_a_change(defaults):
    # a saved "cuda" that PyTorch cannot use is shown as "auto": shown differs from seen
    seen, shown = {**defaults, 'device': 'cuda'}, {**defaults, 'device': 'auto'}
    saved = {**defaults, 'device': 'cuda'}
    updates, changed, taken_over = reconcile_settings(dict(defaults), seen, shown, saved, defaults)
    assert updates == {} and changed == {} and taken_over == []


def test_slider_noise_after_a_save_does_not_look_like_another_session(defaults):
    # the caller stores the raw widget value as shown and the written value as seen (review)
    noisy = 0.1 + 4 * 0.05
    seen, shown = {**defaults, 'person_confidence': 0.3}, {**defaults, 'person_confidence': noisy}
    updates, changed, taken_over = reconcile_settings({**defaults, 'person_confidence': noisy}, seen, shown,
                                                      dict(defaults), defaults)
    assert updates == {} and changed == {} and taken_over == []


def test_an_unreadable_file_keeps_what_the_widgets_show(defaults):
    seen, shown = dict(defaults), dict(defaults)
    widgets = {**defaults, 'top': 400}
    updates, changed, taken_over = reconcile_settings(widgets, seen, shown, None, defaults)
    assert updates == {} and changed == {'top': 400} and taken_over == []
    # a new page without a readable file shows the defaults
    seen, shown = {}, {}
    updates, changed, taken_over = reconcile_settings({}, seen, shown, None, defaults)
    assert updates == defaults and changed == {} and taken_over == []
