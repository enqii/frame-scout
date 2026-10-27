"""Reading and saving the app's profiles.json without losing data (framescout_core, A2)."""
import json
import os
from pathlib import Path

import pytest

from framescout_core import (NEVER_DELETED, ProfilesChangedError, RunLock, load_profiles, read_profiles, read_profiles_versioned,
                             save_profiles)


def write(path, data, encoding='utf-8'):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding=encoding)
    return path


def test_a_missing_file_has_no_profiles(tmp_path):
    assert read_profiles(tmp_path / 'profiles.json') == []


def test_the_current_format_is_read_unchanged_including_unknown_keys(tmp_path):
    profiles = [{'name': 'Red car', 'franchise': 'Vehicles', 'features': 'red',
                 'prompts': ['a red car'], 'reference_images': ['references/red-car/reference-1.jpg'],
                 'note': 'kept'},
                {'name': 'Bär'}]
    path = write(tmp_path / 'profiles.json', {'profiles': profiles}, encoding='utf-8-sig')
    assert read_profiles(path) == profiles


def test_an_empty_profile_list_is_allowed(tmp_path):
    # the app must open with no profiles (the engine rejects an empty list instead)
    assert read_profiles(write(tmp_path / 'profiles.json', {'profiles': []})) == []


def test_the_v3_format_is_converted_instead_of_read_as_empty(tmp_path):
    # A2: the app used to read {name: [prompts]} as [] and the next save wiped the file
    path = write(tmp_path / 'profiles.json', {'Dog': ['a dog on a meadow'], 'Cat': []})
    assert read_profiles(path) == [{'name': 'Dog', 'prompts': ['a dog on a meadow']},
                                   {'name': 'Cat', 'prompts': []}]


@pytest.mark.parametrize('data', [
    [{'name': 'Dog'}],                          # top-level list (was an AttributeError)
    'Dog',                                      # a plain string
    {'profiles': {'name': 'Dog'}},              # "profiles" is not a list
    {'profiles': ['Dog']},                      # a profile is not an object
    {'profiles': [{'franchise': 'Pets'}]},      # no name
    {'profiles': [{'name': 'Dog'}, {'name': ' dog '}]},  # duplicate name
    {'profiles': [{'name': 'Dog', 'prompts': 'a dog'}]},  # wrong field type
    {'Dog': 'a dog'},                           # v3 with a string instead of a prompt list
])
def test_documents_the_app_cannot_represent_are_rejected(tmp_path, data):
    with pytest.raises(ValueError):
        read_profiles(write(tmp_path / 'profiles.json', data))


def test_malformed_json_raises_a_value_error(tmp_path):
    path = tmp_path / 'profiles.json'
    path.write_text('{"profiles": [', encoding='utf-8')
    with pytest.raises(ValueError):
        read_profiles(path)


def test_saved_profiles_are_read_back_and_loadable_by_the_engine(tmp_path):
    path = tmp_path / 'profiles.json'
    profiles = [{'name': 'Bär', 'franchise': '', 'features': 'brown fur', 'prompts': [],
                 'reference_images': []}]
    save_profiles(path, profiles)
    assert json.loads(path.read_text(encoding='utf-8')) == {'profiles': profiles}
    assert 'Bär' in path.read_text(encoding='utf-8')  # readable, not \u-escaped
    assert read_profiles(path) == profiles
    assert [p['name'] for p in load_profiles(path, [])] == ['Bär']


def test_other_top_level_keys_of_the_file_are_kept(tmp_path):
    # review: {"version": 2, "profiles": [...]} lost "version" on the first save
    path = write(tmp_path / 'profiles.json', {'version': 2, 'profiles': [{'name': 'Dog'}], 'note': 'mine'})
    save_profiles(path, [{'name': 'Cat'}])
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data == {'version': 2, 'profiles': [{'name': 'Cat'}], 'note': 'mine'}
    assert list(data) == ['version', 'profiles', 'note']


def test_the_v3_format_is_saved_without_its_old_keys(tmp_path):
    # in v3 the top-level keys are profile names; they must not survive next to "profiles"
    path = write(tmp_path / 'profiles.json', {'Dog': ['a dog on a meadow']})
    save_profiles(path, read_profiles(path))
    assert json.loads(path.read_text(encoding='utf-8')) == {
        'profiles': [{'name': 'Dog', 'prompts': ['a dog on a meadow']}]}


def test_the_previous_file_is_kept_as_backup(tmp_path):
    path = tmp_path / 'profiles.json'
    path.write_bytes(b'{"Dog": ["a dog on a meadow"]}\r\n')  # e.g. the v3 original
    save_profiles(path, [{'name': 'Dog', 'prompts': ['a dog on a meadow']}])
    assert (tmp_path / 'profiles.json.bak').read_bytes() == b'{"Dog": ["a dog on a meadow"]}\r\n'
    save_profiles(path, [])
    assert json.loads((tmp_path / 'profiles.json.bak').read_text(encoding='utf-8')) == {
        'profiles': [{'name': 'Dog', 'prompts': ['a dog on a meadow']}]}
    assert json.loads(path.read_text(encoding='utf-8')) == {'profiles': []}


def test_without_a_previous_file_no_backup_is_written(tmp_path):
    save_profiles(tmp_path / 'profiles.json', [{'name': 'Dog'}])
    # the lock file of the save stays (empty), like settings.json.lock (A13)
    assert sorted(p.name for p in tmp_path.iterdir()) == ['profiles.json', 'profiles.json.lock']


def test_no_temporary_file_is_left_behind(tmp_path):
    path = tmp_path / 'profiles.json'
    save_profiles(path, [{'name': 'Dog'}])
    save_profiles(path, [{'name': 'Cat'}])
    assert sorted(p.name for p in tmp_path.iterdir()) == ['profiles.json', 'profiles.json.bak', 'profiles.json.lock']


def test_both_files_are_flushed_to_disk_before_they_get_their_final_names(tmp_path, monkeypatch):
    # review: without fsync, a power loss can persist the rename before the data and
    # leave an empty profiles.json and profiles.json.bak
    path = write(tmp_path / 'profiles.json', {'profiles': [{'name': 'Dog'}]})
    events = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd):
        events.append('fsync')
        real_fsync(fd)

    def replace(src, dst):
        events.append(('replace', Path(dst).name))
        real_replace(src, dst)

    monkeypatch.setattr(os, 'fsync', fsync)
    monkeypatch.setattr(os, 'replace', replace)
    save_profiles(path, [{'name': 'Cat'}])
    assert events == ['fsync', ('replace', 'profiles.json.bak'), 'fsync', ('replace', 'profiles.json')]


def test_if_the_backup_fails_the_profiles_file_is_not_changed(tmp_path, monkeypatch):
    path = write(tmp_path / 'profiles.json', {'profiles': [{'name': 'Dog'}]})
    original = path.read_bytes()
    real_replace = os.replace

    def replace(src, dst):
        if str(dst).endswith('.bak'):
            raise PermissionError('backup not writable')
        real_replace(src, dst)

    monkeypatch.setattr(os, 'replace', replace)
    with pytest.raises(PermissionError):
        save_profiles(path, [], retry_delay=0)
    assert path.read_bytes() == original
    assert sorted(p.name for p in tmp_path.iterdir()) == ['profiles.json', 'profiles.json.lock']


# A13: a save is based on the profiles a page showed; it must not overwrite a change that
# another tab, session or a text editor made to profiles.json in between

def test_the_version_tells_whether_the_file_changed(tmp_path):
    path = write(tmp_path / 'profiles.json', {'profiles': [{'name': 'Dog'}]})
    profiles, version = read_profiles_versioned(path)
    assert profiles == [{'name': 'Dog'}] and version
    assert read_profiles_versioned(path)[1] == version  # unchanged file: same version
    path.write_bytes(path.read_bytes() + b' ')  # any change counts, even one without effect
    assert read_profiles_versioned(path)[1] != version


def test_a_missing_file_has_no_version(tmp_path):
    assert read_profiles_versioned(tmp_path / 'profiles.json') == ([], None)


def test_the_versioned_read_validates_like_read_profiles(tmp_path):
    with pytest.raises(ValueError):
        read_profiles_versioned(write(tmp_path / 'profiles.json', {'profiles': [{'name': 'Dog'}, {'name': 'dog'}]}))
    path = write(tmp_path / 'profiles.json', {'Dog': ['a dog on a meadow']})  # v3 is converted
    assert read_profiles_versioned(path)[0] == read_profiles(path)


def test_a_save_based_on_the_current_file_is_written(tmp_path):
    path = write(tmp_path / 'profiles.json', {'profiles': [{'name': 'Dog'}]})
    _, version = read_profiles_versioned(path)
    save_profiles(path, [{'name': 'Cat'}], expected=version)
    assert read_profiles(path) == [{'name': 'Cat'}]


def test_a_save_based_on_an_older_file_changes_nothing(tmp_path):
    path = write(tmp_path / 'profiles.json', {'profiles': [{'name': 'Dog'}]})
    (tmp_path / 'profiles.json.bak').write_bytes(b'older backup')
    _, shown = read_profiles_versioned(path)
    write(path, {'profiles': [{'name': 'Dog', 'features': 'edited by hand'}]})
    current = path.read_bytes()
    with pytest.raises(ProfilesChangedError) as error:
        save_profiles(path, [{'name': 'Cat'}], expected=shown)
    assert isinstance(error.value, ValueError)  # handled like any other refused save
    assert 'profiles.json' in str(error.value)
    assert path.read_bytes() == current
    assert (tmp_path / 'profiles.json.bak').read_bytes() == b'older backup'


def test_the_second_of_two_sessions_saving_the_same_version_is_refused(tmp_path):
    path = write(tmp_path / 'profiles.json', {'profiles': [{'name': 'Dog'}, {'name': 'Cat'}]})
    profiles, version = read_profiles_versioned(path)
    # session A deletes "Dog", session B, still showing the old list, edits "Cat" (index 1)
    save_profiles(path, profiles[1:], expected=version)
    with pytest.raises(ProfilesChangedError):
        save_profiles(path, [profiles[0], {'name': 'Cat', 'features': 'grey'}], expected=version)
    assert read_profiles(path) == [{'name': 'Cat'}]


def test_a_file_created_since_the_page_showed_none_is_not_overwritten(tmp_path):
    path = tmp_path / 'profiles.json'
    _, shown = read_profiles_versioned(path)
    write(path, {'profiles': [{'name': 'Dog'}]})
    with pytest.raises(ProfilesChangedError):
        save_profiles(path, [{'name': 'Cat'}], expected=shown)
    assert read_profiles(path) == [{'name': 'Dog'}]


def test_a_file_missing_when_shown_and_now_is_written(tmp_path):
    path = tmp_path / 'profiles.json'
    _, shown = read_profiles_versioned(path)
    save_profiles(path, [{'name': 'Cat'}], expected=shown)
    assert read_profiles(path) == [{'name': 'Cat'}]


def test_a_file_deleted_since_the_page_showed_it_is_not_created_again(tmp_path):
    path = write(tmp_path / 'profiles.json', {'profiles': [{'name': 'Dog'}]})
    _, shown = read_profiles_versioned(path)
    path.unlink()
    with pytest.raises(ProfilesChangedError):
        save_profiles(path, [{'name': 'Cat'}], expected=shown)
    assert not path.exists()


def test_a_save_waits_for_another_save_and_then_checks_the_version(tmp_path):
    # the check and the write happen under profiles.json.lock: no other save can write
    # between them (app sessions are threads of one process; RunLocks conflict there too)
    path = write(tmp_path / 'profiles.json', {'profiles': [{'name': 'Dog'}]})
    _, version = read_profiles_versioned(path)
    other = RunLock(tmp_path / 'profiles.json.lock')
    assert other.acquire()
    try:
        with pytest.raises(OSError):
            save_profiles(path, [{'name': 'Cat'}], expected=version, lock_timeout=0)
    finally:
        other.release()
    assert read_profiles(path) == [{'name': 'Dog'}]
    save_profiles(path, [{'name': 'Cat'}], expected=version, lock_timeout=0)
    assert read_profiles(path) == [{'name': 'Cat'}]


def test_the_version_is_checked_when_the_lock_is_held(tmp_path, monkeypatch):
    # a change made while this save waits for the lock is noticed, not overwritten
    path = write(tmp_path / 'profiles.json', {'profiles': [{'name': 'Dog'}]})
    _, version = read_profiles_versioned(path)
    real_acquire = RunLock.acquire

    def acquire(self, *args, **kwargs):
        write(path, {'profiles': [{'name': 'Dog'}, {'name': 'Bird'}]})  # saved by another session meanwhile
        return real_acquire(self, *args, **kwargs)

    monkeypatch.setattr(RunLock, 'acquire', acquire)
    with pytest.raises(ProfilesChangedError):
        save_profiles(path, [{'name': 'Cat'}], expected=version)
    assert read_profiles(path) == [{'name': 'Dog'}, {'name': 'Bird'}]


def test_the_cleanup_never_deletes_the_lock_file():
    assert 'profiles.json.lock' in NEVER_DELETED


def test_a_replace_that_fails_for_a_moment_is_retried(tmp_path, monkeypatch):
    # on Windows, replacing fails while another session reads the file at that moment (review)
    path = write(tmp_path / 'profiles.json', {'profiles': [{'name': 'Dog'}]})
    original = path.read_bytes()
    real_replace = os.replace
    calls = []

    def flaky(src, dst):
        calls.append(Path(dst).name)
        if calls.count(Path(dst).name) == 1:
            raise PermissionError('in use')
        real_replace(src, dst)

    monkeypatch.setattr(os, 'replace', flaky)
    save_profiles(path, [{'name': 'Cat'}], retry_delay=0)
    assert calls == ['profiles.json.bak', 'profiles.json.bak', 'profiles.json', 'profiles.json']
    assert read_profiles(path) == [{'name': 'Cat'}]
    assert (tmp_path / 'profiles.json.bak').read_bytes() == original


def test_a_replace_that_keeps_failing_raises_os_error(tmp_path, monkeypatch):
    path = write(tmp_path / 'profiles.json', {'profiles': [{'name': 'Dog'}]})
    original = path.read_bytes()
    real_replace = os.replace

    def failing(src, dst):
        if Path(dst).name == 'profiles.json':
            raise PermissionError('in use')
        real_replace(src, dst)

    monkeypatch.setattr(os, 'replace', failing)
    with pytest.raises(OSError):
        save_profiles(path, [{'name': 'Cat'}], attempts=3, retry_delay=0)
    assert path.read_bytes() == original


def test_a_transient_read_error_is_retried(tmp_path, monkeypatch):
    # on Windows, reading fails for a moment while another session replaces the file (review)
    path = write(tmp_path / 'profiles.json', {'profiles': [{'name': 'Dog'}]})
    expected = read_profiles_versioned(path)
    real_read = Path.read_bytes
    calls = []

    def flaky(self):
        calls.append(self)
        if len(calls) == 1:
            raise PermissionError('being replaced')
        return real_read(self)

    monkeypatch.setattr(Path, 'read_bytes', flaky)
    assert read_profiles_versioned(path, retry_delay=0) == expected
    assert len(calls) == 2


def test_a_read_error_that_persists_raises_os_error(tmp_path, monkeypatch):
    path = write(tmp_path / 'profiles.json', {'profiles': [{'name': 'Dog'}]})

    def failing(self):
        raise PermissionError('in use')

    monkeypatch.setattr(Path, 'read_bytes', failing)
    with pytest.raises(OSError):
        read_profiles_versioned(path, attempts=3, retry_delay=0)


def test_a_save_returns_the_version_of_the_file_it_wrote(tmp_path):
    # the app's next save is based on its own saved file, not on the one before it (review)
    path = write(tmp_path / 'profiles.json', {'profiles': [{'name': 'Dog'}]})
    _, shown = read_profiles_versioned(path)
    version = save_profiles(path, [{'name': 'Cat'}], expected=shown)
    assert version == read_profiles_versioned(path)[1] != shown
    save_profiles(path, [{'name': 'Bird'}], expected=version)
    assert read_profiles(path) == [{'name': 'Bird'}]


def test_without_an_expected_version_the_save_is_not_checked(tmp_path):
    # e.g. a script or test that writes the file directly (the app always passes one)
    path = write(tmp_path / 'profiles.json', {'profiles': [{'name': 'Dog'}]})
    save_profiles(path, [{'name': 'Cat'}])
    assert read_profiles(path) == [{'name': 'Cat'}]
