"""Run lock and status file: one search per output folder, progress the app can read back (A4, A5)."""
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

from framescout_core import (ALL_ANALYZED, FINAL_PHASES, LOADING_DETECTOR, NOTHING_NEW, analysis_only,
                             analysis_result_text, run_name, RUN_LOCK, RUN_STATUS, RunLock, StatusReporter, final_status, lock_held,
                             nothing_new_message, read_status, run_active, started_in_time, status_fraction, status_text,
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


def test_a_new_run_keeps_the_throughput_of_earlier_runs_but_not_their_rate(tmp_path):
    # the run tab's duration before the start needs the speed of an earlier search, also
    # after a search that analyzed nothing new (F12)
    path = tmp_path / RUN_STATUS
    record = {'signature': 's', 'device': 'cpu', 'per_minute': 30.0}
    write_status(path, {'pid': 1, 'phase': 'finished', 'rate': 31.0, 'throughput': [record, 'broken'], 'done': 9})
    StatusReporter(path, 2).update('starting')
    StatusReporter(path, 3).update('scanning')  # the engine takes over the app's "starting"
    status = read_status(path)
    assert status['throughput'] == [record]
    assert status['rate'] is None and status['done'] == 0 and status['pid'] == 3


def test_a_first_run_or_an_unreadable_status_has_no_throughput(tmp_path):
    path = tmp_path / RUN_STATUS
    StatusReporter(path, 1).update('loading')
    assert read_status(path)['throughput'] == []
    assert read_status(path)['finishing'] == {} and read_status(path)['thumbnails'] is None
    path.write_text('{"broken', encoding='utf-8')
    StatusReporter(path, 1).update('loading')
    assert read_status(path)['throughput'] == []
    assert read_status(path)['finishing'] == {}


def test_a_new_run_keeps_the_speed_of_scoring_and_thumbnails_but_not_their_plan(tmp_path):
    # the estimate of what follows the analysis needs an earlier search's speeds (F16)
    path = tmp_path / RUN_STATUS
    write_status(path, {'pid': 1, 'phase': 'finished', 'thumbnails': 300,
                        'finishing': {'scoring': 900.0, 'thumbnails': 0, 'x': 1.0}})
    StatusReporter(path, 2).update('starting')
    status = read_status(path)
    assert status['finishing'] == {'scoring': 900.0}
    assert status['thumbnails'] is None


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


def test_a_running_phase_shows_the_message_of_the_run():
    # a repeat search on an analyzed folder ranks only, without loading the detector (F2)
    assert NOTHING_NEW == 'Nothing new to analyze – ranking only'
    status = {'phase': 'scoring', 'done': 3, 'total': 10, 'message': NOTHING_NEW}
    assert status_text(status) == f'Scoring photos: 3/10 · {NOTHING_NEW}'
    assert status_text({'phase': 'exporting', 'message': NOTHING_NEW}) == f'Writing galleries · {NOTHING_NEW}'


def test_the_detector_load_keeps_the_analysis_progress(tmp_path):
    # the detector loads on the first photo the cache does not have: the analysis phase and
    # its counts stay, the message names the load and is cleared afterwards (F2, review)
    assert LOADING_DETECTOR == 'Loading the person detector'
    path = tmp_path / RUN_STATUS
    status = StatusReporter(path, 1)
    status.update('analyzing', total=10)
    status.update(done=4, cached=4)
    status.update(message=LOADING_DETECTOR, force=True)
    loading = read_status(path)
    assert (loading['phase'], loading['done'], loading['total']) == ('analyzing', 4, 10)
    counts = 'Analyzing photos: 4/10 · 0 new · 4 from cache · 0 errors'
    assert status_text(loading) == f'{counts} · {LOADING_DETECTOR}'
    assert status_fraction(loading) == pytest.approx(0.4)
    status.update(message=None, force=True)
    assert status_text(read_status(path)) == counts


def test_a_final_phase_does_not_repeat_its_message():
    # the app shows the message of a failed or interrupted run in its own warning
    assert status_text({'phase': 'failed', 'message': 'boom'}) == 'Failed'
    assert status_text({'phase': 'interrupted', 'message': 'Stopped in the app.'}) == 'Interrupted'
    assert status_text({'phase': 'scoring', 'message': None}) == 'Scoring photos'
    assert status_text({'phase': 'scoring', 'message': 3}) == 'Scoring photos'


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


def test_a_finished_run_carries_its_warnings():
    # review of E50: a search that finished despite unreadable cache rows says so in the app
    assert final_status(0, ['Rows left out.', 'Check cache.']) == ('finished', 'Rows left out. Check cache.')
    assert final_status(0, []) == ('finished', None)
    assert final_status(130, ['x']) == ('interrupted', 'Interrupted (Ctrl+C).')


def test_a_failed_analysis_is_not_called_a_search():
    # review of F18: the app shows the engine's message after "The last analysis failed"
    assert final_status(1, run='analysis') == ('failed', 'The analysis ended with exit code 1.')
    assert final_status(1) == ('failed', 'The search ended with exit code 1.')
    assert final_status(0, ['Rows left out.'], run='analysis') == ('finished', 'Rows left out.')


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


# --- an analysis without a search (F18) ---

def test_an_analysis_run_is_named_as_such():
    assert analysis_only({'phase': 'finished', 'analyze_only': True})
    # a search run, an older status or a field that is not exactly True: a search
    for status in ({'phase': 'finished'}, {'analyze_only': False}, {'analyze_only': 1}, {'analyze_only': 'yes'},
                   None, []):
        assert not analysis_only(status)
    assert run_name({'analyze_only': True}) == 'analysis'
    assert run_name({'phase': 'failed'}) == 'search run'


def test_the_reporter_of_an_analysis_marks_every_write(tmp_path):
    # review: the run kind is given once, not by every update (the app's "starting", the
    # engine's phases and its final status)
    path = tmp_path / RUN_STATUS
    reporter = StatusReporter(path, 1, analyze_only=True)
    reporter.update('starting')
    assert analysis_only(read_status(path))
    reporter.update('analyzing', done=1)
    reporter.finish('failed', 2, 'Bad option.')
    assert analysis_only(read_status(path))
    # a search's status has no such field, as before F18
    StatusReporter(path, 1).update('scanning')
    assert 'analyze_only' not in read_status(path)


def test_the_status_of_an_analysis_starts_as_an_analysis():
    assert status_text({'phase': 'starting', 'analyze_only': True}) == 'Starting the analysis'
    assert status_text({'phase': 'starting'}) == 'Starting the search'
    # the other phases read the same as a search's
    status = {'phase': 'analyzing', 'done': 25, 'total': 50, 'new': 20, 'cached': 4, 'errors': 1, 'analyze_only': True}
    assert status_text(status) == 'Analyzing photos: 25/50 · 20 new · 4 from cache · 1 errors'
    assert status_text({'phase': 'analyzing', 'analyze_only': True, 'message': ALL_ANALYZED}) == \
        f'Analyzing photos · {ALL_ANALYZED}'


def test_an_analysis_with_errors_does_not_claim_all_photos_are_analyzed():
    # review: no new analysis can also mean photos whose cache row or file could not be read
    assert nothing_new_message(analyze_only=True, errors=0) == ALL_ANALYZED
    message = nothing_new_message(analyze_only=True, errors=2)
    assert message != ALL_ANALYZED and 'All photos' not in message and 'log' in message
    # a search ranks the photos it has either way
    assert nothing_new_message(analyze_only=False, errors=0) == NOTHING_NEW
    assert nothing_new_message(analyze_only=False, errors=2) == NOTHING_NEW


def test_a_finished_analysis_names_its_counts_and_leaves_the_results():
    text = analysis_result_text({'phase': 'finished', 'analyze_only': True, 'new': 1200, 'cached': 3, 'errors': 0})
    assert text.startswith('1,200 photos newly analyzed, 3 already in the cache.')
    # the risk of F18: a run without results.json must not look like a failed search
    assert 'results of the last search stay as they are' in text
    # the analyses help only a search with the same settings
    assert 'search model' in text and 'person detection' in text
    one = analysis_result_text({'new': 1, 'cached': 1, 'errors': 1})
    assert one.startswith('1 photo newly analyzed, 1 already in the cache, 1 could not be analyzed (see the log).')
    # counts that are missing or no numbers count as none
    assert analysis_result_text({'new': 'x'}).startswith('0 photos newly analyzed, 0 already in the cache.')
