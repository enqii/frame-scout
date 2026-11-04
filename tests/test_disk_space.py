"""Free disk space checks before installing PyTorch and before a search (F3); no real drive is filled."""
import os
import sqlite3
from collections import namedtuple
from pathlib import Path

import pytest

from framescout_core import disk_space
from framescout_core import (CACHE_BYTES_PER_PHOTO, DETECTOR_DOWNLOAD, MODELS, OTHER_PACKAGES_SPACE, SPACE_RESERVE, THUMBNAIL_BYTES,
                             TORCH_INSTALL_SPACE, LowSpace, analyzed_photos, app_search_needs, download_bytes,
                             downloaded_models, eval_run_needs, low_space, low_space_lines,
                             search_space_bytes, search_space_needs, torch_install_needs)

MB, GB = 1024 ** 2, 1024 ** 3  # the units of disk_space and size_text (review)
Usage = namedtuple('Usage', 'total used free')
Stat = namedtuple('Stat', 'st_dev')


class Drives:
    """Stands in for shutil.disk_usage and os.stat: folders under a known root are on its drive."""

    def __init__(self, **roots):
        # roots: name -> (root folder, free bytes[, device number[, total bytes]]); by default
        # the device number is the name and the total 1000 GB
        defaults = {name: (name, 1000 * GB) for name in roots}
        self.roots = {name: (*root, *defaults[name][len(root) - 2:]) for name, root in roots.items()}
        self.asked = []

    def _root(self, path):
        for root, free, device, total in self.roots.values():
            if Path(path) == root or root in Path(path).parents:
                return free, device, total
        raise OSError(f'no drive for {path}')

    def disk_usage(self, path):
        self.asked.append(Path(path))
        free, _, total = self._root(path)
        return Usage(total, total - free, free)

    def stat(self, path):
        _, device, _ = self._root(path)
        return Stat(device)


def test_download_sizes_of_the_model_labels():
    assert download_bytes('605 MB') == 605 * MB
    assert download_bytes('1.71 GB') == round(1.71 * GB)
    for model in MODELS.values():  # every model's label can be read
        assert download_bytes(model.download) > 100 * MB
    for text in ('', 'big', '5 TB', None):
        with pytest.raises(ValueError):
            download_bytes(text)


def test_search_space_counts_cache_rows_and_thumbnails():
    assert search_space_bytes(0, 150, 3) == 0
    assert search_space_bytes(1000, 150, 2) == 1000 * CACHE_BYTES_PER_PHOTO + 150 * 2 * THUMBNAIL_BYTES
    # fewer photos than matches per profile: one thumbnail per photo and profile at most
    assert search_space_bytes(10, 150, 2) == 10 * CACHE_BYTES_PER_PHOTO + 10 * 2 * THUMBNAIL_BYTES


def test_photos_in_the_cache_need_no_cache_rows(tmp_path):
    # review: a repeat search of a large, analyzed collection writes almost nothing
    assert search_space_bytes(1000, 150, 2, analyzed=1000) == 150 * 2 * THUMBNAIL_BYTES
    assert search_space_bytes(1000, 150, 2, analyzed=400) == 600 * CACHE_BYTES_PER_PHOTO + 150 * 2 * THUMBNAIL_BYTES
    results = tmp_path / 'results'
    model = MODELS['vit-b-32-openai']
    assert search_space_needs(results, 1000, 150, 2, model, tmp_path, analyzed=1000)[0] == (
        results, 150 * 2 * THUMBNAIL_BYTES)


def make_cache(path, rows):
    """A feature cache with (photo path, signature) rows, as the engine writes it."""
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE features (path TEXT NOT NULL, signature TEXT NOT NULL, mtime_ns INTEGER NOT NULL, '
                'size INTEGER NOT NULL, labels TEXT NOT NULL, vectors BLOB NOT NULL, PRIMARY KEY(path, signature))')
    con.executemany('INSERT INTO features VALUES (?,?,0,0,?,?)', [(p, s, '[]', b'') for p, s in rows])
    con.commit()
    con.close()


def test_analyzed_photos_counts_the_photos_with_rows_of_the_signature(tmp_path):
    photos = [tmp_path / 'photos' / f'{n}.jpg' for n in range(4)]
    cache = tmp_path / 'cache.sqlite'
    assert analyzed_photos(cache, 'abc', photos) == 0  # no cache yet
    assert not cache.exists()  # not created
    make_cache(cache, [(str(photos[0]), 'abc'), (str(photos[1]), 'abc'), (str(photos[2]), 'other'),
                       (str(tmp_path / 'elsewhere.jpg'), 'abc')])
    # rows of other settings or of photos outside this search do not count
    assert analyzed_photos(cache, 'abc', photos) == 2
    assert analyzed_photos(cache, 'other', photos) == 1
    # a damaged file counts as no cache (on the safe side)
    broken = tmp_path / 'broken.sqlite'
    broken.write_bytes(b'not a database')
    assert analyzed_photos(broken, 'abc', photos) == 0


def test_search_needs_name_downloads_only_when_missing(tmp_path):
    results, hub = tmp_path / 'results', tmp_path / 'hub'
    model = MODELS['vit-b-32-openai']
    weights = tmp_path / 'ultralytics' / 'yolo11n.pt'
    needs = search_space_needs(results, 100, 150, 1, model, hub, weights)
    assert needs == [(results, search_space_bytes(100, 150, 1)), (hub, download_bytes(model.download)),
                     (weights.parent, DETECTOR_DOWNLOAD)]
    # person detection off: no detector download
    assert search_space_needs(results, 100, 150, 1, model, hub, None)[2:] == []
    # cached model files and detector weights: nothing to download
    snapshot = hub / 'models--timm--vit_base_patch32_clip_224.openai'
    (snapshot / 'refs').mkdir(parents=True)
    (snapshot / 'refs' / 'main').write_text('abc', encoding='utf-8')
    (snapshot / 'snapshots' / 'abc').mkdir(parents=True)
    (snapshot / 'snapshots' / 'abc' / 'open_clip_model.safetensors').write_bytes(b'x')
    weights.parent.mkdir()
    weights.write_bytes(b'x')
    assert search_space_needs(results, 100, 150, 1, model, hub, weights) == [(results, search_space_bytes(100, 150, 1))]


def test_a_hub_cache_that_does_not_answer_is_not_read(tmp_path, monkeypatch):
    # review: a disconnected network share in HF_HUB_CACHE must not freeze the page
    def never_read(*args):
        raise AssertionError('must not read the hub cache')
    monkeypatch.setattr(disk_space, 'model_cached', never_read)
    results, hub = tmp_path / 'results', tmp_path / 'hub'
    needs = search_space_needs(results, 10, 150, 1, MODELS['vit-b-32-openai'], hub,
                               reachable=lambda roots, timeout: dict.fromkeys(roots, False))
    # its drive is left out (low_space leaves out the others that do not answer)
    assert needs == [(results, search_space_bytes(10, 150, 1))]


def test_evaluation_runs_need_room_for_every_model(tmp_path):
    # E51: framescout_eval.py run gives each model an output folder (and feature cache) of its own
    first, second = MODELS['vit-b-32-openai'], MODELS['vit-b-16-datacomp']
    hub, weights = tmp_path / 'hub', tmp_path / 'ultralytics' / 'yolo11n.pt'
    a, b = tmp_path / 'engine' / 'a', tmp_path / 'engine' / 'b'
    results = search_space_bytes(100, 150, 2)
    assert eval_run_needs([(a, first), (b, second)], 100, 150, 2, hub, weights) == [
        (a, results), (b, results), (hub, download_bytes(first.download) + download_bytes(second.download)),
        (weights.parent, DETECTOR_DOWNLOAD)]
    # person detection off, and a model whose files are in the cache: nothing to download
    snapshot = hub / 'models--timm--vit_base_patch32_clip_224.openai'
    (snapshot / 'refs').mkdir(parents=True)
    (snapshot / 'refs' / 'main').write_text('abc', encoding='utf-8')
    (snapshot / 'snapshots' / 'abc').mkdir(parents=True)
    (snapshot / 'snapshots' / 'abc' / 'open_clip_model.safetensors').write_bytes(b'x')
    assert eval_run_needs([(a, first)], 100, 150, 2, hub, None) == [(a, results)]
    # a hub cache that does not answer is left out
    assert eval_run_needs([(b, second)], 100, 150, 2, hub, None,
                          reachable=lambda roots, timeout: dict.fromkeys(roots, False)) == [(b, results)]


def test_app_search_needs_use_the_folders_the_app_gives_the_engine(tmp_path):
    base = tmp_path / 'project'
    base.mkdir()
    results, model = base / 'results', MODELS['vit-b-32-openai']
    cache = base / '.cache'
    # the variables cache_env sets: a YOLO_CONFIG_DIR of the user is replaced, as for the engine
    environ = {'YOLO_CONFIG_DIR': str(tmp_path / 'own')}
    assert app_search_needs(base, results, environ, 100, 150, 2, model, True, analyzed=40) == [
        (results, search_space_bytes(100, 150, 2, 40)), (cache / 'huggingface' / 'hub', download_bytes(model.download)),
        (cache / 'ultralytics', DETECTOR_DOWNLOAD)]
    # a HF_HUB_CACHE of the user is kept (cache_env does not set it); weights an older version
    # downloaded into the project folder are moved, not downloaded; detection off: no weights
    (base / 'yolo11n.pt').write_bytes(b'w')
    environ = {'HF_HUB_CACHE': str(tmp_path / 'hub')}
    assert app_search_needs(base, results, environ, 100, 150, 2, model, True)[1:] == [
        (tmp_path / 'hub', download_bytes(model.download))]
    (base / 'yolo11n.pt').unlink()
    assert app_search_needs(base, results, environ, 100, 150, 2, model, False)[1:] == [
        (tmp_path / 'hub', download_bytes(model.download))]


def cache_weights(hub, repo):
    """Put the weights file of the Hub repo into the hub cache folder hub, as huggingface_hub does."""
    folder = hub / ('models--' + repo.replace('/', '--'))
    (folder / 'refs').mkdir(parents=True)
    (folder / 'refs' / 'main').write_text('abc', encoding='utf-8')
    (folder / 'snapshots' / 'abc').mkdir(parents=True)
    (folder / 'snapshots' / 'abc' / 'open_clip_model.safetensors').write_bytes(b'x')


def test_downloaded_models_look_in_the_cache_the_app_gives_the_engine(tmp_path):
    # A39: the model list says "downloaded" for the models whose files are in that cache
    base = tmp_path / 'project'
    base.mkdir()
    assert downloaded_models(base, {}) == set()
    cache_weights(base / '.cache' / 'huggingface' / 'hub', MODELS['vit-b-32-openai'].weights_repo)
    # SigLIP needs its tokenizer files too
    cache_weights(base / '.cache' / 'huggingface' / 'hub', MODELS['vit-b-16-siglip'].weights_repo)
    assert downloaded_models(base, {'HF_HOME': str(tmp_path / 'own')}) == {'vit-b-32-openai'}
    # a HF_HUB_CACHE of the user is kept, as for the engine
    hub = tmp_path / 'hub'
    cache_weights(hub, MODELS['vit-l-14-datacomp'].weights_repo)
    assert downloaded_models(base, {'HF_HUB_CACHE': str(hub)}) == {'vit-l-14-datacomp'}


def test_downloaded_models_do_not_read_a_cache_that_does_not_answer(tmp_path, monkeypatch):
    # a disconnected network share in HF_HUB_CACHE must not freeze the page: no model counts as downloaded
    def never_read(*args):
        raise AssertionError('must not read the hub cache')
    monkeypatch.setattr(disk_space, 'model_cached', never_read)
    assert downloaded_models(tmp_path, {'HF_HUB_CACHE': str(tmp_path / 'hub')},
                             reachable=lambda roots, timeout: dict.fromkeys(roots, False)) == set()


def test_torch_install_needs_per_build(tmp_path):
    venv, temp = tmp_path / '.venv', tmp_path / '.tmp'
    download, installed = TORCH_INSTALL_SPACE['cpu']
    assert torch_install_needs('cpu', venv, temp) == [(temp, download), (venv, installed)]
    download, installed = TORCH_INSTALL_SPACE['cuda']
    for build in ('cu130', 'cu126'):
        assert torch_install_needs(build, venv, temp) == [(temp, download), (venv, installed)]
    # the CUDA build is the large one (about 2.5 GB download)
    assert TORCH_INSTALL_SPACE['cuda'][0] >= 2 * GB > TORCH_INSTALL_SPACE['cpu'][0]
    # PyTorch installed already: only the other packages of requirements.txt (review), which
    # the sizes of a PyTorch install include
    download, installed = OTHER_PACKAGES_SPACE
    assert torch_install_needs('cu130', venv, temp, torch=False) == [(temp, download), (venv, installed)]
    assert all(installed < space[1] for space in TORCH_INSTALL_SPACE.values())


def test_enough_space_gives_no_warning(tmp_path):
    drives = Drives(c=(tmp_path, 100 * GB))
    assert low_space([(tmp_path / 'results', 5 * GB)], disk_usage=drives.disk_usage, stat=drives.stat) == []


def test_low_space_on_one_drive_is_reported(tmp_path):
    drives = Drives(c=(tmp_path, 2 * GB))
    folder = tmp_path / 'results'
    low = low_space([(folder, int(1.5 * GB))], disk_usage=drives.disk_usage, stat=drives.stat)
    # 0.5 GB would be left, less than the reserve
    assert low == [LowSpace(folder, int(1.5 * GB), 2 * GB)]
    assert SPACE_RESERVE > GB // 2


def test_needs_on_the_same_drive_add_up(tmp_path):
    drives = Drives(c=(tmp_path / 'c', 3 * GB), d=(tmp_path / 'd', 3 * GB))
    (tmp_path / 'c').mkdir()
    (tmp_path / 'd').mkdir()
    results, cache, other = tmp_path / 'c' / 'results', tmp_path / 'c' / '.cache', tmp_path / 'd' / 'cache'
    # each need alone fits on its drive, the two on drive c together leave less than the reserve
    needs = [(results, GB), (cache, int(1.5 * GB)), (other, GB)]
    low = low_space(needs, disk_usage=drives.disk_usage, stat=drives.stat)
    assert low == [LowSpace(results, int(2.5 * GB), 3 * GB)]


def test_one_volume_reached_through_two_paths_is_one_drive(monkeypatch):
    # e.g. a subst or mapped drive letter and C:\ for the same volume: the same device
    # number and size, other anchors; the needs add up (review)
    monkeypatch.setattr(disk_space, '_existing_folder', lambda path: Path(path).parent)
    drives = Drives(s=(Path('S:/'), 3 * GB, 7), c=(Path('C:/'), 3 * GB, 7))
    results, hub = Path('S:/FrameScout/results'), Path('C:/hub/models')
    low = low_space([(results, GB), (hub, int(1.5 * GB))], disk_usage=drives.disk_usage, stat=drives.stat,
                    reachable=lambda roots, timeout: dict.fromkeys(roots, True))
    assert low == [LowSpace(results, int(2.5 * GB), 3 * GB)]


def test_volumes_with_the_same_serial_number_but_other_sizes_stay_apart(tmp_path):
    # a cloned disk keeps the volume serial number Windows reports as st_dev
    drives = Drives(c=(tmp_path / 'c', 3 * GB, 7, 500 * GB), d=(tmp_path / 'd', 3 * GB, 7, 2000 * GB))
    (tmp_path / 'c').mkdir()
    (tmp_path / 'd').mkdir()
    needs = [(tmp_path / 'c' / 'results', GB), (tmp_path / 'd' / 'hub', int(1.5 * GB))]
    assert low_space(needs, disk_usage=drives.disk_usage, stat=drives.stat) == []


def test_a_missing_folder_is_checked_on_the_drive_of_its_nearest_existing_parent(tmp_path):
    drives = Drives(c=(tmp_path, GB))
    folder = tmp_path / 'not' / 'there' / 'yet'
    assert low_space([(folder, 1)], disk_usage=drives.disk_usage, stat=drives.stat) == [LowSpace(folder, 1, GB)]
    assert drives.asked == [tmp_path]  # the folder itself is never created


def test_nothing_needed_or_an_unknown_drive_gives_no_warning(tmp_path):
    drives = Drives(c=(tmp_path / 'c', 0))
    assert low_space([(tmp_path / 'c', 0)], disk_usage=drives.disk_usage, stat=drives.stat) == []
    # a drive that cannot be asked (e.g. a disconnected network share): no warning, no error
    assert low_space([(tmp_path / 'x', GB)], disk_usage=drives.disk_usage, stat=drives.stat) == []


def test_a_drive_that_does_not_answer_in_time_gives_no_warning(tmp_path):
    # review: a stat on a disconnected network share can hang; its root is probed with a timeout first
    drives = Drives(c=(tmp_path, 0))
    probed = []

    def unreachable(roots, timeout):
        probed.append((roots, timeout))
        return dict.fromkeys(roots, False)
    assert low_space([(tmp_path, GB)], disk_usage=drives.disk_usage, stat=drives.stat, timeout=0.5,
                     reachable=unreachable) == []
    assert drives.asked == [] and probed == [([os.path.splitdrive(str(tmp_path))[0] + os.sep], 0.5)]


def test_the_real_drive_can_be_asked(tmp_path):
    # with the standard functions: some free space is found, nothing fails
    assert low_space([(tmp_path, 1)], reserve=0) == []
    assert low_space([(tmp_path, 10 ** 18)])[0].free > 0


def test_low_space_lines_name_folder_need_and_free_space(tmp_path):
    lines = low_space_lines([LowSpace(tmp_path, int(1.5 * GB), 2 * GB)])
    assert lines == [f'{tmp_path}: about 1.5 GB needed, 2.0 GB free']
    # the sizes of the constants read the same in a warning (review: not 5.6 GB for 6 GB)
    _, installed = TORCH_INSTALL_SPACE['cuda']
    assert low_space_lines([LowSpace(tmp_path, installed, SPACE_RESERVE)]) == [f'{tmp_path}: about 6.0 GB needed, 1.0 GB free']
