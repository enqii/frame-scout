"""The shipped example profiles and creating profiles.json from them (I5, I7)."""
from pathlib import Path

import pytest

import framescout_core
from framescout_core import create_from_example, load_profiles

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = REPO / 'profiles.example.json'


def test_missing_profiles_file_is_created_from_the_example(tmp_path):
    example = tmp_path / 'profiles.example.json'
    example.write_bytes(b'{"profiles": [{"name": "Red car"}]}\r\n')
    target = tmp_path / 'profiles.json'
    assert create_from_example(target, example) is True
    assert target.read_bytes() == example.read_bytes()


def test_an_existing_profiles_file_is_never_overwritten(tmp_path):
    example = tmp_path / 'profiles.example.json'
    example.write_text('{"profiles": [{"name": "Red car"}]}', encoding='utf-8')
    target = tmp_path / 'profiles.json'
    target.write_text('{"profiles": [{"name": "My own profile"}]}', encoding='utf-8')
    assert create_from_example(target, example) is False
    assert target.read_text(encoding='utf-8') == '{"profiles": [{"name": "My own profile"}]}'


def test_an_empty_existing_profiles_file_is_not_replaced_either(tmp_path):
    example = tmp_path / 'profiles.example.json'
    example.write_text('{"profiles": [{"name": "Red car"}]}', encoding='utf-8')
    target = tmp_path / 'profiles.json'
    target.write_bytes(b'')
    assert create_from_example(target, example) is False
    assert target.read_bytes() == b''


def test_the_example_is_not_read_when_the_profiles_file_exists(tmp_path):
    # the app calls this on every Streamlit rerun (review); an unreadable "example"
    # (here a folder) must not even be opened once profiles.json exists
    target = tmp_path / 'profiles.json'
    target.write_text('{"profiles": []}', encoding='utf-8')
    assert create_from_example(target, tmp_path) is False


def test_without_an_example_nothing_is_created(tmp_path):
    target = tmp_path / 'profiles.json'
    assert create_from_example(target, tmp_path / 'missing.example.json') is False
    assert not target.exists()


def test_no_temporary_file_is_left_behind(tmp_path):
    example = tmp_path / 'profiles.example.json'
    example.write_text('{"profiles": []}', encoding='utf-8')
    assert create_from_example(tmp_path / 'profiles.json', example) is True
    assert sorted(p.name for p in tmp_path.iterdir()) == ['profiles.example.json', 'profiles.json']


def test_the_target_never_exists_half_written(tmp_path, monkeypatch):
    # the copy is complete before it appears under the final name (review: a crash or a
    # parallel session must never see an empty profiles.json)
    example = tmp_path / 'profiles.example.json'
    example.write_bytes(b'{"profiles": [{"name": "Red car"}]}')
    target = tmp_path / 'profiles.json'
    seen = []
    real_publish = framescout_core._publish_new

    def publish(tmp, final):
        seen.append((final.exists(), tmp.read_bytes()))
        real_publish(tmp, final)

    monkeypatch.setattr(framescout_core, '_publish_new', publish)
    assert create_from_example(target, example) is True
    assert seen == [(False, example.read_bytes())]


def test_a_file_created_concurrently_wins_and_is_not_replaced(tmp_path, monkeypatch):
    example = tmp_path / 'profiles.example.json'
    example.write_text('{"profiles": [{"name": "Red car"}]}', encoding='utf-8')
    target = tmp_path / 'profiles.json'
    real_publish = framescout_core._publish_new

    def publish(tmp, final):
        final.write_text('{"profiles": [{"name": "Other session"}]}', encoding='utf-8')
        real_publish(tmp, final)

    monkeypatch.setattr(framescout_core, '_publish_new', publish)
    assert create_from_example(target, example) is False
    assert target.read_text(encoding='utf-8') == '{"profiles": [{"name": "Other session"}]}'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['profiles.example.json', 'profiles.json']


def test_a_failed_copy_leaves_neither_target_nor_temporary_file(tmp_path, monkeypatch):
    example = tmp_path / 'profiles.example.json'
    example.write_text('{"profiles": []}', encoding='utf-8')

    def publish(tmp, final):
        raise PermissionError('read-only folder')

    monkeypatch.setattr(framescout_core, '_publish_new', publish)
    with pytest.raises(PermissionError):
        create_from_example(tmp_path / 'profiles.json', example)
    assert [p.name for p in tmp_path.iterdir()] == ['profiles.example.json']


def test_the_shipped_example_loads_and_is_general_purpose():
    profiles = load_profiles(EXAMPLE, [])
    assert [p['name'] for p in profiles] == [
        'Red car', 'Golden retriever', 'Mountain landscape', 'Bicycle', 'Birthday cake',
        'Person with umbrella']
    assert all(p['refs'] == [] for p in profiles)
    text = EXAMPLE.read_text(encoding='utf-8').lower()
    for word in ('joker', 'harley', 'batman', 'nier', 'cosplay'):
        assert word not in text
