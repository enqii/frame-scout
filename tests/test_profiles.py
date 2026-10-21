"""Profile loading, validation and prompt generation (framescout_core.load_profiles)."""
import json

import pytest

from framescout_core import load_profiles

GENERIC = ['A photograph of {t}.', 'An image showing {t}.', 'A detailed photo of {t}.',
           'A scene featuring {t}.']


def generic(target):
    return [template.format(t=target) for template in GENERIC]


def write_profiles(folder, data, encoding='utf-8'):
    path = folder / 'profiles.json'
    path.write_text(json.dumps(data, ensure_ascii=False), encoding=encoding)
    return path


def test_name_only_profile_gets_four_generic_prompts(tmp_path):
    path = write_profiles(tmp_path, {'profiles': [{'name': 'Golden Retriever'}]})
    [profile] = load_profiles(path, [])
    assert profile == {'name': 'Golden Retriever', 'prompts': generic('Golden Retriever'), 'refs': []}


def test_context_features_and_custom_prompts_are_combined_in_order(tmp_path):
    path = write_profiles(tmp_path, {'profiles': [{
        'name': 'Red car', 'franchise': 'Vehicles', 'features': ' red bodywork, four wheels ',
        'prompts': ['a red sports car'], 'reference_images': []}]})
    [profile] = load_profiles(path, [])
    assert profile['prompts'] == generic('Red car (Vehicles)') + [
        'A photograph of Red car (Vehicles), with red bodywork, four wheels.',
        'An image showing red bodywork, four wheels, depicting Red car (Vehicles).',
        'a red sports car']


def test_name_is_stripped(tmp_path):
    path = write_profiles(tmp_path, {'profiles': [{'name': '  Red car  ', 'franchise': '  '}]})
    [profile] = load_profiles(path, [])
    assert profile['name'] == 'Red car'
    assert profile['prompts'] == generic('Red car')


def test_reference_paths_are_resolved_relative_to_the_profile_file(tmp_path):
    folder = tmp_path / 'project'
    folder.mkdir()
    path = write_profiles(folder, {'profiles': [{'name': 'Dog', 'reference_images': ['references/dog/a.jpg']}]})
    [profile] = load_profiles(path, [])
    assert profile['refs'] == [(folder / 'references' / 'dog' / 'a.jpg').resolve()]


def test_utf8_bom_and_non_ascii_names_are_accepted(tmp_path):
    path = write_profiles(tmp_path, {'profiles': [{'name': 'Bär'}]}, encoding='utf-8-sig')
    assert path.read_bytes().startswith(b'\xef\xbb\xbf')
    assert [p['name'] for p in load_profiles(path, [])] == ['Bär']


def test_legacy_v3_mapping_of_names_to_prompts(tmp_path):
    path = write_profiles(tmp_path, {'Dog': ['a dog on a meadow'], 'Cat': []})
    profiles = load_profiles(path, [])
    assert [p['name'] for p in profiles] == ['Dog', 'Cat']
    assert profiles[0]['prompts'] == generic('Dog') + ['a dog on a meadow']
    assert profiles[1]['prompts'] == generic('Cat')


@pytest.mark.parametrize('data', [
    [{'name': 'Dog'}],                 # top-level list
    {'profiles': {'name': 'Dog'}},     # "profiles" is not a list
    {'profiles': ['Dog']},             # a profile is not an object
    {'profiles': []},                  # nothing to search for
])
def test_invalid_document_structure_is_rejected(tmp_path, data):
    with pytest.raises(ValueError):
        load_profiles(write_profiles(tmp_path, data), [])


def test_malformed_json_raises_a_value_error(tmp_path):
    path = tmp_path / 'profiles.json'
    path.write_text('{"profiles": [', encoding='utf-8')
    with pytest.raises(ValueError):  # json.JSONDecodeError is a ValueError
        load_profiles(path, [])


@pytest.mark.parametrize('profile', [{}, {'name': ''}, {'name': '   '}, {'name': 7}])
def test_missing_or_blank_name_is_rejected(tmp_path, profile):
    with pytest.raises(ValueError):
        load_profiles(write_profiles(tmp_path, {'profiles': [profile]}), [])


def test_duplicate_names_are_rejected_case_insensitively(tmp_path):
    path = write_profiles(tmp_path, {'profiles': [{'name': 'Red car'}, {'name': 'RED CAR'}]})
    with pytest.raises(ValueError):
        load_profiles(path, [])


@pytest.mark.parametrize('field, value', [
    ('franchise', 1), ('features', ['red']), ('prompts', 'a red car'),
    ('reference_images', 'a.jpg'), ('prompts', ['ok', '  ']), ('prompts', [3]),
    ('reference_images', ['']),
])
def test_wrong_field_types_or_blank_entries_are_rejected(tmp_path, field, value):
    path = write_profiles(tmp_path, {'profiles': [{'name': 'Red car', field: value}]})
    with pytest.raises(ValueError):
        load_profiles(path, [])


def test_inline_profiles_split_into_name_context_and_features():
    profiles = load_profiles(None, ['Dog', 'Red car | Vehicles', 'Lamp|Home|white shade|brass foot'])
    assert [p['name'] for p in profiles] == ['Dog', 'Red car', 'Lamp']
    assert profiles[0]['prompts'] == generic('Dog')
    assert profiles[1]['prompts'] == generic('Red car (Vehicles)')
    # only the first two "|" separate fields; the rest belongs to the features
    assert profiles[2]['prompts'][-1] == 'An image showing white shade|brass foot, depicting Lamp (Home).'
    assert all(p['refs'] == [] for p in profiles)


def test_inline_profiles_are_appended_after_file_profiles(tmp_path):
    path = write_profiles(tmp_path, {'profiles': [{'name': 'Dog'}]})
    assert [p['name'] for p in load_profiles(path, ['Cat'])] == ['Dog', 'Cat']


def test_inline_profile_must_not_duplicate_a_file_profile(tmp_path):
    path = write_profiles(tmp_path, {'profiles': [{'name': 'Dog'}]})
    with pytest.raises(ValueError):
        load_profiles(path, ['dog'])


def test_no_profiles_at_all_is_rejected():
    with pytest.raises(ValueError):
        load_profiles(None, [])
