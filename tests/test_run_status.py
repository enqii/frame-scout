"""Run lock and status file: one search per output folder, progress the app can read back (A4, A5)."""
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

from framescout_core import (FINAL_PHASES, RUN_LOCK, RUN_STATUS, RunLock, StatusReporter, final_status, lock_held,
                             read_status, run_active, started_in_time, status_fraction, status_text,
                             stopped_status, write_status)

REPO = Path(__file__).resolve().parents[1]


# --- RunLock: held by the engine while it runs ---

def test_a_second_lock_on_the_same_file_fails_until_the_first_is_released(tmp_path):
    path = tmp_path / RUN_LOCK
    first, second = RunLock(path), RunLock(path)
    assert first.acquire()
    try:
        assert first.held
        assert not second.acquire()
        assert not second.held
        assert lock_held(path)
    finally:
        first.release()
    assert not first.held
    assert not lock_held(path)
    assert second.acquire()
    second.release()


def test_checking_the_lock_does_not_take_it_from_its_holder(tmp_path):
    path = tmp_path / RUN_LOCK
    holder = RunLock(path)
    assert holder.acquire()
    try:
        assert lock_held(path)
        assert lock_held(path)  # still held after the first check
        assert not RunLock(path).acquire()
    finally:
        holder.release()


def test_a_missing_lock_file_is_not_held_and_not_created(tmp_path):
    path = tmp_path / RUN_LOCK
    assert not lock_held(path)
    assert not path.exists()
    assert not lock_held(tmp_path / 'missing-folder' / RUN_LOCK)


def test_acquire_waits_up_to_the_timeout(tmp_path):
    path = tmp_path / RUN_LOCK
    holder = RunLock(path)
    assert holder.acquire()
    now = [0.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    try:
        assert not RunLock(path).acquire(timeout=1.0, poll=0.25, clock=lambda: now[0], sleep=sleep)
        assert sleeps and sum(sleeps) >= 1.0
    finally:
        holder.release()


def test_acquire_gets_the_lock_once_the_holder_lets_go(tmp_path):
    # the app holds the lock for a moment while it starts the engine, or while it checks
    # it; the engine retries instead of giving up at once
    path = tmp_path / RUN_LOCK
    holder = RunLock(path)
    assert holder.acquire()
    waiter = RunLock(path)
    assert waiter.acquire(timeout=5.0, poll=0.01, sleep=lambda _: holder.release())
    assert waiter.held
    waiter.release()


def test_release_is_idempotent(tmp_path):
    lock = RunLock(tmp_path / RUN_LOCK)
    lock.release()  # never acquired
    assert lock.acquire()
    lock.release()
    lock.release()
    assert not lock_held(tmp_path / RUN_LOCK)


def test_acquire_twice_keeps_one_lock(tmp_path):
    lock = RunLock(tmp_path / RUN_LOCK)
    assert lock.acquire()
    assert lock.acquire()
    lock.release()
    assert not lock_held(tmp_path / RUN_LOCK)


HOLD_LOCK = '''
import sys, time
from pathlib import Path
from framescout_core import RunLock
lock = RunLock(Path(sys.argv[1]))
print('locked' if lock.acquire() else 'busy', flush=True)
time.sleep(60)
'''


def test_the_lock_of_a_killed_process_is_released(tmp_path):
    # the app's Stop button ends the engine with terminate()/kill(), which skips every
    # finally block: the operating system must release the lock, so a stopped or crashed
    # run never blocks the next start (A4)
    path = tmp_path / RUN_LOCK
    proc = subprocess.Popen([sys.executable, '-c', HOLD_LOCK, str(path)], cwd=str(REPO),
                            stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == 'locked'
        assert lock_held(path)
        assert not RunLock(path).acquire()
    finally:
        proc.kill()
        proc.wait()
        proc.stdout.close()
    deadline = time.monotonic() + 10
    while lock_held(path) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not lock_held(path)


# --- StatusReporter / read_status: the status file the app reads ---

class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_the_first_update_is_written_with_pid_and_start_time(tmp_path):
    path = tmp_path / RUN_STATUS
    StatusReporter(path, 1234).update('loading')
    status = read_status(path)
    assert status['pid'] == 1234
    assert status['phase'] == 'loading'
    assert status['started'] and status['updated']
    assert status['exit_code'] is None
    assert (status['done'], status['total'], status['new'], status['cached'], status['errors']) == (0, 0, 0, 0, 0)


def test_progress_updates_are_throttled_but_phase_changes_are_written_at_once(tmp_path):
    path, clock = tmp_path / RUN_STATUS, Clock()
    reporter = StatusReporter(path, 1, interval=1.0, clock=clock)
    reporter.update('analyzing', total=100)
    reporter.update(done=10)
    assert read_status(path)['done'] == 0  # too soon after the last write
    clock.now = 1.5
    reporter.update(done=20)
    assert read_status(path)['done'] == 20
    reporter.update(done=30)
    reporter.update('scoring', total=100)  # a new phase is written at once
    status = read_status(path)
    assert (status['phase'], status['done'], status['total']) == ('scoring', 0, 100)


def test_a_new_phase_resets_its_progress_but_keeps_the_analysis_counts(tmp_path):
    path = tmp_path / RUN_STATUS
    reporter = StatusReporter(path, 1)
    reporter.update('analyzing', done=50, total=50, new=40, cached=9, errors=1, force=True)
    reporter.update('exporting', total=12)
    status = read_status(path)
    assert (status['done'], status['total']) == (0, 12)
    assert (status['new'], status['cached'], status['errors']) == (40, 9, 1)


def test_forced_updates_are_written_immediately(tmp_path):
    path, clock = tmp_path / RUN_STATUS, Clock()
    reporter = StatusReporter(path, 1, interval=10.0, clock=clock)
    reporter.update('analyzing', total=5)
    reporter.update(done=5, force=True)
    assert read_status(path)['done'] == 5


def test_finish_writes_the_final_phase_and_exit_code(tmp_path):
    path = tmp_path / RUN_STATUS
    reporter = StatusReporter(path, 1)
    reporter.update('analyzing', total=3)
    assert reporter.finish('failed', 2, 'Photo folder does not exist')
    status = read_status(path)
    assert status['phase'] == 'failed'
    assert status['exit_code'] == 2
    assert status['message'] == 'Photo folder does not exist'
    assert 'failed' in FINAL_PHASES


def test_a_failed_write_does_not_raise_and_is_retried_later(tmp_path):
    # the app reads the file every two seconds; on Windows replacing a file that is open
    # for reading fails for that moment, which must not stop the search
    path = tmp_path / RUN_STATUS
    path.mkdir()  # replacing a folder with a file always fails
    reporter = StatusReporter(path, 1, retries=2, retry_delay=0)
    reporter.update('analyzing', total=10)
    assert not reporter.finish('finished', 0)
    path.rmdir()
    reporter.update(done=1)  # the pending state is written with the next update
    assert read_status(path)['phase'] == 'finished'


def test_the_status_file_is_written_atomically(tmp_path):
    path = tmp_path / RUN_STATUS
    StatusReporter(path, 1).update('loading')
    assert [x.name for x in tmp_path.iterdir()] == [RUN_STATUS]  # no temporary files left


def test_unreadable_status_files_read_as_none(tmp_path):
    path = tmp_path / RUN_STATUS
    assert read_status(path) is None  # missing
    path.write_text('{"pid": 1, "phase": "anal', encoding='utf-8')
    assert read_status(path) is None
    path.write_text('[1, 2]', encoding='utf-8')
    assert read_status(path) is None
    path.write_bytes(b'\xff\xfe\x00')
    assert read_status(path) is None


def test_the_status_file_is_json_with_a_format_version(tmp_path):
    path = tmp_path / RUN_STATUS
    StatusReporter(path, 7).update('loading')
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['format'] == 1


# --- run_active: is a search running in this output folder? ---

def never(pid):
    raise AssertionError('alive() must not be called')


def test_a_held_lock_means_a_run_is_active():
    assert run_active(None, True, never)
    assert run_active({'phase': 'finished', 'pid': 1}, True, never)


def test_a_starting_run_counts_while_its_process_lives():
    # between the app's start and the engine taking the lock, only the status written by
    # the app ("starting", with the engine's process id) shows the run (A4)
    status = {'phase': 'starting', 'pid': 42}
    assert run_active(status, False, lambda pid: pid == 42)
    assert not run_active(status, False, lambda pid: False)


def test_without_the_lock_an_unfinished_status_of_a_dead_process_is_not_active():
    # a run ended with kill() never writes its final status
    assert not run_active({'phase': 'analyzing', 'pid': 42}, False, lambda pid: False)


def test_final_or_missing_status_without_the_lock_is_not_active():
    for phase in FINAL_PHASES:
        assert not run_active({'phase': phase, 'pid': 42}, False, never)
    assert not run_active(None, False, never)
    assert not run_active({'phase': 'analyzing'}, False, never)  # no pid
    assert not run_active({'phase': 'analyzing', 'pid': 'x'}, False, never)


# --- status_text / status_fraction: what the progress bar shows (A5) ---

def test_analysis_progress_names_new_cached_and_errors():
    status = {'phase': 'analyzing', 'done': 25, 'total': 4997, 'new': 20, 'cached': 4, 'errors': 1}
    assert status_text(status) == 'Analyzing photos: 25/4,997 · 20 new · 4 from cache · 1 errors'
    assert status_fraction(status) == pytest.approx(25 / 4997)


def test_later_phases_have_their_own_progress():
    assert status_text({'phase': 'scoring', 'done': 3, 'total': 10}) == 'Scoring photos: 3/10'
    assert status_text({'phase': 'exporting', 'done': 5, 'total': 150}) == 'Writing galleries: 5/150 matches'
    assert status_fraction({'phase': 'exporting', 'done': 5, 'total': 150}) == pytest.approx(5 / 150)


def test_phases_without_a_count_show_their_name_only():
    assert status_text({'phase': 'loading'}) == 'Loading the AI models'
    assert status_fraction({'phase': 'loading'}) is None
    assert status_fraction({'phase': 'analyzing', 'done': 0, 'total': 0}) is None
    assert status_text({'phase': 'something-new'}) == 'something-new'


def test_the_fraction_stays_between_zero_and_one():
    assert status_fraction({'phase': 'scoring', 'done': 12, 'total': 10}) == 1.0
    assert status_fraction({'phase': 'scoring', 'done': -1, 'total': 10}) == 0.0
    assert status_fraction({'phase': 'scoring', 'done': 'x', 'total': 10}) is None


# --- write_status / stopped_status: the app marks a run it stopped ---

def test_write_status_round_trips(tmp_path):
    path = tmp_path / RUN_STATUS
    assert write_status(path, {'pid': 3, 'phase': 'loading'})
    assert read_status(path) == {'pid': 3, 'phase': 'loading'}


def test_write_status_retries_a_failed_replace(tmp_path, monkeypatch):
    # the app reads the file every two seconds; on Windows a replace fails for that moment
    real_replace = os.replace
    calls = []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) == 1:
            raise PermissionError('in use')
        real_replace(src, dst)

    monkeypatch.setattr(os, 'replace', flaky)
    path = tmp_path / RUN_STATUS
    assert write_status(path, {'pid': 3}, attempts=2, retry_delay=0)
    assert len(calls) == 2 and read_status(path) == {'pid': 3}


def test_write_status_gives_up_after_its_attempts(tmp_path):
    path = tmp_path / RUN_STATUS
    path.mkdir()
    assert not write_status(path, {'pid': 3}, attempts=3, retry_delay=0)


def test_a_stopped_run_is_marked_interrupted_and_keeps_its_progress():
    # terminate()/kill() skips the engine's final write; the app writes it instead, so
    # every tab shows "stopped" rather than "ended unexpectedly"
    status = {'pid': 5, 'phase': 'analyzing', 'started': 't', 'done': 7, 'total': 9, 'exit_code': None}
    stopped = stopped_status(status)
    assert stopped['phase'] == 'interrupted' and stopped['phase'] in FINAL_PHASES
    assert stopped['message'] == 'Stopped in the app.'
    assert (stopped['pid'], stopped['started'], stopped['done'], stopped['total']) == (5, 't', 7, 9)
    assert stopped['exit_code'] is None
    assert status['phase'] == 'analyzing'  # the input is not changed


# --- started_in_time: is a process with the status's pid really that run's? (review) ---

STARTED = '2026-10-21T10:00:00+02:00'
STARTED_EPOCH = datetime.fromisoformat(STARTED).timestamp()


def test_the_run_process_was_created_before_its_status_was_written():
    # the app writes "starting" right after Popen, the engine writes its status after it
    # started; "started" has whole seconds, so a process created in the same second is accepted
    status = {'pid': 5, 'started': STARTED}
    assert started_in_time(status, STARTED_EPOCH - 3)
    assert started_in_time(status, STARTED_EPOCH + 0.9)


def test_a_process_that_reused_the_pid_later_is_not_the_run():
    # a killed engine leaves a status that is not final; another process (even another
    # engine with another --output) that gets the same pid later must not count (review)
    status = {'pid': 5, 'started': STARTED}
    assert not started_in_time(status, STARTED_EPOCH + 10)
    assert not started_in_time(status, STARTED_EPOCH + 3600)


def test_a_status_without_a_readable_start_time_matches_no_process():
    assert not started_in_time({'pid': 5}, STARTED_EPOCH)
    assert not started_in_time({'pid': 5, 'started': 'yesterday'}, STARTED_EPOCH)
    assert not started_in_time({'pid': 5, 'started': 17}, STARTED_EPOCH)


# --- final_status: the engine's final phase from its exit code (review) ---

def test_exit_codes_map_to_final_phases():
    assert final_status(0) == ('finished', None)
    assert final_status(130) == ('interrupted', 'Interrupted (Ctrl+C).')
    phase, message = final_status(1)
    assert phase == 'failed' and '1' in message
    assert all(final_status(code)[0] in FINAL_PHASES for code in (0, 1, 2, 3, 130))


# --- lock_held when the lock file cannot be opened (review) ---

def test_a_lock_file_that_cannot_be_opened_counts_as_held(tmp_path, monkeypatch):
    # e.g. a PermissionError on Windows while the file is pending delete or blocked by an
    # antivirus scanner: Start stays disabled instead of the page crashing
    path = tmp_path / RUN_LOCK
    path.write_bytes(b'')

    def refuse(*args, **kwargs):
        raise PermissionError(13, 'Access is denied')

    monkeypatch.setattr(os, 'open', refuse)
    assert lock_held(path)
