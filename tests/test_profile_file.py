"""Reading and saving the app's profiles.json without losing data (framescout_core, A2)."""
import json
import os
from pathlib import Path

import pytest

from framescout_core import load_profiles, read_profiles, save_profiles


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
    assert sorted(p.name for p in tmp_path.iterdir()) == ['profiles.json']


def test_no_temporary_file_is_left_behind(tmp_path):
    path = tmp_path / 'profiles.json'
    save_profiles(path, [{'name': 'Dog'}])
    save_profiles(path, [{'name': 'Cat'}])
    assert sorted(p.name for p in tmp_path.iterdir()) == ['profiles.json', 'profiles.json.bak']


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
        save_profiles(path, [])
    assert path.read_bytes() == original
    assert sorted(p.name for p in tmp_path.iterdir()) == ['profiles.json']
