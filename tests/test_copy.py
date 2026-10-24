"""Copying marked photos to a folder and the saved target folders (framescout_core, A17)."""
import json
import os
from pathlib import Path

import pytest

from framescout_core import (copy_photos, copy_summary_text, copy_target, default_copy_folder, default_settings,
                             read_copy_folders, read_settings, rename_copy_folder, save_copy_folder, save_settings)


def photo(path, data=b'photo'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# --- target folder -----------------------------------------------------------------------

def test_the_default_target_is_a_profile_folder_in_pictures(tmp_path):
    assert default_copy_folder(tmp_path, 'red-car') == tmp_path / 'FrameScout' / 'red-car'


def test_a_folder_outside_the_photo_folders_is_accepted(tmp_path):
    target, problem = copy_target(str(tmp_path / 'copies' / 'red-car'), [str(tmp_path / 'photos')])
    assert problem is None
    assert target == tmp_path / 'copies' / 'red-car'


@pytest.mark.parametrize('text', ['', '   '])
def test_an_empty_target_is_refused(tmp_path, text):
    target, problem = copy_target(text, [str(tmp_path / 'photos')])
    assert target is None and 'Enter' in problem


def test_a_relative_target_is_refused(tmp_path):
    target, problem = copy_target('copies', [str(tmp_path / 'photos')])
    assert target is None and 'complete path' in problem


@pytest.mark.parametrize('inside', ['photos', 'photos/sub/matches'])
def test_a_target_in_a_photo_folder_is_refused(tmp_path, inside):
    target, problem = copy_target(str(tmp_path / inside), [str(tmp_path / 'other'), str(tmp_path / 'photos')])
    assert target is None
    assert 'photo folder' in problem and 'twice' in problem


@pytest.mark.skipif(os.name != 'nt', reason='Windows paths are case-insensitive')
def test_the_photo_folder_check_ignores_case_on_windows(tmp_path):
    (tmp_path / 'Photos').mkdir()
    target, problem = copy_target(str(tmp_path / 'PHOTOS' / 'x'), [str(tmp_path / 'Photos')])
    assert target is None


def test_a_photo_folder_inside_the_target_is_accepted(tmp_path):
    # flat copies land next to the photo folder, not in it
    target, problem = copy_target(str(tmp_path), [str(tmp_path / 'photos')])
    assert problem is None


def test_an_empty_photo_folder_entry_is_ignored(tmp_path):
    target, problem = copy_target(str(tmp_path / 'copies'), ['', None])
    assert problem is None


def test_a_file_as_target_is_refused(tmp_path):
    photo(tmp_path / 'copies')
    target, problem = copy_target(str(tmp_path / 'copies'), [])
    assert target is None and 'file' in problem


def test_a_user_folder_target_is_expanded(tmp_path, monkeypatch):
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    monkeypatch.setenv('HOME', str(tmp_path))
    target, problem = copy_target('~/copies', [])
    assert problem is None and target == tmp_path / 'copies'


# --- copying ------------------------------------------------------------------------------

def test_photos_are_copied_flat_with_their_date(tmp_path):
    a = photo(tmp_path / 'photos' / 'a.jpg', b'A')
    b = photo(tmp_path / 'photos' / 'sub' / 'b.jpg', b'B')
    os.utime(a, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))
    target = tmp_path / 'out' / 'red-car'
    summary = copy_photos([str(a), str(b)], target)
    assert summary == {'copied': 2, 'already': 0, 'renamed': 0, 'failed': []}
    assert (target / 'a.jpg').read_bytes() == b'A' and (target / 'b.jpg').read_bytes() == b'B'
    assert (target / 'a.jpg').stat().st_mtime_ns == a.stat().st_mtime_ns
    assert sorted(x.name for x in target.iterdir()) == ['a.jpg', 'b.jpg']  # no temporary files left
    assert a.read_bytes() == b'A' and b.exists()  # originals untouched


def test_the_same_file_again_is_already_there(tmp_path):
    a = photo(tmp_path / 'photos' / 'a.jpg', b'A')
    target = tmp_path / 'out'
    copy_photos([str(a)], target)
    assert copy_photos([str(a)], target) == {'copied': 0, 'already': 1, 'renamed': 0, 'failed': []}
    assert [x.name for x in target.iterdir()] == ['a.jpg']


def test_the_same_name_with_other_content_is_renamed_never_overwritten(tmp_path):
    target = tmp_path / 'out'
    photo(target / 'a.jpg', b'existing')
    photo(target / 'a (2).jpg', b'also existing')
    a = photo(tmp_path / 'photos' / 'a.jpg', b'new')
    assert copy_photos([str(a)], target) == {'copied': 0, 'already': 0, 'renamed': 1, 'failed': []}
    assert (target / 'a.jpg').read_bytes() == b'existing'
    assert (target / 'a (2).jpg').read_bytes() == b'also existing'
    assert (target / 'a (3).jpg').read_bytes() == b'new'
    # copying again finds the renamed copy
    assert copy_photos([str(a)], target)['already'] == 1


def test_two_photos_with_one_name_in_one_copy(tmp_path):
    a = photo(tmp_path / 'photos' / 'x' / 'img.jpg', b'one')
    b = photo(tmp_path / 'photos' / 'y' / 'img.jpg', b'two')
    c = photo(tmp_path / 'photos' / 'z' / 'img.jpg', b'one')  # a duplicate of a
    assert copy_photos([str(a), str(b), str(c)], tmp_path / 'out') == {
        'copied': 1, 'already': 1, 'renamed': 1, 'failed': []}
    assert (tmp_path / 'out' / 'img (2).jpg').read_bytes() == b'two'


def test_a_missing_photo_fails_and_the_rest_is_copied(tmp_path):
    a = photo(tmp_path / 'photos' / 'a.jpg')
    gone = tmp_path / 'photos' / 'gone.jpg'
    summary = copy_photos([str(gone), str(a)], tmp_path / 'out')
    assert summary['copied'] == 1
    assert [p for p, _ in summary['failed']] == [str(gone)]


def test_a_folder_with_the_target_name_is_not_overwritten(tmp_path):
    target = tmp_path / 'out'
    (target / 'a.jpg').mkdir(parents=True)
    a = photo(tmp_path / 'photos' / 'a.jpg')
    assert copy_photos([str(a)], target)['renamed'] == 1
    assert (target / 'a (2).jpg').is_file()


def test_the_summary_text():
    assert copy_summary_text({'copied': 20, 'already': 2, 'renamed': 1, 'failed': []}) == (
        '20 copied · 2 already there · 1 renamed · 0 failed')
    assert copy_summary_text({'copied': 0, 'already': 0, 'renamed': 0, 'failed': [('a', 'x')]}).endswith('1 failed')


# --- saved target folders in settings.json ---------------------------------------------------

def test_no_saved_folders_without_a_file(tmp_path):
    assert read_copy_folders(tmp_path / 'settings.json') == {}


def test_a_target_folder_is_saved_per_profile(tmp_path):
    settings = tmp_path / 'settings.json'
    save_copy_folder(settings, 'Red car', 'D:/cars', default='C:/Pictures/FrameScout/red-car')
    save_copy_folder(settings, 'Dog', 'D:/dogs', default='C:/Pictures/FrameScout/dog')
    assert read_copy_folders(settings) == {'Red car': 'D:/cars', 'Dog': 'D:/dogs'}


def test_the_default_folder_is_not_stored(tmp_path):
    settings = tmp_path / 'settings.json'
    save_copy_folder(settings, 'Red car', 'C:/Pictures/FrameScout/red-car', default='C:/Pictures/FrameScout/red-car')
    assert not settings.exists()
    save_copy_folder(settings, 'Red car', 'D:/cars', default='x')
    save_copy_folder(settings, 'Red car', '  x  ', default='x')  # back to the default: removed
    assert read_copy_folders(settings) == {}


def test_target_folders_and_settings_do_not_disturb_each_other(tmp_path):
    settings = tmp_path / 'settings.json'
    defaults = default_settings(tmp_path)
    save_settings(settings, {'top': 300}, defaults)
    save_copy_folder(settings, 'Red car', 'D:/cars', default='x')
    save_settings(settings, {'batch_size': 4}, defaults)
    assert read_copy_folders(settings) == {'Red car': 'D:/cars'}
    assert read_settings(settings, defaults)[0]['top'] == 300


def test_invalid_saved_folders_are_ignored(tmp_path):
    settings = tmp_path / 'settings.json'
    settings.write_text(json.dumps({'copy_folders': {'Red car': 'D:/cars', 'Dog': 3, 'Cat': ''}}), encoding='utf-8')
    assert read_copy_folders(settings) == {'Red car': 'D:/cars'}
    settings.write_text(json.dumps({'copy_folders': ['D:/cars']}), encoding='utf-8')
    assert read_copy_folders(settings) == {}


def test_an_unreadable_settings_file_is_never_replaced(tmp_path):
    settings = tmp_path / 'settings.json'
    settings.write_text('not json', encoding='utf-8')
    with pytest.raises(ValueError):
        read_copy_folders(settings)
    with pytest.raises(ValueError):
        save_copy_folder(settings, 'Red car', 'D:/cars', default='x')
    assert settings.read_text(encoding='utf-8') == 'not json'


def test_a_renamed_profile_keeps_its_target_folder(tmp_path):
    settings = tmp_path / 'settings.json'
    save_copy_folder(settings, 'Red car', 'D:/cars', default='x')
    rename_copy_folder(settings, 'Red car', 'Blue car')
    assert read_copy_folders(settings) == {'Blue car': 'D:/cars'}
    rename_copy_folder(settings, 'Nothing', 'Else')  # no folder saved: no change
    assert read_copy_folders(settings) == {'Blue car': 'D:/cars'}


# --- review findings ------------------------------------------------------------------------

def test_a_name_that_cannot_be_created_moves_on_to_the_next(tmp_path, monkeypatch):
    # e.g. a dangling symbolic link: exists() is False, but the name is taken (review: no endless loop)
    import framescout_core
    publish = framescout_core._publish_new

    def refuse_first(tmp, target):
        if target.name == 'a.jpg':
            raise FileExistsError(target)
        publish(tmp, target)

    monkeypatch.setattr(framescout_core, '_publish_new', refuse_first)
    a = photo(tmp_path / 'photos' / 'a.jpg')
    assert copy_photos([str(a)], tmp_path / 'out')['renamed'] == 1
    assert (tmp_path / 'out' / 'a (2).jpg').is_file()


def test_a_dangling_link_with_the_photo_name_is_kept(tmp_path):
    target = tmp_path / 'out'
    target.mkdir()
    try:
        os.symlink(tmp_path / 'nowhere.jpg', target / 'a.jpg')
    except (OSError, NotImplementedError):
        pytest.skip('symbolic links cannot be created here')
    a = photo(tmp_path / 'photos' / 'a.jpg')
    assert copy_photos([str(a)], target)['renamed'] == 1
    assert (target / 'a.jpg').is_symlink() and (target / 'a (2).jpg').is_file()
