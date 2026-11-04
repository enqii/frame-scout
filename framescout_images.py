"""Image decoding of FrameScout: photos as upright RGB images and gallery thumbnails (E49).

Needs Pillow and, for AVIF, HEIC/HEIF and camera RAW photos, pillow-heif and rawpy (E25),
but neither torch nor numpy: the engine decodes photos with it, and the evaluation tool
(framescout_eval.py pool) renders the thumbnails its labelling page lacks without loading
the engine, its torch import and the engine's cache variables (E42). Importing it
registers the HEIF decoder with Pillow and sets Pillow's limits for large and truncated
files, for every program that imports it.
"""
import io
from pathlib import Path

from PIL import Image, ImageFile, ImageOps

from framescout_core import (DRAFT_REDUCING_GAP, RAW_EXT, available_decoders, missing_decoder, raw_preview_transpose,
                             raw_preview_usable)

# pillow-heif and rawpy are in requirements.txt; an older installation without them still
# runs and skips those photos with a note. The app checks the same way (available_decoders),
# so both agree (review).
DECODERS = available_decoders()
if DECODERS.heif:
    from pillow_heif import register_heif_opener
    register_heif_opener()
if DECODERS.raw:
    import rawpy

Image.MAX_IMAGE_PIXELS = 160_000_000
ImageFile.LOAD_TRUNCATED_IMAGES = True
# EXIF tag of the image orientation
ORIENTATION = 0x0112
THUMBNAIL_SIZE = 380


def open_image(path, min_size=None):
    """Open path as an upright RGB image.

    With min_size, a JPEG is decoded at 1/2, 1/4 or 1/8 scale (Image.draft) as long as
    both edges stay at least min_size pixels long; other formats ignore it (E2). A camera
    RAW file is read with open_raw (E25).
    """
    suffix = Path(path).suffix.lower()
    # e.g. a HEIC reference image without pillow-heif: say why instead of a decoder error;
    # other extensions are left to Pillow, as before (a reference image can be any format)
    reason = missing_decoder(suffix, DECODERS)
    if reason:
        raise OSError(reason)
    if suffix in RAW_EXT:
        return open_raw(path, min_size)
    with Image.open(path) as image:
        if min_size:
            image.draft(None, (min_size, min_size))
        return ImageOps.exif_transpose(image).convert('RGB')


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
