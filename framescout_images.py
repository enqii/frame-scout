"""Image decoding of FrameScout: photos as upright RGB images and gallery thumbnails (E49).

Needs Pillow and, for AVIF, HEIC/HEIF and camera RAW photos, pillow-heif and rawpy (E25),
but neither torch nor numpy: the engine decodes photos with it, and the evaluation tool
(framescout_eval.py pool) renders the thumbnails its labelling page lacks without loading
the engine, its torch import and the engine's cache variables (E42). Importing it
registers the HEIF decoder with Pillow and sets Pillow's limits for large and truncated
files, for every program that imports it.
"""
import io
import threading
from contextlib import contextmanager
from pathlib import Path

from PIL import Image, ImageFile, ImageOps

from framescout_core import (DRAFT_REDUCING_GAP, RAW_EXT, TruncatedImageError, available_decoders, jpeg_scans_missing,
                             missing_decoder, raw_preview_transpose, raw_preview_usable)

# pillow-heif and rawpy are in requirements.txt; an older installation without them still
# runs and skips those photos with a note. The app checks the same way (available_decoders),
# so both agree (review).
DECODERS = available_decoders()
if DECODERS.heif:
    from pillow_heif import register_heif_opener
    register_heif_opener()
if DECODERS.raw:
    import rawpy


class _LenientUnlessStrict:
    """The value of ImageFile.LOAD_TRUNCATED_IMAGES: true, except in a thread inside _strict() (E53).

    Pillow (and pillow-heif) only ask for its truth value when they load an image, so a
    partner that must decode completely can be loaded strictly while the other decoding
    threads keep loading truncated photos as far as their data goes; tests/test_images.py
    pins how Pillow uses it.
    """

    def __init__(self):
        self._local = threading.local()

    def __bool__(self):
        return not getattr(self._local, 'strict', False)

    def __repr__(self):
        return f'{type(self).__name__}(now {bool(self)})'


_LOAD_TRUNCATED = _LenientUnlessStrict()


@contextmanager
def _strict():
    """Load images in this thread as Pillow does by default: a truncated or damaged one raises."""
    before = getattr(_LOAD_TRUNCATED._local, 'strict', False)
    _LOAD_TRUNCATED._local.strict = True
    try:
        yield
    finally:
        _LOAD_TRUNCATED._local.strict = before


Image.MAX_IMAGE_PIXELS = 160_000_000
ImageFile.LOAD_TRUNCATED_IMAGES = _LOAD_TRUNCATED
# the errors with which Pillow and pillow-heif reject image data they cannot decode
_DECODE_ERRORS = (OSError, ValueError, SyntaxError, EOFError)
# formats whose truncated images decode without any of their pixels (E59): always loaded
# strictly (_open); Pillow's own AVIF reader already rejects a truncated AVIF
_STRICT_FORMATS = ('HEIF', 'AVIF')
# the end of image marker of a JPEG, and the restart markers RST0-RST7 (_ends_only_its_marker)
_JPEG_END = b'\xff\xd9'
_JPEG_RESTARTS = [bytes((0xFF, 0xD0 + n)) for n in range(8)]
# bytes appended in place of missing image data; never 0x00, since libjpeg itself fills
# missing data with zero bits, and never 0xFF, which starts a marker
_JPEG_FILLERS = [b'\xaa' * 256, b'\x55' * 256]
# EXIF tag of the image orientation
ORIENTATION = 0x0112
THUMBNAIL_SIZE = 380


def open_image(path, min_size=None, complete=False):
    """Open path as an upright RGB image.

    With min_size, a JPEG is decoded at 1/2, 1/4 or 1/8 scale (Image.draft) as long as
    both edges stay at least min_size pixels long; other formats ignore it (E2). A camera
    RAW file is read with open_raw (E25). A JPEG whose data ends early or is damaged decodes
    with the missing part gray (LOAD_TRUNCATED_IMAGES); a truncated HEIC/HEIF raises (E59),
    since it would decode all black. With complete, the image must
    decode completely (_open_complete): such a JPEG raises TruncatedImageError instead, so
    that the engine analyzes the RAW file of its shot (E46, E53).
    """
    suffix = Path(path).suffix.lower()
    # e.g. a HEIC reference image without pillow-heif: say why instead of a decoder error;
    # other extensions are left to Pillow, as before (a reference image can be any format)
    reason = missing_decoder(suffix, DECODERS)
    if reason:
        raise OSError(reason)
    if suffix in RAW_EXT:
        return open_raw(path, min_size)
    if complete:
        return _open_complete(path, min_size)
    return _open(path, min_size)[0]


def _open(path, min_size=None):
    """Return (path as an upright RGB image, whether it is a JPEG whose data ended before its end marker).

    A HEIF image (_STRICT_FORMATS) is always loaded strictly (E59): pillow-heif decodes a
    truncated one all black where truncated images are allowed, which is no part of the photo.
    """
    with Image.open(path) as image:
        if min_size:
            image.draft(None, (min_size, min_size))
        if image.format in _STRICT_FORMATS:
            with _strict():
                image.load()
        upright = ImageOps.exif_transpose(image).convert('RGB')
        # Pillow's JPEG reader sets _ended when the file ends before its end marker (it then
        # pretends the marker); tests/test_images.py pins it
        return upright, bool(getattr(image, '_ended', False))


def _open_complete(path, min_size=None):
    """open_image of a photo that must decode completely (E46, E53, E57).

    Decoded strictly first (_strict): Pillow then raises for a JPEG whose data ends early
    and for one whose data libjpeg gives up on in the middle, which otherwise decode with a
    gray part (E53), and pillow-heif for a truncated HEIC, which otherwise decodes all black.
    If that fails, a JPEG that still decodes as far as its data goes raises
    TruncatedImageError (a retry can analyze it as far as it goes), unless it lacks only
    its end marker (_ends_only_its_marker, E57): its image data is complete, so it is
    returned. Any other file raises the error of the strict decoding.
    """
    try:
        with _strict():
            return _open(path, min_size)[0]
    except _DECODE_ERRORS as exc:
        strict_error = exc
    try:
        with Image.open(path) as image:
            is_jpeg = image.format in ('JPEG', 'MPO')
        upright, ended = _open(path, min_size) if is_jpeg else (None, False)
    except _DECODE_ERRORS:
        upright = None
    if upright is None:
        raise strict_error
    if ended and _ends_only_its_marker(path, min_size):
        return upright
    raise TruncatedImageError('image data ends early or is damaged (decodes only in part)') from strict_error


def _decoded(data, min_size):
    """The pixels of the JPEG data, decoded as _open does (truncated data as far as it goes)."""
    with Image.open(io.BytesIO(data)) as image:
        if min_size:
            image.draft(None, (min_size, min_size))
        image.load()
        return image.tobytes()


def _ends_only_its_marker(path, min_size=None):
    """Whether the JPEG path, which ends before its end marker, holds all of its image data (E57).

    Data that ends outside the image data of a scan, or before its scans cover the whole
    image (e.g. between two scans of a progressive JPEG), lacks scans (jpeg_scans_missing).
    Otherwise it ends in the image data of its last scan: Pillow (libjpeg) decodes it with
    an end marker appended and fills the image data that is missing with zero bits. Decoded
    again with other bytes in place of the missing data (_JPEG_FILLERS, also after each
    restart marker in case the data ends where the next restart interval begins), a
    truncated JPEG gives other pixels, while bytes after the complete image data are
    skipped as garbage, so the pixels stay the same.
    """
    try:
        data = Path(path).read_bytes()
        if jpeg_scans_missing(data):
            return False
        variants = []
        if data.endswith(b'\xff'):
            # the first half of a stuffed 0xFF byte or of a marker (e.g. of the end marker
            # itself): filler bytes right after it would form a marker that ends the data as
            # the end marker does, so they follow a 0x00. The data as it is must decode the
            # same: Pillow drops the 0xFF of a stuffed byte whose 0x00 is missing.
            variants.append(data + _JPEG_END)
            data += b'\x00'
        fillers = _JPEG_FILLERS + [marker + _JPEG_FILLERS[0] for marker in _JPEG_RESTARTS]
        variants += [data + filler + _JPEG_END for filler in fillers]
        base = _decoded(data + _JPEG_END, min_size)
        return all(_decoded(variant, min_size) == base for variant in variants)
    except _DECODE_ERRORS:
        return False  # e.g. the file changed meanwhile: it does not count as complete


def open_raw(path, min_size=None):
    """Open the camera RAW file path as an upright RGB image (E25).

    The preview the camera embedded is used if it is large enough and can be read
    (raw_preview); otherwise the sensor data is decoded at half size with the camera's
    white balance, and LibRaw turns that image upright itself.
    """
    with rawpy.imread(str(path)) as raw:
        preview = raw_preview(raw, min_size)
        if preview is None:
            preview = Image.fromarray(raw.postprocess(half_size=True, use_camera_wb=True, output_bps=8))
    return preview.convert('RGB')


def raw_preview(raw, min_size=None):
    """Return the upright preview embedded in the rawpy file raw, or None if there is no usable one.

    A JPEG or bitmap preview is usable if its longer edge is long enough
    (raw_preview_usable); a JPEG preview is drafted with min_size like any JPEG. A preview
    that cannot be read (corrupt, truncated, unknown format) is not usable either, so the
    caller falls back to the sensor data instead of failing the photo (review).
    """
    try:
        thumb = raw.extract_thumb()
        if thumb.format == rawpy.ThumbFormat.JPEG:
            with Image.open(io.BytesIO(thumb.data)) as image:
                if not raw_preview_usable(*image.size):
                    return None
                if min_size:
                    image.draft(None, (min_size, min_size))
                turn = raw_preview_transpose(image.getexif().get(ORIENTATION), raw.sizes.flip)
                # both load the pixels before the file closes
                image = ImageOps.exif_transpose(image) if turn == 'exif' else image.convert('RGB')
        elif thumb.format == rawpy.ThumbFormat.BITMAP:
            image = Image.fromarray(thumb.data)
            if not raw_preview_usable(*image.size):
                return None
            turn = raw_preview_transpose(None, raw.sizes.flip)
        else:
            return None
        if turn not in (None, 'exif'):
            image = image.transpose(getattr(Image.Transpose, turn))
        return image
    except (rawpy.LibRawError, OSError, ValueError, SyntaxError):
        # LibRawError covers a missing or unsupported thumbnail; Pillow raises OSError
        # (UnidentifiedImageError), ValueError or SyntaxError for broken image data
        return None


def render_thumbnail(path, target):
    """Write the gallery thumbnail of the photo path to target (a .jpg name).

    Decoded at reduced scale like an unloaded image in Image.thumbnail (E2). The
    evaluation tool renders the thumbnails its labelling page lacks with it (E35).
    """
    im = open_image(path, DRAFT_REDUCING_GAP * THUMBNAIL_SIZE)
    im.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE)); im.save(target, quality=82)
