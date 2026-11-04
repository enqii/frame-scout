"""The cache health check of "Clean up storage": SQLite's quick_check of cache.sqlite3, and setting a damaged cache aside (F1)."""
import os
import sqlite3
from pathlib import Path

from ._common import _broken_names
from .cleanup import _BUSY, CLEANUP_LOCK_TIMEOUT, _holding_run_lock, _sqlite_uri
from .signature import CACHE_FILE, CACHE_SIDE_FILES


# A damaged cache.sqlite3 (disk full, power loss, a bad sector) otherwise shows only as an
# error in a search. "Check cache" runs PRAGMA quick_check under the run lock of the results
# folder (it reads the whole file: a few seconds for a large cache, and no search may write
# meanwhile); a damaged file is never deleted, only renamed on the user's request, so the
# next search builds a new cache and analyzes every photo again.
# at most this many problems quick_check reports
CACHE_CHECK_LINES = 20


def _file_key(path):
    """(size, mtime_ns) of path, or None if it is missing: tells whether the file changed since a check."""
    try:
        stat = Path(path).stat()
    except FileNotFoundError:
        return None
    return stat.st_size, stat.st_mtime_ns


def _quick_check(cache):
    """Return ('ok' | 'damaged' | 'unreadable' | 'unchecked', details) of PRAGMA quick_check on the existing file cache.

    Opened read-write (never created), so a hot journal of a stopped search is rolled back
    first, as the next search would do. An error SQLite reports as damage (sqlite3's
    DatabaseError: "file is not a database", "database disk image is malformed") makes the
    file damaged. A disk I/O error (SQLITE_IOERR) makes it unreadable: a bad sector, which
    setting the file aside helps against, or a drive that is not reachable now (review). Any
    other error (OperationalError: e.g. the file cannot be opened or is locked) leaves it
    unchecked, since setting the file aside would not help.
    """
    try:
        con = sqlite3.connect(_sqlite_uri(cache, 'rw'), uri=True, timeout=5)
        try:
            rows = [str(row[0]) for row in con.execute(f'PRAGMA quick_check({CACHE_CHECK_LINES})')]
        finally:
            con.close()
    except sqlite3.OperationalError as exc:
        return ('unreadable' if _io_error(exc) else 'unchecked'), [str(exc)]
    except sqlite3.DatabaseError as exc:
        return 'damaged', [str(exc)]
    return ('ok', []) if rows == ['ok'] else ('damaged', rows[:CACHE_CHECK_LINES])


def _io_error(exc):
    """Whether the sqlite3 error exc is a disk I/O error (SQLITE_IOERR or one of its extended codes)."""
    code = getattr(exc, 'sqlite_errorcode', None)
    if code is not None:
        return code & 0xff == sqlite3.SQLITE_IOERR
    return str(exc).startswith('disk I/O error')


def cache_error(exc):
    """Whether the exception exc of a search is an error of the cache file itself (E50).

    'damaged' for an error SQLite reports as damage (exactly sqlite3.DatabaseError: "file is
    not a database", "database disk image is malformed"), 'unreadable' for a disk I/O error,
    as _quick_check tells them apart; None for anything else (e.g. a locked or full cache,
    or an error of a photo), which "Check cache" would not help against.
    """
    if type(exc) is sqlite3.DatabaseError:
        return 'damaged'
    if isinstance(exc, sqlite3.OperationalError) and _io_error(exc):
        return 'unreadable'
    return None


def cache_error_message(cache, exc):
    """The message of a search that stopped on the error exc of the cache file cache, or None (E50).

    Points to "Check cache" in the app instead of leaving SQLite's raw error alone; None if
    exc is no error of the cache file itself (cache_error).
    """
    kind = cache_error(exc)
    check = ('In the app, open "Clean up storage" and click "Check cache": it can set a damaged cache aside, and the '
             'next search then analyzes every photo again. Your photos are not affected.')
    if kind == 'damaged':
        return f'The feature cache {cache} is damaged ({exc}). {check}'
    if kind == 'unreadable':
        return (f'The feature cache {cache} could not be read or written ({exc}). Check that the drive of the results '
                f'folder is connected and working, then start the search again. If the error stays: {check}')
    return None


def cache_read_warning(cache, exc, count):
    """The warning of a search that finished although count photos could not be read from the cache (E50, review).

    exc: the first such error, an error of the cache file itself (cache_error). A damaged
    page can hit only a few rows: the search leaves out those photos instead of stopping,
    and its end points to "Check cache" (cache_error_message).
    """
    left_out = f'{count} photo was' if count == 1 else f'{count} photos were'
    return (f'{left_out} left out of this search because the feature cache could not be read for them. '
            f'{cache_error_message(cache, exc)}')


def check_cache(results, alive, lock_timeout=CLEANUP_LOCK_TIMEOUT):
    """Check the cache file of the folder results with SQLite's quick_check; return the result (F1).

    The result has refused (why nothing was checked, else None), state ('missing': no cache
    file; 'ok'; 'damaged'; 'unreadable': a disk I/O error; 'unchecked': the check itself
    failed otherwise; None if refused), details
    (the problems or the error) and file (size and mtime_ns of the file after the check, for
    set_cache_aside). Holds the run lock of results like clean_up, so it is refused while a
    search runs or is being started (alive as for clean_up), and no search starts meanwhile.
    Nothing is changed (but for the rollback of a hot journal, see _quick_check).
    """
    results = Path(results)
    cache = results / CACHE_FILE
    result = {'refused': None, 'state': 'missing', 'details': [], 'file': None}
    if not cache.is_file():
        return result
    with _holding_run_lock(results, alive, lock_timeout) as busy:
        if busy:
            result.update(refused=f'{_BUSY[busy]} Check the cache after it has finished.', state=None)
            return result
        if cache.is_file():
            result['state'], result['details'] = _quick_check(cache)
            result['file'] = _file_key(cache)
    return result


def cache_check_current(results, result):
    """Whether the cache file of results is still as the check_cache result result saw it (F1 review).

    False once the file was changed, created or removed since the check, e.g. by a cleanup
    (deleted rows, compacting), a search started in any tab or a rename, so the app drops
    the outdated result and its rename offer. A refused check stays (it says why, not what
    the file is like). One stat of the file.
    """
    if result.get('refused'):
        return True
    expected = result.get('file')
    return _file_key(Path(results) / CACHE_FILE) == (None if expected is None else tuple(expected))


def set_cache_aside(results, alive, expected, lock_timeout=CLEANUP_LOCK_TIMEOUT, now=None):
    """Rename the damaged cache file of results to <name>.broken-<YYYYMMDD-HHMMSS>; return the result (F1).

    Never deletes it. expected is the file of the check_cache result the user saw: a file
    changed or removed since is not renamed. The side files (CACHE_SIDE_FILES) get the same
    new name with their suffix, so no journal is left for a new cache; the date is the local
    time of now (a time.time() value; None: now), with -2, -3, ... if a name is taken. The
    next search then creates a new cache. Holds the run lock like check_cache. The result has
    refused (why nothing was renamed, else None) and renamed (the new names, the cache first).
    Raises OSError if a rename fails; the files renamed before it get their names back.
    """
    results = Path(results)
    cache = results / CACHE_FILE
    result = {'refused': None, 'renamed': []}
    with _holding_run_lock(results, alive, lock_timeout) as busy:
        if busy:
            result['refused'] = f'{_BUSY[busy]} Try again after it has finished.'
            return result
        if expected is None or _file_key(cache) != tuple(expected):
            result['refused'] = f'{CACHE_FILE} was changed or removed since the check. Check it again.'
            return result
        sides = [suffix for suffix in CACHE_SIDE_FILES if cache.with_name(CACHE_FILE + suffix).exists()]
        target = next(name for name in _broken_names(cache, now)
                      if not any(name.with_name(name.name + suffix).exists() for suffix in ('', *CACHE_SIDE_FILES)))
        # the side files first, while the cache keeps its name: a failure never leaves a
        # journal without its database
        moves = [(cache.with_name(CACHE_FILE + suffix), target.with_name(target.name + suffix)) for suffix in sides]
        moves.append((cache, target))
        done = []
        try:
            for source, destination in moves:
                os.rename(source, destination)
                done.append((source, destination))
        except OSError:
            for source, destination in reversed(done):
                try:
                    os.rename(destination, source)
                except OSError:  # the error of the rename is the one to report
                    continue
            raise
        result['renamed'] = [target.name, *(target.name + suffix for suffix in sides)]
    return result
