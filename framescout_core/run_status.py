"""The status file of a search run (A4, A5) and how the app reads it."""
import json
import time
from datetime import datetime
from pathlib import Path

from ._common import _replace_with_retry


# One search at a time per output folder (A4): the engine holds RUN_LOCK in the output
# folder while it runs and reports its phase and progress in RUN_STATUS (A5), which the
# app reads to show a run again after a browser reload, in another tab or session.
RUN_LOCK = 'run.lock'
RUN_STATUS = 'run-status.json'
STATUS_FORMAT = 1
# phases in run order; the app writes "starting", the engine the others
PHASE_LABELS = {
    'starting': 'Starting the search',
    'scanning': 'Looking for photos',
    'loading': 'Loading the AI models',
    'analyzing': 'Analyzing photos',
    'scoring': 'Scoring photos',
    'exporting': 'Writing galleries',
    'finished': 'Finished',
    'failed': 'Failed',
    'interrupted': 'Interrupted',
}
FINAL_PHASES = frozenset({'finished', 'failed', 'interrupted'})


def _timestamp():
    return datetime.now().astimezone().isoformat(timespec='seconds')


class StatusReporter:
    """Writes the status file of a search run: process id, phase and progress (A4, A5).

    update() merges the given fields; it writes the file when the phase changes, when force
    is set, and otherwise at most every interval seconds, so a progress update per photo
    costs nothing. The file is replaced atomically (never half-written). Writing is best
    effort: on Windows replacing a file fails while another process has it open (the app
    reads it every two seconds); a failed update is retried with the next one and never
    stops the search. finish() writes the final phase, trying harder.
    """

    def __init__(self, path, pid, interval=1.0, clock=time.monotonic, retries=20, retry_delay=0.05):
        self.path = Path(path)
        self.interval, self.clock, self.retries, self.retry_delay = interval, clock, retries, retry_delay
        started = _timestamp()
        self.state = {'format': STATUS_FORMAT, 'pid': pid, 'phase': None, 'started': started, 'updated': started,
                      'done': 0, 'total': 0, 'new': 0, 'cached': 0, 'errors': 0,
                      'exit_code': None, 'message': None}
        self._written = None  # clock() of the last successful write

    def update(self, phase=None, force=False, **fields):
        """Merge phase and fields into the status; write it if due. Returns True if written now."""
        if phase is not None and phase != self.state['phase']:
            # a new phase starts its own progress count; the analysis counts are kept
            self.state.update(phase=phase, done=0, total=0)
            force = True
        self.state.update(fields)
        if not force and self._written is not None and self.clock() - self._written < self.interval:
            return False
        # a phase change is worth a few retries, a single progress update is not
        return self._write(attempts=1 + self.retries if force else 1)

    def finish(self, phase, exit_code, message=None):
        """Write the final phase (one of FINAL_PHASES) with the exit code; returns True if written."""
        self.state.update(phase=phase, exit_code=exit_code, message=message)
        return self._write(attempts=1 + self.retries)

    def _write(self, attempts):
        self.state['updated'] = _timestamp()
        if not write_status(self.path, self.state, attempts, self.retry_delay):
            return False
        self._written = self.clock()
        return True


def write_status(path, status, attempts=1, retry_delay=0.05):
    """Replace the status file path with the dict status atomically; return True if written.

    Tries up to attempts times, retry_delay seconds apart; never raises OSError.
    """
    data = (json.dumps(status, ensure_ascii=False, indent=1) + '\n').encode('utf-8')
    try:
        _replace_with_retry(path, data, attempts, retry_delay, durable=False)
    except OSError:
        return False
    return True


def stopped_status(status):
    """Return status marked as stopped from the app: phase "interrupted", progress kept.

    terminate()/kill() skips the engine's own final write, so the app writes this instead.
    """
    return {**status, 'phase': 'interrupted', 'exit_code': None, 'message': 'Stopped in the app.',
            'updated': _timestamp()}


def started_in_time(status, create_time, tolerance=2.0):
    """Return True if a process created at create_time (seconds since the epoch) can be the run of status.

    The process of a run exists before its status is written (the app writes "starting"
    after Popen, the engine its status after it started), so a process with the status's
    pid that was created later got the pid after the run's process ended (review). The
    tolerance covers the whole seconds of "started" and clock rounding.
    """
    try:
        started = datetime.fromisoformat(status['started']).timestamp()
    except (KeyError, TypeError, ValueError):
        return False
    return create_time <= started + tolerance


def final_status(code):
    """Return (phase, message) of the engine's final status for its exit code."""
    if code == 0:
        return 'finished', None
    if code == 130:
        return 'interrupted', 'Interrupted (Ctrl+C).'
    return 'failed', f'The search ended with exit code {code}.'


def read_status(path):
    """Return the status dict of a run (see StatusReporter), or None if missing or unreadable."""
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):  # ValueError includes JSON and Unicode decoding errors
        return None
    return data if isinstance(data, dict) else None


def run_active(status, held, alive):
    """Return True if a search is running in the output folder of status.

    held: whether the RunLock of that folder is held (lock_held). Without the lock, a run
    counts only while it is being started: the app writes the status "starting" with the
    engine's process id before the engine takes the lock, and alive(pid) tells whether
    that process still runs. A status that is not final (e.g. after kill(), which skips
    the final write) does not count once its process is gone.
    """
    if held:
        return True
    if not status or status.get('phase') in FINAL_PHASES:
        return False
    pid = status.get('pid')
    return isinstance(pid, int) and not isinstance(pid, bool) and bool(alive(pid))


def _count(status, key):
    value = status.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def status_fraction(status):
    """Return the progress of the current phase between 0 and 1, or None if it has no count."""
    done, total = _count(status, 'done'), _count(status, 'total')
    if done is None or not total or total < 0:
        return None
    return min(max(done / total, 0.0), 1.0)


def status_text(status):
    """Return the line the app shows for a status: the phase and, if it counts, its progress."""
    phase = status.get('phase')
    label = PHASE_LABELS.get(phase, str(phase))
    done, total = _count(status, 'done'), _count(status, 'total')
    if not total or done is None:
        return label
    if phase == 'analyzing':
        new, cached, errors = (_count(status, k) or 0 for k in ('new', 'cached', 'errors'))
        return f'{label}: {done:,}/{total:,} · {new:,} new · {cached:,} from cache · {errors:,} errors'
    if phase == 'exporting':
        return f'{label}: {done:,}/{total:,} matches'
    return f'{label}: {done:,}/{total:,}'
