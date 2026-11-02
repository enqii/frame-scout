"""Free disk space checks before installing PyTorch and before a search (F3).

A full disk leaves a broken .venv, a half-downloaded model or failed cache commits, so
install_torch.py and the app compare what they are about to write with the free space of
each drive involved. The sizes are estimates on the safe side; the result is a warning,
never a block.
"""
import os
import re
import shutil
from pathlib import Path
from typing import NamedTuple

from .cleanup import size_text
from .hub import model_cached

# in the units size_text shows them in (and Windows Explorer shows free space in): a "GB"
# here is 1024 ** 3 bytes, so 1.2 GB in the code reads 1.2 GB in a warning (review)
_MB = 1024 ** 2
_GB = 1024 ** 3
# what installing PyTorch writes, about (download, installed) per kind of build: pip
# downloads the wheel into the temporary folder (.tmp in the project folder when
# Install-FrameScout.bat runs it) and unpacks it into the venv, where requirements.txt adds
# about 0.4 GB next. The CPU build was measured (torch 0.55 GB, all packages 0.9 GB on
# Windows); the CUDA build is about 2.5 GB to download and was not measured unpacked.
TORCH_INSTALL_SPACE = {'cpu': (300 * _MB, 1200 * _MB), 'cuda': (3 * _GB, 6 * _GB)}
# the feature cache rows of one photo: float16 embeddings of the whole image and of the
# person crops (about 2-3 KB per photo on average), with room for SQLite
CACHE_BYTES_PER_PHOTO = 10_000
# one gallery thumbnail: a JPEG of at most 380 pixels (20-40 KB)
THUMBNAIL_BYTES = 50_000
# the person detector's weights (yolo11n.pt is 5.4 MB), downloaded on first use
DETECTOR_DOWNLOAD = 6 * _MB
# a drive should keep at least this much free after the install or search
SPACE_RESERVE = 1 * _GB

_SIZE = re.compile(r'(\d+(?:\.\d+)?) (MB|GB)')


class LowSpace(NamedTuple):
    """A drive that would keep less than the reserve free: its first folder, the bytes needed there, its free bytes."""
    folder: Path
    needed: int
    free: int


def download_bytes(text):
    """Return the bytes of a size text like a SearchModel's download ("605 MB", "1.71 GB"); ValueError otherwise.

    Read in the units of this module (1 GB = 1024 ** 3 bytes): a label in decimal units comes
    out up to 7 % larger, on the safe side.
    """
    match = _SIZE.fullmatch(text) if isinstance(text, str) else None
    if not match:
        raise ValueError(f'Not a download size: {text!r}')
    return round(float(match[1]) * (_GB if match[2] == 'GB' else _MB))


def search_space_bytes(photos, top, profiles):
    """Return about what a search writes to the results folder: cache rows and gallery thumbnails.

    Every photo counts as not analyzed yet (the app does not open the cache for this), and
    every gallery as new: min(top, photos) thumbnails for each profile.
    """
    return photos * CACHE_BYTES_PER_PHOTO + min(top, photos) * profiles * THUMBNAIL_BYTES


def search_space_needs(results, photos, top, profiles, model, hub_cache, detector_weights=None):
    """Return the (folder, bytes) pairs a search writes: results, a missing model, missing detector weights.

    model is the SearchModel of the search, hub_cache the Hugging Face cache folder it is
    loaded from (hub_cache_dir); detector_weights is the path the person detector loads its
    weights from, or None with person detection off.
    """
    needs = [(Path(results), search_space_bytes(photos, top, profiles))]
    if not model_cached(model, hub_cache):
        needs.append((Path(hub_cache), download_bytes(model.download)))
    if detector_weights is not None and not Path(detector_weights).is_file():
        needs.append((Path(detector_weights).parent, DETECTOR_DOWNLOAD))
    return needs


def torch_install_needs(build, venv, temp):
    """Return the (folder, bytes) pairs installing the PyTorch build ("cpu", "cu130", ...) writes."""
    download, installed = TORCH_INSTALL_SPACE['cpu' if build == 'cpu' else 'cuda']
    return [(Path(temp), download), (Path(venv), installed)]


def _existing_folder(path):
    """The path or its nearest parent that exists; None if there is none."""
    path = Path(os.path.abspath(path))
    for folder in (path, *path.parents):
        if folder.exists():
            return folder
    return None


def low_space(needs, reserve=SPACE_RESERVE, disk_usage=shutil.disk_usage, stat=os.stat):
    """Return a LowSpace for every drive that would keep less than reserve bytes free.

    needs are (folder, bytes) pairs; a folder that does not exist yet counts on the drive of
    its nearest existing parent (nothing is created), and the needs of folders on the same
    drive add up. A need of 0 bytes, and a drive that cannot be asked (e.g. a disconnected
    network share), give no warning.
    """
    drives = {}
    for folder, size in needs:
        if size <= 0:
            continue
        try:
            existing = _existing_folder(folder)
            if existing is None:
                continue
            # the device number tells drives apart; the anchor too, should a file system report 0
            key = (stat(existing).st_dev, existing.anchor.lower())
            if key not in drives:
                drives[key] = [Path(folder), 0, disk_usage(existing).free]
        except OSError:
            continue
        drives[key][1] += size
    return [LowSpace(*drive) for drive in drives.values() if drive[2] - drive[1] < reserve]


def low_space_lines(low):
    """Return one line per LowSpace: "<folder>: about 1.4 GB needed, 1.9 GB free"."""
    return [f'{entry.folder}: about {size_text(entry.needed)} needed, {size_text(entry.free)} free' for entry in low]
