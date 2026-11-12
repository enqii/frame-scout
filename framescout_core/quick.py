"""Quick search: one search text over the photos already analyzed, without a profile (F10).

The engine's --quick-query scores only photos with a current cache row of the search's
signature (no analysis, no person detector) and writes its gallery and result file to the
folder QUICK_DIR inside the output folder, with thumbnails of its own, so the galleries,
results.json and marks.json of the profile search stay untouched. The cleanup of the output
folder does not look into it; the quick search cleans its own folder (auto_cleanup).

"Find similar" (F11, the engine's --like) is a quick search without a text: it ranks the
analyzed photos by their image similarity with the cached vector of one photo (the part
shown on its card) and writes to the same folder.
"""
import os
from pathlib import Path

from .photos import raw_fallbacks
from .profiles import generic_prompts
from .thumbnails import FULL_IMAGE_LABEL, crop_label

QUICK_DIR = 'quick'
QUICK_GALLERY = 'quick.html'
# characters of a quick search text; CLIP reads at most 77 tokens of a prompt anyway
QUICK_QUERY_MAX = 300


def quick_profile(query):
    """Return the search profile of a quick search for query, as load_profiles builds one of that name.

    White space (also line breaks) is joined to single spaces; the text is not split at
    "|" as a --character is. Raises ValueError for an empty text or one longer than
    QUICK_QUERY_MAX characters.
    """
    name = ' '.join(str(query).split())
    if not name:
        raise ValueError('The quick search text is empty.')
    if len(name) > QUICK_QUERY_MAX:
        raise ValueError(f'The quick search text is longer than {QUICK_QUERY_MAX} characters.')
    prompts = generic_prompts(name)
    return {'name': name, 'prompts': prompts, 'generated': len(prompts), 'refs': []}


def like_profile(photo, part):
    """Return the search profile of "Find similar" (F11) for the part (crop label) of photo: no text.

    Its name names the photo and, for a part other than the whole photo, the part.
    """
    name = f'Similar to {Path(photo).name}'
    if part != FULL_IMAGE_LABEL:
        name += f' ({part})'
    return {'name': name, 'prompts': [], 'generated': 0, 'refs': []}


def like_crop(labels, part):
    """Return the index of the crop of a cache row whose label (as the gallery shows it) is part (F11).

    labels: the crop labels stored in the cache row (crop_label maps the legacy ones).
    Raises ValueError naming the parts the row has if it has no such part.
    """
    shown = [crop_label(label) for label in labels]
    if part in shown:
        return shown.index(part)
    raise ValueError(f'The photo has no part "{part}" with these AI settings, only: {", ".join(shown)}.')


def like_scan_path(photo, scanned, same_file=os.path.samefile):
    """Return the path by which the scan names photo, the photo of "Find similar" (F11 review).

    The cache keys a photo by the path the scan found it at, and the photo and its shot are
    left out by that path: a photo given by another path to the same file (other letter case,
    a link or junction, a mapped drive) is looked up by the scanned one. scanned: the scan's
    photos and RAW files. Only files of the same name (ignoring case) are compared with
    same_file, so the scan is not stat-ed once per photo; photo itself if none is the same
    file (e.g. a photo outside the searched folders).
    """
    photo = Path(photo)
    # by the text: Windows paths compare equal ignoring case, the cache's keys do not
    if any(str(path) == str(photo) for path in scanned):
        return photo
    name = photo.name.casefold()
    for path in scanned:
        if path.name.casefold() == name:
            try:
                if same_file(path, photo):
                    return path
            except OSError:
                continue
    return photo


def like_labels_fit(labels, count):
    """Whether the crop labels of the cache row of "Find similar"'s photo fit its count of vectors (F11 review).

    They do if they are a list of texts, one per vector, and the row has at least one; the
    engine counts any other row as broken (not analyzed), so like_crop's index names a vector.
    """
    return (isinstance(labels, list) and 0 < len(labels) == count
            and all(isinstance(label, str) for label in labels))


def quick_photos(paths, fallbacks, analyzed, exclude=None):
    """Return (photos to score, photos not analyzed) of a quick search, both in the order of paths.

    paths: the photos of the scan; fallbacks: {partner: RAW file} (raw_fallbacks, E30): a
    partner without a current row is scored through its RAW file if that has one and no other
    partner of the shot has a row (a full search analyzed the RAW file in the partner's place
    only then), once per shot; analyzed(path): whether path has a cache row of the search's
    signature with its current modification time and size (the engine's check, which counts
    a row it cannot read as none), asked once per photo. A partner without a row whose shot
    is searched (through another partner or its RAW file) is neither scored nor counted as
    not analyzed (E61): a full search would not analyze the shot again through it either.
    Every partner of a shot without any row counts as not analyzed. exclude: the photo of
    "Find similar" (F11): neither it nor another photo of its shot (its RAW file and every
    partner of that RAW file, whichever of them it is and whether they have rows of their
    own, review) is scored or counted as not analyzed.
    """
    shot_raw = exclude if exclude in fallbacks.values() else fallbacks.get(exclude)
    skip = {exclude} | {path for path, raw in fallbacks.items() if shot_raw is not None and raw == shot_raw}
    paths = [path for path in paths if path not in skip]
    rows = {path: analyzed(path) for path in paths}
    # the shots (by their RAW file) that are searched: those with an analyzed partner, whose
    # RAW file is never shown in addition to it (review), and those searched through it
    searched = {fallbacks[path] for path in paths if rows[path] and path in fallbacks}
    raw_rows = {}  # asked once per shot
    chosen, missing = [], []
    for path in paths:
        if rows[path]:
            chosen.append(path)
            continue
        raw = fallbacks.get(path)
        if raw is not None:
            if raw in searched:
                continue  # E61
            if raw not in raw_rows:
                raw_rows[raw] = analyzed(raw)
            if raw_rows[raw]:
                chosen.append(raw)
                searched.add(raw)
                continue
        missing.append(path)
    return chosen, missing


def quick_scope(scan, analyzed):
    """Return (searched, not analyzed, partners) of a quick search over scan, as the engine counts them (E61).

    scan: the PhotoScan of the chosen folders; analyzed: the paths among its photos and RAW
    files (raw_pairs) that have a current cache row of the search's signature
    (analyzed_paths). Each count is of the scan's photos, so they add up to them (review):
    searched, the photos with a row of their own (analyzed_photos of scan.paths); not
    analyzed, those quick_photos counts as missing; partners, the JPEG/HEIC partners searched
    through another file of their shot (another partner or the RAW file the engine analyzes
    in their place), which quick_photos neither scores nor counts as missing.
    """
    chosen, missing = quick_photos(scan.paths, raw_fallbacks(scan), analyzed.__contains__)
    photos = set(scan.paths)
    own = photos.intersection(chosen)
    return len(own), len(missing), len(photos - own - set(missing))


def quick_folders_differ(searched, folders):
    """Whether a quick search searched other photo folders than folders, the ones chosen now (review).

    searched: the "photo_folders" of its result file; folders: the app's resolved folders, of
    which the engine searches those that exist. The order does not matter.
    """
    return {str(folder) for folder in searched} != {str(folder) for folder in folders}


def quick_scope_text(photos, searched, not_analyzed, partners=0):
    """Return what the app says before a quick search: how many photos it searches and how many not.

    photos: the photos counted in the folders; searched, not_analyzed, partners: the counts
    of quick_scope (E61): the photos analyzed and searched, those not analyzed, and the
    partners whose shot is searched through another file of it.
    """
    if photos <= 0:
        return 'No supported photos found in these folders: there is nothing to search.'
    searched = min(max(searched, 0), photos)
    partners = min(max(partners, 0), photos - searched)
    not_analyzed = min(max(not_analyzed, 0), photos - searched - partners)
    if not searched and not partners:
        return (f'None of the {photos:,} photos is analyzed with these AI settings yet, so a quick search finds '
                'nothing. Start a search with your profiles first: it analyzes them.')
    if searched == photos:
        return f'All {photos:,} photos are analyzed with these AI settings and searched.'
    shots = 'its shot' if partners == 1 else 'their shots'
    through = f'another file of {shots} (the same picture in another format) is searched'

    def rest(count):
        return 'the other photo is' if count == 1 else f'the other {count:,} are'

    if not searched:
        # every photo searched is a partner, searched through another file of its shot (review)
        if partners == photos:
            lead = 'The photo is' if photos == 1 else f'The {photos:,} photos are'
        else:
            lead = f'{partners:,} of {photos:,} photos {"is" if partners == 1 else "are"}'
        itself = 'itself' if partners == 1 else 'themselves'
        text = f'{lead} not analyzed with these AI settings {itself}, but {through}'
        if not_analyzed:
            text += f'; {rest(not_analyzed)} not searched until a search with your profiles analyzes them'
        return text + '.'
    text = f'{searched:,} of {photos:,} photos are analyzed with these AI settings and searched'
    if not_analyzed:
        others = f'{not_analyzed:,} {"is" if not_analyzed == 1 else "are"}' if partners else rest(not_analyzed)
        text += f'; {others} not searched until a search with your profiles analyzes them'
    if partners:
        lead = ('1 other is' if partners == 1 else f'{partners:,} others are') if not_analyzed else rest(partners)
        text += f'; {lead} not analyzed, but {through}'
    return text + '.'


def quick_note(searched, not_analyzed, like=False):
    """Return the note of a quick search's gallery and results: what was searched and why its scores differ.

    like: of "Find similar" (F11), whose photo is not among the searched ones.
    """
    if like:
        text = ('Photos similar to the chosen one among the other '
                + (f'{searched:,} photos' if searched != 1 else 'photo') + ' analyzed with these AI settings')
    else:
        text = f'Quick search over the {searched:,} photos analyzed with these AI settings'
    text += (f'; {not_analyzed:,} {"photo was" if not_analyzed == 1 else "photos were"} not analyzed and not '
             'searched.'
             if not_analyzed else '.')
    return text + (' The scores are scaled over the photos searched, so they differ from those of a search with '
                   'profiles.')
