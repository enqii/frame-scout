"""Free disk space checks before installing PyTorch and before a search (F3).

A full disk leaves a broken .venv, a half-downloaded model or failed cache commits, so
install_torch.py and the app compare what they are about to write with the free space of
each drive involved. The sizes are estimates on the safe side; the result is a warning,
never a block.
"""
import os
import re
import shutil
import sqlite3
from pathlib import Path
from typing import NamedTuple

from .cache_dirs import cache_paths, find_yolo_weights
from .cleanup import _reachable_roots, _read_only_uri, _root_of, size_text
from .hub import hub_cache_dir, model_cached
from .signature import DEFAULT_YOLO_MODEL

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
# the part of it the other packages of requirements.txt take, installed after PyTorch: what a
# rerun of the installer needs when PyTorch is there but they are not (review; an estimate)
OTHER_PACKAGES_SPACE = (200 * _MB, 400 * _MB)
# the feature cache rows of one photo: float16 embeddings of the whole image and of the
# person crops (about 2-3 KB per photo on average), with room for SQLite
CACHE_BYTES_PER_PHOTO = 10_000
# one gallery thumbnail: a JPEG of at most 380 pixels (20-40 KB)
THUMBNAIL_BYTES = 50_000
# the person detector's weights (yolo11n.pt is 5.4 MB), downloaded on first use
DETECTOR_DOWNLOAD = 6 * _MB
# a drive should keep at least this much free after the install or search
SPACE_RESERVE = 1 * _GB
# seconds a drive or share root may take to answer before the check leaves it out: a stat on
# a disconnected network share can hang far longer, and the app checks on its page runs (review)
SPACE_CHECK_TIMEOUT = 1.0

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


def search_space_bytes(photos, top, profiles, analyzed=0):
    """Return about what a search writes to the results folder: cache rows and gallery thumbnails.

    Cache rows for the photos not analyzed yet (analyzed: how many of the photos have rows
    of the search's settings, analyzed_photos), and every gallery counts as new: min(top,
    photos) thumbnails for each profile.
    """
    return max(0, photos - analyzed) * CACHE_BYTES_PER_PHOTO + min(top, photos) * profiles * THUMBNAIL_BYTES


def analyzed_photos(cache_file, signature, paths):
    """Return how many of the photo paths have a row of signature in the feature cache cache_file.

    Read-only (a missing file is not created); a missing or unreadable cache counts as
    empty, on the safe side. Paths are compared as the engine writes them (str of the path
    of the scan), case-insensitively on Windows.
    """
    cache_file = Path(cache_file)
    try:
        if not cache_file.is_file():
            return 0
        con = sqlite3.connect(_read_only_uri(cache_file), uri=True, timeout=1)
        try:
            # the primary key (path, signature) covers this query: only the index is read
            cached = {os.path.normcase(path) for (path,) in
                      con.execute('SELECT path FROM features WHERE signature=?', (signature,))}
        finally:
            con.close()
    except (sqlite3.Error, OSError):
        return 0
    return sum(os.path.normcase(str(path)) in cached for path in paths)


def search_space_needs(results, photos, top, profiles, model, hub_cache, detector_weights=None, analyzed=0,
                       timeout=SPACE_CHECK_TIMEOUT, reachable=_reachable_roots):
    """Return the (folder, bytes) pairs a search writes: results, a missing model, missing detector weights.

    model is the SearchModel of the search, hub_cache the Hugging Face cache folder it is
    loaded from (hub_cache_dir); detector_weights is the path the person detector loads its
    weights from, or None with person detection off; analyzed as in search_space_bytes. The
    hub cache and the weights are looked at only if their drive answers within timeout
    seconds (reachable: cleanup's root probe); otherwise their download is left out.
    """
    needs = [(Path(results), search_space_bytes(photos, top, profiles, analyzed))]
    folders = [Path(hub_cache)] + ([] if detector_weights is None else [Path(detector_weights).parent])
    answers = _reachable(folders, timeout, reachable)
    if answers[Path(hub_cache)] and not model_cached(model, hub_cache):
        needs.append((Path(hub_cache), download_bytes(model.download)))
    if detector_weights is not None and answers[Path(detector_weights).parent] and not Path(detector_weights).is_file():
        needs.append((Path(detector_weights).parent, DETECTOR_DOWNLOAD))
    return needs


def app_search_needs(base, results, environ, photos, top, profiles, model, person_detection, analyzed=0,
                     timeout=SPACE_CHECK_TIMEOUT, reachable=_reachable_roots):
    """Return the search_space_needs of a search the app starts (F3 review: tested here, not in app.py).

    The app runs the engine in base with the cache variables of cache_paths(base) set over
    environ (cache_env), so the model comes from the Hugging Face cache those give (a
    HF_HUB_CACHE of the user is kept) and the person detector's weights are looked up as
    yolo_weights does (find_yolo_weights); person_detection False needs no weights.
    """
    environ = {**environ, **{name: str(path) for name, path in cache_paths(base).items()}}
    weights = None
    if person_detection:
        found, cached = find_yolo_weights(DEFAULT_YOLO_MODEL, base, base, environ)
        weights = found or cached
    return search_space_needs(results, photos, top, profiles, model, hub_cache_dir(environ), weights, analyzed,
                              timeout, reachable)


def torch_install_needs(build, venv, temp, torch=True):
    """Return the (folder, bytes) pairs installing the PyTorch build ("cpu", "cu130", ...) writes.

    torch False: PyTorch is installed already, only the other packages are.
    """
    if torch:
        download, installed = TORCH_INSTALL_SPACE['cpu' if build == 'cpu' else 'cuda']
    else:
        download, installed = OTHER_PACKAGES_SPACE
    return [(Path(temp), download), (Path(venv), installed)]


def _existing_folder(path):
    """The path or its nearest parent that exists; None if there is none."""
    path = Path(os.path.abspath(path))
    for folder in (path, *path.parents):
        if folder.exists():
            return folder
    return None


def _reachable(folders, timeout, reachable):
    """{folder: whether its drive or share root answers within timeout seconds} (reachable: _reachable_roots)."""
    roots = {folder: _root_of(os.path.abspath(folder)) for folder in folders}
    answers = reachable(sorted(set(roots.values())), timeout) if roots else {}
    return {folder: answers[root] for folder, root in roots.items()}


def low_space(needs, reserve=SPACE_RESERVE, disk_usage=shutil.disk_usage, stat=os.stat, timeout=SPACE_CHECK_TIMEOUT,
              reachable=_reachable_roots):
    """Return a LowSpace for every drive that would keep less than reserve bytes free.

    needs are (folder, bytes) pairs; a folder that does not exist yet counts on the drive of
    its nearest existing parent (nothing is created), and the needs of folders on the same
    drive (volume, by device number and size) add up. A need of 0 bytes, and a drive that
    cannot be asked or does not answer within timeout seconds (e.g. a disconnected network
    share; reachable probes the roots in threads, see cleanup), give no warning.
    """
    needs = [(folder, size) for folder, size in needs if size > 0]
    answers = _reachable([folder for folder, _ in needs], timeout, reachable)
    drives = {}
    for folder, size in needs:
        if not answers[folder]:
            continue
        try:
            existing = _existing_folder(folder)
            if existing is None:
                continue
            usage = disk_usage(existing)
            # one volume is one drive, however it is reached (a subst or mapped drive letter, a
            # UNC path): its device number (the volume serial number on Windows) with its size,
            # since a cloned disk keeps the serial number; the anchor if a file system reports 0
            # (review)
            device = stat(existing).st_dev
            key = (device or existing.anchor.lower(), usage.total)
            if key not in drives:
                drives[key] = [Path(folder), 0, usage.free]
        except OSError:
            continue
        drives[key][1] += size
    return [LowSpace(*drive) for drive in drives.values() if drive[2] - drive[1] < reserve]


def low_space_lines(low):
    """Return one line per LowSpace: "<folder>: about 1.4 GB needed, 1.9 GB free"."""
    return [f'{entry.folder}: about {size_text(entry.needed)} needed, {size_text(entry.free)} free' for entry in low]
