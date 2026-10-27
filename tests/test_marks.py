"""Marks of gallery photos in results/marks.json (framescout_core, A17)."""
import json
import threading

import pytest

from framescout_core import (MARK_MATCH, MARK_NO_MATCH, MARK_OPEN, MARK_STATES, MARKS_FILE, RunLock, delete_marks,
                             read_marks, rename_marks, save_marks)


def stored(path):
    return json.loads(path.read_text(encoding='utf-8'))


def test_three_states_and_the_file_name():
    assert MARKS_FILE == 'marks.json'
    assert MARK_STATES == (MARK_OPEN, MARK_MATCH, MARK_NO_MATCH) == ('open', 'match', 'no-match')


def test_a_missing_file_has_no_marks(tmp_path):
    assert read_marks(tmp_path / MARKS_FILE) == {}


def test_marks_are_saved_per_profile_and_read_back(tmp_path):
    path = tmp_path / 'results' / MARKS_FILE  # the folder is created if needed
    assert save_marks(path, 'Red car', {'C:/p/a.jpg': MARK_MATCH, 'C:/p/b.jpg': MARK_NO_MATCH}) == {
        'C:/p/a.jpg': MARK_MATCH, 'C:/p/b.jpg': MARK_NO_MATCH}
    save_marks(path, 'Dog', {'C:/p/a.jpg': MARK_NO_MATCH})
    assert read_marks(path) == {'Red car': {'C:/p/a.jpg': MARK_MATCH, 'C:/p/b.jpg': MARK_NO_MATCH},
                                'Dog': {'C:/p/a.jpg': MARK_NO_MATCH}}
    assert stored(path)['format'] == 1


def test_open_removes_a_mark_and_an_empty_profile(tmp_path):
    path = tmp_path / MARKS_FILE
    save_marks(path, 'Red car', {'a.jpg': MARK_MATCH, 'b.jpg': MARK_MATCH})
    assert save_marks(path, 'Red car', {'a.jpg': MARK_OPEN}) == {'b.jpg': MARK_MATCH}
    save_marks(path, 'Red car', {'b.jpg': MARK_OPEN})
    assert read_marks(path) == {}
    assert stored(path)['profiles'] == {}


def test_opening_an_unmarked_photo_creates_no_file(tmp_path):
    path = tmp_path / MARKS_FILE
    assert save_marks(path, 'Red car', {'a.jpg': MARK_OPEN}) == {}
    assert not path.exists()


def test_a_change_is_merged_into_the_current_file(tmp_path):
    # another session saved a mark in between: it is kept
    path = tmp_path / MARKS_FILE
    save_marks(path, 'Red car', {'a.jpg': MARK_MATCH})
    save_marks(path, 'Red car', {'b.jpg': MARK_MATCH})
    assert read_marks(path) == {'Red car': {'a.jpg': MARK_MATCH, 'b.jpg': MARK_MATCH}}


def test_unknown_keys_of_the_file_are_kept(tmp_path):
    path = tmp_path / MARKS_FILE
    path.write_text(json.dumps({'format': 1, 'profiles': {}, 'later': [1]}), encoding='utf-8')
    save_marks(path, 'Red car', {'a.jpg': MARK_MATCH})
    assert stored(path)['later'] == [1]


@pytest.mark.parametrize('content', ['not json', '[]', '{"format": 2, "profiles": {}}', '{"format": 1}',
                                     '{"format": 1, "profiles": {"Red car": {"a.jpg": "maybe"}}}',
                                     '{"format": 1, "profiles": {"Red car": ["a.jpg"]}}'])
def test_an_unreadable_file_raises_and_is_never_replaced(tmp_path, content):
    path = tmp_path / MARKS_FILE
    path.write_text(content, encoding='utf-8')
    with pytest.raises(ValueError):
        read_marks(path)
    with pytest.raises(ValueError):
        save_marks(path, 'Red car', {'a.jpg': MARK_MATCH})
    with pytest.raises(ValueError):
        rename_marks(path, 'Red car', 'Blue car')
    with pytest.raises(ValueError):
        delete_marks(path, 'Red car')
    assert path.read_text(encoding='utf-8') == content


@pytest.mark.parametrize('state', ['maybe', None, 1])
def test_an_unknown_state_is_refused(tmp_path, state):
    with pytest.raises(ValueError):
        save_marks(tmp_path / MARKS_FILE, 'Red car', {'a.jpg': state})
    assert not (tmp_path / MARKS_FILE).exists()


def test_saving_waits_for_the_lock_and_gives_up(tmp_path):
    path = tmp_path / MARKS_FILE
    lock = RunLock(tmp_path / (MARKS_FILE + '.lock'))
    assert lock.acquire()
    try:
        with pytest.raises(OSError):
            save_marks(path, 'Red car', {'a.jpg': MARK_MATCH}, lock_timeout=0.05)
    finally:
        lock.release()
    assert not path.exists()


def test_parallel_saves_lose_no_mark(tmp_path):
    path = tmp_path / MARKS_FILE
    errors = []

    def mark(n):
        try:
            save_marks(path, 'Red car', {f'{n}.jpg': MARK_MATCH}, attempts=40)
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=mark, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert read_marks(path) == {'Red car': {f'{n}.jpg': MARK_MATCH for n in range(8)}}


def test_a_renamed_profile_keeps_its_marks(tmp_path):
    path = tmp_path / MARKS_FILE
    save_marks(path, 'Red car', {'a.jpg': MARK_MATCH, 'b.jpg': MARK_NO_MATCH})
    save_marks(path, 'Dog', {'c.jpg': MARK_MATCH})
    assert rename_marks(path, 'Red car', 'Blue car') is True
    assert read_marks(path) == {'Blue car': {'a.jpg': MARK_MATCH, 'b.jpg': MARK_NO_MATCH},
                                'Dog': {'c.jpg': MARK_MATCH}}


def test_renaming_merges_into_old_marks_of_the_new_name(tmp_path):
    # marks of a deleted profile of that name are kept; the renamed profile's marks win
    path = tmp_path / MARKS_FILE
    save_marks(path, 'Old', {'a.jpg': MARK_MATCH})
    save_marks(path, 'New', {'a.jpg': MARK_NO_MATCH, 'b.jpg': MARK_MATCH})
    rename_marks(path, 'Old', 'New')
    assert read_marks(path) == {'New': {'a.jpg': MARK_MATCH, 'b.jpg': MARK_MATCH}}


def test_renaming_a_profile_without_marks_changes_nothing(tmp_path):
    path = tmp_path / MARKS_FILE
    assert rename_marks(path, 'Red car', 'Blue car') is False
    assert not path.exists()
    save_marks(path, 'Dog', {'c.jpg': MARK_MATCH})
    before = path.read_bytes()
    assert rename_marks(path, 'Red car', 'Blue car') is False
    assert path.read_bytes() == before


# --- deleting a profile (A22) ------------------------------------------------------------

def test_deleting_a_profile_deletes_only_its_marks(tmp_path):
    path = tmp_path / MARKS_FILE
    save_marks(path, 'Red car', {'a.jpg': MARK_MATCH, 'b.jpg': MARK_NO_MATCH})
    save_marks(path, 'Dog', {'a.jpg': MARK_MATCH})
    assert delete_marks(path, 'Red car') == 2
    assert read_marks(path) == {'Dog': {'a.jpg': MARK_MATCH}}


def test_a_new_profile_of_a_deleted_name_starts_without_marks(tmp_path):
    # the bug of A22: marks are keyed by the name, so they must go with the deleted profile
    path = tmp_path / MARKS_FILE
    save_marks(path, 'Red car', {'a.jpg': MARK_MATCH})
    delete_marks(path, 'Red car')
    assert read_marks(path).get('Red car', {}) == {}
    save_marks(path, 'Old', {'b.jpg': MARK_MATCH})
    save_marks(path, 'New', {'c.jpg': MARK_MATCH})
    delete_marks(path, 'New')
    rename_marks(path, 'Old', 'New')  # a rename to the deleted name merges nothing old
    assert read_marks(path) == {'New': {'b.jpg': MARK_MATCH}}


def test_deleting_a_profile_without_marks_changes_nothing(tmp_path):
    path = tmp_path / 'results' / MARKS_FILE
    assert delete_marks(path, 'Red car') == 0  # no results folder: nothing is created
    assert not path.parent.exists()
    path.parent.mkdir()
    assert delete_marks(path, 'Red car') == 0
    assert not path.exists()
    save_marks(path, 'Dog', {'c.jpg': MARK_MATCH})
    before = path.read_bytes()
    assert delete_marks(path, 'Red car') == 0
    assert path.read_bytes() == before


def test_deleting_keeps_unknown_keys_and_changes_of_other_sessions(tmp_path):
    path = tmp_path / MARKS_FILE
    path.write_text(json.dumps({'format': 1, 'later': [1], 'profiles': {
        'Red car': {'a.jpg': MARK_MATCH}, 'Dog': {'b.jpg': MARK_NO_MATCH}}}), encoding='utf-8')
    assert delete_marks(path, 'Red car') == 1
    assert stored(path) == {'format': 1, 'later': [1], 'profiles': {'Dog': {'b.jpg': MARK_NO_MATCH}}}


def test_deleting_waits_for_the_lock_and_gives_up(tmp_path):
    path = tmp_path / MARKS_FILE
    save_marks(path, 'Red car', {'a.jpg': MARK_MATCH})
    lock = RunLock(tmp_path / (MARKS_FILE + '.lock'))
    assert lock.acquire()
    try:
        with pytest.raises(OSError):
            delete_marks(path, 'Red car', lock_timeout=0.05)
    finally:
        lock.release()
    assert read_marks(path) == {'Red car': {'a.jpg': MARK_MATCH}}
