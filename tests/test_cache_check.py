"""The cache health check of "Clean up storage" and setting a damaged cache aside (framescout_core, F1)."""
import json
import os
import sqlite3
import time

import pytest

import framescout_core
from framescout_core import (CACHE_FILE, CACHE_SIDE_FILES, DEFAULT_YOLO_MODEL, MARKS_FILE, RUN_LOCK, RUN_STATUS,
                             RunLock, check_cache, cleanup_running, prepare_cache, set_cache_aside)

# 2026-11-02 12:30:45 local time
NOW = time.mktime((2026, 11, 2, 12, 30, 45, 0, 0, -1))
BROKEN = CACHE_FILE + '.broken-20261102-123045'


def no_engine(pid, status):
    return False


def healthy_cache(results, rows=300):
    """A cache as the engine writes it, with rows spread over many pages."""
    results.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(results / CACHE_FILE)
    try:
        signature = prepare_cache(con, True, 12, .3, DEFAULT_YOLO_MODEL)
        with con:
            con.executemany('INSERT INTO features VALUES (?, ?, ?, ?, ?, ?)',
                            [(f'C:/photos/{n}.jpg', signature, n, 1000 + n, '["Full image"]', os.urandom(512))
                             for n in range(rows)])
    finally:
        con.close()
    return results / CACHE_FILE


def damage(cache):
    """Overwrite pages in the middle of the file, e.g. after a disk error."""
    data = bytearray(cache.read_bytes())
    middle = len(data) // 2
    data[middle:middle + 8192] = b'\xff' * 8192
    cache.write_bytes(bytes(data))


def test_a_missing_cache_is_reported_as_missing(tmp_path):
    result = check_cache(tmp_path / 'results', no_engine)
    assert result['refused'] is None and result['state'] == 'missing'
    assert not (tmp_path / 'results').exists()  # nothing is created


def test_a_healthy_cache_passes(tmp_path):
    cache = healthy_cache(tmp_path)
    before = cache.read_bytes()
    result = check_cache(tmp_path, no_engine)
    assert result['refused'] is None and result['state'] == 'ok' and result['details'] == []
    assert cache.read_bytes() == before
    assert result['file'] == (cache.stat().st_size, cache.stat().st_mtime_ns)


def test_an_empty_file_counts_as_an_empty_cache(tmp_path):
    (tmp_path / CACHE_FILE).write_bytes(b'')  # SQLite treats it as an empty database
    assert check_cache(tmp_path, no_engine)['state'] == 'ok'


def test_a_file_that_is_no_database_is_damaged(tmp_path):
    (tmp_path / CACHE_FILE).write_bytes(b'x' * 4096)
    result = check_cache(tmp_path, no_engine)
    assert result['state'] == 'damaged' and result['details']
    assert (tmp_path / CACHE_FILE).read_bytes() == b'x' * 4096


def test_damaged_pages_are_found(tmp_path):
    cache = healthy_cache(tmp_path)
    damage(cache)
    result = check_cache(tmp_path, no_engine)
    assert result['state'] == 'damaged' and result['details']
    assert len(result['details']) <= framescout_core.CACHE_CHECK_LINES


def test_an_error_that_is_no_damage_leaves_the_cache_unchecked(tmp_path, monkeypatch):
    healthy_cache(tmp_path)

    def connect(*args, **kwargs):
        raise sqlite3.OperationalError('unable to open database file')

    monkeypatch.setattr(framescout_core.cache_check.sqlite3, 'connect', connect)
    result = check_cache(tmp_path, no_engine)
    assert result['state'] == 'unchecked' and result['details'] == ['unable to open database file']


class FailingConnection:
    """A connection whose quick_check fails with error, e.g. on a bad sector of the disk."""

    def __init__(self, error):
        self.error = error

    def execute(self, sql):
        raise self.error

    def close(self):
        pass


@pytest.mark.parametrize('code', [sqlite3.SQLITE_IOERR, sqlite3.SQLITE_IOERR | (2 << 8), None])
def test_a_disk_io_error_makes_the_cache_unreadable(tmp_path, monkeypatch, code):
    # review: a bad sector shows as "disk I/O error" (an OperationalError), and setting the
    # file aside is the remedy, so it is offered (SQLITE_IOERR_READ is an extended code)
    cache = healthy_cache(tmp_path)
    error = sqlite3.OperationalError('disk I/O error')
    if code is not None:
        error.sqlite_errorcode = code
    monkeypatch.setattr(framescout_core.cache_check.sqlite3, 'connect', lambda *args, **kwargs: FailingConnection(error))
    result = check_cache(tmp_path, no_engine)
    assert result['state'] == 'unreadable' and result['details'] == ['disk I/O error']
    assert result['file'] == (cache.stat().st_size, cache.stat().st_mtime_ns)
    monkeypatch.undo()
    done = set_cache_aside(tmp_path, no_engine, result['file'], now=NOW)
    assert done == {'refused': None, 'renamed': [BROKEN]}


def test_a_locked_cache_stays_unchecked(tmp_path, monkeypatch):
    healthy_cache(tmp_path)
    error = sqlite3.OperationalError('database is locked')
    error.sqlite_errorcode = sqlite3.SQLITE_BUSY
    monkeypatch.setattr(framescout_core.cache_check.sqlite3, 'connect', lambda *args, **kwargs: FailingConnection(error))
    assert check_cache(tmp_path, no_engine)['state'] == 'unchecked'


def test_the_check_is_refused_while_a_search_runs(tmp_path):
    healthy_cache(tmp_path)
    lock = RunLock(tmp_path / RUN_LOCK)
    assert lock.acquire()
    try:
        result = check_cache(tmp_path, no_engine, lock_timeout=0.05)
    finally:
        lock.release()
    assert result['refused'] and result['state'] is None


def test_the_check_is_refused_while_a_search_is_being_started(tmp_path):
    healthy_cache(tmp_path)
    (tmp_path / RUN_STATUS).write_text(json.dumps({'phase': 'starting', 'pid': 4242}), encoding='utf-8')
    result = check_cache(tmp_path, lambda pid, status: pid == 4242)
    assert result['refused'] and result['state'] is None


def test_the_check_holds_the_run_lock(tmp_path, monkeypatch):
    healthy_cache(tmp_path)
    seen = []
    real = framescout_core.cache_check._quick_check

    def check(cache):
        seen.append((not RunLock(tmp_path / RUN_LOCK).acquire(), cleanup_running(tmp_path)))
        return real(cache)

    monkeypatch.setattr(framescout_core.cache_check, '_quick_check', check)
    assert check_cache(tmp_path, no_engine)['state'] == 'ok'
    assert seen == [(True, True)]
    assert not cleanup_running(tmp_path)
    lock = RunLock(tmp_path / RUN_LOCK)
    assert lock.acquire()  # released afterwards
    lock.release()


# --- setting a damaged cache aside ----------------------------------------------------------

def checked_damaged(tmp_path):
    (tmp_path / CACHE_FILE).write_bytes(b'x' * 4096)
    (tmp_path / MARKS_FILE).write_text('{}', encoding='utf-8')
    result = check_cache(tmp_path, no_engine)
    assert result['state'] == 'damaged'
    return result


def test_a_damaged_cache_is_renamed_never_deleted(tmp_path):
    result = checked_damaged(tmp_path)
    (tmp_path / (CACHE_FILE + '-journal')).write_bytes(b'journal')  # goes with it, never onto a new cache
    done = set_cache_aside(tmp_path, no_engine, result['file'], now=NOW)
    assert done == {'refused': None, 'renamed': [BROKEN, BROKEN + '-journal']}
    assert not (tmp_path / CACHE_FILE).exists() and not (tmp_path / (CACHE_FILE + '-journal')).exists()
    assert (tmp_path / BROKEN).read_bytes() == b'x' * 4096
    assert (tmp_path / (BROKEN + '-journal')).read_bytes() == b'journal'
    assert (tmp_path / MARKS_FILE).read_text(encoding='utf-8') == '{}'
    assert CACHE_SIDE_FILES == ('-journal', '-wal', '-shm')


def test_a_name_in_use_gets_a_number(tmp_path):
    (tmp_path / BROKEN).write_bytes(b'older')
    result = checked_damaged(tmp_path)
    done = set_cache_aside(tmp_path, no_engine, result['file'], now=NOW)
    assert done['renamed'] == [BROKEN + '-2']
    assert (tmp_path / BROKEN).read_bytes() == b'older'


def test_a_cache_changed_since_the_check_is_not_renamed(tmp_path):
    result = checked_damaged(tmp_path)
    healthy_cache(tmp_path / 'new')
    os.replace(tmp_path / 'new' / CACHE_FILE, tmp_path / CACHE_FILE)  # e.g. restored by hand
    done = set_cache_aside(tmp_path, no_engine, result['file'], now=NOW)
    assert done['refused'] and done['renamed'] == []
    assert (tmp_path / CACHE_FILE).exists() and not (tmp_path / BROKEN).exists()


def test_a_missing_cache_is_not_renamed(tmp_path):
    result = checked_damaged(tmp_path)
    (tmp_path / CACHE_FILE).unlink()
    assert set_cache_aside(tmp_path, no_engine, result['file'], now=NOW)['refused']


def test_setting_aside_is_refused_while_a_search_runs(tmp_path):
    result = checked_damaged(tmp_path)
    lock = RunLock(tmp_path / RUN_LOCK)
    assert lock.acquire()
    try:
        done = set_cache_aside(tmp_path, no_engine, result['file'], lock_timeout=0.05, now=NOW)
    finally:
        lock.release()
    assert done['refused'] and (tmp_path / CACHE_FILE).exists()


def test_a_failed_rename_puts_the_side_files_back(tmp_path, monkeypatch):
    result = checked_damaged(tmp_path)
    (tmp_path / (CACHE_FILE + '-journal')).write_bytes(b'journal')
    real = os.rename

    def rename(src, dst):
        if os.path.basename(src) == CACHE_FILE:
            raise PermissionError('in use')
        return real(src, dst)

    monkeypatch.setattr(framescout_core.cache_check.os, 'rename', rename)
    with pytest.raises(OSError):
        set_cache_aside(tmp_path, no_engine, result['file'], now=NOW)
    assert (tmp_path / CACHE_FILE).exists() and (tmp_path / (CACHE_FILE + '-journal')).read_bytes() == b'journal'
    assert not list(tmp_path.glob('*.broken-*'))
