"""The photos of a search: supported extensions, RAW+JPEG pairs, skipped files and RAW previews (E25)."""
import collections
from pathlib import Path

import pytest

from framescout_core import (ALL_DECODERS, AVIF_EXT, EXT, HEIF_EXT, RAW_EXT, RAW_FLIP_TRANSPOSE,
                             RAW_PREVIEW_MIN_EDGE, Decoders, PhotoScan, available_decoders, missing_decoder,
                             raw_preview_transpose, raw_preview_usable, scan_photos, skipped_lines,
                             supported_extensions)

NO_HEIF = Decoders(avif=True, heif=False, raw=True)
NO_RAW = Decoders(avif=True, heif=True, raw=False)
NO_AVIF = Decoders(avif=False, heif=True, raw=True)
NONE = Decoders(avif=False, heif=False, raw=False)


def touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'x')
    return path


# --- the extensions ---

def test_avif_heif_and_raw_extensions():
    assert AVIF_EXT == {'.avif'}
    assert HEIF_EXT == {'.heic', '.heif'}
    assert RAW_EXT == {'.dng', '.cr2', '.cr3', '.nef', '.arw', '.orf', '.rw2', '.raf', '.pef', '.srw'}
    assert AVIF_EXT <= EXT and HEIF_EXT <= EXT and RAW_EXT <= EXT


def test_supported_extensions_leave_out_missing_decoders():
    assert supported_extensions() == EXT
    assert supported_extensions(ALL_DECODERS) == EXT
    assert supported_extensions(NO_HEIF) == EXT - HEIF_EXT
    assert supported_extensions(NO_RAW) == EXT - RAW_EXT
    assert supported_extensions(NO_AVIF) == EXT - AVIF_EXT
    assert supported_extensions(NONE) == EXT - AVIF_EXT - HEIF_EXT - RAW_EXT
    assert '.jpg' in supported_extensions(NONE)


class FakeFeatures:
    def __init__(self, avif):
        self.avif = avif

    def check(self, name):
        assert name == 'avif'
        return self.avif


def importer(available, avif=True):
    """An import_module that only knows the module names in available (review)."""
    imported = []

    def import_module(name):
        imported.append(name)
        if name not in available:
            raise ImportError(name)
        return FakeFeatures(avif) if name == 'PIL.features' else object()
    import_module.imported = imported
    return import_module


def test_available_decoders_import_the_packages():
    # really imports them (not only find_spec), as the engine does: a package that is
    # installed but cannot be loaded counts as missing in the app and the engine (review)
    load = importer({'PIL.features', 'pillow_heif', 'rawpy'})
    assert available_decoders(load) == ALL_DECODERS
    assert set(load.imported) == {'PIL.features', 'pillow_heif', 'rawpy'}
    assert available_decoders(importer({'PIL.features', 'rawpy'})) == NO_HEIF
    assert available_decoders(importer({'PIL.features', 'pillow_heif'})) == NO_RAW
    assert available_decoders(importer({'PIL.features', 'pillow_heif', 'rawpy'}, avif=False)) == NO_AVIF
    assert available_decoders(importer(set())) == NONE


def test_available_decoders_count_a_package_that_fails_to_load_as_missing():
    def import_module(name):
        if name == 'rawpy':
            raise OSError('DLL load failed')  # e.g. a blocked LibRaw DLL
        return FakeFeatures(True) if name == 'PIL.features' else object()
    assert available_decoders(import_module) == NO_RAW


def test_missing_decoder():
    for suffix in ('.jpg', '.png', '.gif', ''):
        assert missing_decoder(suffix, NONE) is None
    assert missing_decoder('.heic', ALL_DECODERS) is None
    heif = missing_decoder('.HEIF', NO_HEIF)
    assert 'pillow-heif' in heif and 'HEIC' in heif and 'Install-FrameScout.bat' in heif
    raw = missing_decoder('.cr3', NO_RAW)
    assert 'rawpy' in raw and 'RAW' in raw and 'Install-FrameScout.bat' in raw
    avif = missing_decoder('.avif', NO_AVIF)
    # re-running the installer would not replace an installed Pillow build without AVIF
    assert 'Pillow' in avif and 'AVIF' in avif and 'Install-FrameScout.bat' not in avif
    assert missing_decoder('.cr3', NO_HEIF) is None


# --- scan_photos ---

def test_scan_finds_supported_files_recursively_and_sorted(tmp_path):
    b = touch(tmp_path / 'b.JPG')
    a = touch(tmp_path / 'sub' / 'a.heic')
    c = touch(tmp_path / 'sub' / 'deeper' / 'c.avif')
    raw = touch(tmp_path / 'd.CR3')
    (tmp_path / 'empty-folder.jpg').mkdir()  # a folder is never a photo
    scan = scan_photos(tmp_path)
    assert isinstance(scan, PhotoScan)
    assert scan.paths == sorted([a, b, c, raw])
    assert scan.raw_pairs == []
    assert scan.unsupported == collections.Counter()


def test_scan_leaves_out_the_excluded_folder(tmp_path):
    photo = touch(tmp_path / 'photo.jpg')
    touch(tmp_path / 'results' / 'thumbnails' / 'thumb.jpg')
    touch(tmp_path / 'results' / 'run.log')
    scan = scan_photos(tmp_path, exclude=tmp_path / 'results')
    assert scan.paths == [photo]
    # files of the output folder are neither photos nor skipped files
    assert scan.unsupported == collections.Counter()


def test_scan_counts_unsupported_files_by_extension(tmp_path):
    photo = touch(tmp_path / 'photo.png')
    touch(tmp_path / 'clip.MOV'); touch(tmp_path / 'sub' / 'clip2.mov')
    touch(tmp_path / 'photo.png.xmp')
    touch(tmp_path / 'README')
    scan = scan_photos(tmp_path)
    assert scan.paths == [photo]
    assert scan.unsupported == collections.Counter({'.mov': 2, '.xmp': 1, '': 1})


def test_scan_counts_files_of_missing_decoders_as_unsupported(tmp_path):
    photo = touch(tmp_path / 'photo.jpg')
    touch(tmp_path / 'phone.heic'); touch(tmp_path / 'camera.nef')
    scan = scan_photos(tmp_path, supported_extensions(NONE))
    assert scan.paths == [photo]
    assert scan.unsupported == collections.Counter({'.heic': 1, '.nef': 1})


@pytest.mark.parametrize('partner', ['IMG_0001.JPG', 'img_0001.jpeg', 'IMG_0001.heic', 'IMG_0001.HEIF'])
def test_scan_skips_a_raw_file_with_a_jpeg_or_heic_of_the_same_name(tmp_path, partner):
    raw = touch(tmp_path / 'IMG_0001.CR2')
    kept = touch(tmp_path / partner)
    scan = scan_photos(tmp_path)
    assert scan.paths == [kept]
    # the skipped RAW files themselves, so the log can name them (review)
    assert scan.raw_pairs == [raw]
    assert scan.unsupported == collections.Counter()


def test_scan_keeps_raw_files_without_a_partner_in_the_same_folder(tmp_path):
    # a JPEG of the same name in another folder, or a PNG/TIFF next to it, is no partner
    raw = touch(tmp_path / 'IMG_0002.NEF')
    other_folder = touch(tmp_path / 'exports' / 'IMG_0002.jpg')
    png = touch(tmp_path / 'IMG_0003.png')
    raw3 = touch(tmp_path / 'IMG_0003.dng')
    scan = scan_photos(tmp_path)
    assert scan.paths == sorted([raw, other_folder, png, raw3])
    assert scan.raw_pairs == []


def test_scan_ignores_a_heic_partner_that_cannot_be_read(tmp_path):
    # without pillow-heif the HEIC file is skipped, so the RAW file is the only copy
    raw = touch(tmp_path / 'IMG_0004.arw')
    touch(tmp_path / 'IMG_0004.heic')
    scan = scan_photos(tmp_path, supported_extensions(NO_HEIF))
    assert scan.paths == [raw]
    assert scan.raw_pairs == []
    assert scan.unsupported == collections.Counter({'.heic': 1})


def test_scan_of_an_empty_folder(tmp_path):
    assert scan_photos(tmp_path) == PhotoScan([], [], collections.Counter())


# --- skipped_lines ---

def scan_of(raw_pairs=(), **unsupported):
    """A PhotoScan with the RAW file names raw_pairs and unsupported extensions given as ext=count."""
    counts = collections.Counter({('.' + k if k != 'none' else ''): v for k, v in unsupported.items()})
    return PhotoScan([], [Path('photos') / name for name in raw_pairs], counts)


def test_skipped_lines_without_skipped_files():
    assert skipped_lines(scan_of()) == []


def test_skipped_lines_name_raw_pairs_with_an_example():
    line, = skipped_lines(scan_of(['IMG_0003.CR2', 'IMG_0001.CR2', 'IMG_0002.CR2']))
    assert line == ('3 RAW files skipped: a JPEG or HEIC photo of the same name is in the same folder '
                    '(e.g. IMG_0003.CR2).')
    line, = skipped_lines(scan_of(['DSC_1.NEF']))
    assert line == '1 RAW file skipped: a JPEG or HEIC photo of the same name is in the same folder (DSC_1.NEF).'


def test_skipped_lines_name_the_most_common_extensions():
    line, = skipped_lines(scan_of(mov=8, xmp=3, none=1))
    assert line == '12 files skipped (unsupported extension): .mov 8, .xmp 3, no extension 1.'
    line, = skipped_lines(scan_of(txt=1))
    assert line == '1 file skipped (unsupported extension): .txt 1.'


def test_skipped_lines_shorten_a_long_extension_list():
    unsupported = collections.Counter({f'.x{i}': 10 - i for i in range(8)})
    line, = skipped_lines(PhotoScan([], [], unsupported))
    assert line.startswith(f'{sum(unsupported.values())} files skipped (unsupported extension): .x0 10, .x1 9, ')
    assert '.x4 6' in line and '.x5' not in line
    assert line.endswith(', 3 more extensions.')


def test_skipped_lines_both_kinds():
    lines = skipped_lines(scan_of(['a.dng', 'b.dng'], mov=1))
    assert len(lines) == 2


def test_skipped_lines_explain_files_of_a_missing_decoder_once():
    # files whose package is missing are named with the reason, not again as an
    # "unsupported extension"; nothing is said when the folder has none of them (review)
    scan = scan_of(heic=1, heif=1, nef=1, cr3=2, avif=1, mov=4)
    lines = skipped_lines(scan, NONE)
    assert len(lines) == 4
    avif, heif, raw, other = lines
    assert avif.startswith('1 AVIF file skipped: ') and 'Pillow' in avif
    assert heif.startswith('2 HEIC/HEIF files skipped: ') and 'pillow-heif' in heif
    assert raw.startswith('3 RAW files skipped: ') and 'rawpy' in raw
    assert other == '4 files skipped (unsupported extension): .mov 4.'
    assert skipped_lines(scan_of(mov=4), NONE) == [other]
    assert skipped_lines(scan_of(), NONE) == []
    # with the decoder, such an extension can only be in the scan if it was passed
    # differently; it is then an unsupported extension like any other
    assert skipped_lines(scan_of(heic=2), ALL_DECODERS) == ['2 files skipped (unsupported extension): .heic 2.']


# --- RAW previews ---

def test_raw_preview_usable_needs_a_long_enough_edge():
    assert raw_preview_usable(RAW_PREVIEW_MIN_EDGE, 10)
    assert raw_preview_usable(10, RAW_PREVIEW_MIN_EDGE)
    assert raw_preview_usable(6000, 4000)
    assert not raw_preview_usable(RAW_PREVIEW_MIN_EDGE - 1, RAW_PREVIEW_MIN_EDGE - 1)
    assert not raw_preview_usable(160, 120)


def test_raw_flip_transpose_matches_exif_orientations():
    # LibRaw's sizes.flip: 3 = rotate 180°, 5 = rotate 90° counterclockwise, 6 = rotate 90°
    # clockwise to make the image upright; Pillow's ROTATE_90 turns counterclockwise, and
    # exif_transpose uses ROTATE_270 for EXIF orientation 6 (90° clockwise)
    assert RAW_FLIP_TRANSPOSE == {3: 'ROTATE_180', 5: 'ROTATE_90', 6: 'ROTATE_270'}


@pytest.mark.parametrize('orientation, flip, expected', [
    (None, 0, None), (1, 0, None), (None, 6, 'ROTATE_270'), (1, 5, 'ROTATE_90'), (None, 3, 'ROTATE_180'),
    # the preview's own EXIF orientation wins, so a preview is never turned twice
    (6, 6, 'exif'), (3, 0, 'exif'), (8, 5, 'exif'),
    # unknown values leave the preview as it is
    (None, 7, None), (0, 0, None), (9, 0, None),
])
def test_raw_preview_transpose(orientation, flip, expected):
    assert raw_preview_transpose(orientation, flip) == expected
