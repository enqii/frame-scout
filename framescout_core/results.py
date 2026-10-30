"""The results file of a run (results.json), gallery paging and opening photos."""
import hashlib
import json
import os
import re
from pathlib import Path

from ._common import _publish_together, _replace_with_retry
from .names import EXT
from .profiles import load_profiles, read_profiles


# The result of a search (A12, P4): besides the HTML galleries, the engine writes what it
# ranked to RESULTS_FILE in the output folder, so the app shows the galleries of the last
# search under the profile names they were made for, with their date, instead of deriving
# file names from the current profile list. Written once at the end of the export, together
# with the galleries (publish_export, E24): an interrupted export leaves the galleries and
# the file of the previous complete search.
RESULTS_FILE = 'results.json'
# format 2 lists the photo folders of the search ("photo_folders", A25); format 1 had one
# ("photo_folder") and is still read. App versions before A25 reject format 2.
RESULTS_FORMAT = 2
# the app's gallery: cards per page
GALLERY_PAGE_SIZE = 48
# names the app joins to the results folder: plain file names only, never a path
_GALLERY_NAME = re.compile(r'[^\\/:*?"<>|\x00-\x1f]+\.html')
_THUMBNAIL_NAME = re.compile(r'[0-9a-f]{24}\.jpg')


def search_fingerprint(profile, base):
    """Return a short hash of what decides a profile's search, for a profile of load_profiles.

    That is its search texts (generated from name, context and features, plus the custom
    ones) and its reference image paths: the app compares it with the current profile to
    say that a result is older than the last change of the profile. base is the resolved
    folder of the profiles file: a reference inside it counts by its path relative to it,
    so moving the project folder does not change the fingerprint (review).
    """
    def reference(path):
        try:
            return path.relative_to(base).as_posix()
        except ValueError:
            return str(path)
    data = {'prompts': profile['prompts'], 'generated': profile['generated'],
            'references': [reference(x) for x in profile['refs']]}
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def profile_fingerprints(filename):
    """Return {name: search_fingerprint} of the profiles in the app's profiles JSON file, in file order.

    {} if the file is missing or has no profiles; raises like read_profiles otherwise.
    """
    if not read_profiles(filename):
        return {}
    base = Path(filename).resolve().parent
    return {p['name']: search_fingerprint(p, base) for p in load_profiles(filename, [])}


def profile_state(entry, fingerprints):
    """Return 'current', 'changed' (searched with other texts or references) or 'missing' (renamed or deleted).

    entry: a profile of the result file; fingerprints: profile_fingerprints of the current file.
    """
    current = fingerprints.get(entry['name'])
    if current is None:
        return 'missing'
    return 'current' if current == entry['fingerprint'] else 'changed'


def result_card(rank, path, relative, label, score, text, visual, caption, detail, thumbnail):
    """Return the result file's entry of one gallery card.

    path: the photo; relative: its name as the HTML gallery shows it, its path in its photo
    folder, after the folder's label if the search had several (photo_name; computed once
    by the engine for both, review).
    """
    return {'rank': rank, 'path': str(path), 'relative': relative, 'label': label,
            'score': score, 'text': text, 'visual': visual, 'caption': caption, 'detail': detail,
            'thumbnail': thumbnail}


def results_document(started, finished, folders, settings, photos, profiles):
    """Return the content of the result file.

    started/finished: ISO timestamps of the run; folders: the photo folders searched;
    settings: the search options; photos: how many photos were found; profiles: per profile
    a dict with name, fingerprint (search_fingerprint), gallery (HTML file name),
    normalized and cards (result_card, in gallery order).
    """
    return {'format': RESULTS_FORMAT, 'started': started, 'finished': finished,
            'photo_folders': [str(f) for f in folders], 'settings': settings, 'photos': photos,
            'profiles': profiles}


def _results_bytes(document):
    return (json.dumps(document, ensure_ascii=False, indent=1) + '\n').encode('utf-8')


def write_results(path, document):
    """Replace the result file path with document atomically (retried while the app reads it)."""
    _replace_with_retry(path, _results_bytes(document), attempts=40, retry_delay=0.05)


def publish_export(folder, galleries, document, replace=os.replace, attempts=40, retry_delay=0.05):
    """Publish the HTML galleries of an export together with its result file (E24).

    galleries: [(file name, HTML text)] in folder; document: the content of RESULTS_FILE
    (results_document). All files are written in full to temporary files
    (<name>.<random>.tmp) first; only then are the galleries renamed into place, and
    RESULTS_FILE last, so a search stopped or failing while it writes leaves the galleries
    and the result file of the previous search. Only the few renames are not one step: a
    kill between them can still leave a gallery newer than RESULTS_FILE. Renames are retried
    while another process has a file open (replace, attempts and retry_delay: for tests).
    Raises OSError; the temporary files are removed (left only by a killed process, which
    auto_cleanup removes after a later search, E26).
    """
    folder = Path(folder)
    files = [(folder / name, text.encode('utf-8')) for name, text in galleries]
    files.append((folder / RESULTS_FILE, _results_bytes(document)))
    _publish_together(files, attempts, retry_delay, replace)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_card(card):
    strings = ('path', 'relative', 'label', 'caption', 'detail', 'thumbnail')
    if (not isinstance(card, dict) or not isinstance(card.get('rank'), int) or isinstance(card['rank'], bool)
            or any(not isinstance(card.get(k), str) for k in strings) or not _is_number(card.get('score'))
            or any(card.get(k) is not None and not _is_number(card[k]) for k in ('text', 'visual'))):
        raise ValueError(f'invalid gallery card: {card!r}'[:300])
    if not _THUMBNAIL_NAME.fullmatch(card['thumbnail']):
        raise ValueError(f"invalid thumbnail name: {card['thumbnail']!r}")


def read_results(path):
    """Return the result file path as written by the engine, or None if it does not exist.

    A file of format 1 (before A25) is returned like one of format 2: its "photo_folder" as
    the list "photo_folders" (empty if it had none). Raises ValueError for a file of
    another format or with invalid entries, in particular a gallery or thumbnail name that
    is not a plain file name (the app opens them in the results folder), and OSError if it
    cannot be read.
    """
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    if not isinstance(data, dict) or data.get('format') not in (1, RESULTS_FORMAT):
        raise ValueError(f'{Path(path).name} is not a FrameScout result file of format 1 or {RESULTS_FORMAT}')
    if data['format'] == 1:
        folder = data.pop('photo_folder', None)
        data['photo_folders'] = [folder] if isinstance(folder, str) and folder else []
    folders = data.get('photo_folders')
    if not isinstance(folders, list) or not all(isinstance(f, str) for f in folders):
        raise ValueError('"photo_folders" must be a list of folder names')
    profiles = data.get('profiles')
    if not isinstance(profiles, list):
        raise ValueError('"profiles" must be a list')
    names = set()
    for entry in profiles:
        if (not isinstance(entry, dict) or not isinstance(entry.get('name'), str) or not entry['name']
                or not isinstance(entry.get('fingerprint'), str) or not isinstance(entry.get('gallery'), str)
                or not isinstance(entry.get('cards'), list)):
            raise ValueError(f'invalid profile entry: {entry!r}'[:300])
        if not _GALLERY_NAME.fullmatch(entry['gallery']):
            raise ValueError(f"invalid gallery file name: {entry['gallery']!r}")
        if entry['name'] in names:  # the app picks a profile by its name (review)
            raise ValueError(f"duplicate profile name: {entry['name']!r}")
        names.add(entry['name'])
        for card in entry['cards']:
            _check_card(card)
    return data


def page_count(cards, size):
    """Return the number of gallery pages for cards cards, at least 1."""
    return max(1, -(-cards // size))


def page_cards(cards, page, size):
    """Return the cards of page (1-based) of a gallery; a page out of range shows the nearest one."""
    page = min(max(page, 1), page_count(len(cards), size))
    return cards[(page - 1) * size:page * size]


def openable_photo(path):
    """Return path as a Path if it is an existing image file with an absolute path, else None.

    The app opens a photo of the result file with the program the system associates with
    it; checking the extension makes sure that is an image viewer, never a program.
    """
    photo = Path(path)
    if not photo.is_absolute() or photo.suffix.lower() not in EXT or not photo.is_file():
        return None
    return photo


def open_command(path, system):
    """Return the command that opens path with its default program on system (platform.system()).

    Not for Windows: there the app uses os.startfile.
    """
    return ['open', str(path)] if system == 'Darwin' else ['xdg-open', str(path)]


def reveal_command(path, system):
    """Return the command that shows the file path in the file manager of system (platform.system()).

    Not for Windows: there the app calls the shell function SHOpenFolderAndSelectItems,
    since "explorer /select," parses its own command line and, checked on Windows 11, did
    not select a file whose name contains a comma. Linux has no common way to select a
    file, so its folder is opened.
    """
    if system == 'Darwin':
        return ['open', '-R', str(path)]
    return ['xdg-open', str(Path(path).parent)]
