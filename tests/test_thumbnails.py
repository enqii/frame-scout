"""Gallery thumbnails of the HTML export (framescout_core.ensure_thumbnail, E6)."""
import os
import shutil
from pathlib import Path

import framescout_core
from framescout_core import SkippedPhotos, ensure_thumbnail, gallery_cards, thumbnail_name


def make_photo(folder, name='photo.jpg', mtime_ns=1_700_000_000_000_000_000):
    path = folder / name
    path.write_bytes(b'photo')
    os.utime(path, ns=(mtime_ns, mtime_ns))
    return path


def renderer(calls):
    def render(path, target):
        calls.append((path, target))
        target.write_bytes(b'thumbnail')
    return render


def test_the_thumbnail_name_is_unchanged_so_existing_thumbnails_stay_valid():
    # the engine has always named thumbnails sha256(str(path) + str(mtime_ns))[:24] + '.jpg'
    assert thumbnail_name(r'C:\photos\a.jpg', 1_700_000_000_000_000_000) == '1c6b57780fa2df6f925b878c.jpg'


def test_a_missing_thumbnail_is_rendered(tmp_path):
    photo = make_photo(tmp_path)
    thumbs = tmp_path / 'thumbnails'
    thumbs.mkdir()
    calls, log = [], []
    name = ensure_thumbnail(photo, thumbs, tmp_path / 'vorschaubilder', renderer(calls), log.append)
    assert name == thumbnail_name(photo, photo.stat().st_mtime_ns)
    # rendered to a temporary .jpg in the same folder, then renamed (review)
    [(rendered, target)] = calls
    assert rendered == photo and target.parent == thumbs and target.suffix == '.jpg'
    assert [p.name for p in thumbs.iterdir()] == [name]
    assert (thumbs / name).read_bytes() == b'thumbnail'
    assert log == []


def test_an_existing_thumbnail_is_not_rendered_again(tmp_path):
    photo = make_photo(tmp_path)
    thumbs = tmp_path / 'thumbnails'
    thumbs.mkdir()
    name = thumbnail_name(photo, photo.stat().st_mtime_ns)
    (thumbs / name).write_bytes(b'existing')
    calls = []
    assert ensure_thumbnail(photo, thumbs, tmp_path / 'vorschaubilder', renderer(calls), print) == name
    assert calls == []
    assert (thumbs / name).read_bytes() == b'existing'


def test_a_thumbnail_of_an_older_version_is_copied_and_left_in_place(tmp_path):
    photo = make_photo(tmp_path)
    thumbs, legacy = tmp_path / 'thumbnails', tmp_path / 'vorschaubilder'
    thumbs.mkdir()
    legacy.mkdir()
    name = thumbnail_name(photo, photo.stat().st_mtime_ns)
    (legacy / name).write_bytes(b'old thumbnail')
    calls = []
    assert ensure_thumbnail(photo, thumbs, legacy, renderer(calls), print) == name
    assert calls == []
    assert (thumbs / name).read_bytes() == b'old thumbnail'
    assert (legacy / name).read_bytes() == b'old thumbnail'


def test_a_photo_deleted_after_scoring_is_skipped_instead_of_aborting_the_export(tmp_path):
    # E6: the photo was scored, then deleted or moved before its gallery card is written
    photo = tmp_path / 'deleted.jpg'
    thumbs = tmp_path / 'thumbnails'
    thumbs.mkdir()
    calls, log = [], []
    assert ensure_thumbnail(photo, thumbs, tmp_path / 'vorschaubilder', renderer(calls), log.append) is None
    assert calls == []
    assert len(log) == 1 and log[0].startswith(f'Thumbnail not possible ({photo}): ')


def test_an_interrupted_render_leaves_no_thumbnail_that_later_runs_would_reuse(tmp_path):
    # review: a half-written thumbnail under the final name passed the exists() check of
    # every later export, so the gallery kept showing a broken image
    photo = make_photo(tmp_path)
    thumbs = tmp_path / 'thumbnails'
    thumbs.mkdir()

    def render(path, target):
        assert target.suffix == '.jpg'  # Pillow picks the format from the extension
        target.write_bytes(b'half')
        raise OSError('No space left on device')

    log = []
    assert ensure_thumbnail(photo, thumbs, tmp_path / 'vorschaubilder', render, log.append) is None
    assert list(thumbs.iterdir()) == []
    calls = []
    name = ensure_thumbnail(photo, thumbs, tmp_path / 'vorschaubilder', renderer(calls), log.append)
    assert calls and (thumbs / name).read_bytes() == b'thumbnail'


def test_an_interrupted_copy_of_an_old_thumbnail_leaves_nothing_behind(tmp_path, monkeypatch):
    photo = make_photo(tmp_path)
    thumbs, legacy = tmp_path / 'thumbnails', tmp_path / 'vorschaubilder'
    thumbs.mkdir()
    legacy.mkdir()
    name = thumbnail_name(photo, photo.stat().st_mtime_ns)
    (legacy / name).write_bytes(b'old thumbnail')

    def copyfile(src, dst):
        Path(dst).write_bytes(b'old')
        raise OSError('I/O error')

    monkeypatch.setattr(shutil, 'copyfile', copyfile)
    log = []
    assert ensure_thumbnail(photo, thumbs, legacy, renderer([]), log.append) is None
    assert list(thumbs.iterdir()) == []
    assert (legacy / name).read_bytes() == b'old thumbnail'


def test_a_photo_that_cannot_be_rendered_is_skipped(tmp_path):
    photo = make_photo(tmp_path)
    thumbs = tmp_path / 'thumbnails'
    thumbs.mkdir()

    def render(path, target):
        raise ValueError('cannot identify image file')

    log = []
    assert ensure_thumbnail(photo, thumbs, tmp_path / 'vorschaubilder', render, log.append) is None
    assert log == [f'Thumbnail not possible ({photo}): cannot identify image file']


def test_gallery_cards_rank_only_photos_with_a_thumbnail_and_fill_up_to_top():
    # a skipped photo leaves no gap in the ranks, and lower-ranked photos fill up (E12)
    tried = []

    def thumbnail(photo):
        tried.append(photo)
        return None if photo in ('b', 'd') else photo + '.jpg'

    cards = list(gallery_cards(['a', 'b', 'c', 'd', 'e', 'f'], 3, thumbnail))
    assert cards == [(1, 'a', 'a.jpg'), (2, 'c', 'c.jpg'), (3, 'e', 'e.jpg')]
    assert tried == ['a', 'b', 'c', 'd', 'e']  # stops as soon as the gallery is full


def test_gallery_cards_show_fewer_cards_when_too_few_photos_have_a_thumbnail():
    cards = list(gallery_cards(['a', 'b', 'c'], 5, lambda photo: None if photo == 'a' else photo + '.jpg'))
    assert cards == [(1, 'b', 'b.jpg'), (2, 'c', 'c.jpg')]
    assert list(gallery_cards([], 5, lambda photo: 'x.jpg')) == []


def test_a_skipped_photo_is_tried_and_logged_once_per_export(tmp_path):
    # a photo that ranks in several galleries is not decoded and logged again (review of E12)
    thumbs = tmp_path / 'thumbnails'
    thumbs.mkdir()
    good, missing = make_photo(tmp_path, 'good.jpg'), tmp_path / 'missing.jpg'
    calls, log = [], []
    skipped = SkippedPhotos(log.append)
    for _ in range(3):
        assert skipped.thumbnail(missing, thumbs, tmp_path / 'vorschaubilder', renderer(calls)) is None
        assert skipped.thumbnail(good, thumbs, tmp_path / 'vorschaubilder', renderer(calls)) == \
            thumbnail_name(good, good.stat().st_mtime_ns)
    assert len(log) == 1 and log[0].startswith(f'Thumbnail not possible ({missing}): ')
    assert [path for path, _ in calls] == [good]
    assert skipped.summary() is None


def test_only_the_first_skipped_photos_are_logged_then_a_summary(tmp_path):
    # a vanished photo folder must not flood run.log with one line per photo and gallery
    thumbs = tmp_path / 'thumbnails'
    thumbs.mkdir()
    log = []
    skipped = SkippedPhotos(log.append, limit=2)
    for name in ('a.jpg', 'b.jpg', 'c.jpg', 'd.jpg'):
        assert skipped.thumbnail(tmp_path / name, thumbs, tmp_path / 'vorschaubilder', renderer([])) is None
    assert [line.split(': ')[0] for line in log] == [f'Thumbnail not possible ({tmp_path / "a.jpg"})',
                                                    f'Thumbnail not possible ({tmp_path / "b.jpg"})']
    assert skipped.summary() == ('4 photos got no thumbnail and are left out of the galleries; '
                                 'only the first 2 are listed above.')
