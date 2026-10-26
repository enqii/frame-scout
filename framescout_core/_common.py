"""Internal helpers that several areas share (not part of the package's interface).

Atomic file writes (_publish_via_temp, _publish_new, _replace_atomically,
_replace_with_retry), reading a JSON object file with retries (_read_json_object), the
locked read-change-write of a JSON file (_update_locked) and the comparable form of a
path (_path_key).
"""
import json
import os
import tempfile
import time
from pathlib import Path

from .locks import RunLock


def _path_key(path):
    """Comparable form of a path: resolved, and case-insensitive where the OS is (Windows)."""
    return os.path.normcase(path.resolve())


def _publish_via_temp(target, write, publish, suffix='.tmp', durable=True):
    """Create target from a complete temporary file; never leave a partial target behind.

    write(tmp) fills a new temporary file in target's folder (named <target name>.<random>
    <suffix>); with durable, its data is flushed to disk (fsync) so that after a power
    loss the final name cannot point to an empty or partial file. Then publish(tmp, target)
    gives it the final name (os.replace, or _publish_new to never replace a file). The
    temporary file is removed whatever happens.
    """
    fd, name = tempfile.mkstemp(dir=target.parent, prefix=target.name + '.', suffix=suffix)
    os.close(fd)
    tmp = Path(name)
    try:
        write(tmp)
        if durable:
            with open(tmp, 'r+b') as handle:
                os.fsync(handle.fileno())
        publish(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


def _publish_new(tmp, target):
    """Give the complete file tmp the name target; raise FileExistsError if target exists."""
    if os.name == 'nt':
        os.rename(tmp, target)  # never replaces an existing file on Windows (any file system)
    else:
        os.link(tmp, target)  # POSIX rename would replace target; a hard link does not


def _replace_atomically(target, data):
    """Replace target with data via a temporary file that is flushed to disk first."""
    _publish_via_temp(target, lambda tmp: tmp.write_bytes(data), os.replace)


def _replace_with_retry(target, data, attempts, retry_delay, durable=True):
    """Replace target with the bytes data atomically, trying up to attempts times.

    On Windows, replacing a file fails while another process or thread has it open, e.g. an
    app session reading the status or settings file at that moment; the tries are
    retry_delay seconds apart. Raises the last OSError if every try fails.
    """
    for attempt in range(max(attempts, 1)):
        try:
            _publish_via_temp(Path(target), lambda tmp: tmp.write_bytes(data), os.replace, durable=durable)
            return
        except OSError:
            if attempt + 1 >= attempts:
                raise
            time.sleep(retry_delay)


def _read_json_object(filename, what, attempts=5, retry_delay=0.05):
    """Return the JSON object of the file filename ({} if it is missing); ValueError if unreadable.

    On Windows, reading fails for a moment while another session replaces the file, so an
    OSError is retried up to attempts times, retry_delay seconds apart. what names the file
    in the error for a file that is not a JSON object.
    """
    for attempt in range(max(attempts, 1)):
        try:
            text = Path(filename).read_text(encoding='utf-8-sig')
            break
        except FileNotFoundError:
            return {}
        except OSError:
            if attempt + 1 >= attempts:
                raise
            time.sleep(retry_delay)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f'The {what} must be a JSON object.')
    return data


def _update_locked(filename, read, update, attempts, retry_delay, lock_timeout):
    """Read, change and replace the JSON file filename under a RunLock on <filename>.lock.

    read() returns the current content, update(content) the new one, or None to leave the
    file as it is. App sessions are threads of one process, and two RunLocks conflict there
    too, so two sessions saving at the same moment cannot lose a change; the lock file stays
    (empty). The file is replaced atomically, tried up to attempts times. Raises OSError if
    the lock is not free within lock_timeout seconds; errors of read() and update() (e.g.
    ValueError for an unreadable file, which is then never replaced) are passed on.
    """
    filename = Path(filename)
    lock = RunLock(filename.with_name(filename.name + '.lock'))
    if not lock.acquire(timeout=lock_timeout, poll=0.01):
        raise OSError(f'{filename.name} is being saved by another session')
    try:
        document = update(read())
        if document is not None:
            data = (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
            _replace_with_retry(filename, data, attempts, retry_delay)
    finally:
        lock.release()
