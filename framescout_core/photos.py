"""The photos of a search (E25): which files are read, which are skipped, and RAW previews."""
import collections
import importlib
import os
import time
from pathlib import Path

from .names import AVIF_EXT, EXT, HEIF_EXT, RAW_EXT


# A RAW file is skipped when a photo of the same name with one of these extensions is in
# the same folder: cameras write RAW+JPEG pairs of the same shot, which would otherwise
# appear twice in the results (user decision at the E25 hold point).
RAW_PARTNER_EXT = frozenset({'.jpg', '.jpeg'}) | HEIF_EXT
# The engine uses the JPEG preview a RAW file embeds if its longer edge has at least this
# many pixels, and otherwise decodes the sensor data at half size (E25). Some cameras
# embed only a small thumbnail, too small for person crops and the gallery. Changing it
# changes the embeddings of RAW photos: bump framescout_core.ENGINE then.
RAW_PREVIEW_MIN_EDGE = 1024
# LibRaw's sizes.flip (3: rotate 180°, 5: rotate 90° counterclockwise, 6: rotate 90°
# clockwise to make the image upright) as the PIL Image.Transpose method that does it.
RAW_FLIP_TRANSPOSE = {3: 'ROTATE_180', 5: 'ROTATE_90', 6: 'ROTATE_270'}
# how many extensions the log line about skipped files names
SKIPPED_EXTENSIONS_SHOWN = 5

# paths: the photos to analyze, sorted; raw_pairs: the RAW files skipped for a partner of
# the same name, sorted; unsupported: Counter {extension: files} of the other files ('' for
# files without an extension); found_again: the photos found again through another path (a
# link or hard link) and analyzed once; folders_again: the folders reached again through a
# link, searched once (A37; both 0 by default); stats: {path: (mtime_ns, size)} of the paths
# and raw_pairs as the scan saw them, which the app compares with the cache rows (A44, E61
# review; empty by default: a photo without one is looked at when needed). The default is a
# plain dict, so that a scan can be pickled and copied (review); it is shared, so the stats
# of a scan are never changed
PhotoScan = collections.namedtuple('PhotoScan', 'paths raw_pairs unsupported found_again folders_again stats',
                                   defaults=(0, 0, {}))

# Whether this Python environment can read AVIF (Pillow built with libavif), HEIC/HEIF
# (pillow-heif) and camera RAW (rawpy) files.
Decoders = collections.namedtuple('Decoders', 'avif heif raw')
ALL_DECODERS = Decoders(True, True, True)
# per decoder: its extensions, the name of its files in the log, why they are skipped and
# what helps
_INSTALL_HINT = 'Run Install-FrameScout.bat again to install it.'
_DECODER_FORMATS = (
    ('avif', AVIF_EXT, 'AVIF', 'this Pillow build cannot read AVIF',
     'The Pillow wheels from PyPI (version 11.3 or later) can.'),
    ('heif', HEIF_EXT, 'HEIC/HEIF', 'pillow-heif is not installed or cannot be loaded', _INSTALL_HINT),
    ('raw', RAW_EXT, 'RAW', 'rawpy is not installed or cannot be loaded', _INSTALL_HINT),
)


def available_decoders(import_module=importlib.import_module):
    """Return the Decoders of this Python environment.

    The packages are imported, not only looked up, so that a package that is installed but
    cannot be loaded (e.g. a blocked DLL) counts as missing in the app as in the engine
    (review). Any exception of an import counts as missing.
    """
    def loads(name):
        try:
            return import_module(name)
        except Exception:
            return None

    features = loads('PIL.features')
    try:
        avif = bool(features is not None and features.check('avif'))
    except Exception:
        avif = False
    return Decoders(avif, loads('pillow_heif') is not None, loads('rawpy') is not None)


def supported_extensions(decoders=ALL_DECODERS):
    """Return the extensions that can be read with decoders: EXT without those of a missing decoder."""
    extensions = EXT
    for field, formats, *_ in _DECODER_FORMATS:
        if not getattr(decoders, field):
            extensions -= formats
    return extensions


def missing_decoder(suffix, decoders):
    """Return why a file with this extension cannot be read with decoders, or None if that is not the reason."""
    suffix = suffix.lower()
    for field, formats, name, reason, hint in _DECODER_FORMATS:
        if suffix in formats and not getattr(decoders, field):
            return f'{reason}, so {name} files cannot be read. {hint}'
    return None


def _shot(path):
    """The key of the shot a file belongs to: its folder and its name ignoring case and extension."""
    return path.parent, path.stem.casefold()


def _identity(path):
    """The (device, file id) of what path names, following links; None if it cannot be read (A28).

    Two paths of the same identity are the same folder or file, e.g. a mapped drive letter
    and the UNC path of the same share, a subst drive, a junction or a hard link. None
    also for a file system without file ids (st_ino 0): such paths are compared by text.
    """
    try:
        stat = os.stat(path)
    except (OSError, ValueError):
        return None
    return (stat.st_dev, stat.st_ino) if stat.st_ino else None


def _file_stat(path):
    """os.stat of a photo file, or None if it cannot be read."""
    try:
        return os.stat(path)
    except (OSError, ValueError):
        return None


def _file_times(stat):
    """(mtime_ns, size) of a photo file of its _file_stat, as the engine compares them with its cache rows, or None."""
    return None if stat is None else (stat.st_mtime_ns, stat.st_size)


def _file_identity(stat):
    """The identity of a photo file of its _file_stat: _identity with its size and modification time (review).

    Hard links and file links share all four. Including size and time keeps two different
    photos apart on a file system whose file ids are not unique.
    """
    if stat is None:
        return None
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns) if stat.st_ino else None


def _real_path_key(path):
    """The key of a folder or file without an identity: its path with all links resolved (review).

    A link loop on a file system without file ids then still ends at a folder walked before.
    """
    try:
        path = os.path.realpath(path)
    except (OSError, ValueError):
        pass
    return 'path', _folder_key(path)


def _is_link(entry):
    """True if the directory entry is a symbolic link or a junction (Windows), not a real folder."""
    try:
        return entry.is_symlink() or entry.is_junction()
    except OSError:
        return False


def _shot_pairs(paths):
    """Split the photos of a scan into (photos, RAW files skipped for a partner of the same name)."""
    partners = {_shot(p) for p in paths if p.suffix.lower() in RAW_PARTNER_EXT}
    photos, pairs = [], []
    for p in paths:
        paired = p.suffix.lower() in RAW_EXT and _shot(p) in partners
        (pairs if paired else photos).append(p)
    return photos, pairs


def scan_each_folder(folders, extensions=EXT, exclude=None):
    """Return the PhotoScan of each of folders and its subfolders, scanned together (A25, A28, A29).

    Files inside exclude (the output folder) are left out completely. A RAW file is
    skipped when a file of the same name (ignoring case) with an extension of
    RAW_PARTNER_EXT is in the same folder and is supported itself.

    Folder links (symbolic links and junctions) are followed, so event folders linked into
    one folder are searched, but every folder is walked once, compared by its identity
    (_identity): a link into a folder already walked, e.g. into the same or another of
    folders, or a loop, adds nothing. All real subfolders of all folders are walked before
    any link, so a photo reached both ways is found by its real path, in the folder it is
    really in. A photo found twice by another path (a hard link, a file link) counts once,
    for the first path in that order (photos are the same when their identity, size and
    modification time are: _file_identity). A folder or file whose identity cannot be read
    is compared by its path with all links resolved (_real_path_key).

    The output folder exclude is left out wherever it is reached: as one of folders or
    inside one (by path), or through a link or another path (by identity). A folder that
    cannot be read through one path is tried again through another (review).

    Each PhotoScan counts what was left out as found before (A37), for the folder it was
    reached through again: found_again, the photos found again by another path, and
    folders_again, the folder links into a folder already walked (also a loop); a folder
    listed twice or inside another listed one is not counted (see distinct_folders).

    The modification time and size of each photo and skipped RAW file, read for its identity
    anyway, are kept in stats (A44): the app compares them with the cache rows without reading
    them again (a RAW file's for a quick search, E61 review).
    """
    exclude_path = None if exclude is None else Path(exclude)
    exclude_id = None if exclude is None else _identity(exclude)
    found = [[] for _ in folders]
    unsupported = [collections.Counter() for _ in folders]
    found_again, folders_again = [0] * len(folders), [0] * len(folders)
    seen_folders, seen_files = set(), set()
    real = collections.deque((index, Path(folder)) for index, folder in enumerate(folders))
    links = collections.deque()

    def excluded(folder, identity):
        if exclude_path is None:
            return False
        return (folder == exclude_path or exclude_path in folder.parents
                or (exclude_id is not None and identity == exclude_id))

    def walk(index, folder, via_link):
        identity = _identity(folder) or _real_path_key(folder)
        if identity in seen_folders:
            # only a link is counted: a folder listed twice or inside another listed one is
            # distinct_folders' case (A25), which the app and the engine name themselves (review)
            folders_again[index] += via_link
            return
        if excluded(folder, identity):
            return
        try:
            with os.scandir(folder) as listing:
                entries = sorted(listing, key=lambda entry: entry.name)
        except (OSError, ValueError):
            return  # missing or not readable: nothing found, as with Path.rglob
        seen_folders.add(identity)
        for entry in entries:
            path = folder / entry.name
            try:
                is_dir = entry.is_dir()
                is_file = not is_dir and entry.is_file()
            except OSError:
                continue
            if is_dir:
                (links if _is_link(entry) else real).append((index, path))
            elif is_file:
                suffix = path.suffix.lower()
                if suffix not in extensions:
                    unsupported[index][suffix] += 1
                    continue
                stat = _file_stat(path)
                file_identity = _file_identity(stat) or _real_path_key(path)
                if file_identity in seen_files:
                    found_again[index] += 1
                else:
                    seen_files.add(file_identity)
                    found[index].append(path)
                    if stat is not None:
                        stats[path] = _file_times(stat)

    stats = {}
    while real or links:
        walk(*(real.popleft() + (False,) if real else links.popleft() + (True,)))
    scans = []
    for paths, counts, again, folders_seen in zip(found, unsupported, found_again, folders_again):
        photos, pairs = _shot_pairs(paths)
        scans.append(PhotoScan(sorted(photos), sorted(pairs), counts, again, folders_seen,
                               {p: stats[p] for p in (*photos, *pairs) if p in stats}))
    return scans


def scan_photos(root, extensions=EXT, exclude=None):
    """Return the PhotoScan of the files in root and its subfolders (see scan_each_folder)."""
    return scan_each_folder([root], extensions, exclude)[0]


def raw_fallbacks(scan):
    """Return {partner: RAW file} of the RAW files scan (a PhotoScan) skipped for a partner (E30).

    Every partner of a skipped RAW file (a JPEG/HEIC of the same name in the same folder)
    maps to it, so the engine can analyze the RAW file instead if the partner cannot be
    decoded. If a partner has several RAW files (e.g. a camera RAW and a DNG made from it),
    it maps to the first one in sorted order: one shot, one fallback.
    """
    raws = {}
    for raw in sorted(scan.raw_pairs):
        raws.setdefault(_shot(raw), raw)
    fallbacks = {}
    for path in scan.paths:
        raw = raws.get(_shot(path))
        if raw is not None and path.suffix.lower() in RAW_PARTNER_EXT:
            fallbacks[path] = raw
    return fallbacks


class TruncatedImageError(OSError):
    """A photo whose data ends early, decoded with complete=True (framescout_images.open_image, E46)."""


# JPEG markers (jpeg_scans_missing): the start of frame markers (SOF0-SOF15 without DHT, JPG
# and DAC), the progressive ones among them, start of scan, and the markers without a length
# (restart markers RST0-RST7, start of image, TEM)
_JPEG_FRAMES = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}
_JPEG_PROGRESSIVE = frozenset({0xC2, 0xC6, 0xCA, 0xCE})
_JPEG_SCAN = 0xDA
_JPEG_STANDALONE = frozenset(range(0xD0, 0xD8)) | {0xD8, 0x01}


def _scan_data_end(data, start):
    """The position of the marker after the image data of a scan from start on; None if the data ends first."""
    position = data.find(b'\xff', start)
    while 0 <= position < len(data) - 1:
        follower = data[position + 1]
        # 0x00: a stuffed 0xFF byte; a restart marker belongs to the image data
        if follower != 0x00 and follower not in _JPEG_STANDALONE:
            return position
        position = data.find(b'\xff', position + 2)
    return None


def _scans_cover(components, scans, progressive):
    """Whether the scans [(component ids, first and last coefficient, precision shift)] complete every component."""
    if not progressive:
        return components <= set().union(*(ids for ids, *_ in scans))
    for component in components:
        # at full precision (no bits left for a later refinement scan): the DC coefficient
        # and the AC coefficients 1-63
        if not any(component in ids and first == 0 and low == 0 for ids, first, _, low in scans):
            return False
        ac = set()
        for ids, first, last, low in scans:
            if component in ids and first > 0 and low == 0:
                ac.update(range(first, last + 1))
        if not ac >= set(range(1, 64)):
            return False
    return True


def jpeg_scans_missing(data):
    """Whether the JPEG data, which ends before its end marker, certainly lacks scans (E57).

    Its marker segments are followed from the start: data that ends inside or right after a
    marker segment (not inside the image data of a scan) lacks scans, and so does data
    whose scans so far do not cover every component of the frame (baseline) or every
    coefficient of every component at full precision (progressive). False if it ends inside
    the image data of a scan that completes the image: whether that data is complete is
    left to the decoder (framescout_images); False too if the data cannot be followed.
    """
    if not data.startswith(b'\xff\xd8'):
        return False
    components, progressive, scans = None, False, []
    position, size = 2, len(data)
    while True:
        if position + 1 >= size:
            return True  # right after a marker segment, or inside a marker
        if data[position] != 0xFF:
            return False
        marker = data[position + 1]
        if marker == 0xFF:  # fill byte before a marker
            position += 1
            continue
        if marker in _JPEG_STANDALONE:
            position += 2
            continue
        end = position + 2 + int.from_bytes(data[position + 2:position + 4], 'big')
        if position + 4 > size or end > size:
            return True  # inside a marker segment
        payload = data[position + 4:end]
        if marker in _JPEG_FRAMES and len(payload) >= 6:
            progressive = marker in _JPEG_PROGRESSIVE
            components = {payload[6 + 3 * i] for i in range(payload[5]) if 6 + 3 * i < len(payload)}
        elif marker == _JPEG_SCAN:
            count = payload[0] if payload else 0
            if components is None or len(payload) < 4 + 2 * count:
                return False
            scans.append(({payload[1 + 2 * i] for i in range(count)}, payload[1 + 2 * count],
                          payload[2 + 2 * count], payload[3 + 2 * count] & 0x0F))
            end = _scan_data_end(data, end)
            if end is None:
                return not _scans_cover(components, scans, progressive)
        position = end


class RawFallback:
    """The RAW files a search analyzes instead of their partner that cannot be analyzed (E30).

    A partner that fails (cache scan, decoding or storing) is deferred with defer(partner);
    once all photos are done, choose(analyzed) decides each deferred failure with the
    outcome of the whole shot known: the RAW file is analyzed only if no partner of the
    shot was analyzed (e.g. the good JPEG next to a broken HEIC, review), and only once for
    several failed partners. use(partner, raw) records a RAW file that was analyzed;
    photos(paths) names it in place of its partner, so the shot keeps its place and the
    number of photos stays the same. used: {partner: RAW file} of the analyzed ones.

    A partner must decode completely (strict): a merely truncated JPEG, which decodes with
    its missing part gray, fails (TruncatedImageError) so that the RAW file is analyzed
    instead (E46). If that RAW file fails too, retry() returns the truncated partner, which
    is then analyzed as far as its data goes, so a RAW file LibRaw cannot read does not cost
    the shot. That also holds for a truncated partner that did not get the RAW file because
    another partner of the shot failed first (E53): it waits for the RAW file instead of
    being lost, and stays a failure only once the RAW file was analyzed.
    """

    def __init__(self, scan):
        self.fallbacks = raw_fallbacks(scan)
        self.failed = []
        self.used = {}
        self.truncated = set()  # deferred partners that failed only because their data ends early
        self.lenient = set()  # truncated partners analyzed as far as their data goes (retry)
        # {RAW file: ([its truncated partners], the partner it was picked for)} of the RAW
        # files choose picked
        self._waiting = {}
        self._late_lost = []  # waiting partners that did not get the RAW file (retry decides)
        self._retry = []

    def strict(self, path):
        """Whether path must decode completely: a partner with a RAW file not retried yet (E46)."""
        return path in self.fallbacks and path not in self.lenient

    def defer(self, path, truncated=False):
        """Record a failed photo; True if it is decided later (by choose or retry), not counted now.

        That is a partner with a RAW file that failed for the first time (truncated: only
        because its data ends early, E46), or the RAW file choose picked for a truncated
        partner (its truncated partners are retried). A RAW file picked for a partner that
        failed otherwise counts as that partner's failure (E53): the truncated partners that
        wait for it are retried and count on their own.
        """
        if path in self._waiting:
            partners, picked_for = self._waiting.pop(path)
            self._retry.extend(partners)
            for partner in partners:
                if partner != picked_for:
                    self._late_lost.remove(partner)
            return picked_for in partners
        if path not in self.fallbacks or path in self.failed or path in self.lenient:
            return False
        self.failed.append(path)
        if truncated:
            self.truncated.add(path)
        return True

    def choose(self, analyzed):
        """Return ({partner: RAW file to analyze instead}, [partners that stay failures]).

        analyzed(path) tells whether a photo of the search was analyzed. The deferred
        failures are decided in the order they were deferred, each one once. The truncated
        partners of a shot whose RAW file another partner got are not in the list: they wait
        for the outcome of that RAW file (E53, retry).
        """
        failed, self.failed = self.failed, []
        # only the other partners of shots with a failure are asked about
        failed_raws = {self.fallbacks[partner] for partner in failed}
        shots_done = {raw for partner, raw in self.fallbacks.items()
                      if raw in failed_raws and partner not in failed and analyzed(partner)}
        chosen, lost = {}, []
        for partner in failed:
            raw = self.fallbacks[partner]
            if raw in shots_done or raw in chosen.values():
                lost.append(partner)
            else:
                chosen[partner] = raw
        self._waiting = {raw: ([partner] if partner in self.truncated else [], partner)
                         for partner, raw in chosen.items()}
        for partner in lost:
            raw = self.fallbacks[partner]
            if partner in self.truncated and raw in self._waiting:
                self._waiting[raw][0].append(partner)
                self._late_lost.append(partner)
        self._waiting = {raw: wait for raw, wait in self._waiting.items() if wait[0]}
        return chosen, [partner for partner in lost if partner not in self._late_lost]

    def retry(self):
        """Return (truncated partners whose RAW file failed too, partners that stay failures) (E46, E53).

        The first are analyzed as far as their data goes; from then on they are no longer
        strict, and a failure of theirs counts (defer returns False). The second are the
        truncated partners that waited for the RAW file another partner of their shot got,
        which was analyzed (E53): they count as failures now. Called once the RAW files
        choose picked are done.
        """
        partners, self._retry, self._waiting = self._retry, [], {}
        lost, self._late_lost = self._late_lost, []
        self.lenient.update(partners)
        return partners, lost

    def use(self, partner, raw):
        self.used[partner] = raw

    def photos(self, paths):
        return [self.used.get(path, path) for path in paths]


def _folder_key(folder):
    """The text a folder is compared by: case-insensitive where the file system is (Windows)."""
    return os.path.normcase(str(folder))


def _inside_prefix(key):
    """The text every _folder_key of a path inside the folder of key starts with."""
    return key if key.endswith(os.sep) else key + os.sep


def _inside_key(key, parent):
    """True if the folder of key is inside (below) the folder of parent; both are _folder_key texts."""
    return key != parent and key.startswith(_inside_prefix(parent))


def distinct_folders(folders, identity=_identity):
    """Return (kept, dropped) of the listed photo folders of a search (A25, A28).

    folders: resolved paths in the order listed. A folder listed twice is searched once, and
    a folder inside another listed folder is searched as part of it, so no photo is found
    twice through the list. kept: the folders to search, in list order; dropped: (folder,
    why) of the others. Folders are compared by their paths and by their identity
    (identity(path): see _identity), so the same folder by another path, e.g. a mapped
    drive letter and the UNC path of one share, a subst drive or a junction, is recognized
    too, and so is a folder whose parent folder is another listed folder by another path.
    A folder without an identity (e.g. a missing one) is compared by its path only.

    identity is called once per listed folder, and for the parent folders of a folder only
    when it and at least one other listed folder have an identity, so an unreachable
    network folder is not asked again for each of its parent folders (review).
    """
    unique, unique_ids, dropped, seen = [], [], [], {}
    for folder in folders:
        key, folder_id = _folder_key(folder), identity(folder)
        first = seen.get(key) or (seen.get(folder_id) if folder_id is not None else None)
        if first is not None:
            note = ('is listed twice' if _folder_key(first) == key
                    else f'is the same folder as the listed folder {first} by another path')
            dropped.append((folder, f'The photo folder {folder} {note}; it is searched once.'))
            continue
        seen[key] = folder
        if folder_id is not None:
            seen[folder_id] = folder
        unique.append(folder)
        unique_ids.append(folder_id)
    keys = [_folder_key(f) for f in unique]
    ids = {folder_id: folder for folder, folder_id in zip(unique, unique_ids) if folder_id is not None}
    kept = []
    for folder, key, folder_id in zip(unique, keys, unique_ids):
        parent = next((f for f, k in zip(unique, keys) if _inside_key(key, k)), None)
        if parent is None and folder_id is not None and len(ids) > 1:
            # a parent folder of folder that is another listed folder by another path
            parent = next((ids[i] for i in map(identity, folder.parents)
                           if i is not None and i in ids and ids[i] is not folder), None)
        if parent is None:
            kept.append(folder)
        else:
            dropped.append((folder, f'The photo folder {folder} is inside the listed folder {parent}; '
                                    'it is searched as part of it.'))
    return kept, dropped


def output_folder_problem(folders, output):
    """Return why output cannot be the output folder of a search of the photo folders, or None.

    folders and output are resolved paths. Refused: output equal to a photo folder, and a
    photo folder inside output, whose files the scan always leaves out (review). An output
    folder inside a photo folder is fine: the scan leaves it out.
    """
    key = _folder_key(output)
    for folder in folders:
        if _folder_key(folder) == key:
            return 'The output folder must not be a photo folder.'
        if _inside_key(_folder_key(folder), key):
            return (f'The photo folder {folder} is inside the output folder {output}, whose files a search never '
                    'reads. Choose another output folder or move the photos.')
    return None


def missing_folders_message(folders):
    """Return the error for a search none of whose photo folders exists."""
    if len(folders) == 1:
        return f'Photo folder does not exist: {folders[0]}'
    return 'None of the photo folders exists: ' + '; '.join(str(f) for f in folders)


def _label_parts(folder):
    anchor = folder.anchor.rstrip('\\/')
    parts = list(folder.parts[1:]) if folder.anchor else list(folder.parts)
    return ([anchor] if anchor else []) + parts or [str(folder)]


def folder_labels(folders):
    """Return the label of each photo folder that the gallery puts before a photo's path (A25).

    One folder has no label (''), so the gallery of a single folder is unchanged. Several
    are labeled by their names; folders of the same name (ignoring case) get as many of
    their last path parts as tell them apart, a drive root its drive (e.g. "D:"). A label
    is never the start of another one ("Event" and "Event/sub"): it gets more of its path
    too, so no two photos of different folders get the same name (review).
    """
    if len(folders) < 2:
        return [''] * len(folders)
    parts = [_label_parts(f) for f in folders]
    depth = [1] * len(folders)
    while True:
        labels = [os.sep.join(p[-d:]) for p, d in zip(parts, depth)]
        folded = [label.casefold() for label in labels]
        counts = collections.Counter(folded)
        deeper = {i for i in range(len(labels)) if counts[folded[i]] > 1 and depth[i] < len(parts[i])}
        for i, short in enumerate(folded):
            for j, long in enumerate(folded):
                if long.startswith(short + os.sep):
                    # the shorter label gets more of its path, or else the longer one
                    if depth[i] < len(parts[i]):
                        deeper.add(i)
                    elif depth[j] < len(parts[j]):
                        deeper.add(j)
        if not deeper:
            return labels
        for i in deeper:
            depth[i] += 1


def photo_name(path, folders, labels):
    """Return the name the gallery shows for the photo path: its path in its folder, after the folder's label.

    folders and labels as for folder_labels; a photo outside all folders keeps its full path.
    """
    for folder, label in zip(folders, labels):
        try:
            relative = str(path.relative_to(folder))
        except ValueError:
            continue
        return label + os.sep + relative if label else relative
    return str(path)


def scan_folders(folders, extensions=EXT, exclude=None):
    """Return the PhotoScan of several photo folders together (scan_photos of each, joined; A25).

    folders should be distinct_folders' kept list; scan_each_folder finds no photo twice.
    """
    return join_scans(scan_each_folder(folders, extensions, exclude))


def remembered_scans(memory, folders, extensions=EXT, exclude=None, recount=False, clock=time.time,
                     scan=scan_each_folder):
    """Return (scans, counted_at): scan_each_folder of folders, remembered in memory (A27).

    The app counts the photos of the listed folders on every page run; walking a large
    folder tree on a network drive or HDD each time is slow. memory is a dict the app keeps
    per browser session; the scans are taken from it while the folders (in order), the
    extensions and the output folder are the ones it was counted for, and scanned again when
    one of them changes or recount is true (the "Recount" button). A photo added or removed
    in a folder meanwhile is therefore counted only after a recount; counted_at (clock() of
    the count, None without folders) lets the page say how old the count is. Without folders
    (e.g. the only folder's drive disconnected) memory is cleared, so the same folder is
    counted again when it is back (review). The search itself always scans the folders again.
    """
    folders = list(folders)
    if not folders:
        memory.clear()
        return [], None
    key = (tuple(str(f) for f in folders), frozenset(extensions), None if exclude is None else str(exclude))
    if recount or memory.get('key') != key:
        memory['scans'] = list(scan(folders, extensions, exclude))
        memory['counted_at'] = clock()
        memory['key'] = key
    return memory['scans'], memory['counted_at']


def join_scans(scans):
    """Return one PhotoScan of the PhotoScans of several folders (the app counts each folder on its own)."""
    paths, pairs, unsupported, found_again, folders_again, stats = [], [], collections.Counter(), 0, 0, {}
    for scan in scans:
        paths += scan.paths
        pairs += scan.raw_pairs
        unsupported.update(scan.unsupported)
        found_again += scan.found_again
        folders_again += scan.folders_again
        stats.update(scan.stats)
    return PhotoScan(sorted(paths), sorted(pairs), unsupported, found_again, folders_again, stats)


def _files(count, kind=''):
    noun = 'file' if count == 1 else 'files'
    return f'{count} {kind} {noun}' if kind else f'{count} {noun}'


def skipped_lines(scan, decoders=ALL_DECODERS):
    """Return the log lines about the files of scan (a PhotoScan) that are not analyzed.

    Files of a missing decoder (see decoders) get one line with the reason, and only if the
    folder has such files; they are not named again as an unsupported extension (review).
    Photos and folders reached again through another path get a line each (A37), so a
    count lower than a file manager's is explained.
    """
    lines = []
    if scan.raw_pairs:
        example = scan.raw_pairs[0].name
        example = f'e.g. {example}' if len(scan.raw_pairs) > 1 else example
        lines.append(f'{_files(len(scan.raw_pairs), "RAW")} skipped: a JPEG or HEIC photo of the same name is in '
                     f'the same folder ({example}).')
    other = collections.Counter(scan.unsupported)
    for field, formats, name, reason, hint in _DECODER_FORMATS:
        if getattr(decoders, field):
            continue
        count = sum(other.pop(suffix, 0) for suffix in formats)
        if count:
            lines.append(f'{_files(count, name)} skipped: {reason}. {hint}')
    other = +other  # drops zero counts
    if other:
        ranked = sorted(other.items(), key=lambda item: (-item[1], item[0]))
        shown = [f'{suffix or "no extension"} {count}' for suffix, count in ranked[:SKIPPED_EXTENSIONS_SHOWN]]
        more = len(ranked) - SKIPPED_EXTENSIONS_SHOWN
        if more > 0:
            shown.append(f'{more} more extension' + ('' if more == 1 else 's'))
        lines.append(f'{_files(sum(other.values()))} skipped (unsupported extension): ' + ', '.join(shown) + '.')
    if scan.found_again:
        noun = 'photo' if scan.found_again == 1 else 'photos'
        lines.append(f'{scan.found_again} {noun} found again through another path (a link or hard link), '
                     'analyzed once.')
    if scan.folders_again:
        noun = 'folder' if scan.folders_again == 1 else 'folders'
        lines.append(f'{scan.folders_again} {noun} reached again through a link, searched once.')
    return lines


def raw_preview_usable(width, height):
    """Return True if an embedded RAW preview of this size is used instead of decoding the sensor data."""
    return max(width, height) >= RAW_PREVIEW_MIN_EDGE


def raw_preview_transpose(preview_orientation, flip):
    """Return how to turn an embedded RAW preview upright.

    'exif' if the preview's own EXIF orientation (preview_orientation, None if it has
    none) says it is turned (2..8): ImageOps.exif_transpose does it. Otherwise the
    Image.Transpose name for LibRaw's flip of the RAW file, or None if it is upright.
    The preview's own orientation wins, so a preview is never turned twice.
    """
    if preview_orientation in range(2, 9):
        return 'exif'
    return RAW_FLIP_TRANSPOSE.get(flip)
