"""The app's "Clean up storage": what FrameScout no longer needs, listed and deleted (E7, E11)."""
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from urllib.parse import quote

from ._common import _path_key
from .locks import RunLock
from .marks import MARKS_FILE, read_marks, remove_marks
from .names import EXT, profile_slugs
from .profiles import _backup_path, _read_entries, read_profiles
from .results import RESULTS_FILE, _GALLERY_NAME, _THUMBNAIL_NAME, read_results
from .run_status import RUN_LOCK, RUN_STATUS, read_status, run_active
from .settings import SETTINGS_FILE
from .signature import CACHE_FILE, classify_signatures, engine_id


# Cleanup (E7, E11, E13, E23, A14; user decisions at the PR #18 hold point): the app's
# "Clean up storage" lists what FrameScout no longer needs per category and deletes the
# selected categories permanently after a confirmation, holding the run lock of the
# results folder; at the end of every search the engine itself removes the harmless part
# (temporary and unreferenced thumbnails, auto_cleanup). Never deleted: the marks file
# (only single marks of photos that no longer exist, if the user selects them), the run,
# status and result files, the cache file itself, settings and profiles.
# Unbound entries (E8/A21, user decision 2026-10-28): cache rows and marks stay keyed by the
# absolute photo path, so a renamed or moved photo counts as a new one; the old rows and
# marks stay until the cleanup offers them as "unbound" (photo gone, its drive reachable).
THUMBNAILS_DIR = 'thumbnails'
# the thumbnail folder of versions before I7: no longer written, still linked by their galleries
LEGACY_THUMBNAILS_DIR = 'vorschaubilder'
# every gallery the engine has written (also v1.1) has this title
GALLERY_MARKER = '<title>FrameScout – '
CLEANUP_CATEGORIES = ('temp_thumbnails', 'galleries', 'thumbnails', 'cache_missing', 'marks_unbound', 'cache_old',
                      'cache_other', 'cache_models', 'references')
# the categories of cache rows (deleted by signature, except cache_missing: by path and signature)
CACHE_CATEGORIES = ('cache_missing', 'cache_old', 'cache_other', 'cache_models')
# selected when a scan is shown; cache rows and marks of unbound photos (any folder searched so
# far; a drive letter another disk got makes photos look unbound, A35), reference images, rows
# of other current settings and rows of other search models (E22) are not
CLEANUP_DEFAULTS = {'temp_thumbnails': True, 'galleries': True, 'thumbnails': True, 'cache_missing': False,
                    'marks_unbound': False, 'cache_old': True, 'cache_other': False, 'cache_models': False,
                    'references': False}
# seconds the reachability probe of the drive and share roots may take (all roots together); a
# stat on a disconnected network share can hang much longer
ROOT_TIMEOUT = 5.0
# a folder with at most this many photos to check gets one stat per photo, a fuller one is
# listed once (see _PathCheck)
_STAT_UP_TO = 4
NEVER_DELETED = frozenset({MARKS_FILE, MARKS_FILE + '.lock', RUN_LOCK, RUN_STATUS, RESULTS_FILE, CACHE_FILE,
                           SETTINGS_FILE, SETTINGS_FILE + '.lock', 'profiles.json', 'profiles.json.bak',
                           'profiles.json.lock'})
# seconds clean_up waits for the run lock of the results folder
CLEANUP_LOCK_TIMEOUT = 1.0
# the temporary file of ensure_thumbnail (tempfile.mkstemp: <name>.<random>.jpg); a stop
# during the export can leave it (E13)
_TEMP_THUMBNAIL = re.compile(r'[0-9a-f]{24}\.jpg\.[a-z0-9_]+\.jpg')
# the temporary files (<name>.<random>.tmp, _temp_path) of the atomic writes into the results
# folder: status and result file and marks (one file each), the galleries of publish_export
# (E24); terminate()/kill() during a write leaves one (E26)
_TEMP_FILE = re.compile('(?:' + '|'.join(re.escape(name) for name in (RUN_STATUS, RESULTS_FILE, MARKS_FILE))
                        + '|' + _GALLERY_NAME.pattern + r')\.[a-z0-9_]{8}\.tmp')
# seconds after which such a temporary file counts as left over: the write of an app
# session (marks.json, a stopped status) takes a fraction of a second
STALE_TEMP_AGE = 60
_GALLERY_LINK = re.compile(r'\b(' + THUMBNAILS_DIR + '|' + LEGACY_THUMBNAILS_DIR + r')/([0-9a-f]{24}\.jpg)')


def _category(key, items=(), size=0, problem=None, **more):
    return {'key': key, 'items': list(items), 'size': size, 'default': CLEANUP_DEFAULTS[key], 'problem': problem,
            'names': [], **more}


def _file_size(path):
    try:
        return Path(path).stat().st_size
    except OSError:
        return 0


def _files(folder, pattern):
    """The files directly in folder whose name matches pattern (a compiled regex), sorted by name."""
    try:
        return sorted(p for p in Path(folder).iterdir() if pattern.fullmatch(p.name) and p.is_file())
    except (FileNotFoundError, NotADirectoryError):
        return []


def _temp_thumbnails(results):
    return _files(results / THUMBNAILS_DIR, _TEMP_THUMBNAIL)


def _html_files(results):
    try:
        return sorted(p for p in results.glob('*.html') if p.is_file())
    except OSError:
        return []


def _result_names(results):
    """Return (thumbnail names, lowercase gallery names) results.json lists; ValueError if it cannot be read."""
    try:
        data = read_results(results / RESULTS_FILE)
    except (OSError, ValueError) as exc:
        raise ValueError(f'{RESULTS_FILE} cannot be read ({exc})') from None
    if data is None:  # a results folder of a version before A12
        return set(), set()
    return ({card['thumbnail'] for entry in data['profiles'] for card in entry['cards']},
            {entry['gallery'].lower() for entry in data['profiles']})


def _gallery_links(path):
    """Return (text starts like a FrameScout gallery, {(folder, thumbnail name)} it links); ValueError if unreadable."""
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except OSError as exc:
        raise ValueError(f'{path.name} cannot be read ({exc})') from None
    return GALLERY_MARKER in text[:4096], {match.groups() for match in _GALLERY_LINK.finditer(text)}


def _unlinked_thumbnails(results, links, listed):
    """The thumbnails (both folders) that neither results.json (listed) nor links ({(folder, name)}) name."""
    free = []
    for folder in (THUMBNAILS_DIR, LEGACY_THUMBNAILS_DIR):
        for path in _files(results / folder, _THUMBNAIL_NAME):
            if (folder, path.name) in links or (folder == THUMBNAILS_DIR and path.name in listed):
                continue
            free.append(path)
    return free


def _load_profile_file(profiles_file):
    """Return the profile list of the app's profiles file; ValueError if it is missing or cannot be read."""
    profiles_file = Path(profiles_file)
    if not profiles_file.is_file():
        raise ValueError(f'{profiles_file.name} does not exist')
    try:
        return read_profiles(profiles_file)
    except (OSError, ValueError) as exc:
        raise ValueError(f'{profiles_file.name} cannot be read ({exc})') from None


def _gallery_state(results, profiles):
    """Return (orphaned, kept, listed thumbnails); orphaned/kept are {path: links}. ValueError if unknown.

    profiles: the current profile list. Orphaned: a FrameScout gallery (GALLERY_MARKER) that
    results.json does not list and that is not the gallery of a current profile, e.g. of a
    renamed or deleted profile or under an old slug (A3). Every other HTML file is kept.
    """
    listed, listed_galleries = _result_names(results)
    current = {slug + '.html' for slug in profile_slugs([p['name'].strip() for p in profiles])}
    orphaned, kept = {}, {}
    for path in _html_files(results):
        marked, links = _gallery_links(path)
        name = path.name.lower()
        if marked and name not in listed_galleries and name not in current:
            orphaned[path] = links
        else:
            kept[path] = links
    return orphaned, kept, listed


def _union(link_sets):
    return set().union(*link_sets)


def _missing(path):
    """True only if path certainly does not exist (an error such as no permission counts as existing)."""
    try:
        os.stat(path)
    except (FileNotFoundError, NotADirectoryError):
        return True
    except (OSError, ValueError):
        return False
    return False


def _root_of(path):
    """The drive or share root of the absolute path, e.g. C:\\ or \\\\server\\share\\ (/ on POSIX)."""
    return os.path.splitdrive(path)[0] + os.sep


def _probe_root(root):
    """True if the drive or share root can be reached now (a disconnected drive or offline share cannot)."""
    return os.path.isdir(root)


class _Probe:
    """One reachability probe of a root in a daemon thread; answer stays None until it returns."""

    def __init__(self, root):
        self.answer = None
        self.thread = threading.Thread(target=self._run, args=(root,), daemon=True, name='FrameScout root probe')
        self.thread.start()

    def _run(self, root):
        try:
            self.answer = bool(_probe_root(root))
        except Exception:  # any failure: not reachable
            self.answer = False


# the latest probe per root: a probe that still hangs is waited for again instead of starting
# another thread, so the threads of a dead share do not pile up over the scans (review)
_PROBES = {}
_PROBES_LOCK = threading.Lock()


def _reachable_roots(roots, timeout=ROOT_TIMEOUT):
    """Return {root: reachable now} for the drive or share roots, probed in parallel.

    A stat on a disconnected network share can hang for a long time, so each probe runs in a
    daemon thread, and a root whose probe has not answered within timeout seconds (one
    timeout for all roots) counts as not reachable; its thread ends on its own later. A root
    whose earlier probe still runs gets no second thread: that probe is waited for again.
    """
    probes = {}
    with _PROBES_LOCK:
        for root in roots:
            probe = _PROBES.get(root)
            if probe is None or not probe.thread.is_alive():
                probe = _PROBES[root] = _Probe(root)
            probes[root] = probe
    deadline = time.monotonic() + timeout
    for probe in probes.values():
        probe.thread.join(max(0.0, deadline - time.monotonic()))
    return {root: probes[root].answer is True for root in roots}


def _folder_names(folder):
    """The normcased names in folder; False if it certainly does not exist, None if it cannot be listed."""
    try:
        return {os.path.normcase(name) for name in os.listdir(folder)}
    except (FileNotFoundError, NotADirectoryError):
        return False
    except (OSError, ValueError):
        return None


def _gone_in(folder, members):
    """The paths of members (all in folder) that certainly no longer exist.

    At most _STAT_UP_TO paths: one stat each. More: one listing of the folder; a folder that
    does not exist makes them all gone, one that cannot be listed keeps them. The names the
    listing does not hold are gone; the first _STAT_UP_TO of them are confirmed by a stat in
    case the listing spells a name differently (e.g. another Unicode normalization), and if
    one of those exists, every absent name gets its own stat (review: not one stat per
    photo of a renamed folder of 50,000 photos).
    """
    if len(members) <= _STAT_UP_TO:
        return {p for p in members if _missing(p)}
    names = _folder_names(folder)
    if names is False:
        return set(members)
    if names is None:
        return set()
    absent = sorted(p for p in members if os.path.normcase(os.path.basename(p)) not in names)
    if all(_missing(p) for p in absent[:_STAT_UP_TO]):
        return set(absent)
    return {p for p in absent if _missing(p)}


def _by_folder(paths):
    folders = {}
    for path in paths:
        folders.setdefault(os.path.dirname(path), []).append(path)
    return folders


class _PathCheck:
    """Tells which photo paths certainly no longer exist ("unbound", E8/A21); one per scan or deletion step.

    Each path is checked once (the answer is kept, so the cache rows and the marks of a scan
    share one pass), each drive or share root is probed once (_reachable_roots): the paths
    under a root that is not reachable now are not checked, as their photos may only be
    offline. Paths are grouped by folder (_gone_in): a folder with at most _STAT_UP_TO paths
    gets one stat per path, a fuller one is listed once (one directory listing instead of a
    stat per photo, measured about 70 times faster on a network share), and of the names the
    listing does not hold only a few are confirmed by a stat. A folder that does not exist
    makes all its paths gone; one that cannot be listed (e.g. no permission) keeps them. A path that is not
    absolute is never gone. After the pass, the gone paths are checked once more and then
    their roots are probed again, so a share that dropped during the pass (and is back, or
    still offline) does not make its photos look deleted.
    """

    def __init__(self, root_timeout=ROOT_TIMEOUT):
        self._timeout = root_timeout
        self._gone = set()
        self._checked = set()  # paths with an answer: gone, there or never gone
        self._unreachable = {}  # path -> its root that was not reachable

    def check(self, paths, progress=None):
        """Check the paths not checked yet; progress(done, total) is called per folder."""
        todo = {p for p in paths if p not in self._checked and p not in self._unreachable}
        absolute = {p for p in todo if os.path.isabs(p)}
        self._checked |= todo - absolute
        roots = {}
        for path in absolute:
            roots.setdefault(_root_of(path), []).append(path)
        reachable = _reachable_roots(sorted(roots), self._timeout) if roots else {}
        checked = []
        for root, members in roots.items():
            if reachable[root]:
                checked += members
            else:
                self._unreachable.update(dict.fromkeys(members, root))
        folders = _by_folder(checked)
        gone = set()
        total = len(folders)
        step = max(1, total // 100)
        for done, (folder, members) in enumerate(sorted(folders.items()), 1):
            gone |= _gone_in(folder, members)
            if progress and (done % step == 0 or done == total):
                progress(done, total)
        # a share that went offline during the pass makes its folders look missing: the gone
        # paths are looked at once more (a share back by now shows them again, review), then
        # their roots are probed again (a share still offline is not checked)
        gone = set().union(*(_gone_in(folder, members) for folder, members in _by_folder(gone).items()))
        suspects = {_root_of(p) for p in gone}
        lost = {root for root, up in _reachable_roots(sorted(suspects), self._timeout).items() if not up}
        for path in [p for p in gone if _root_of(p) in lost]:
            gone.discard(path)
            self._unreachable[path] = _root_of(path)
        self._gone |= gone
        self._checked |= {p for p in absolute if p not in self._unreachable}

    def result(self, paths):
        """Return (the paths of paths that are gone, {root: number of paths not checked}); checks them first."""
        paths = set(paths)
        self.check(paths)
        unchecked = {}
        for path in paths:
            if path in self._unreachable:
                root = self._unreachable[path]
                unchecked[root] = unchecked.get(root, 0) + 1
        return paths & self._gone, unchecked


def _unchecked_notes(unchecked):
    """The notes of the roots that were not reachable ({root: number of photos})."""
    return [f'{root} is not reachable now (e.g. a disconnected drive or an offline network share), so '
            f'{count_text(count, "photo", "photos")} there {"was" if count == 1 else "were"} not checked.'
            for root, count in sorted(unchecked.items())]


def _read_only_uri(path):
    """Return the SQLite URI that opens the existing file path read-only (never creating it).

    Path.as_uri() gives a UNC path (\\\\server\\share\\...) a host authority, which SQLite
    rejects; the URI form with an empty authority and the server in the path works for both
    (checked on Windows with \\\\localhost\\C$, review).
    """
    posix = Path(path).resolve().as_posix()
    if not posix.startswith('/'):
        posix = '/' + posix  # C:/... -> /C:/...
    return 'file://' + quote(posix, safe='/:') + '?mode=ro'


def _read_cache(cache):
    """Return ([(path, signature, bytes)], {signature: engine}) of the cache file, read-only; None if missing."""
    if not cache.is_file():
        return None
    try:
        con = sqlite3.connect(_read_only_uri(cache), uri=True, timeout=5)
        try:
            tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            rows = (con.execute('SELECT path, signature, length(labels) + length(vectors) FROM features').fetchall()
                    if 'features' in tables else [])
            recorded = dict(con.execute('SELECT signature, engine FROM signatures').fetchall()
                            if 'signatures' in tables else [])
        finally:
            con.close()
    except sqlite3.Error as exc:
        raise ValueError(f'{cache.name} cannot be read ({exc})') from None
    return rows, recorded


def _unbound_rows(rows, check, among=None):
    """The cache_missing category: the rows [(path, signature, size)] whose photo no longer exists (E7, E8).

    Wherever the photo was, also outside the current photo folders (user decision on E8/A21:
    a renamed or moved photo counts as a new one, its old rows are unbound); check: the
    _PathCheck of this scan or deletion step; among: only these (path, signature) pairs (None: all).
    """
    if among is not None:
        rows = [row for row in rows if (row[0], row[1]) in among]
    # each photo is looked at once, however many signatures it has (review)
    gone, unchecked = check.result({path for path, _, _ in rows})
    dead = [(path, signature, size or 0) for path, signature, size in rows if path in gone]
    category = _category('cache_missing', sorted((p, s) for p, s, _ in dead), sum(size for *_, size in dead),
                         rows=len(dead), notes=_unchecked_notes(unchecked))
    category['names'] = _gone_folders({path for path, _, _ in dead})
    return category


def _gone_folders(photos):
    """The folders of photos, fullest first, e.g. "D:\\Photos\\2020 (1,234 photos)".

    Shown before the deletion, so that e.g. the folders of an earlier disk whose drive
    letter another disk got are seen before their rows are deleted (review, A35).
    """
    counts = {}
    for photo in photos:
        folder = os.path.dirname(photo)
        counts[folder] = counts.get(folder, 0) + 1
    return [f'{folder} ({count_text(count, "photo", "photos")})'
            for folder, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _attempt(read):
    """Return read(), or the ValueError it raised (e.g. an unreadable file, shown as the reason)."""
    try:
        return read()
    except ValueError as exc:
        return exc


def _cache_rows(results):
    """Return (rows, recorded) of the cache in results ([] and {} without a cache); ValueError if unreadable."""
    read = _read_cache(results / CACHE_FILE)
    return read if read else ([], {})


def _cache_categories(cache, current, current_model, check, among=None):
    """The cache categories (CACHE_CATEGORIES); current_model: the search model key.

    cache: _attempt(_cache_rows) of the results folder; check, among: as for _unbound_rows.
    """
    keys = CACHE_CATEGORIES
    if isinstance(cache, ValueError):
        return {key: _category(key, problem=f'Not offered: {cache}.', rows=0) for key in keys}
    rows, recorded = cache
    found = {}
    classes = (classify_signatures({signature for _, signature, _ in rows}, recorded, current,
                                   current_engine=engine_id(current_model)) if rows else {})
    for key, wanted in (('cache_old', 'old'), ('cache_other', 'other'), ('cache_models', 'model')):
        chosen = {signature for signature, kind in classes.items() if kind == wanted}
        sizes = [size or 0 for _, signature, size in rows if signature in chosen]
        found[key] = _category(key, sorted(chosen), sum(sizes), rows=len(sizes))
    found['cache_missing'] = _unbound_rows(rows, check, among)
    return {key: found[key] for key in keys}


def _read_marks_entries(results):
    """The (profile, photo path) pairs of the marks file in results; ValueError if it cannot be read."""
    try:
        marks = read_marks(results / MARKS_FILE)
    except (OSError, ValueError) as exc:
        raise ValueError(f'{MARKS_FILE} cannot be read ({exc})') from None
    return [(profile, photo) for profile, photos in marks.items() for photo in photos]


def _unbound_marks(entries, check, among=None):
    """The marks_unbound category: the marks of photos that no longer exist (E8/A21).

    Kept by default (user decision): the photo may come back. entries:
    _attempt(_read_marks_entries) of the results folder; check, among: as for _unbound_rows.
    """
    if isinstance(entries, ValueError):
        return _category('marks_unbound', problem=f'Not offered: {entries}.', notes=[])
    if among is not None:
        entries = [entry for entry in entries if entry in among]
    gone, unchecked = check.result({photo for _, photo in entries})
    items = sorted(entry for entry in entries if entry[1] in gone)
    category = _category('marks_unbound', items, notes=_unchecked_notes(unchecked))
    category['names'] = [f'{profile}: {photo}' for profile, photo in items]
    return category


def _referenced_files(profiles_file, profiles):
    """The _path_key of every reference image of profiles (of profiles_file) and of its .bak; ValueError if unknown."""
    profiles_file = Path(profiles_file)
    refs = [ref for p in profiles for ref in p.get('reference_images', [])]
    backup = _backup_path(profiles_file)
    try:
        entries = _read_entries(backup)
    except FileNotFoundError:
        entries = []
    except (OSError, ValueError) as exc:
        raise ValueError(f'{backup.name} cannot be read ({exc})') from None
    for entry in entries:
        images = entry.get('reference_images') if isinstance(entry, dict) else None
        if isinstance(images, list):
            refs += [ref for ref in images if isinstance(ref, str)]
    base = profiles_file.resolve().parent
    return {_path_key(base / ref) for ref in refs}


def _unreferenced_references(refs_root, profiles_file, profiles=None):
    """The image files in refs_root that neither profiles_file nor its .bak references (A14).

    profiles: the profile list of profiles_file if already read; None reads the file now.
    """
    if profiles is None:
        profiles = _load_profile_file(profiles_file)
    used = _referenced_files(profiles_file, profiles)
    refs_root = Path(refs_root)
    if not refs_root.is_dir():
        return []
    return sorted(p for p in refs_root.rglob('*')
                  if p.suffix.lower() in EXT and p.is_file() and _path_key(p) not in used)


def scan_cleanup(results, profiles_file, refs_root, current_signature, *, current_model, progress=None):
    """Return {category: dict} of what the cleanup can delete; nothing is changed (E7).

    results: the results folder; profiles_file: the app's profiles.json; refs_root: the
    references folder; current_signature: the cache signature of the current settings
    (never offered); current_model: the search model key of the current settings (E22;
    required, as the signature, a hash, does not tell it): rows of the other registered
    models are cache_models, not cache_old; progress(done, total): called while the photos
    of the cache rows and marks are checked (one pass, per folder; the slow part).
    Each category of CLEANUP_CATEGORIES has items (paths; (path, signature) rows for
    cache_missing; the signatures for cache_old/cache_other/cache_models; (profile, photo
    path) pairs for marks_unbound), size (bytes), default, problem (why it is not offered,
    else None) and names (to show); the cache categories have rows; cache_missing and
    marks_unbound have notes (the drive or share roots that were not reachable and how many
    photos there were not checked); galleries has thumbnails/thumbnails_size: the
    thumbnails only the orphaned galleries link, deleted together with them.
    """
    results, refs_root = Path(results), Path(refs_root)
    temps = _temp_thumbnails(results)
    found = {'temp_thumbnails': _category('temp_thumbnails', temps, sum(_file_size(p) for p in temps))}
    profiles = None
    try:
        profiles = _load_profile_file(profiles_file)  # read once for galleries and references (review)
        orphaned, kept, listed = _gallery_state(results, profiles)
    except ValueError as exc:
        problem = f'Not offered: {exc}.'
        found['galleries'] = _category('galleries', problem=problem, thumbnails=[], thumbnails_size=0)
        found['thumbnails'] = _category('thumbnails', problem=problem)
    else:
        # one listing of the thumbnail folders: unlinked by the kept galleries, then split by
        # whether an orphaned gallery links them (review)
        orphan_links = _union(orphaned.values())
        candidates = _unlinked_thumbnails(results, _union(kept.values()), listed)
        free = [p for p in candidates if (p.parent.name, p.name) not in orphan_links]
        extra = [p for p in candidates if (p.parent.name, p.name) in orphan_links]
        found['galleries'] = _category('galleries', sorted(orphaned), sum(_file_size(p) for p in orphaned),
                                       thumbnails=extra, thumbnails_size=sum(_file_size(p) for p in extra))
        found['galleries']['names'] = [p.name for p in found['galleries']['items']]
        found['thumbnails'] = _category('thumbnails', free, sum(_file_size(p) for p in free))
    # one existence pass over the photos of the cache rows and of the marks (E8/A21)
    cache = _attempt(lambda: _cache_rows(results))
    entries = _attempt(lambda: _read_marks_entries(results))
    check = _PathCheck()
    check.check({path for path, _, _ in ([] if isinstance(cache, ValueError) else cache[0])} |
                {photo for _, photo in ([] if isinstance(entries, ValueError) else entries)}, progress)
    found.update(_cache_categories(cache, current_signature, current_model, check))
    found['marks_unbound'] = _unbound_marks(entries, check)
    try:
        refs = _unreferenced_references(refs_root, profiles_file, profiles)
    except ValueError as exc:
        found['references'] = _category('references', problem=f'Not offered: {exc}.')
    else:
        found['references'] = _category('references', refs, sum(_file_size(p) for p in refs))
        found['references']['names'] = [str(p.relative_to(refs_root)) for p in refs]
    return {key: found[key] for key in CLEANUP_CATEGORIES}


def _remove_file(path, summary):
    """Delete the file path permanently and count it in summary; return True if deleted."""
    if path.name in NEVER_DELETED:  # no category holds such a name; a guard for the user's files
        summary['failed'].append((str(path), 'never deleted'))
        return False
    try:
        size = path.stat().st_size
        path.unlink()
    except FileNotFoundError:
        return False
    except OSError as exc:
        summary['failed'].append((str(path), str(exc)))
        return False
    summary['files'] += 1
    summary['freed'] += size
    return True


def _remove_empty_folders(folder, stop):
    """Remove folder and its emptied parents below stop (stop itself stays); only empty folders."""
    folder, stop_key = Path(folder), _path_key(Path(stop))
    while _path_key(folder) != stop_key and stop_key in {_path_key(p) for p in folder.parents}:
        try:
            folder.rmdir()  # fails for a folder that is not empty
        except OSError:
            return
        folder = folder.parent


def _new_summary():
    return {'refused': None, 'files': 0, 'rows': 0, 'marks': 0, 'freed': 0, 'compacted': False, 'failed': [],
            'skipped': []}


def _delete_unlinked(results, links, listed, allowed, summary):
    """Delete the thumbnails of allowed that neither links nor results.json (listed) names now."""
    allowed = set(allowed)
    if allowed:
        for path in _unlinked_thumbnails(results, links, listed):
            if path in allowed:
                _remove_file(path, summary)
    # the old folder goes once nothing in it is linked any more
    _remove_empty_folders(results / LEGACY_THUMBNAILS_DIR, results)


def _delete_rows(results, shown, selected, current, current_model, vacuum, summary):
    """Delete the selected cache rows that the scan shown listed and that still qualify now.

    Only the photos of the unbound rows the scan showed are checked again, not the whole cache.
    """
    among = {tuple(item) for item in shown['cache_missing']['items']} if 'cache_missing' in selected else set()
    fresh = _cache_categories(_attempt(lambda: _cache_rows(results)), current, current_model, _PathCheck(), among)
    rows, signatures = [], []
    for key in CACHE_CATEGORIES:
        if key not in selected:
            continue
        if fresh[key]['problem']:
            summary['skipped'].append(fresh[key]['problem'])
            continue
        still = set(fresh[key]['items'])
        if key == 'cache_missing':
            rows += [tuple(item) for item in shown[key]['items'] if tuple(item) in still]
        else:
            signatures += [item for item in shown[key]['items'] if item in still]
    if not rows and not signatures:
        return
    cache = results / CACHE_FILE
    before = _file_size(cache)
    try:
        con = sqlite3.connect(cache, timeout=5)
        try:
            deleted = 0
            with con:  # one transaction: all rows or none
                for signature in signatures:
                    deleted += con.execute('DELETE FROM features WHERE signature=?', (signature,)).rowcount
                for path, signature in rows:
                    deleted += con.execute('DELETE FROM features WHERE path=? AND signature=?',
                                           (path, signature)).rowcount
            summary['rows'] += deleted
            if vacuum and deleted:
                try:
                    con.execute('VACUUM')  # the file shrinks only now
                    summary['compacted'] = True
                except sqlite3.Error as exc:
                    summary['failed'].append((cache.name, f'not compacted: {exc}'))
        finally:
            con.close()
    except sqlite3.Error as exc:
        summary['failed'].append((cache.name, str(exc)))
        return
    summary['freed'] += max(0, before - _file_size(cache))


def _delete_marks(results, shown, summary):
    """Remove the unbound marks the scan shown listed whose photo is still gone now (E8/A21).

    The photos are checked in this step, with a check of its own (an answer of the cache
    step, which can include a VACUUM, may be out of date, review), and before the marks lock
    is taken (a slow check must not block a mark being saved); then only these entries are
    removed from marks.json, never the file.
    """
    entries = _attempt(lambda: _read_marks_entries(results))
    if isinstance(entries, ValueError):
        summary['skipped'].append(f'Marks were kept: {entries}.')
        return
    fresh = _unbound_marks(entries, _PathCheck(), {tuple(item) for item in shown['marks_unbound']['items']})
    summary['marks'] += remove_marks(results / MARKS_FILE, fresh['items'])


# results folders a clean_up of this process works on now: the app's sessions are threads of
# one process, so another tab can tell a cleanup holding the run lock from a search (review)
_CLEANING = set()


def cleanup_running(results):
    """Return True if a clean_up of this process holds the run lock of the results folder now."""
    return _path_key(Path(results)) in _CLEANING


def _galleries_and_thumbnails(results, shown, selected, profiles_file, summary):
    """The gallery and thumbnail steps of clean_up: read the galleries once, delete, then the thumbnails."""
    try:
        orphaned, kept, listed = _gallery_state(results, _load_profile_file(profiles_file))
    except ValueError as exc:
        summary['skipped'].append(f'Galleries and thumbnails were kept: {exc}.')
        return
    deleted = set()
    allowed_thumbnails = list(shown['thumbnails']['items']) if 'thumbnails' in selected else []
    if 'galleries' in selected:
        allowed = set(shown['galleries']['items'])
        for path in sorted(orphaned):
            if path in allowed and _remove_file(path, summary):
                deleted.add(path)
        # the thumbnails only these galleries showed belong to them (review)
        allowed_thumbnails += shown['galleries'].get('thumbnails', [])
    # every gallery left on disk keeps what it links; nothing writes galleries meanwhile (lock)
    links = _union([*kept.values(), *(v for p, v in orphaned.items() if p not in deleted)])
    _delete_unlinked(results, links, listed, allowed_thumbnails, summary)


def clean_up(results, shown, selected, vacuum, alive, profiles_file, refs_root, current_signature,
             lock_timeout=CLEANUP_LOCK_TIMEOUT, *, current_model):
    """Delete the selected categories of the scan shown (scan_cleanup) permanently; return a summary (E7).

    current_model: the search model key of the current settings, as for scan_cleanup (E22).
    Unbound cache rows and marks are deleted only if their photo is still gone now and its
    drive or share is reachable (E8/A21); of marks.json only those entries are removed.

    Holds the run lock of results, so it is refused while a search runs (also one being
    started: alive(pid, status) tells whether the process of a "starting" status runs) and
    no search can start meanwhile. Under the lock everything is looked at again, and only
    what the scan showed and still qualifies now is deleted: e.g. a reference image a profile
    uses since the scan stays (profiles.json and its .bak are read again), and so does a
    thumbnail a gallery links since. Deleting the orphaned galleries also deletes the
    thumbnails only they linked. vacuum compacts the cache file after rows were deleted.
    The summary has refused (why nothing was done, else None), files, rows, freed (bytes),
    marks (marks removed), compacted (VACUUM done), failed [(name, error)] and skipped (steps that could not be
    done). An error in one step (e.g. a folder that cannot be listed) ends only that step and
    is listed in skipped, so the summary always tells what was deleted (review).
    """
    results = Path(results)
    summary = _new_summary()
    selected = set(selected) & set(CLEANUP_CATEGORIES)
    results.mkdir(parents=True, exist_ok=True)  # for the lock file
    lock = RunLock(results / RUN_LOCK)
    if not lock.acquire(timeout=lock_timeout):
        summary['refused'] = 'A search is running. Clean up after it has finished.'
        return summary
    key = _path_key(results)
    _CLEANING.add(key)
    try:
        status = read_status(results / RUN_STATUS)
        if run_active(status, False, lambda pid: alive(pid, status)):
            summary['refused'] = 'A search is being started. Clean up after it has finished.'
            return summary

        def temporary():
            allowed = set(shown['temp_thumbnails']['items'])
            for path in _temp_thumbnails(results):
                if path in allowed:
                    _remove_file(path, summary)

        def references():
            try:
                now = _unreferenced_references(refs_root, profiles_file)  # profiles.json read again
            except ValueError as exc:
                summary['skipped'].append(f'Reference images were kept: {exc}.')
                return
            allowed = set(shown['references']['items'])
            for path in now:
                if path in allowed and _remove_file(path, summary):
                    _remove_empty_folders(path.parent, refs_root)

        steps = [('Temporary thumbnails', 'temp_thumbnails' in selected, temporary),
                 ('Galleries and thumbnails', bool({'galleries', 'thumbnails'} & selected),
                  lambda: _galleries_and_thumbnails(results, shown, selected, profiles_file, summary)),
                 ('Cache entries', True,
                  lambda: _delete_rows(results, shown, selected, current_signature, current_model, vacuum, summary)),
                 ('Marks', 'marks_unbound' in selected, lambda: _delete_marks(results, shown, summary)),
                 ('Reference images', 'references' in selected, references)]
        for name, wanted, step in steps:
            if not wanted:
                continue
            try:
                step()
            except (OSError, ValueError, sqlite3.Error) as exc:
                # e.g. a folder that cannot be listed: this step ends, the others still run,
                # and the summary keeps what was already deleted (review)
                summary['skipped'].append(f'{name}: stopped ({exc}).')
    finally:
        _CLEANING.discard(key)
        lock.release()
    return summary


def _stale_temp_files(results, now):
    """The temporary files (_TEMP_FILE) directly in results last changed STALE_TEMP_AGE or more seconds before now."""
    stale = []
    for path in _files(results, _TEMP_FILE):
        try:
            if now - path.stat().st_mtime >= STALE_TEMP_AGE:
                stale.append(path)
        except OSError:  # gone meanwhile
            continue
    return stale


def auto_cleanup(results, now=None):
    """Remove left-over temporary files and the thumbnails nothing links; return a summary.

    For the engine at the end of a search, with the run lock held. Left over: the temporary
    thumbnails (E13) and the temporary files of the status, result and marks file and of the
    galleries that are at least STALE_TEMP_AGE seconds old (E24, E26; a younger one may be
    written by an app session now, e.g. marks.json; now: time.time() for tests). Every HTML
    file in results counts as kept here, so a thumbnail one of them or results.json links
    stays; if one of them or results.json cannot be read, every thumbnail stays. An emptied
    legacy thumbnail folder is removed. The summary's files and freed count every removed
    file, temporary those of them that were temporary files.
    """
    results = Path(results)
    summary = _new_summary()
    for path in [*_temp_thumbnails(results), *_stale_temp_files(results, time.time() if now is None else now)]:
        _remove_file(path, summary)
    summary['temporary'] = summary['files']
    try:
        listed, _ = _result_names(results)
        links = _union(_gallery_links(p)[1] for p in _html_files(results))
    except ValueError as exc:
        summary['skipped'].append(f'Thumbnails were kept: {exc}.')
        return summary
    _delete_unlinked(results, links, listed, [*_files(results / THUMBNAILS_DIR, _THUMBNAIL_NAME),
                                              *_files(results / LEGACY_THUMBNAILS_DIR, _THUMBNAIL_NAME)], summary)
    return summary


def size_text(size):
    """Return a byte count for people: 0 B, 12 KB, 3.4 MB, 1.2 GB."""
    if size < 1024:
        return f'{size} B'
    if size < 1024 ** 2:
        return f'{size / 1024:.0f} KB'
    if size < 1024 ** 3:
        return f'{size / 1024 ** 2:.1f} MB'
    return f'{size / 1024 ** 3:.1f} GB'


def count_text(count, one, many):
    """Return e.g. "1 file" or "1,200 files"."""
    return f'{count:,} {one if count == 1 else many}'


def cleanup_summary_text(summary):
    """Return the line the app shows after a cleanup, e.g. "Deleted 3 files and 1,200 cache entries · 2 KB freed"."""
    parts = [count_text(summary['files'], 'file', 'files'), count_text(summary['rows'], 'cache entry', 'cache entries')]
    if summary.get('marks'):
        parts.append(count_text(summary['marks'], 'mark', 'marks'))
    text = f"Deleted {', '.join(parts[:-1])} and {parts[-1]} · {size_text(summary['freed'])} freed"
    if summary['rows'] and not summary.get('compacted'):
        # SQLite keeps the file size until VACUUM (review)
        text += f'; {CACHE_FILE} was not compacted, so it keeps its size and reuses the space for new analyses'
    if summary['failed']:
        text += f" · {len(summary['failed']):,} could not be deleted"
    return text
