"""The shipped example profiles and creating profiles.json from them (I5, I7)."""
from pathlib import Path

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


def test_without_an_example_nothing_is_created(tmp_path):
    target = tmp_path / 'profiles.json'
    assert create_from_example(target, tmp_path / 'missing.example.json') is False
    assert not target.exists()


def test_the_shipped_example_loads_and_is_general_purpose():
    profiles = load_profiles(EXAMPLE, [])
    assert [p['name'] for p in profiles] == [
        'Red car', 'Golden retriever', 'Mountain landscape', 'Bicycle', 'Birthday cake',
        'Person with umbrella']
    assert all(p['refs'] == [] for p in profiles)
    text = EXAMPLE.read_text(encoding='utf-8').lower()
    for word in ('joker', 'harley', 'batman', 'nier', 'cosplay'):
        assert word not in text
