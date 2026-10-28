"""Cleaning up the results folder, the feature cache and the reference images (E7, E11, E13, E23, A14)."""
import json
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from framescout_core import (CACHE_FILE, DEFAULT_MODEL, DEFAULT_YOLO_MODEL, ENGINE, MARKS_FILE, RESULTS_FILE, RUN_LOCK, RUN_STATUS,
                             RunLock, auto_cleanup, clean_up, cleanup_summary_text, engine_id, feature_signature,
                             prepare_cache,
                             result_card, results_document, save_profiles, scan_cleanup, size_text, write_results)

CURRENT = feature_signature(True, 12, .3, DEFAULT_YOLO_MODEL)
OTHER = feature_signature(True, 5, .5, DEFAULT_YOLO_MODEL)
OLD = 'f' * 64  # e.g. a row of ENGINE v4: neither recorded nor known
T1, T2, T3, T4 = ('1' * 24 + '.jpg', '2' * 24 + '.jpg', '3' * 24 + '.jpg', '4' * 24 + '.jpg')


def gallery(name, thumbs=(), folder='thumbnails'):
    imgs = ''.join(f'<article><img loading="lazy" src="{folder}/{t}" alt="x"></article>' for t in thumbs)
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            f'<title>FrameScout – {name}</title><style></style><main>{imgs}</main></html>')


def card(thumbnail, rank=1):
    return result_card(rank, Path('/photos/a.jpg'), 'a.jpg', 'Full image', 1.0, 0.3, None, 'Score +1.00', 'text',
                       thumbnail)


class Project:
    """A project folder: profiles.json, references/, photos/ and results/."""

    def __init__(self, base):
        self.base = base
        self.results = base / 'results'
        self.thumbs = self.results / 'thumbnails'
        self.legacy = self.results / 'vorschaubilder'
        self.refs = base / 'references'
        self.photos = base / 'photos'
        self.profiles = base / 'profiles.json'
        for folder in (self.thumbs, self.refs, self.photos):
            folder.mkdir(parents=True)
        self.set_profiles([{'name': 'Red car', 'reference_images': []}])

    def set_profiles(self, profiles):
        self.profiles.write_text(json.dumps({'profiles': profiles}), encoding='utf-8')

    def write_results(self, entries):
        """entries: [(name, gallery, [thumbnails])]"""
        profiles = [{'name': n, 'fingerprint': 'x', 'gallery': g, 'normalized': True,
                     'cards': [card(t, i) for i, t in enumerate(ts, 1)]} for n, g, ts in entries]
        write_results(self.results / RESULTS_FILE, results_document('s', 'f', [self.photos], {}, 1, profiles))

    def thumb(self, name, folder=None, data=b'jpg'):
        path = (folder or self.thumbs) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def page(self, file_name, title, thumbs=(), folder='thumbnails'):
        path = self.results / file_name
        path.write_text(gallery(title, thumbs, folder), encoding='utf-8')
        return path

    def cache(self, rows, recorded=()):
        """rows: [(path, signature)]; recorded: [(signature, engine)] in the signatures table."""
        con = sqlite3.connect(self.results / CACHE_FILE)
        prepare_cache(con, True, 12, .3, DEFAULT_YOLO_MODEL)
        con.execute('DELETE FROM signatures')
        for signature, engine in recorded:
            con.execute('INSERT INTO signatures VALUES (?,?,?)', (signature, engine, '{}'))
        for path, signature in rows:
            con.execute('INSERT INTO features VALUES (?,?,?,?,?,?)',
                        (str(path), signature, 1, 2, '["Full image"]', b'v' * 1000))
        con.commit()
        con.close()

    def rows(self):
        con = sqlite3.connect(self.results / CACHE_FILE)
        try:
            return sorted(con.execute('SELECT path, signature FROM features').fetchall())
        finally:
            con.close()

    def photo(self, name):
        path = self.photos / name
        path.write_bytes(b'photo')
        return path

    def scan(self, current=CURRENT, current_model=DEFAULT_MODEL, **options):
        return scan_cleanup(self.results, self.profiles, self.refs, current, current_model=current_model, **options)

    def clean(self, scan, selected, vacuum=False, alive=lambda pid, status: False, current=CURRENT,
              current_model=DEFAULT_MODEL, **options):
        return clean_up(self.results, scan, selected, vacuum, alive, self.profiles, self.refs, current,
                        current_model=current_model, **options)

    def marks(self, profiles):
        (self.results / MARKS_FILE).write_text(json.dumps({'format': 1, 'profiles': profiles}), encoding='utf-8')


@pytest.fixture
def project(tmp_path):
    return Project(tmp_path)


def temp_thumbnail(folder, name):
    # the name ensure_thumbnail's temporary file gets (via tempfile.mkstemp)
    fd, path = tempfile.mkstemp(dir=folder, prefix=name + '.', suffix='.jpg')
    os.close(fd)
    return Path(path)


# temporary thumbnails (E13)

def test_temporary_thumbnails_of_a_stopped_export_are_found(project):
    tmp = temp_thumbnail(project.thumbs, T1)
    project.thumb(T1)
    (project.thumbs / 'notes.txt').write_text('mine')
    scan = project.scan()
    assert scan['temp_thumbnails']['items'] == [tmp]
    assert scan['temp_thumbnails']['default'] is True


# galleries and thumbnails (E7, E23)

def test_orphaned_galleries_are_only_framescout_galleries_of_no_current_profile_or_result(project):
    project.set_profiles([{'name': 'Red car'}, {'name': 'Bär'}])
    project.write_results([('Old dog', 'old-dog.html', [])])
    project.page('red-car.html', 'Red car')  # gallery of a current profile
    project.page('baer.html', 'Bär')
    project.page('old-dog.html', 'Old dog')  # listed in results.json (E23)
    orphan = project.page('b-r.html', 'Bär')  # the old slug of "Bär" (A3)
    deleted = project.page('cat.html', 'Cat')  # a deleted profile
    (project.results / 'my-notes.html').write_text('<html><title>Notes</title></html>', encoding='utf-8')
    scan = project.scan()
    assert sorted(scan['galleries']['items']) == sorted([orphan, deleted])
    assert scan['galleries']['names'] == ['b-r.html', 'cat.html']
    assert scan['galleries']['size'] == orphan.stat().st_size + deleted.stat().st_size


def test_thumbnails_linked_from_results_or_kept_galleries_are_kept(project):
    project.write_results([('Red car', 'red-car.html', [T1])])
    project.page('red-car.html', 'Red car', [T1])
    project.page('blue-car.html', 'Blue car', [T2])  # orphaned gallery: its thumbnail goes with it
    # not a FrameScout gallery (no FrameScout title): kept, and so is its thumbnail
    (project.results / 'my-page.html').write_text(f'<html><img src="thumbnails/{T3}"></html>', encoding='utf-8')
    for name in (T1, T2, T3, T4):
        project.thumb(name)
    legacy_linked = project.thumb(T1, project.legacy)
    project.page('legacy.html', 'Red car', [T1], folder='vorschaubilder')  # orphaned, links the old folder
    legacy_free = project.thumb(T4, project.legacy)
    scan = project.scan()
    assert scan['thumbnails']['items'] == [project.thumbs / T4, legacy_free]
    # the thumbnails only orphaned galleries link belong to the galleries category (review)
    assert sorted(scan['galleries']['thumbnails']) == sorted([project.thumbs / T2, legacy_linked])
    assert scan['galleries']['thumbnails_size'] == 2 * len(b'jpg')
    assert scan['thumbnails']['default'] is True


def test_thumbnails_only_orphaned_galleries_link_are_not_a_thumbnail_item(project):
    # nothing to delete on its own: the category must not offer "0 files" (review)
    project.page('cat.html', 'Cat', [T2])
    project.thumb(T2)
    scan = project.scan()
    assert scan['thumbnails']['items'] == [] and scan['galleries']['thumbnails'] == [project.thumbs / T2]


def test_deleting_the_galleries_deletes_the_thumbnails_only_they_showed(project):
    project.page('cat.html', 'Cat', [T2])
    project.page('dog.html', 'Dog', [T3])
    project.thumb(T1)  # linked by nothing: a thumbnail item, not selected here
    project.thumb(T2)
    project.thumb(T3)
    scan = project.scan()
    shown = {**scan, 'galleries': {**scan['galleries'], 'items': [project.results / 'cat.html']}}  # dog.html unseen
    summary = project.clean(shown, {'galleries'})
    assert sorted(p.name for p in project.results.glob('*.html')) == ['dog.html']
    # dog.html stays, so its thumbnail stays although the scan listed it with the galleries
    assert sorted(p.name for p in project.thumbs.iterdir()) == [T1, T3]
    assert summary['files'] == 2


def test_galleries_and_thumbnails_are_not_offered_if_results_json_cannot_be_read(project):
    (project.results / RESULTS_FILE).write_text('{broken', encoding='utf-8')
    project.page('cat.html', 'Cat')
    project.thumb(T1)
    scan = project.scan()
    for key in ('galleries', 'thumbnails'):
        assert scan[key]['items'] == [] and RESULTS_FILE in scan[key]['problem']


@pytest.mark.parametrize('content', ['{broken', None])
def test_galleries_and_thumbnails_are_not_offered_without_readable_profiles(project, content):
    if content is None:
        project.profiles.unlink()
    else:
        project.profiles.write_text(content, encoding='utf-8')
    project.page('cat.html', 'Cat')
    project.thumb(T1)
    scan = project.scan()
    for key in ('galleries', 'thumbnails', 'references'):
        assert scan[key]['items'] == [] and 'profiles.json' in scan[key]['problem']


# cache rows (E7, E11)

def test_rows_of_photos_that_no_longer_exist_anywhere_are_unbound(project):
    # E8/A21 (user decision): a renamed, moved or deleted photo is "unbound", in whatever
    # folder it was; a photo of an earlier search's folder that still exists is not
    kept = project.photo('a.jpg')
    gone = project.photos / 'sub' / 'b.jpg'
    elsewhere = project.base / 'elsewhere'
    elsewhere.mkdir()
    earlier = elsewhere / 'c.jpg'  # another folder searched earlier: still there
    earlier.write_bytes(b'photo')
    moved = elsewhere / 'd.jpg'  # its photo was moved away
    vanished = project.base / 'renamed folder' / 'e.jpg'  # the whole folder was renamed
    project.cache([(kept, CURRENT), (gone, CURRENT), (gone, OLD), (earlier, CURRENT), (moved, OTHER),
                   (vanished, CURRENT)])
    scan = project.scan()
    assert sorted(scan['cache_missing']['items']) == sorted(
        [(str(gone), CURRENT), (str(gone), OLD), (str(moved), OTHER), (str(vanished), CURRENT)])
    assert scan['cache_missing']['rows'] == 4 and scan['cache_missing']['default'] is True
    assert scan['cache_missing']['problem'] is None and scan['cache_missing']['notes'] == []
    summary = project.clean(scan, {'cache_missing'})
    assert summary['rows'] == 4 and project.rows() == sorted([(str(kept), CURRENT), (str(earlier), CURRENT)])


def unreachable(*roots):
    """A _probe_root for the monkeypatch: the roots (normcased) are not reachable, every other root is."""
    from framescout_core import cleanup
    real = cleanup._probe_root
    keys = {os.path.normcase(root) for root in roots}
    return lambda root: False if os.path.normcase(root) in keys else real(root)


def root_of(path):
    return os.path.splitdrive(str(path))[0] + os.sep


def test_rows_on_a_root_that_is_not_reachable_are_not_checked(project, monkeypatch):
    # e.g. a disconnected USB disk or an offline network share: the photos are only offline
    from framescout_core import cleanup
    gone = project.photos / 'b.jpg'
    project.cache([(gone, CURRENT), (project.photos / 'c.jpg', OLD)])
    monkeypatch.setattr(cleanup, '_probe_root', unreachable(root_of(project.photos)))
    scan = project.scan()
    assert scan['cache_missing']['items'] == [] and scan['cache_missing']['problem'] is None
    notes = scan['cache_missing']['notes']
    assert len(notes) == 1 and root_of(project.photos) in notes[0] and '2 photos' in notes[0]
    assert 'not reachable' in notes[0]


def test_rows_whose_root_went_offline_since_the_scan_are_kept(project, monkeypatch):
    from framescout_core import cleanup
    gone = project.photos / 'b.jpg'
    project.cache([(gone, CURRENT)])
    scan = project.scan()
    assert scan['cache_missing']['items'] == [(str(gone), CURRENT)]
    monkeypatch.setattr(cleanup, '_probe_root', unreachable(root_of(project.photos)))
    summary = project.clean(scan, {'cache_missing'})
    assert summary['rows'] == 0 and project.rows() == [(str(gone), CURRENT)]


def test_a_root_that_goes_offline_during_the_check_is_not_checked(project, monkeypatch):
    # a share that drops during the pass makes its folders look missing: the root is
    # probed again for the paths found gone
    from framescout_core import cleanup
    project.cache([(project.photos / 'b.jpg', CURRENT)])
    answers = iter([True, False])
    monkeypatch.setattr(cleanup, '_probe_root', lambda root: next(answers))
    scan = project.scan()
    assert scan['cache_missing']['items'] == [] and len(scan['cache_missing']['notes']) == 1


@pytest.mark.skipif(os.name != 'nt', reason='drive letters are a Windows feature')
def test_rows_on_a_drive_letter_that_is_not_there_are_not_checked(project):
    free = [letter for letter in 'QRSTUVWXYZ' if not os.path.exists(letter + ':\\')]
    if not free:
        pytest.skip('every drive letter Q-Z is in use')
    offline = free[-1] + ':\\Photos\\a.jpg'
    project.cache([(offline, CURRENT), (project.photos / 'b.jpg', CURRENT)])
    scan = project.scan()
    assert scan['cache_missing']['items'] == [(str(project.photos / 'b.jpg'), CURRENT)]
    assert free[-1] + ':\\' in scan['cache_missing']['notes'][0]


def test_a_root_probe_that_hangs_counts_as_not_reachable(monkeypatch):
    # a stat on a disconnected network share can hang for a long time
    import threading
    import time
    from framescout_core import cleanup
    release = threading.Event()
    monkeypatch.setattr(cleanup, '_probe_root', lambda root: release.wait(5) or root == 'fast')
    start = time.monotonic()
    try:
        assert cleanup._reachable_roots(['slow', 'fast', 'slower'], timeout=0.2) == {
            'slow': False, 'fast': False, 'slower': False}
    finally:
        release.set()
    assert time.monotonic() - start < 2  # one timeout for all roots, not one per root
    monkeypatch.setattr(cleanup, '_probe_root', lambda root: root == 'up')
    assert cleanup._reachable_roots(['up', 'down'], timeout=1) == {'up': True, 'down': False}


def test_a_root_probe_that_still_hangs_gets_no_second_thread(monkeypatch):
    # every scan probes a dead share again: its hanging threads must not pile up (review)
    import threading
    from framescout_core import cleanup
    release, calls = threading.Event(), []
    monkeypatch.setattr(cleanup, '_probe_root', lambda root: calls.append(root) or release.wait(5))
    try:
        assert cleanup._reachable_roots(['dead share'], timeout=0.1) == {'dead share': False}
        assert cleanup._reachable_roots(['dead share'], timeout=0.1) == {'dead share': False}
        assert calls == ['dead share']
    finally:
        release.set()
    cleanup._PROBES['dead share'].thread.join(5)
    # the earlier probe has answered: the next call probes again
    monkeypatch.setattr(cleanup, '_probe_root', lambda root: calls.append(root) or True)
    assert cleanup._reachable_roots(['dead share'], timeout=1) == {'dead share': True}
    assert calls == ['dead share', 'dead share']


def test_a_folder_with_many_rows_is_listed_once(project, monkeypatch):
    # one listing per folder instead of one stat per photo (much faster on a network share)
    from framescout_core import cleanup
    names = [f'IMG_{n}.jpg' for n in range(10)]
    for name in names[:8]:
        project.photo(name)
    project.cache([(project.photos / name, CURRENT) for name in names])
    listed, stated = [], []
    real_listdir, real_missing = os.listdir, cleanup._missing
    monkeypatch.setattr(os, 'listdir', lambda path: listed.append(path) or real_listdir(path))
    monkeypatch.setattr(cleanup, '_missing', lambda path: stated.append(path) or real_missing(path))
    scan = project.scan()
    assert sorted(scan['cache_missing']['items']) == [(str(project.photos / n), CURRENT) for n in names[8:]]
    assert [os.path.normcase(p) for p in listed].count(os.path.normcase(str(project.photos))) == 1
    # a name the listing does not hold is confirmed by its own stat
    assert sorted(stated) == [str(project.photos / n) for n in names[8:]]


def test_many_names_a_listing_does_not_hold_need_only_a_few_stats(project, monkeypatch):
    # e.g. a folder whose 50,000 photos were moved away: the listing is trusted once a few
    # of the absent names are confirmed (review)
    from framescout_core import cleanup
    names = [f'IMG_{n:02}.jpg' for n in range(30)]
    project.photo(names[0])
    project.cache([(project.photos / name, CURRENT) for name in names])
    stated = []
    real = cleanup._missing
    monkeypatch.setattr(cleanup, '_missing', lambda path: stated.append(path) or real(path))
    assert project.scan()['cache_missing']['rows'] == 29
    assert len(stated) == cleanup._STAT_UP_TO


def test_a_listing_that_spells_names_differently_is_checked_by_a_stat_each(project, monkeypatch):
    # e.g. another Unicode normalization: a confirmed name exists, so no absent name is trusted
    names = [f'IMG_{n:02}.jpg' for n in range(10)]
    for name in names:
        project.photo(name)
    project.cache([(project.photos / name, CURRENT) for name in names])
    real = os.listdir

    def listdir(path):
        found = real(path)
        if os.path.normcase(str(path)) == os.path.normcase(str(project.photos)):
            return [name.replace('IMG', 'img_x') for name in found]
        return found

    monkeypatch.setattr(os, 'listdir', listdir)
    assert project.scan()['cache_missing']['items'] == []


@pytest.mark.skipif(os.name != 'nt', reason='Windows file names ignore case')
def test_a_listed_name_of_another_case_exists(project):
    names = [f'IMG_{n}.jpg' for n in range(6)]
    for name in names:
        project.photo(name)
    project.cache([(project.photos / name.upper(), CURRENT) for name in names])
    assert project.scan()['cache_missing']['items'] == []


def test_rows_of_a_whole_missing_folder_need_no_stat_each(project, monkeypatch):
    from framescout_core import cleanup
    gone = project.base / 'renamed' / 'event'
    project.cache([(gone / f'IMG_{n}.jpg', CURRENT) for n in range(10)])
    stated = []
    real = cleanup._missing
    monkeypatch.setattr(cleanup, '_missing', lambda path: stated.append(path) or real(path))
    assert project.scan()['cache_missing']['rows'] == 10
    assert stated == []


def test_rows_of_a_folder_that_cannot_be_listed_are_kept(project, monkeypatch):
    # e.g. no permission: nothing tells that the photos are gone
    names = [f'IMG_{n}.jpg' for n in range(6)]
    project.cache([(project.photos / name, CURRENT) for name in names])
    real = os.listdir

    def listdir(path):
        if os.path.normcase(str(path)) == os.path.normcase(str(project.photos)):
            raise PermissionError('access denied')
        return real(path)

    monkeypatch.setattr(os, 'listdir', listdir)
    assert project.scan()['cache_missing']['items'] == []


def test_a_relative_path_is_never_unbound(project):
    project.cache([('relative\\a.jpg' if os.name == 'nt' else 'relative/a.jpg', CURRENT), ('', CURRENT)])
    assert project.scan()['cache_missing']['items'] == []


def test_the_check_reports_its_progress_once_for_rows_and_marks(project):
    project.cache([(project.base / f'folder {n}' / 'a.jpg', CURRENT) for n in range(3)])
    project.marks({'Red car': {str(project.base / 'folder 3' / 'a.jpg'): 'match'}})
    seen = []
    project.scan(progress=lambda done, total: seen.append((done, total)))
    # one pass over the folders of the cache rows and of the marks together
    assert seen[-1] == (4, 4) and all(0 <= done <= total == 4 for done, total in seen)


# marks of photos that no longer exist (E8/A21)

def test_marks_of_photos_that_no_longer_exist_are_offered_unselected(project):
    kept = project.photo('a.jpg')
    gone = project.photos / 'b.jpg'
    relative = 'c.jpg'  # not an absolute path: never checked
    project.marks({'Red car': {str(kept): 'match', str(gone): 'no-match', relative: 'match'},
                   'Dog': {str(gone): 'match'}})
    scan = project.scan()
    category = scan['marks_unbound']
    assert category['items'] == [('Dog', str(gone)), ('Red car', str(gone))]
    assert category['default'] is False and category['problem'] is None and category['notes'] == []
    assert category['names'] == [f'Dog: {gone}', f'Red car: {gone}']


def test_marks_on_a_root_that_is_not_reachable_are_not_offered(project, monkeypatch):
    from framescout_core import cleanup
    project.marks({'Red car': {str(project.photos / 'b.jpg'): 'match'}})
    monkeypatch.setattr(cleanup, '_probe_root', unreachable(root_of(project.photos)))
    category = project.scan()['marks_unbound']
    assert category['items'] == [] and len(category['notes']) == 1 and '1 photo ' in category['notes'][0]


def test_no_or_an_unreadable_marks_file(project):
    assert project.scan()['marks_unbound']['items'] == []
    assert not (project.results / MARKS_FILE).exists()  # the scan creates no marks file
    (project.results / MARKS_FILE).write_text('{broken', encoding='utf-8')
    category = project.scan()['marks_unbound']
    assert category['items'] == [] and MARKS_FILE in category['problem']
    summary = project.clean({**project.scan(), 'marks_unbound': {**category, 'items': [('Red car', 'x')]}},
                            {'marks_unbound'})
    assert (project.results / MARKS_FILE).read_text(encoding='utf-8') == '{broken'
    assert summary['marks'] == 0 and MARKS_FILE in ' '.join(summary['skipped'])


def test_deleting_unbound_marks_removes_only_those_entries(project):
    kept = project.photo('a.jpg')
    gone, back = project.photos / 'b.jpg', project.photos / 'c.jpg'
    project.marks({'Red car': {str(kept): 'match', str(gone): 'no-match', str(back): 'match'},
                   'Dog': {str(gone): 'match'}})
    scan = project.scan()
    assert len(scan['marks_unbound']['items']) == 3
    project.photo('c.jpg')  # back since the scan: its mark stays
    late = project.photos / 'd.jpg'  # unbound, but not shown by the scan
    from framescout_core import save_marks
    save_marks(project.results / MARKS_FILE, 'Dog', {str(late): 'no-match'})
    summary = project.clean(scan, {'marks_unbound'})
    assert summary['marks'] == 2 and summary['files'] == 0
    assert json.loads((project.results / MARKS_FILE).read_text(encoding='utf-8'))['profiles'] == {
        'Red car': {str(kept): 'match', str(back): 'match'}, 'Dog': {str(late): 'no-match'}}


def test_unbound_marks_are_kept_unless_selected(project):
    gone = project.photos / 'b.jpg'
    project.marks({'Red car': {str(gone): 'match'}})
    project.cache([(gone, CURRENT)])
    scan = project.scan()
    summary = project.clean(scan, {'cache_missing'})
    assert summary['rows'] == 1 and summary['marks'] == 0
    assert json.loads((project.results / MARKS_FILE).read_text(encoding='utf-8'))['profiles'] == {
        'Red car': {str(gone): 'match'}}


def test_rows_of_old_engines_and_other_settings(project):
    photo = project.photo('a.jpg')
    cli = 'c' * 64  # e.g. another --yolo-model, recorded by the engine of this version
    recorded_old = 'd' * 64
    project.cache([(photo, CURRENT), (photo, OTHER), (photo, OLD), (photo, cli), (photo, recorded_old)],
                  recorded=[(cli, ENGINE), (recorded_old, 'v4-old')])
    scan = project.scan()
    assert sorted(scan['cache_old']['items']) == sorted([OLD, recorded_old])
    assert scan['cache_old']['rows'] == 2 and scan['cache_old']['default'] is True
    assert sorted(scan['cache_other']['items']) == sorted([OTHER, cli])
    assert scan['cache_other']['rows'] == 2 and scan['cache_other']['default'] is False
    assert scan['cache_old']['size'] > 0


def test_rows_of_other_search_models_are_kept_by_default(project):
    # E22: switching back to a model reuses its rows, so they are offered unselected
    photo = project.photo('a.jpg')
    b16 = feature_signature(True, 12, .3, DEFAULT_YOLO_MODEL, model='vit-b-16-datacomp')
    l14 = feature_signature(False, 12, .3, DEFAULT_YOLO_MODEL, model='vit-l-14-datacomp')
    project.cache([(photo, CURRENT), (photo, OTHER), (photo, b16), (photo, l14)],
                  recorded=[(b16, engine_id('vit-b-16-datacomp')), (l14, engine_id('vit-l-14-datacomp'))])
    scan = project.scan()
    assert sorted(scan['cache_models']['items']) == sorted([b16, l14])
    assert scan['cache_models']['rows'] == 2 and scan['cache_models']['default'] is False
    assert scan['cache_old']['items'] == [] and scan['cache_other']['items'] == [OTHER]
    summary = project.clean(scan, {'cache_models'})
    assert summary['rows'] == 2 and project.rows() == sorted([(str(photo), CURRENT), (str(photo), OTHER)])


def test_with_another_model_chosen_the_default_rows_are_another_model(project):
    photo = project.photo('a.jpg')
    b16 = feature_signature(True, 12, .3, DEFAULT_YOLO_MODEL, model='vit-b-16-datacomp')
    b16_other = feature_signature(True, 5, .5, DEFAULT_YOLO_MODEL, model='vit-b-16-datacomp')
    # CURRENT and OTHER: rows of the default model, OTHER written before the side table
    project.cache([(photo, CURRENT), (photo, OTHER), (photo, b16), (photo, b16_other)],
                  recorded=[(CURRENT, ENGINE), (b16_other, engine_id('vit-b-16-datacomp'))])
    scan = project.scan(current=b16, current_model='vit-b-16-datacomp')
    assert sorted(scan['cache_models']['items']) == sorted([CURRENT, OTHER])
    assert scan['cache_other']['items'] == [b16_other] and scan['cache_old']['items'] == []
    # the deletion classifies again with the same model
    summary = project.clean(scan, {'cache_models', 'cache_other'}, current=b16, current_model='vit-b-16-datacomp')
    assert summary['rows'] == 3 and project.rows() == [(str(photo), b16)]


def test_the_search_model_must_be_named(project):
    # E22 review: the signature alone does not tell the model, and a default would sort the
    # rows of a non-default signature into the wrong categories without an error
    with pytest.raises(TypeError, match='current_model'):
        scan_cleanup(project.results, project.profiles, project.refs, CURRENT)
    scan = project.scan()
    with pytest.raises(TypeError, match='current_model'):
        clean_up(project.results, scan, set(), False, lambda pid, status: False, project.profiles, project.refs,
                 CURRENT)


def test_no_cache_means_nothing_to_clean(project):
    scan = project.scan()
    for key in ('cache_missing', 'cache_old', 'cache_other', 'cache_models'):
        assert scan[key]['items'] == [] and scan[key]['problem'] is None
    assert not (project.results / CACHE_FILE).exists()  # the scan creates no cache


def test_an_unreadable_cache_is_not_offered(project):
    (project.results / CACHE_FILE).write_bytes(b'not a database' * 100)
    scan = project.scan()
    for key in ('cache_missing', 'cache_old', 'cache_other', 'cache_models'):
        assert scan[key]['items'] == [] and CACHE_FILE in scan[key]['problem']


# reference images (A14)

def test_reference_files_no_profile_or_backup_references(project):
    used = project.refs / 'red-car' / 'reference-1.jpg'
    backup = project.refs / 'red-car' / 'reference-2.jpg'
    leftover = project.refs / 'cat' / 'reference-1.png'
    for path in (used, backup, leftover):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'image')
    (project.refs / 'cat' / 'desktop.ini').write_text('x')  # not an image: never offered
    project.set_profiles([{'name': 'Red car', 'reference_images': ['references/red-car/reference-2.jpg']}])
    save_profiles(project.profiles, [{'name': 'Red car', 'reference_images': ['references/red-car/reference-1.jpg']}])
    scan = project.scan()
    assert scan['references']['items'] == [leftover]
    assert scan['references']['names'] == [str(Path('cat') / 'reference-1.png')]
    assert scan['references']['default'] is False


def test_references_are_not_offered_if_the_backup_cannot_be_read(project):
    (project.refs / 'x.jpg').write_bytes(b'image')
    (project.base / 'profiles.json.bak').write_text('{broken', encoding='utf-8')
    scan = project.scan()
    assert scan['references']['items'] == [] and 'profiles.json.bak' in scan['references']['problem']


# deleting

def everything(scan):
    return set(scan)


def test_a_full_cleanup_never_deletes_user_data_and_run_files(project):
    keep = {name: project.results / name for name in
            (MARKS_FILE, MARKS_FILE + '.lock', RUN_LOCK, RUN_STATUS, RESULTS_FILE)}
    project.write_results([('Red car', 'red-car.html', [T1])])
    for name in (MARKS_FILE + '.lock', RUN_LOCK):
        (project.results / name).write_bytes(b'')
    (project.results / RUN_STATUS).write_text('{"phase": "finished", "pid": 1}', encoding='utf-8')
    (project.base / 'settings.json').write_text('{}', encoding='utf-8')
    project.page('red-car.html', 'Red car', [T1])
    project.page('cat.html', 'Cat', [T2])
    project.thumb(T1)
    project.thumb(T2)
    project.thumb(T3, project.legacy)
    temp_thumbnail(project.thumbs, T4)
    photo = project.photo('a.jpg')
    project.cache([(photo, CURRENT), (photo, OLD), (photo, OTHER), (project.photos / 'gone.jpg', CURRENT)])
    # the only mark is unbound: the entry goes, the file stays
    project.marks({'Red car': {str(project.photos / 'gone.jpg'): 'match'}})
    (project.refs / 'old.jpg').write_bytes(b'image')
    scan = project.scan()
    summary = project.clean(scan, everything(scan), vacuum=True)
    assert summary['refused'] is None and summary['failed'] == []
    for path in keep.values():
        assert path.exists(), path.name
    assert json.loads(keep[MARKS_FILE].read_text(encoding='utf-8')) == {'format': 1, 'profiles': {}}
    assert summary['marks'] == 1
    assert (project.base / 'settings.json').exists() and project.profiles.exists()
    assert sorted(p.name for p in project.results.iterdir()) == sorted(
        [*keep, CACHE_FILE, 'red-car.html', 'thumbnails'])
    assert [p.name for p in project.thumbs.iterdir()] == [T1]
    assert not project.legacy.exists()  # emptied, and no kept gallery links it
    assert project.rows() == [(str(photo), CURRENT)]
    assert list(project.refs.iterdir()) == []
    assert summary['files'] == 5 and summary['rows'] == 3
    assert summary['freed'] > 0


def test_only_selected_categories_are_deleted(project):
    project.page('cat.html', 'Cat', [T2])
    project.thumb(T1)
    project.thumb(T2)
    scan = project.scan()
    summary = project.clean(scan, {'thumbnails'})
    # the orphaned gallery stays, and with it its thumbnail
    assert (project.results / 'cat.html').exists()
    assert sorted(p.name for p in project.thumbs.iterdir()) == [T2]
    assert summary['files'] == 1


def test_only_what_the_scan_showed_is_deleted(project):
    project.thumb(T1)
    (project.refs / 'a.jpg').write_bytes(b'image')
    scan = project.scan()
    project.thumb(T2)  # appeared after the scan: the user has not seen it
    project.page('cat.html', 'Cat')
    (project.refs / 'b.jpg').write_bytes(b'image')
    project.set_profiles([{'name': 'Red car', 'reference_images': ['references/a.jpg']}])  # now in use
    project.clean(scan, everything(scan))
    assert sorted(p.name for p in project.thumbs.iterdir()) == [T2]
    assert (project.results / 'cat.html').exists()
    # profiles.json is read again before deleting: a reference added since is kept
    assert sorted(p.name for p in project.refs.iterdir()) == ['a.jpg', 'b.jpg']


def test_a_thumbnail_a_kept_gallery_links_since_the_scan_is_kept(project):
    project.thumb(T1)
    scan = project.scan()
    project.page('red-car.html', 'Red car', [T1])
    project.clean(scan, {'thumbnails'})
    assert (project.thumbs / T1).exists()


def test_cache_rows_of_a_photo_that_is_back_are_kept(project):
    gone = project.photos / 'b.jpg'
    project.cache([(gone, CURRENT)])
    scan = project.scan()
    project.photo('b.jpg')
    summary = project.clean(scan, {'cache_missing'})
    assert project.rows() == [(str(gone), CURRENT)] and summary['rows'] == 0


def test_vacuum_shrinks_the_cache_file(project):
    photo = project.photo('a.jpg')
    project.cache([(project.photos / f'{i}.jpg', OLD) for i in range(300)] + [(photo, CURRENT)])
    before = (project.results / CACHE_FILE).stat().st_size
    summary = project.clean(project.scan(), {'cache_old'}, vacuum=True)
    assert summary['rows'] == 300
    assert (project.results / CACHE_FILE).stat().st_size < before
    assert summary['freed'] >= before - (project.results / CACHE_FILE).stat().st_size


def test_the_cleanup_is_refused_while_a_search_runs(project):
    project.thumb(T1)
    scan = project.scan()
    lock = RunLock(project.results / RUN_LOCK)
    assert lock.acquire()
    try:
        summary = project.clean(scan, everything(scan))
    finally:
        lock.release()
    assert summary['refused'] and (project.thumbs / T1).exists()


def test_the_cleanup_is_refused_while_a_search_is_being_started(project):
    project.thumb(T1)
    (project.results / RUN_STATUS).write_text(json.dumps({'phase': 'starting', 'pid': 4242}), encoding='utf-8')
    scan = project.scan()
    summary = project.clean(scan, everything(scan), alive=lambda pid, status: pid == 4242)
    assert summary['refused'] and (project.thumbs / T1).exists()


def test_a_search_cannot_take_the_lock_during_the_cleanup(project, monkeypatch):
    import framescout_core
    project.thumb(T1)
    scan = project.scan()
    held = []
    real = framescout_core.cleanup._remove_file

    def remove(path, summary):
        held.append(not RunLock(project.results / RUN_LOCK).acquire())
        return real(path, summary)

    monkeypatch.setattr(framescout_core.cleanup, '_remove_file', remove)
    project.clean(scan, {'thumbnails'})
    assert held == [True]
    lock = RunLock(project.results / RUN_LOCK)
    assert lock.acquire()  # released afterwards
    lock.release()


# the engine's automatic cleanup (E13, unreferenced thumbnails)

def test_auto_cleanup_removes_temporary_and_unreferenced_thumbnails(project):
    project.write_results([('Red car', 'red-car.html', [T1])])
    project.page('red-car.html', 'Red car', [T1])
    project.page('cat.html', 'Cat', [T2])  # every gallery counts as kept here
    for name in (T1, T2, T3):
        project.thumb(name)
    temp_thumbnail(project.thumbs, T4)
    project.thumb(T3, project.legacy)
    (project.thumbs / 'notes.txt').write_text('mine')
    removed = auto_cleanup(project.results)
    assert sorted(p.name for p in project.thumbs.iterdir()) == sorted([T1, T2, 'notes.txt'])
    assert not project.legacy.exists()
    assert removed['files'] == 3
    assert (project.results / 'cat.html').exists()


def test_auto_cleanup_keeps_thumbnails_if_results_json_cannot_be_read(project):
    (project.results / RESULTS_FILE).write_text('{broken', encoding='utf-8')
    project.thumb(T1)
    temp_thumbnail(project.thumbs, T2)
    removed = auto_cleanup(project.results)
    assert [p.name for p in project.thumbs.iterdir()] == [T1]
    assert removed['files'] == 1 and removed['skipped']


def test_auto_cleanup_without_thumbnail_folder(tmp_path):
    assert auto_cleanup(tmp_path)['files'] == 0


# texts

def test_size_text():
    assert size_text(0) == '0 B'
    assert size_text(2048) == '2 KB'
    assert size_text(5 * 1024 ** 2 + 300 * 1024) == '5.3 MB'
    assert size_text(3 * 1024 ** 3) == '3.0 GB'


def test_cleanup_summary_text():
    text = cleanup_summary_text({'refused': None, 'files': 3, 'rows': 1200, 'freed': 2048, 'compacted': True,
                                 'failed': [('a.jpg', 'in use')], 'skipped': []})
    assert text == 'Deleted 3 files and 1,200 cache entries · 2 KB freed · 1 could not be deleted'
    assert cleanup_summary_text({'refused': None, 'files': 1, 'rows': 0, 'freed': 0, 'compacted': False,
                                 'failed': [], 'skipped': []}) == 'Deleted 1 file and 0 cache entries · 0 B freed'
    # without compacting, deleted rows free nothing on disk: said instead of a bare "0 B freed" (review)
    assert cleanup_summary_text({'refused': None, 'files': 0, 'rows': 1, 'freed': 0, 'compacted': False,
                                 'failed': [], 'skipped': []}) == (
        'Deleted 0 files and 1 cache entry · 0 B freed; cache.sqlite3 was not compacted, so it keeps its size and '
        'reuses the space for new analyses')
    assert cleanup_summary_text({'refused': None, 'files': 2, 'rows': 0, 'marks': 1, 'freed': 10,
                                 'compacted': False, 'failed': [], 'skipped': []}) == (
        'Deleted 2 files, 0 cache entries and 1 mark · 10 B freed')


def test_rows_deleted_without_compacting_are_reported_as_not_compacted(project):
    project.cache([(project.photos / 'gone.jpg', OLD)])
    summary = project.clean(project.scan(), {'cache_old'}, vacuum=False)
    assert summary['rows'] == 1 and summary['compacted'] is False and summary['freed'] == 0
    summary = project.clean(project.scan(), {'cache_old'}, vacuum=True)
    assert summary['rows'] == 0 and summary['compacted'] is False  # nothing left to delete: no VACUUM


# the read-only cache URI (review)

def make_db(path):
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE t (x)')
    con.commit()
    con.close()


def test_the_read_only_uri_opens_a_path_with_special_characters(tmp_path):
    from framescout_core.cleanup import _read_only_uri
    path = tmp_path / 'a b#%?.sqlite3' if os.name != 'nt' else tmp_path / 'a b#%;.sqlite3'
    make_db(path)
    con = sqlite3.connect(_read_only_uri(path), uri=True)
    try:
        assert con.execute('SELECT COUNT(*) FROM t').fetchone() == (0,)
        with pytest.raises(sqlite3.OperationalError):
            con.execute('INSERT INTO t VALUES (1)')  # read-only
    finally:
        con.close()


@pytest.mark.skipif(os.name != 'nt', reason='UNC paths are a Windows feature')
def test_the_read_only_uri_opens_a_unc_path(tmp_path):
    # FrameScout run from a network share: Path.as_uri() would give the URI a host authority
    from framescout_core.cleanup import _read_only_uri
    path = tmp_path.resolve() / 'cache.sqlite3'
    make_db(path)
    unc = Path('//localhost/' + str(path)[0] + '$' + str(path)[2:])  # \\localhost\C$\...
    if not unc.is_file():
        pytest.skip('the administrative share of drive C on localhost is not available here')
    con = sqlite3.connect(_read_only_uri(unc), uri=True)
    try:
        assert con.execute('SELECT COUNT(*) FROM t').fetchone() == (0,)
    finally:
        con.close()


def test_each_photo_is_looked_at_once_however_many_signatures_it_has(project, monkeypatch):
    import framescout_core
    gone = project.photos / 'b.jpg'
    project.cache([(gone, CURRENT), (gone, OTHER), (gone, OLD)])
    calls = []
    real = framescout_core.cleanup._missing
    monkeypatch.setattr(framescout_core.cleanup, '_missing', lambda path: calls.append(path) or real(path))
    assert project.scan()['cache_missing']['rows'] == 3
    assert calls == [str(gone)]


def test_a_scan_reads_profiles_and_galleries_once(project, monkeypatch):
    # review: profiles.json was parsed twice and every gallery scanned twice per scan
    import framescout_core
    project.page('cat.html', 'Cat', [T2])
    project.page('red-car.html', 'Red car', [T1])
    calls = []
    for name in ('read_profiles', '_gallery_links'):
        real = getattr(framescout_core.cleanup, name)
        monkeypatch.setattr(framescout_core.cleanup, name,
                            lambda *args, real=real, name=name: calls.append(name) or real(*args))
    project.scan()
    assert sorted(calls) == ['_gallery_links', '_gallery_links', 'read_profiles']


def test_an_error_in_one_step_keeps_the_summary_of_what_was_deleted(project, monkeypatch):
    # review: a PermissionError while listing a folder must not lose the count of what is gone
    import framescout_core
    project.thumb(T1)
    (project.refs / 'old.jpg').write_bytes(b'image')
    project.cache([(project.photos / 'gone.jpg', OLD)])
    scan = project.scan()

    def broken(*args, **kwargs):
        raise PermissionError('access denied')

    monkeypatch.setattr(framescout_core.cleanup, '_unreferenced_references', broken)
    summary = project.clean(scan, everything(scan))
    assert summary['files'] == 1 and summary['rows'] == 1
    assert summary['skipped'] == ['Reference images: stopped (access denied).']
    assert (project.refs / 'old.jpg').exists()
    lock = RunLock(project.results / RUN_LOCK)
    assert lock.acquire()  # released
    lock.release()


def test_cleanup_running_while_clean_up_holds_the_lock(project, monkeypatch):
    # other tabs (threads of the same process) tell the cleanup from a search by it (review)
    import framescout_core
    project.thumb(T1)
    scan = project.scan()
    seen = []
    real = framescout_core.cleanup._remove_file

    def remove(path, summary):
        seen.append(framescout_core.cleanup_running(project.results))
        return real(path, summary)

    monkeypatch.setattr(framescout_core.cleanup, '_remove_file', remove)
    assert not framescout_core.cleanup_running(project.results)
    project.clean(scan, {'thumbnails'})
    assert seen == [True]
    assert not framescout_core.cleanup_running(project.results)
