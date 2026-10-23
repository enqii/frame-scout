"""The result file of a search (results.json) and the app's result gallery helpers (A12, P4)."""
import json
from pathlib import Path

import pytest

from framescout_core import (RESULTS_FILE, RESULTS_FORMAT, load_profiles, open_command, openable_photo, page_count,
                             page_cards, profile_fingerprints, profile_state, read_results, result_card,
                             results_document, reveal_command, search_fingerprint, write_results)

THUMB = '1c6b57780fa2df6f925b878c.jpg'


def card(rank=1, **changes):
    return {**result_card(rank, Path(r'C:\photos\sub\a.jpg'), Path(r'C:\photos'), 'Full image', 3.125, 0.31, None,
                          'Score +3.12', 'text 0.310', THUMB), **changes}


def document(cards=None, **profile):
    entry = {'name': 'Red car', 'fingerprint': 'abc', 'gallery': 'red-car.html', 'normalized': True,
             'cards': [card()] if cards is None else cards, **profile}
    return results_document('2026-10-23T14:00:00+02:00', '2026-10-23T14:02:00+02:00', Path(r'C:\photos'),
                            {'top': 150}, 200, [entry])


def write_profiles(folder, profiles):
    path = folder / 'profiles.json'
    path.write_text(json.dumps({'profiles': profiles}), encoding='utf-8')
    return path


def test_a_card_holds_what_the_app_shows_and_opens():
    c = result_card(2, Path('/photos/sub/a.jpg'), Path('/photos'), 'Person 1', 1.5, 0.3, 0.8, 'Score +1.50',
                    'text 0.300 · image 0.800', THUMB)
    assert c == {'rank': 2, 'path': str(Path('/photos/sub/a.jpg')), 'relative': str(Path('sub/a.jpg')),
                 'label': 'Person 1',
                 'score': 1.5, 'text': 0.3, 'visual': 0.8, 'caption': 'Score +1.50',
                 'detail': 'text 0.300 · image 0.800', 'thumbnail': THUMB}


def test_the_document_names_the_run_and_its_profiles():
    data = document()
    assert data['format'] == RESULTS_FORMAT
    assert data['started'] == '2026-10-23T14:00:00+02:00' and data['finished'] == '2026-10-23T14:02:00+02:00'
    assert data['photo_folder'] == str(Path(r'C:\photos')) and data['settings'] == {'top': 150}
    assert data['photos'] == 200
    assert [p['name'] for p in data['profiles']] == ['Red car']


def test_results_round_trip(tmp_path):
    path = tmp_path / RESULTS_FILE
    write_results(path, document())
    assert read_results(path) == document()
    # written atomically: no temporary file is left
    assert [p.name for p in tmp_path.iterdir()] == [RESULTS_FILE]


def test_a_missing_result_file_is_none(tmp_path):
    assert read_results(tmp_path / RESULTS_FILE) is None


@pytest.mark.parametrize('content', [
    'not json',
    '[]',
    '{"format": 2, "profiles": []}',
    '{"format": 1}',
    '{"format": 1, "profiles": {}}',
])
def test_an_unreadable_result_file_raises(tmp_path, content):
    path = tmp_path / RESULTS_FILE
    path.write_text(content, encoding='utf-8')
    with pytest.raises(ValueError):
        read_results(path)


@pytest.mark.parametrize('profile', [
    {'name': ''},
    {'gallery': '../outside.html'},
    {'gallery': r'sub\red-car.html'},
    {'gallery': 'red-car.exe'},
    {'cards': {}},
    {'cards': [card(thumbnail='../x.jpg')]},
    {'cards': [card(thumbnail='x.png')]},
    {'cards': [card(rank='1')]},
    {'cards': [card(path=5)]},
    {'cards': [card(caption=None)]},
])
def test_names_that_could_leave_the_results_folder_are_rejected(tmp_path, profile):
    # the app joins the gallery and thumbnail names to the results folder and opens them
    path = tmp_path / RESULTS_FILE
    data = document(**profile)
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError):
        read_results(path)


def test_the_fingerprint_follows_the_search_texts_and_the_reference_images(tmp_path):
    (tmp_path / 'r.jpg').write_bytes(b'x')
    base = {'name': 'Red car', 'franchise': 'Vehicles', 'features': 'red paint', 'prompts': ['a red car'],
            'reference_images': ['r.jpg']}

    def fingerprint(**changes):
        [profile] = load_profiles(write_profiles(tmp_path, [{**base, **changes}]), [])
        return search_fingerprint(profile)

    same = fingerprint()
    assert fingerprint() == same
    assert fingerprint(name='Red car ') == same  # the stored name is stripped
    assert fingerprint(features='blue paint') != same
    assert fingerprint(franchise='') != same
    assert fingerprint(prompts=[]) != same
    assert fingerprint(reference_images=[]) != same


def test_profile_fingerprints_of_the_apps_profile_file(tmp_path):
    path = write_profiles(tmp_path, [{'name': 'Red car'}, {'name': 'Bicycle', 'features': 'two wheels'}])
    fingerprints = profile_fingerprints(path)
    assert list(fingerprints) == ['Red car', 'Bicycle']
    assert fingerprints == {p['name']: search_fingerprint(p) for p in load_profiles(path, [])}
    assert profile_fingerprints(write_profiles(tmp_path, [])) == {}
    assert profile_fingerprints(tmp_path / 'missing.json') == {}


def test_profile_state_compares_the_search_with_the_current_profile():
    entry = {'name': 'Red car', 'fingerprint': 'abc'}
    assert profile_state(entry, {'Red car': 'abc'}) == 'current'
    assert profile_state(entry, {'Red car': 'def'}) == 'changed'
    # renamed or deleted since the search
    assert profile_state(entry, {'red car': 'abc'}) == 'missing'


@pytest.mark.parametrize('cards,size,pages', [(0, 48, 1), (1, 48, 1), (48, 48, 1), (49, 48, 2), (150, 48, 4)])
def test_page_count(cards, size, pages):
    assert page_count(cards, size) == pages


def test_page_cards_returns_one_page_and_clamps_the_page_number():
    cards = list(range(100))
    assert page_cards(cards, 1, 48) == list(range(48))
    assert page_cards(cards, 3, 48) == [96, 97, 98, 99]
    # a page from a longer result list before a new search shows the last page
    assert page_cards(cards, 9, 48) == [96, 97, 98, 99]
    assert page_cards(cards, 0, 48) == list(range(48))
    assert page_cards([], 1, 48) == []


def test_open_and_reveal_commands_per_system():
    photo = Path('/photos/a b.jpg')
    assert open_command(photo, 'Darwin') == ['open', str(photo)]
    assert open_command(photo, 'Linux') == ['xdg-open', str(photo)]
    assert reveal_command(photo, 'Darwin') == ['open', '-R', str(photo)]
    # no file manager standard to select a file: its folder is opened
    assert reveal_command(photo, 'Linux') == ['xdg-open', str(photo.parent)]


def test_explorer_gets_the_select_switch_and_the_quoted_path_in_one_command_line():
    # Explorer parses its own command line: "/select," must be followed by the path in quotes
    # within the same argument, which a list of arguments would quote as a whole
    assert reveal_command(Path(r'C:\My photos\a.jpg'), 'Windows') == r'explorer /select,"C:\My photos\a.jpg"'


def test_only_existing_image_files_can_be_opened(tmp_path):
    photo = tmp_path / 'a.JPG'
    photo.write_bytes(b'x')
    (tmp_path / 'tool.exe').write_bytes(b'x')
    assert openable_photo(str(photo)) == photo
    assert openable_photo(str(tmp_path / 'tool.exe')) is None  # never start a program
    assert openable_photo(str(tmp_path / 'missing.jpg')) is None
    assert openable_photo(str(tmp_path)) is None
    assert openable_photo('a.JPG') is None  # relative: depends on the app's working directory
