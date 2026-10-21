"""Gallery thumbnails of the HTML export (framescout_core.ensure_thumbnail, E6)."""
import os

from framescout_core import ensure_thumbnail, thumbnail_name


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
    assert calls == [(photo, thumbs / name)]
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


def test_a_photo_that_cannot_be_rendered_is_skipped(tmp_path):
    photo = make_photo(tmp_path)
    thumbs = tmp_path / 'thumbnails'
    thumbs.mkdir()

    def render(path, target):
        raise ValueError('cannot identify image file')

    log = []
    assert ensure_thumbnail(photo, thumbs, tmp_path / 'vorschaubilder', render, log.append) is None
    assert log == [f'Thumbnail not possible ({photo}): cannot identify image file']
