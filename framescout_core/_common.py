"""Internal helpers that several areas share (not part of the package's interface).

Atomic file writes (_publish_via_temp, _publish_new, _replace_atomically,
_replace_with_retry, _publish_together for several files), retrying an action (_retry),
reading a file (_read_with_retry) or a JSON object file (_read_json_object) with retries, the
save lock of a file (_file_lock), the locked read-change-write of a JSON file
(_update_locked) and the comparable form of a path (_path_key).
"""
import json
import os
import tempfile
import time
from contextlib import contextmanager
from functools import partial
from pathlib import Path

from .locks import RunLock


def _path_key(path):
    """Comparable form of a path: resolved, and case-insensitive where the OS is (Windows)."""
    return os.path.normcase(path.resolve())


def _temp_path(target, suffix='.tmp'):
    """Create an empty temporary file <target name>.<random><suffix> in target's folder; return its path.

    The random part is tempfile's: 8 characters of a-z, 0-9 and _ (auto_cleanup relies on it).
    """
    fd, name = tempfile.mkstemp(dir=target.parent, prefix=target.name + '.', suffix=suffix)
    os.close(fd)
    return Path(name)


def _flush_to_disk(path):
    with open(path, 'r+b') as handle:
        os.fsync(handle.fileno())


def _publish_via_temp(target, write, publish, suffix='.tmp', durable=True):
    """Create target from a complete temporary file; never leave a partial target behind.

    write(tmp) fills a new temporary file in target's folder (named <target name>.<random>
    <suffix>); with durable, its data is flushed to disk (fsync) so that after a power
    loss the final name cannot point to an empty or partial file. Then publish(tmp, target)
    gives it the final name (os.replace, or _publish_new to never replace a file). The
    temporary file is removed whatever happens.
    """
    tmp = _temp_path(target, suffix)
    try:
        write(tmp)
        if durable:
            _flush_to_disk(tmp)
        publish(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


def _retry(action, attempts, retry_delay):
    """Return action(), trying up to attempts times, retry_delay seconds apart, while it raises OSError.

    On Windows, replacing a file fails while another process or thread has it open, e.g. an
    app session reading it or a virus scanner. Raises the last OSError if every try fails.
    """
    for attempt in range(max(attempts, 1)):
        try:
            return action()
        except OSError:
            if attempt + 1 >= attempts:
                raise
            time.sleep(retry_delay)


def _publish_together(files, attempts, retry_delay, replace=os.replace):
    """Replace several files at once as far as a file system allows; files: [(target Path, bytes)].

    Every file is first written in full to its own temporary file (see _temp_path) and
    flushed to disk, and the current content of every target is read; only then are they
    given their names, in the order of files, each rename tried up to attempts times
    retry_delay seconds apart (see _retry). An error or a stop while writing therefore leaves
    every target as it was. If a rename fails every try, the targets replaced before it get
    their previous content back (one that did not exist is removed again) as far as that
    works, and the error is raised; only a process killed between the renames, or a failed
    restore, can leave some targets replaced (E45). The temporary files are removed whatever
    happens (a process killed meanwhile leaves them, see auto_cleanup).
    Raises the OSError of a write, a read or a rename that failed every try.
    """
    temps = []
    try:
        for target, data in files:
            tmp = _temp_path(target)
            temps.append(tmp)
            tmp.write_bytes(data)
            _flush_to_disk(tmp)
        previous = [_previous_content(target, attempts, retry_delay) for target, _ in files]
        for index, ((target, _), tmp) in enumerate(zip(files, temps)):
            try:
                _retry(partial(replace, tmp, target), attempts, retry_delay)
            except OSError:
                _restore(files[:index], previous, attempts, retry_delay, replace)
                raise
    finally:
        for tmp in temps:
            tmp.unlink(missing_ok=True)


def _previous_content(target, attempts, retry_delay):
    """The bytes of target, or None if it does not exist (read with retries)."""
    try:
        return _read_with_retry(target.read_bytes, attempts, retry_delay)
    except FileNotFoundError:
        return None


def _restore(files, previous, attempts, retry_delay, replace):
    """Give the targets of files the content previous lists for them again, last first; best effort."""
    for (target, _), data in reversed(list(zip(files, previous))):
        try:
            if data is None:
                _retry(partial(target.unlink, missing_ok=True), attempts, retry_delay)
            else:
                _publish_via_temp(target, lambda tmp: tmp.write_bytes(data),
                                  lambda tmp, name: _retry(partial(replace, tmp, name), attempts, retry_delay))
        except OSError:  # the error of the rename is the one to report
            continue


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
    retry_delay seconds apart (_retry). Raises the last OSError if every try fails.
    """
    _retry(lambda: _publish_via_temp(Path(target), lambda tmp: tmp.write_bytes(data), os.replace, durable=durable),
           attempts, retry_delay)


def _read_with_retry(read, attempts, retry_delay):
    """Return read(), trying up to attempts times, retry_delay seconds apart.

    On Windows, reading a file fails for a moment while another session replaces it, so an
    OSError is retried; FileNotFoundError is passed on at once, the last OSError after the
    last try.
    """
    for attempt in range(max(attempts, 1)):
        try:
            return read()
        except FileNotFoundError:
            raise
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
    try:
        text = _read_with_retry(lambda: Path(filename).read_text(encoding='utf-8-sig'), attempts, retry_delay)
    except FileNotFoundError:
        return {}
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
    with _file_lock(filename, lock_timeout):
        document = update(read())
        if document is not None:
            data = (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
            _replace_with_retry(filename, data, attempts, retry_delay)


@contextmanager
def _file_lock(filename, timeout):
    """Hold a RunLock on <filename>.lock while the block runs, so no other save comes in between.

    App sessions are threads of one process, and two RunLocks conflict there too. The lock
    file stays (empty). Raises OSError if the lock is not free within timeout seconds.
    """
    filename = Path(filename)
    lock = RunLock(filename.with_name(filename.name + '.lock'))
    if not lock.acquire(timeout=timeout, poll=0.01):
        raise OSError(f'{filename.name} is being saved by another session')
    try:
        yield
    finally:
        lock.release()
