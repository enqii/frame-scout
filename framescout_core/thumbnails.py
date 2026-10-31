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


def ensure_thumbnail(path, thumbs, legacy_thumbs, render, log, mtime_ns=None):
    """Return the file name of path's thumbnail in the folder thumbs, or None on failure.

    An existing thumbnail is reused; one of an older version in legacy_thumbs (same name =
    same photo and modification time; None: no such folder) is copied and left in place;
    otherwise render(path, target) writes a new one. Any failure, including a photo that
    was deleted or moved after scoring (E6), is reported with log(message) and the photo
    is skipped, so one missing file cannot abort the whole HTML export. render must
    write to the target it is given (a temporary .jpg name, not the final one). The name
    is made of mtime_ns if given (the evaluation tool's time of scoring, E35), otherwise
    of the photo's current modification time.
    """
    try:
        name = thumbnail_name(path, path.stat().st_mtime_ns if mtime_ns is None else mtime_ns)
        target = thumbs / name
        if not target.exists():
            old = None if legacy_thumbs is None else legacy_thumbs / name
            if old is not None and old.is_file():
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


def gallery_cards(ranked, top, thumbnail):
    """Yield (rank, item, thumbnail name) for the first top items of ranked that get a thumbnail.

    ranked is the full ranking of a gallery, best first; thumbnail(item) returns the
    thumbnail's file name or None for a photo that is skipped (see ensure_thumbnail).
    Ranks count only the photos shown, so a skipped photo leaves no gap, and lower-ranked
    photos fill the gallery up to top cards (E12). Stops trying as soon as it is full.
    """
    rank = 0
    for item in ranked:
        if rank >= top:
            return
        name = thumbnail(item)
        if name is not None:
            rank += 1
            yield rank, item, name


# How many skipped photos an export names one by one in the log before it only counts them.
SKIP_LOG_LIMIT = 50


class SkippedPhotos:
    """The photos of one export that got no thumbnail (review of E12).

    thumbnail() is ensure_thumbnail for a whole export: a photo that failed once is not
    tried again in later galleries, and only the first limit failures are logged, so a
    photo folder that vanished since scoring cannot flood the log with one line per photo
    and gallery. summary() returns the closing log line if more photos were skipped than
    logged, otherwise None.
    """

    def __init__(self, log, limit=SKIP_LOG_LIMIT):
        self.paths, self.log, self.limit = set(), log, limit

    def thumbnail(self, path, thumbs, legacy_thumbs, render):
        if path in self.paths:
            return None
        name = ensure_thumbnail(path, thumbs, legacy_thumbs, render, self._log)
        if name is None:
            self.paths.add(path)
        return name

    def _log(self, message):
        if len(self.paths) < self.limit:
            self.log(message)

    def summary(self):
        if len(self.paths) <= self.limit:
            return None
        return (f'{len(self.paths)} photos got no thumbnail and are left out of the galleries; '
                f'only the first {self.limit} are listed above.')
