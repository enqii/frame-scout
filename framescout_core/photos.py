"""The photos of a search (E25): which files are read, which are skipped, and RAW previews."""
import collections

from .names import EXT, HEIF_EXT, RAW_EXT


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

# paths: the photos to analyze, sorted; raw_pairs: number of RAW files skipped for a
# partner of the same name; unsupported: Counter {extension: files} of the other files
# ('' for files without an extension)
PhotoScan = collections.namedtuple('PhotoScan', 'paths raw_pairs unsupported')


def supported_extensions(heif=True, raw=True):
    """Return the extensions the engine can read: EXT without HEIF_EXT/RAW_EXT if pillow-heif/rawpy is missing."""
    return EXT - (frozenset() if heif else HEIF_EXT) - (frozenset() if raw else RAW_EXT)


def missing_decoder_lines(heif, raw):
    """Return the log lines that say which photo formats are skipped because their package is missing."""
    lines = []
    if not heif:
        lines.append('pillow-heif is not installed: HEIC/HEIF photos are skipped. '
                     'Run Install-FrameScout.bat again to install it.')
    if not raw:
        lines.append('rawpy is not installed: camera RAW photos are skipped. '
                     'Run Install-FrameScout.bat again to install it.')
    return lines


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
    photos = [p for p in paths if p.suffix.lower() not in RAW_EXT or (p.parent, p.stem.casefold()) not in partners]
    return PhotoScan(sorted(photos), len(paths) - len(photos), unsupported)


def _files(count):
    return f'{count} file' if count == 1 else f'{count} files'


def skipped_lines(scan):
    """Return the log lines about the files of scan (a PhotoScan) that are not analyzed."""
    lines = []
    if scan.raw_pairs:
        what = '1 RAW file' if scan.raw_pairs == 1 else f'{scan.raw_pairs} RAW files'
        lines.append(f'{what} skipped: a JPEG or HEIC photo of the same name is in the same folder.')
    if scan.unsupported:
        ranked = sorted(scan.unsupported.items(), key=lambda item: (-item[1], item[0]))
        shown = [f'{suffix or "no extension"} {count}' for suffix, count in ranked[:SKIPPED_EXTENSIONS_SHOWN]]
        more = len(ranked) - SKIPPED_EXTENSIONS_SHOWN
        if more > 0:
            shown.append(f'{more} more extension' + ('' if more == 1 else 's'))
        lines.append(f'{_files(sum(scan.unsupported.values()))} skipped (unsupported extension): '
                     + ', '.join(shown) + '.')
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
