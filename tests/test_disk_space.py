"""Free disk space checks before installing PyTorch and before a search (F3); no real drive is filled."""
from collections import namedtuple
from pathlib import Path

import pytest

from framescout_core import (CACHE_BYTES_PER_PHOTO, DETECTOR_DOWNLOAD, MODELS, SPACE_RESERVE, THUMBNAIL_BYTES,
                             TORCH_INSTALL_SPACE, LowSpace, download_bytes, low_space, low_space_lines,
                             search_space_bytes, search_space_needs, torch_install_needs)

GB = 1000 ** 3
Usage = namedtuple('Usage', 'total used free')
Stat = namedtuple('Stat', 'st_dev')


class Drives:
    """Stands in for shutil.disk_usage and os.stat: folders under a known root are on its drive."""

    def __init__(self, **roots):
        # roots: name -> (root folder, free bytes); the device number is the name
        self.roots = roots
        self.asked = []

    def _root(self, path):
        for name, (root, free) in self.roots.items():
            if Path(path) == root or root in Path(path).parents:
                return name, free
        raise OSError(f'no drive for {path}')

    def disk_usage(self, path):
        self.asked.append(Path(path))
        _, free = self._root(path)
        return Usage(0, 0, free)

    def stat(self, path):
        name, _ = self._root(path)
        return Stat(name)


def test_download_sizes_of_the_model_labels():
    assert download_bytes('605 MB') == 605 * 1000 ** 2
    assert download_bytes('1.71 GB') == 1710 * 1000 ** 2
    for model in MODELS.values():  # every model's label can be read
        assert download_bytes(model.download) > 100 * 1000 ** 2
    for text in ('', 'big', '5 TB', None):
        with pytest.raises(ValueError):
            download_bytes(text)


def test_search_space_counts_cache_rows_and_thumbnails():
    assert search_space_bytes(0, 150, 3) == 0
    assert search_space_bytes(1000, 150, 2) == 1000 * CACHE_BYTES_PER_PHOTO + 150 * 2 * THUMBNAIL_BYTES
    # fewer photos than matches per profile: one thumbnail per photo and profile at most
    assert search_space_bytes(10, 150, 2) == 10 * CACHE_BYTES_PER_PHOTO + 10 * 2 * THUMBNAIL_BYTES


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


def test_torch_install_needs_per_build(tmp_path):
    venv, temp = tmp_path / '.venv', tmp_path / '.tmp'
    download, installed = TORCH_INSTALL_SPACE['cpu']
    assert torch_install_needs('cpu', venv, temp) == [(temp, download), (venv, installed)]
    download, installed = TORCH_INSTALL_SPACE['cuda']
    for build in ('cu130', 'cu126'):
        assert torch_install_needs(build, venv, temp) == [(temp, download), (venv, installed)]
    # the CUDA build is the large one (about 2.5 GB download)
    assert TORCH_INSTALL_SPACE['cuda'][0] >= 2 * GB > TORCH_INSTALL_SPACE['cpu'][0]


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


def test_the_real_drive_can_be_asked(tmp_path):
    # with the standard functions: some free space is found, nothing fails
    assert low_space([(tmp_path, 1)], reserve=0) == []
    assert low_space([(tmp_path, 10 ** 18)])[0].free > 0


def test_low_space_lines_name_folder_need_and_free_space(tmp_path):
    lines = low_space_lines([LowSpace(tmp_path, int(1.5 * GB), 2 * GB)])
    assert lines == [f'{tmp_path}: about 1.4 GB needed, 1.9 GB free']
