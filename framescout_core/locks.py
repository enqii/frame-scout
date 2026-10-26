"""The operating-system file lock (RunLock, A4) used for search runs and for saving JSON files."""
import os
import time
from pathlib import Path

if os.name == 'nt':
    import msvcrt
else:
    import fcntl


def _try_lock(fd):
    """Lock fd exclusively without waiting; raise OSError if another handle holds the lock."""
    if os.name == 'nt':
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # one byte, beyond the end of the empty file
    else:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(fd):
    if os.name == 'nt':
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


class RunLock:
    """An exclusive lock on a file, held while a search runs in an output folder (A4).

    It is a lock of the operating system (Windows byte-range lock, flock elsewhere) on an
    open file, not the existence of the file: when the process ends in any way, including
    terminate()/kill() or a crash, the operating system releases it, so a stopped run never
    leaves a stale lock behind. The file stays in place (empty) after the run. Two RunLock
    objects conflict even within one process.
    """

    def __init__(self, path):
        self.path = Path(path)
        self._fd = None

    @property
    def held(self):
        return self._fd is not None

    def acquire(self, timeout=0.0, poll=0.1, clock=time.monotonic, sleep=time.sleep):
        """Take the lock, trying for up to timeout seconds; return True if it is held now."""
        if self._fd is not None:
            return True
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT)  # not inherited by child processes (PEP 446)
        deadline = clock() + timeout
        while True:
            try:
                _try_lock(fd)
            except OSError:
                if clock() >= deadline:
                    os.close(fd)
                    return False
                sleep(poll)
            else:
                self._fd = fd
                return True

    def release(self):
        """Give the lock back (nothing happens if it is not held)."""
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            _unlock(fd)
        except OSError:
            pass  # closing the file releases the lock as well
        finally:
            os.close(fd)


def lock_held(path):
    """Return True if a process holds the RunLock on path; never creates the file.

    Checks by taking the lock for a moment, so a RunLock.acquire at that very moment fails
    once: the engine and the app therefore acquire with a timeout. A file that exists but
    cannot be opened (e.g. PermissionError while it is pending delete or held by an antivirus
    scanner on Windows) counts as held, the safe side: no start (review).
    """
    try:
        fd = os.open(path, os.O_RDWR)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    try:
        try:
            _try_lock(fd)
        except OSError:
            return True
        _unlock(fd)
        return False
    finally:
        os.close(fd)
