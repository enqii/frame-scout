"""The photos of a search (E25): which files are read, which are skipped, and RAW previews."""
import collections
import importlib
import os

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


def scan_photos(root, extensions=EXT, exclude=None):
    """Return the PhotoScan of the files in root and its subfolders.

    Files inside exclude (the output folder) are left out completely. A RAW file is
    skipped when a file of the same name (ignoring case) with an extension of
    RAW_PARTNER_EXT is in the same folder and is supported itself.
    """
    paths, unsupported = [], collections.Counter()
    for path in root.rglob('*'):
        if not path.is_file() or (exclude is not None and exclude in path.parents):
            continue
        suffix = path.suffix.lower()
        if suffix in extensions:
            paths.append(path)
        else:
            unsupported[suffix] += 1
    partners = {(p.parent, p.stem.casefold()) for p in paths if p.suffix.lower() in RAW_PARTNER_EXT}
    photos, pairs = [], []
    for p in paths:
        paired = p.suffix.lower() in RAW_EXT and (p.parent, p.stem.casefold()) in partners
        (pairs if paired else photos).append(p)
    return PhotoScan(sorted(photos), sorted(pairs), unsupported)


def _folder_key(folder):
    """The text a folder is compared by: case-insensitive where the file system is (Windows)."""
    return os.path.normcase(str(folder))


def _inside_key(key, parent):
    """True if the folder of key is inside (below) the folder of parent; both are _folder_key texts."""
    prefix = parent if parent.endswith(os.sep) else parent + os.sep
    return key != parent and key.startswith(prefix)


def distinct_folders(folders):
    """Return (kept, dropped) of the listed photo folders of a search (A25).

    folders: resolved paths in the order listed. A folder listed twice is searched once, and
    a folder inside another listed folder is searched as part of it, so no photo is found
    twice through the list. kept: the folders to search, in list order; dropped: (folder,
    why) of the others. Only the paths are compared (resolved by the caller); the same
    folder reachable through two paths, e.g. a junction or another drive letter, is not
    recognized.
    """
    unique, dropped, seen = [], [], set()
    for folder in folders:
        key = _folder_key(folder)
        if key in seen:
            dropped.append((folder, f'The photo folder {folder} is listed twice; it is searched once.'))
            continue
        seen.add(key)
        unique.append(folder)
    keys = [_folder_key(f) for f in unique]
    kept = []
    for folder, key in zip(unique, keys):
        parent = next((f for f, k in zip(unique, keys) if _inside_key(key, k)), None)
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

    folders should be distinct_folders' kept list, so no file is found twice.
    """
    return join_scans([scan_photos(folder, extensions, exclude) for folder in folders])


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
