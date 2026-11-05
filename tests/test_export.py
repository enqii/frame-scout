"""Exporting a result list as a CSV table and a file list (framescout_core, F5)."""
import csv
import io
from datetime import datetime
from pathlib import Path

import pytest

import framescout_core.exporting as exporting
from framescout_core import (EXPORT_COLUMNS, EXPORTS_DIR, MARK_MATCH, MARK_NO_MATCH, MARK_OPEN, export_cards, export_csv, export_file_list, export_name, export_result_list,
                             result_card, unlisted_paths)

NOW = datetime(2026, 11, 3, 14, 5, 9)


def card(rank, path, score=1.5, text=0.31, visual=None, label='Full image'):
    return result_card(rank, Path(path), Path(path).name, label, score, text, visual, f'Score {score:+.2f}',
                       'detail', f'{rank:024x}.jpg')


CARDS = [card(1, '/photos/a.jpg', 2.25, 0.3125, 0.8, 'Person 1'), card(2, '/photos/sub/b.jpg', 1.0),
         card(3, '/photos/c, "quoted".jpg', -0.5)]
# the photo paths as the result file holds them (str of a Path: backslashes on Windows)
A, B, C = (c['path'] for c in CARDS)


def rows(text):
    return list(csv.reader(io.StringIO(text, newline='')))


# --- selection -------------------------------------------------------------------------

def test_all_ranked_photos_are_exported_in_rank_order():
    assert export_cards(CARDS, {}) == CARDS


def test_only_matches_keeps_the_ranked_photos_marked_as_match():
    marks = {A: MARK_NO_MATCH, B: MARK_MATCH, str(Path('/photos/elsewhere.jpg')): MARK_MATCH}
    assert export_cards(CARDS, marks, only_matches=True) == [CARDS[1]]


def test_only_matches_needs_readable_marks():
    with pytest.raises(ValueError):
        export_cards(CARDS, None, only_matches=True)


# --- CSV table ---------------------------------------------------------------------------

def test_the_csv_has_a_header_and_one_row_per_photo():
    marks = {A: MARK_MATCH, B: MARK_NO_MATCH}
    table = rows(export_csv(CARDS, marks))
    assert table[0] == list(EXPORT_COLUMNS)
    assert table[1] == ['1', A, '2.2500', '0.3125', '0.8000', 'Person 1', 'match']
    assert table[2] == ['2', B, '1.0000', '0.3100', '', 'Full image', 'no match']
    assert table[3][1] == C  # quoted by the csv module
    assert table[3][-1] == ''  # not marked
    assert len(table) == 4


def test_an_open_mark_is_an_empty_cell():
    assert rows(export_csv(CARDS[:1], {A: MARK_OPEN}))[1][-1] == ''


def test_unreadable_marks_leave_the_mark_column_empty():
    assert [r[-1] for r in rows(export_csv(CARDS, None))[1:]] == ['', '', '']


def test_the_file_list_has_one_path_per_line():
    assert export_file_list(CARDS).splitlines() == [c['path'] for c in CARDS]
    assert export_file_list([]) == ''


@pytest.mark.parametrize('brk', ['\n', '\r', '\r\n', '\x0b', '\x85', ' '])
def test_a_path_with_a_line_break_is_left_out_of_the_file_list_only(brk):
    # possible on Linux/macOS file systems; the CSV quotes it, one line of the list cannot hold it (A42)
    odd = card(2, f'/photos/two{brk}lines.jpg')
    cards = [CARDS[0], odd, CARDS[1]]
    assert unlisted_paths(cards) == [odd['path']]
    assert export_file_list(cards).splitlines() == [A, B]
    assert export_file_list(cards).split('\n') == [A, B, '']
    assert rows(export_csv(cards, {}))[2][1] == odd['path']
    assert unlisted_paths(CARDS) == []


def test_an_empty_path_has_no_line_break():
    # ''.splitlines() is [], which is not [''] (review)
    assert unlisted_paths([{'path': ''}]) == []
    assert export_file_list([{'path': ''}]) == '\n'


def test_the_export_writes_a_path_with_a_line_break_only_to_the_csv(tmp_path):
    odd = card(2, '/photos/two\nlines.jpg')
    table, listing = export_result_list(tmp_path, 'x', [CARDS[0], odd], {}, now=NOW)
    assert listing.read_text(encoding='utf-8') == A + '\n'
    assert [r[1] for r in rows(table.read_text(encoding='utf-8-sig'))[1:]] == [A, odd['path']]


# --- file names --------------------------------------------------------------------------

def test_the_export_name_has_the_slug_date_and_time():
    assert export_name('red-car', NOW) == 'red-car-20261103-140509'
    assert export_name('red-car', NOW, only_matches=True) == 'red-car-20261103-140509-matches'


# --- writing -----------------------------------------------------------------------------

def test_the_export_writes_a_csv_and_a_file_list_into_the_exports_folder(tmp_path):
    marks = {A: MARK_MATCH}
    table, listing = export_result_list(tmp_path, 'red-car', CARDS, marks, now=NOW)
    assert table == tmp_path / EXPORTS_DIR / 'red-car-20261103-140509.csv'
    assert listing == tmp_path / EXPORTS_DIR / 'red-car-20261103-140509.txt'
    data = table.read_bytes()
    assert data.startswith(b'\xef\xbb\xbf')  # UTF-8 with BOM, so that Excel reads the paths right
    assert data.decode('utf-8-sig') == export_csv(CARDS, marks)
    assert listing.read_bytes() == export_file_list(CARDS).encode('utf-8')
    assert sorted(p.name for p in (tmp_path / EXPORTS_DIR).iterdir()) == [table.name, listing.name]


def test_non_ascii_paths_survive(tmp_path):
    cards = [card(1, '/photos/Überfahrt/café ☕.jpg')]
    table, listing = export_result_list(tmp_path, 'x', cards, {}, now=NOW)
    assert rows(table.read_text(encoding='utf-8-sig'))[1][1] == cards[0]['path']
    assert listing.read_text(encoding='utf-8').splitlines() == [cards[0]['path']]


def test_only_matches_is_in_the_name_and_the_content(tmp_path):
    table, listing = export_result_list(tmp_path, 'red-car', CARDS, {A: MARK_MATCH},
                                        only_matches=True, now=NOW)
    assert table.name == 'red-car-20261103-140509-matches.csv'
    assert listing.read_text(encoding='utf-8').splitlines() == [CARDS[0]['path']]


def test_an_earlier_export_is_never_overwritten(tmp_path):
    first = export_result_list(tmp_path, 'red-car', CARDS, {}, now=NOW)
    before = [p.read_bytes() for p in first]
    second = export_result_list(tmp_path, 'red-car', CARDS[:1], {}, now=NOW)
    assert [p.name for p in second] == ['red-car-20261103-140509-2.csv', 'red-car-20261103-140509-2.txt']
    assert [p.read_bytes() for p in first] == before
    # a foreign file taking only one of the two names is skipped as well
    (tmp_path / EXPORTS_DIR / 'red-car-20261103-140509-3.txt').write_text('mine', encoding='utf-8')
    third = export_result_list(tmp_path, 'red-car', CARDS, {}, now=NOW)
    assert third[0].name == 'red-car-20261103-140509-4.csv'
    assert (tmp_path / EXPORTS_DIR / 'red-car-20261103-140509-3.txt').read_text(encoding='utf-8') == 'mine'


def test_a_name_taken_meanwhile_keeps_the_pair_together(tmp_path, monkeypatch):
    # the file list's name is taken between the check and the write: the table written for
    # it is removed and both get the next name
    publish_new = exporting._publish_new
    raced = []

    def racing(tmp, target):
        if target.suffix == '.txt' and not raced:
            raced.append(target)
            target.write_text('other', encoding='utf-8')
        publish_new(tmp, target)

    monkeypatch.setattr(exporting, '_publish_new', racing)
    table, listing = export_result_list(tmp_path, 'red-car', CARDS, {}, now=NOW)
    assert (table.name, listing.name) == ('red-car-20261103-140509-2.csv', 'red-car-20261103-140509-2.txt')
    assert not (tmp_path / EXPORTS_DIR / 'red-car-20261103-140509.csv').exists()
    assert raced[0].read_text(encoding='utf-8') == 'other'
    assert sorted(p.name for p in (tmp_path / EXPORTS_DIR).iterdir()) == [
        'red-car-20261103-140509-2.csv', 'red-car-20261103-140509-2.txt', 'red-car-20261103-140509.txt']


def test_nothing_to_export_writes_nothing(tmp_path):
    with pytest.raises(ValueError):
        export_result_list(tmp_path, 'red-car', CARDS, {}, only_matches=True, now=NOW)
    assert not (tmp_path / EXPORTS_DIR).exists()
