"""Marks of gallery photos in results/marks.json (framescout_core, A17)."""
import json
import os
import re
import threading
import time
from pathlib import Path

import pytest

from framescout_core import (CONSTRAINTS_FILE, MARK_COLORS, MARK_MATCH, MARK_NO_MATCH, MARK_OPEN, MARK_STATES, MARK_STYLE_STREAMLIT,
                             MARKS_BACKUP, MARKS_FILE, NEVER_DELETED, RunLock, UnknownProfileError, delete_marks,
                             hidden_text, hide_no_match, lock_held, mark_style, marks_backup, marks_restore_offer, page_cards,
                             progress_text, read_marks, ReviewProgress, review_progress,
                             remove_marks, rename_marks, restore_marks, save_marks)


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


# --- removing single marks (unbound photos, E8/A21) ---------------------------------------

def test_removing_marks_removes_only_the_named_entries(tmp_path):
    path = tmp_path / MARKS_FILE
    path.write_text(json.dumps({'format': 1, 'later': [1], 'profiles': {
        'Red car': {'a.jpg': MARK_MATCH, 'b.jpg': MARK_NO_MATCH}, 'Dog': {'a.jpg': MARK_MATCH}}}), encoding='utf-8')
    # ('Cat', 'x.jpg') and ('Dog', 'b.jpg') have no mark: nothing happens for them
    assert remove_marks(path, {('Red car', 'a.jpg'), ('Cat', 'x.jpg'), ('Dog', 'b.jpg')}) == 1
    assert stored(path) == {'format': 1, 'later': [1], 'profiles': {
        'Red car': {'b.jpg': MARK_NO_MATCH}, 'Dog': {'a.jpg': MARK_MATCH}}}
    # a profile left without marks is removed from the file, as by save_marks
    assert remove_marks(path, [('Red car', 'b.jpg')]) == 1
    assert read_marks(path) == {'Dog': {'a.jpg': MARK_MATCH}}


def test_removing_marks_of_deleted_profiles_keeps_those_of_a_current_profile(tmp_path):
    # the cleanup of marks of names that are no profile (A34): checked under the lock
    path, profiles = tmp_path / MARKS_FILE, tmp_path / 'profiles.json'
    save_marks(path, 'Dog', {'a.jpg': MARK_MATCH})
    save_marks(path, 'Cat', {'a.jpg': MARK_MATCH})
    profiles.write_text(json.dumps({'profiles': [{'name': 'Cat', 'reference_images': []}]}), encoding='utf-8')
    assert remove_marks(path, {('Dog', 'a.jpg'), ('Cat', 'a.jpg')}, unless_profile_of=profiles) == 1
    assert read_marks(path) == {'Cat': {'a.jpg': MARK_MATCH}}
    profiles.write_text('{broken', encoding='utf-8')
    with pytest.raises(ValueError, match='profiles.json'):
        remove_marks(path, {('Cat', 'a.jpg')}, unless_profile_of=profiles)
    profiles.unlink()  # a missing file is no proof that no profile has the name
    with pytest.raises(ValueError, match='profiles.json does not exist'):
        remove_marks(path, {('Cat', 'a.jpg')}, unless_profile_of=profiles)
    assert read_marks(path) == {'Cat': {'a.jpg': MARK_MATCH}}


def test_removing_no_mark_changes_nothing(tmp_path):
    path = tmp_path / 'results' / MARKS_FILE
    assert remove_marks(path, {('Red car', 'a.jpg')}) == 0  # no results folder: nothing is created
    assert not path.parent.exists()
    path.parent.mkdir()
    assert remove_marks(path, {('Red car', 'a.jpg')}) == 0 and not path.exists()
    save_marks(path, 'Dog', {'c.jpg': MARK_MATCH})
    before = path.read_bytes()
    assert remove_marks(path, {('Red car', 'a.jpg')}) == 0 and remove_marks(path, set()) == 0
    assert path.read_bytes() == before


def test_removing_marks_never_replaces_an_unreadable_file_and_waits_for_the_lock(tmp_path):
    path = tmp_path / MARKS_FILE
    path.write_text('{broken', encoding='utf-8')
    with pytest.raises(ValueError):
        remove_marks(path, {('Red car', 'a.jpg')})
    assert path.read_text(encoding='utf-8') == '{broken'
    save_marks(path.with_name('other.json'), 'Red car', {'a.jpg': MARK_MATCH})
    path = path.with_name('other.json')
    lock = RunLock(tmp_path / 'other.json.lock')
    assert lock.acquire()
    try:
        with pytest.raises(OSError):
            remove_marks(path, {('Red car', 'a.jpg')}, lock_timeout=0.05)
    finally:
        lock.release()
    assert read_marks(path) == {'Red car': {'a.jpg': MARK_MATCH}}


# --- review of A22: no marks for a name that is no profile any more ------------------------

def profiles_file(path, *names):
    path.write_text(json.dumps({'profiles': [{'name': n} for n in names]}), encoding='utf-8')
    return path


def test_marks_are_saved_only_for_a_profile_of_the_profiles_file(tmp_path):
    # a gallery drawn before the profile was deleted or renamed (e.g. in another tab) must
    # not save marks under its old name: a later profile of that name would get them
    profiles = profiles_file(tmp_path / 'profiles.json', 'Red car')
    path = tmp_path / MARKS_FILE
    assert save_marks(path, 'Red car', {'a.jpg': MARK_MATCH}, profiles_file=profiles) == {'a.jpg': MARK_MATCH}
    profiles_file(profiles, 'Dog')  # Red car deleted since
    before = path.read_bytes()
    with pytest.raises(UnknownProfileError, match='Red car'):
        save_marks(path, 'Red car', {'b.jpg': MARK_MATCH}, profiles_file=profiles)
    with pytest.raises(UnknownProfileError):
        save_marks(path, 'Red car', {'a.jpg': MARK_OPEN}, profiles_file=profiles)
    assert path.read_bytes() == before
    with pytest.raises(UnknownProfileError):
        save_marks(tmp_path / 'new' / MARKS_FILE, 'Cat', {'a.jpg': MARK_MATCH}, profiles_file=profiles)
    assert not (tmp_path / 'new' / MARKS_FILE).exists()


def test_an_unreadable_profiles_file_saves_no_marks(tmp_path):
    profiles = tmp_path / 'profiles.json'
    profiles.write_text('not json', encoding='utf-8')
    path = tmp_path / MARKS_FILE
    with pytest.raises(ValueError):
        save_marks(path, 'Red car', {'a.jpg': MARK_MATCH}, profiles_file=profiles)
    assert not path.exists()
    assert profiles.read_text(encoding='utf-8') == 'not json'


def test_the_profile_is_checked_under_the_marks_lock(tmp_path, monkeypatch):
    # while the lock is held: a deletion saves profiles.json first and then deletes the
    # marks under the same lock, so a mark saved in between is deleted with them
    import framescout_core.marks as marks_module
    profiles = profiles_file(tmp_path / 'profiles.json', 'Red car')
    path = tmp_path / MARKS_FILE
    seen = []
    real = marks_module.require_profile

    def check(filename, name):
        seen.append(lock_held(tmp_path / (MARKS_FILE + '.lock')))
        return real(filename, name)

    monkeypatch.setattr(marks_module, 'require_profile', check)
    save_marks(path, 'Red car', {'a.jpg': MARK_MATCH}, profiles_file=profiles)
    assert seen == [True]


# --- hiding the photos marked as no match within a gallery page (A24) ---

def cards_of(count):
    return [{'rank': rank, 'path': f'photo{rank}.jpg'} for rank in range(1, count + 1)]


def test_hide_no_match_drops_only_the_photos_marked_as_no_match():
    cards = cards_of(5)
    marks = {'photo2.jpg': MARK_NO_MATCH, 'photo3.jpg': MARK_MATCH, 'other.jpg': MARK_NO_MATCH}
    kept, hidden = hide_no_match(cards, marks)
    assert [c['rank'] for c in kept] == [1, 3, 4, 5] and hidden == 1
    assert hide_no_match(cards, {}) == (cards, 0)
    assert hide_no_match([], marks) == ([], 0)


def test_hiding_the_rejects_of_a_page_keeps_the_pages_stable():
    # user report: hiding the rejects of page 1 pulled the undecided photos of page 2 up
    cards = cards_of(100)
    marks = {f'photo{rank}.jpg': MARK_NO_MATCH for rank in range(1, 49)}  # all of page 1
    kept, hidden = hide_no_match(page_cards(cards, 1, 48), marks)
    assert kept == [] and hidden == 48  # an empty page rather than photos of page 2
    kept, hidden = hide_no_match(page_cards(cards, 2, 48), marks)
    assert [c['rank'] for c in kept] == list(range(49, 97)) and hidden == 0


@pytest.mark.parametrize('hidden,kept,more_pages,text', [
    (0, 48, True, ''),
    (1, 47, False, '1 photo of this page marked as no match is hidden.'),
    (1200, 3, False, '1,200 photos of this page marked as no match are hidden.'),
    # review: no "All 1 photos" for a page of a single photo
    (1, 0, False, 'The only photo of this page is marked as no match and hidden.'),
    (48, 0, False, 'All 48 photos of this page are marked as no match and hidden.'),
    (48, 0, True, 'All 48 photos of this page are marked as no match and hidden. '
                  'The next page may hold photos still to check.'),
])
def test_hidden_text_counts_the_hidden_photos_of_a_page(hidden, kept, more_pages, text):
    assert hidden_text(hidden, kept, more_pages) == text


# --- review progress per profile and the first open photo (F20) ---

def test_review_progress_counts_the_marks_of_the_ranked_photos():
    cards = cards_of(10)
    marks = {'photo1.jpg': MARK_MATCH, 'photo2.jpg': MARK_NO_MATCH, 'photo3.jpg': MARK_MATCH,
             'photo5.jpg': MARK_NO_MATCH,
             'other.jpg': MARK_MATCH}  # a photo of no card of this search: not counted
    progress = review_progress(cards, marks, 48)
    assert progress == ReviewProgress(matches=2, no_matches=2, open=6, first_open_rank=4, first_open_page=1)


def test_review_progress_finds_the_page_the_gallery_shows_the_first_open_photo_on():
    cards = cards_of(150)
    marks = {f'photo{rank}.jpg': MARK_NO_MATCH if rank % 3 else MARK_MATCH for rank in range(1, 74)}
    progress = review_progress(cards, marks, 48)
    assert (progress.first_open_rank, progress.first_open_page) == (74, 2)
    assert progress.open == 77 and progress.matches + progress.no_matches == 73
    # the page of the gallery's pagination holds that photo, also with the rejects hidden (A24)
    kept, _ = hide_no_match(page_cards(cards, progress.first_open_page, 48), marks)
    assert 74 in [card['rank'] for card in kept]


@pytest.mark.parametrize('index', [0, 47, 48, 95, 96, 149])
def test_review_progress_page_matches_page_cards_at_page_boundaries(index):
    cards = cards_of(150)
    marks = {card['path']: MARK_MATCH for card in cards[:index]}
    progress = review_progress(cards, marks, 48)
    assert progress.first_open_rank == index + 1
    assert cards[index] in page_cards(cards, progress.first_open_page, 48)


def test_review_progress_follows_the_list_order_not_the_rank_numbers():
    # the gallery pages the list as it is stored; the first open photo is the first of the list
    cards = [{'rank': 7, 'path': 'a.jpg'}, {'rank': 3, 'path': 'b.jpg'}]
    assert review_progress(cards, {'a.jpg': MARK_MATCH}, 1) == ReviewProgress(1, 0, 1, 3, 2)


def test_review_progress_counts_every_card_of_a_photo_listed_twice():
    # review: the gallery shows a card per entry, each with the photo's one mark, so the
    # caption counts per card like the pages do
    cards = [{'rank': 1, 'path': 'a.jpg'}, {'rank': 2, 'path': 'b.jpg'}, {'rank': 3, 'path': 'a.jpg'},
             {'rank': 4, 'path': 'c.jpg'}]
    assert review_progress(cards, {'a.jpg': MARK_MATCH}, 2) == ReviewProgress(2, 0, 2, 2, 1)
    assert review_progress(cards, {'a.jpg': MARK_NO_MATCH, 'b.jpg': MARK_MATCH}, 2) == ReviewProgress(1, 2, 1, 4, 2)


def test_review_progress_of_a_fully_checked_or_empty_list_has_no_first_open_photo():
    cards = cards_of(3)
    marks = {'photo1.jpg': MARK_MATCH, 'photo2.jpg': MARK_NO_MATCH, 'photo3.jpg': MARK_NO_MATCH}
    assert review_progress(cards, marks, 48) == ReviewProgress(1, 2, 0, None, None)
    assert review_progress([], marks, 48) == ReviewProgress(0, 0, 0, None, None)
    # an unknown stored state counts as open, as the gallery shows it
    assert review_progress(cards_of(1), {'photo1.jpg': 'maybe'}, 48) == ReviewProgress(0, 0, 1, 1, 1)


@pytest.mark.parametrize('progress,paged,text', [
    (ReviewProgress(0, 0, 0, None, None), False, ''),
    (ReviewProgress(32, 41, 77, 74, 2), True,
     '150 photos: 32 match, 41 no match, 77 undecided. The first undecided photo is #74 on page 2.'),
    (ReviewProgress(0, 0, 5, 1, 1), False, '5 photos: 0 match, 0 no match, 5 undecided. The first undecided photo is #1.'),
    (ReviewProgress(1, 0, 0, None, None), False, '1 photo: 1 match, 0 no match, 0 undecided. Every photo is marked.'),
    (ReviewProgress(1200, 3, 0, None, None), True,
     '1,203 photos: 1,200 match, 3 no match, 0 undecided. Every photo is marked.'),
])
def test_progress_text_summarizes_the_review_of_a_profile(progress, paged, text):
    assert progress_text(progress, paged) == text


# --- the colors of the selected option of a mark (A24) ---

def test_mark_style_colors_the_selected_option_of_each_marked_control():
    style = mark_style({'mark_a1': MARK_MATCH, 'mark_b2': MARK_NO_MATCH, 'mark_c3': MARK_OPEN,
                        'mark_d4': MARK_MATCH})
    assert style.startswith('<style>') and style.endswith('</style>')
    match_background, match_border = MARK_COLORS[MARK_MATCH]
    reject_background, reject_border = MARK_COLORS[MARK_NO_MATCH]
    # one rule per state listing the selected button of each control in that state, named as
    # Streamlit 1.66.1 does: the key class of the element, the variant of its buttons and the
    # data-selected attribute of the selected one (no kind attribute any more, A49)
    assert ('.st-key-mark_a1 button[data-variant="segmented_control"][data-selected], '
            '.st-key-mark_d4 button[data-variant="segmented_control"][data-selected]'
            f'{{background-color:{match_background}!important;border-color:{match_border}!important;'
            'color:inherit!important}') in style
    assert ('.st-key-mark_b2 button[data-variant="segmented_control"][data-selected]'
            f'{{background-color:{reject_background}!important;border-color:{reject_border}!important;'
            'color:inherit!important}') in style
    assert 'mark_c3' not in style  # undecided keeps Streamlit's look
    assert 'kind=' not in style  # the 1.66.1 buttons carry no kind attribute (A49)


def test_mark_style_is_empty_without_a_decided_mark():
    assert mark_style({}) == ''
    assert mark_style({'mark_a1': MARK_OPEN}) == ''


def test_mark_style_names_a_key_as_streamlit_turns_it_into_a_class():
    # Streamlit 1.66 trims the key and replaces every character but letters, digits, "_"
    # and "-" by "-"
    assert '.st-key-mark_a-b-c button' in mark_style({' mark_a.b c ': MARK_MATCH})


def test_mark_style_was_checked_with_the_pinned_streamlit():
    # the selectors rely on Streamlit internals: raising the pin fails here until the
    # selectors were checked against the new version and MARK_STYLE_STREAMLIT updated
    constraints = (Path(__file__).resolve().parent.parent / CONSTRAINTS_FILE).read_text(encoding='utf-8')
    pinned = re.search(r'^streamlit==(\S+)$', constraints, re.MULTILINE)
    assert pinned and pinned.group(1) == MARK_STYLE_STREAMLIT


# --- backup and restore (F1) ----------------------------------------------------------------

# 2026-11-02 12:30:45 local time
NOW = time.mktime((2026, 11, 2, 12, 30, 45, 0, 0, -1))


def test_the_backup_name():
    assert MARKS_BACKUP == 'marks.json.bak'
    assert marks_backup(Path('results') / MARKS_FILE) == Path('results') / MARKS_BACKUP
    assert MARKS_BACKUP in NEVER_DELETED


def test_a_save_keeps_the_previous_file_as_backup(tmp_path):
    path = tmp_path / MARKS_FILE
    save_marks(path, 'Red car', {'a.jpg': MARK_MATCH})
    assert not marks_backup(path).exists()  # the first save has nothing to keep
    first = path.read_bytes()
    save_marks(path, 'Red car', {'b.jpg': MARK_NO_MATCH})
    assert marks_backup(path).read_bytes() == first
    second = path.read_bytes()
    save_marks(path, 'Red car', {'a.jpg': MARK_OPEN})
    assert marks_backup(path).read_bytes() == second  # one generation: the state before the latest save
    assert read_marks(marks_backup(path)) == {'Red car': {'a.jpg': MARK_MATCH, 'b.jpg': MARK_NO_MATCH}}


def test_only_the_marks_file_is_flushed_to_disk_not_its_backup(tmp_path, monkeypatch):
    # review: the backup is written on every mark click; one fsync per change, for the file
    path = tmp_path / MARKS_FILE
    save_marks(path, 'Red car', {'a.jpg': MARK_MATCH})
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
    save_marks(path, 'Red car', {'b.jpg': MARK_MATCH})
    assert events == [('replace', MARKS_BACKUP), 'fsync', ('replace', MARKS_FILE)]


def test_a_save_that_changes_nothing_keeps_the_backup(tmp_path):
    path = tmp_path / MARKS_FILE
    save_marks(path, 'Red car', {'a.jpg': MARK_MATCH})
    save_marks(path, 'Red car', {'b.jpg': MARK_MATCH})
    backup = marks_backup(path).read_bytes()
    save_marks(path, 'Red car', {'a.jpg': MARK_MATCH})
    assert marks_backup(path).read_bytes() == backup


@pytest.mark.parametrize('change', [lambda path: rename_marks(path, 'Red car', 'Blue car'),
                                    lambda path: delete_marks(path, 'Red car'),
                                    lambda path: remove_marks(path, {('Red car', 'a.jpg')})])
def test_renaming_deleting_and_removing_marks_keep_a_backup_too(tmp_path, change):
    path = tmp_path / MARKS_FILE
    save_marks(path, 'Red car', {'a.jpg': MARK_MATCH})
    before = path.read_bytes()
    change(path)
    assert marks_backup(path).read_bytes() == before


def test_an_unreadable_file_never_replaces_the_backup(tmp_path):
    path = tmp_path / MARKS_FILE
    save_marks(path, 'Red car', {'a.jpg': MARK_MATCH})
    save_marks(path, 'Red car', {'b.jpg': MARK_MATCH})
    backup = marks_backup(path).read_bytes()
    path.write_text('{broken', encoding='utf-8')
    with pytest.raises(ValueError):
        save_marks(path, 'Red car', {'c.jpg': MARK_MATCH})
    assert marks_backup(path).read_bytes() == backup


DAMAGED = b'{"format": 1, "prof\x00\x00'  # e.g. a power loss during a sync tool's write


def damaged(tmp_path):
    """A marks file that became unreadable after two saves; its backup holds the first."""
    path = tmp_path / MARKS_FILE
    save_marks(path, 'Red car', {'a.jpg': MARK_MATCH, 'b.jpg': MARK_NO_MATCH})
    save_marks(path, 'Dog', {'c.jpg': MARK_MATCH})
    path.write_bytes(DAMAGED)
    return path


def test_restoring_copies_the_backup_and_keeps_the_damaged_file(tmp_path):
    path = damaged(tmp_path)
    backup = marks_backup(path).read_bytes()
    restored, kept = restore_marks(path, now=NOW)
    assert restored == 2
    assert kept == tmp_path / 'marks.json.broken-20261102-123045'
    assert kept.read_bytes() == DAMAGED
    assert path.read_bytes() == backup and marks_backup(path).read_bytes() == backup
    assert read_marks(path) == {'Red car': {'a.jpg': MARK_MATCH, 'b.jpg': MARK_NO_MATCH}}
    # a second damaged file of the same second gets a name of its own
    path.write_text('{broken', encoding='utf-8')
    assert restore_marks(path, now=NOW)[1] == tmp_path / 'marks.json.broken-20261102-123045-2'
    assert kept.read_bytes() == DAMAGED


def test_a_readable_file_is_never_replaced_by_the_backup(tmp_path):
    path = damaged(tmp_path)
    fixed = path.with_name('fixed.json')
    save_marks(fixed, 'Red car', {'a.jpg': MARK_MATCH})
    path.write_bytes(fixed.read_bytes())  # fixed by hand meanwhile, or restored in another tab
    with pytest.raises(ValueError, match='can be read'):
        restore_marks(path, now=NOW)
    assert path.read_bytes() == fixed.read_bytes()
    assert not list(tmp_path.glob('*.broken-*'))


@pytest.mark.parametrize('backup', [None, b'{broken', b'{"format": 2, "profiles": {}}'])
def test_nothing_is_restored_without_a_readable_backup(tmp_path, backup):
    path = damaged(tmp_path)
    if backup is None:
        marks_backup(path).unlink()
    else:
        marks_backup(path).write_bytes(backup)
    with pytest.raises(ValueError, match=re.escape(MARKS_BACKUP)):
        restore_marks(path, now=NOW)
    assert path.read_bytes() == DAMAGED
    assert not list(tmp_path.glob('*.broken-*'))


def test_a_missing_file_gets_the_backup(tmp_path):
    # removed by hand after the app offered the restore: nothing is lost by restoring
    path = damaged(tmp_path)
    path.unlink()
    assert restore_marks(path, now=NOW) == (2, None)
    assert read_marks(path) == {'Red car': {'a.jpg': MARK_MATCH, 'b.jpg': MARK_NO_MATCH}}


def test_the_restore_is_offered_for_a_damaged_file_with_a_readable_backup(tmp_path):
    path = damaged(tmp_path)
    saved = marks_backup(path).stat().st_mtime
    assert marks_restore_offer(path, ValueError('damaged')) == (2, saved)
    # e.g. a file another program has open: no damage, nothing to restore
    assert marks_restore_offer(path, OSError('in use')) is None
    marks_backup(path).write_text('{broken', encoding='utf-8')
    assert marks_restore_offer(path, ValueError('damaged')) is None
    marks_backup(path).unlink()
    assert marks_restore_offer(path, ValueError('damaged')) is None


def test_the_restore_is_offered_for_a_missing_file_whose_backup_holds_marks(tmp_path):
    # e.g. removed by hand as an older warning advised (A40)
    path = damaged(tmp_path)
    assert marks_restore_offer(path, None) is None  # the file exists (read without an error)
    path.unlink()
    assert marks_restore_offer(path, None) == (2, marks_backup(path).stat().st_mtime)
    marks_backup(path).write_text(json.dumps({'format': 1, 'profiles': {}}), encoding='utf-8')
    assert marks_restore_offer(path, None) is None  # nothing to bring back
    marks_backup(path).unlink()
    assert marks_restore_offer(path, None) is None


def test_the_restore_offer_reads_the_backup_with_the_given_reader(tmp_path):
    # the app passes a cached read_marks: the offer runs on every gallery rerun (review)
    path = damaged(tmp_path)
    path.unlink()
    read = []
    offer = marks_restore_offer(path, None, read=lambda backup: read.append(backup) or {'Red car': {'a.jpg': MARK_MATCH}})
    assert offer == (1, marks_backup(path).stat().st_mtime)
    assert read == [marks_backup(path)]

    def missing(backup):
        raise FileNotFoundError(backup)
    assert marks_restore_offer(path, None, read=missing) is None


def test_restoring_waits_for_the_lock_and_gives_up(tmp_path):
    path = damaged(tmp_path)
    lock = RunLock(tmp_path / (MARKS_FILE + '.lock'))
    assert lock.acquire()
    try:
        with pytest.raises(OSError):
            restore_marks(path, now=NOW, lock_timeout=0.05)
    finally:
        lock.release()
    assert path.read_bytes() == DAMAGED and not list(tmp_path.glob('*.broken-*'))


def test_a_failed_restore_leaves_the_damaged_file(tmp_path, monkeypatch):
    import framescout_core.marks as marks_module
    path = damaged(tmp_path)

    def fail(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr(marks_module, '_replace_with_retry', fail)
    for _ in range(2):  # e.g. the file is held open by a sync tool, and the user tries again
        with pytest.raises(OSError):
            restore_marks(path, now=NOW, attempts=1)
    assert path.read_bytes() == DAMAGED
    # review: no copy of the damaged file per failed try
    assert sorted(p.name for p in tmp_path.iterdir()) == [MARKS_FILE, MARKS_BACKUP, MARKS_FILE + '.lock']
