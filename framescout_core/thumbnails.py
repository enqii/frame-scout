"""Crop labels and gallery thumbnails of the HTML export (E6)."""
import hashlib
import os
import shutil

from ._common import _publish_via_temp


# Label of the uncropped photo among the crops; person crops are labelled "Person <n>".
FULL_IMAGE_LABEL = 'Full image'
# Labels are stored in the feature cache; rows written before the English translation
# (I7) carry the German label. Mapping them on display keeps those rows valid.
_LEGACY_LABELS = {'Gesamtbild': FULL_IMAGE_LABEL}


def crop_label(stored):
    """Return the gallery label for a crop label stored in the feature cache."""
    return _LEGACY_LABELS.get(stored, stored)


def thumbnail_name(path, mtime_ns):
    """Return the file name of the gallery thumbnail of path at modification time mtime_ns."""
    return hashlib.sha256((str(path) + str(mtime_ns)).encode()).hexdigest()[:24] + '.jpg'


def ensure_thumbnail(path, thumbs, legacy_thumbs, render, log):
    """Return the file name of path's thumbnail in the folder thumbs, or None on failure.

    An existing thumbnail is reused; one of an older version in legacy_thumbs (same name =
    same photo and modification time) is copied and left in place; otherwise
    render(path, target) writes a new one. Any failure, including a photo that was
    deleted or moved after scoring (E6), is reported with log(message) and the photo
    is skipped, so one missing file cannot abort the whole HTML export. render must
    write to the target it is given (a temporary .jpg name, not the final one).
    """
    try:
        name = thumbnail_name(path, path.stat().st_mtime_ns)
        target = thumbs / name
        if not target.exists():
            old = legacy_thumbs / name
            if old.is_file():
                def write(tmp):
                    shutil.copyfile(old, tmp)
            else:
                def write(tmp):
                    render(path, tmp)
            # via a temporary .jpg file (Pillow picks the format from the extension), so an
            # interrupted copy or render never leaves a broken thumbnail that later runs reuse
            _publish_via_temp(target, write, os.replace, suffix='.jpg', durable=False)
        return name
    except Exception as exc:
        log(f'Thumbnail not possible ({path}): {exc}')
        return None
