"""The photos of a search (E25): which files are read, which are skipped, and RAW previews."""
import collections
import importlib

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
