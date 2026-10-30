"""The photos of a search (E25): which files are read, which are skipped, and RAW previews."""
import collections
import importlib
import os
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
# files without an extension)
PhotoScan = collections.namedtuple('PhotoScan', 'paths raw_pairs unsupported')

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


def _file_identity(path):
    """The identity of a photo file: _identity with its size and modification time (review).

    Hard links and file links share all four. Including size and time keeps two different
    photos apart on a file system whose file ids are not unique.
    """
    try:
        stat = os.stat(path)
    except (OSError, ValueError):
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
    """
    exclude_path = None if exclude is None else Path(exclude)
    exclude_id = None if exclude is None else _identity(exclude)
    found = [[] for _ in folders]
    unsupported = [collections.Counter() for _ in folders]
    seen_folders, seen_files = set(), set()
    real = collections.deque((index, Path(folder)) for index, folder in enumerate(folders))
    links = collections.deque()

    def excluded(folder, identity):
        if exclude_path is None:
            return False
        return (folder == exclude_path or exclude_path in folder.parents
                or (exclude_id is not None and identity == exclude_id))

    def walk(index, folder):
        identity = _identity(folder) or _real_path_key(folder)
        if identity in seen_folders or excluded(folder, identity):
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
                file_identity = _file_identity(path) or _real_path_key(path)
                if file_identity not in seen_files:
                    seen_files.add(file_identity)
                    found[index].append(path)

    while real or links:
        walk(*(real.popleft() if real else links.popleft()))
    scans = []
    for paths, counts in zip(found, unsupported):
        photos, pairs = _shot_pairs(paths)
        scans.append(PhotoScan(sorted(photos), sorted(pairs), counts))
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


class RawFallback:
    """The RAW files a search analyzes instead of their partner that cannot be analyzed (E30).

    A partner that fails (cache scan, decoding or storing) is deferred with defer(partner);
    once all photos are done, choose(analyzed) decides each deferred failure with the
    outcome of the whole shot known: the RAW file is analyzed only if no partner of the
    shot was analyzed (e.g. the good JPEG next to a broken HEIC, review), and only once for
    several failed partners. use(partner, raw) records a RAW file that was analyzed;
    photos(paths) names it in place of its partner, so the shot keeps its place and the
    number of photos stays the same. used: {partner: RAW file} of the analyzed ones.
    """

    def __init__(self, scan):
        self.fallbacks = raw_fallbacks(scan)
        self.failed = []
        self.used = {}

    def defer(self, path):
        """Record a failed photo; True if it is a partner with a RAW file, decided later by choose."""
        if path not in self.fallbacks or path in self.failed:
            return False
        self.failed.append(path)
        return True

    def choose(self, analyzed):
        """Return ({partner: RAW file to analyze instead}, [partners that stay failures]).

        analyzed(path) tells whether a photo of the search was analyzed. The deferred
        failures are decided in the order they were deferred, each one once.
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
        return chosen, lost

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


def join_scans(scans):
    """Return one PhotoScan of the PhotoScans of several folders (the app counts each folder on its own)."""
    paths, pairs, unsupported = [], [], collections.Counter()
    for scan in scans:
        paths += scan.paths
        pairs += scan.raw_pairs
        unsupported.update(scan.unsupported)
    return PhotoScan(sorted(paths), sorted(pairs), unsupported)


def _files(count, kind=''):
    noun = 'file' if count == 1 else 'files'
    return f'{count} {kind} {noun}' if kind else f'{count} {noun}'


def skipped_lines(scan, decoders=ALL_DECODERS):
    """Return the log lines about the files of scan (a PhotoScan) that are not analyzed.

    Files of a missing decoder (see decoders) get one line with the reason, and only if the
    folder has such files; they are not named again as an unsupported extension (review).
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
