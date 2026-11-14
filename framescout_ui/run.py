"""Starting and stopping the engine, the run status and the checks before a search (A4, A5, F3, A46)."""
import os
import subprocess

import psutil
import streamlit as st

from framescout_core import (FINAL_PHASES, MODELS, PHASE_LABELS, RunLock, StatusReporter, analysis_only,
                             analysis_result_text, analyzed_paths, app_search_needs, cache_paths, cleanup_running,
                             default_cache_env, lock_held, low_space, low_space_lines, quick_scope, read_status,
                             remaining_text, run_active, run_name, started_in_time, state_line, status_fraction,
                             status_text, stopped_status, write_status)

from .common import BASE, LOCK, LOG, LOW_SPACE_TTL, RESULTS, STATUS, plain
from .settings import AI_LABELS


def engine_alive(pid, status):
    """Return True if pid is the running FrameScout engine of status.

    Checks the command line and that the process existed when status was written, so a
    process (also another engine, e.g. with another --output) that got the pid of an ended
    run later does not count (review).
    """
    try:
        process = psutil.Process(pid)
        return (any(part.endswith('framescout_engine.py') for part in process.cmdline())
                and started_in_time(status, process.create_time()))
    except psutil.Error:
        return False


def run_state():
    """Return (active, status) of the search in the results folder, whichever tab or session started it (A4)."""
    status = read_status(STATUS)
    return run_active(status, lock_held(LOCK), lambda pid: engine_alive(pid, status)), status


def start_run(cmd, analyze_only=False):
    """Start the engine with cmd unless a search is running; return None, or why it was not started.

    The app holds the engine's run lock while it starts it, so two tabs or sessions cannot
    start at the same time; the status "starting" shows the run until the engine takes the
    lock over (A4). analyze_only: cmd is an analysis without a search, which its status
    says from "starting" on (F18).
    """
    RESULTS.mkdir(parents=True, exist_ok=True)
    lock = RunLock(LOCK)
    # with a timeout: every open tab checks the lock for a moment every two seconds (review)
    if not lock.acquire(timeout=1):
        return 'A search is already running, or the storage is being cleaned up.'
    try:
        current = read_status(STATUS)
        if run_active(current, False, lambda pid: engine_alive(pid, current)):
            return 'Another search is being started.'
        with LOG.open('w', encoding='utf-8', buffering=1) as log_handle:
            proc = subprocess.Popen(cmd, cwd=str(BASE), env=cache_env(), stdout=log_handle, stderr=subprocess.STDOUT)
        st.session_state.process = proc
        if not StatusReporter(STATUS, proc.pid, analyze_only=analyze_only).update('starting'):
            # without "starting", other tabs would see no run until the engine takes the
            # lock and could start a second one (review)
            end_processes([proc.pid])
            proc.poll()
            return (f'The search was not started: {STATUS} cannot be written (it may be open in another '
                    'program). Try again in a moment.')
        return None
    finally:
        lock.release()


def stop_run():
    """End the running engine, also one started in another tab or before a reload (A4).

    Returns None, or a note for the user.
    """
    # read again: the page may have been drawn before the engine replaced the app's
    # "starting" status with its own (review)
    status = read_status(STATUS)
    pids = []
    proc = st.session_state.get('process')
    if proc is not None and proc.poll() is None:
        pids.append(proc.pid)
    if status and isinstance(status.get('pid'), int) and engine_alive(status['pid'], status):
        pids.append(status['pid'])
    ended = end_processes(pids)
    if proc is not None:
        proc.poll()
    if not ended:
        return 'No running search process was found; it may have just ended.'
    # the stopped engine cannot write its final status; mark it under the lock, which
    # Windows may release a moment after the process has ended (review)
    lock = RunLock(LOCK)
    if not lock.acquire(timeout=10):
        return ('The search was stopped, but its lock was not released yet, so it is not marked as stopped; '
                'the page may show it as ended without finishing.')
    try:
        current = read_status(STATUS)
        # only the status of a stopped process: another start may have replaced it meanwhile
        if current and current.get('pid') in ended and current.get('phase') not in FINAL_PHASES:
            if not write_status(STATUS, stopped_status(current), attempts=20):
                return ('The search was stopped, but the status file could not be updated, so the page may show '
                        'it as ended without finishing.')
    finally:
        lock.release()
    return None


def end_processes(pids):
    """Terminate the processes pids with their child processes, kill what is left after 5 s.

    Returns the set of process ids that were found (and ended).
    """
    targets = {}
    for pid in pids:
        try:
            # with child processes: on Windows the venv's python.exe starts the interpreter as one
            process = psutil.Process(pid)
            for x in [process, *process.children(recursive=True)]:
                targets[x.pid] = x
        except psutil.Error:
            pass
    for x in targets.values():
        try:
            x.terminate()
        except psutil.Error:
            pass
    _, remaining = psutil.wait_procs(list(targets.values()), timeout=5)
    for x in remaining:
        try:
            x.kill()
        except psutil.Error:
            pass
    psutil.wait_procs(remaining, timeout=5)
    return set(targets)


def cache_env():
    # A36: a cache variable the user set is kept, as for a manual engine run (engine_cache_env
    # is this copy plus default_cache_env); the project's own cache folders default_cache_env
    # set are created up front, a folder the user named is left to the libraries
    env = os.environ.copy()
    paths = cache_paths(BASE)
    for name in default_cache_env(env, BASE):
        paths[name].mkdir(parents=True, exist_ok=True)
    temp = BASE/'.tmp'
    temp.mkdir(parents=True, exist_ok=True)
    env['TMP'] = env['TEMP'] = str(temp)
    # run.log is written and read as UTF-8; without this the engine writes the ANSI code
    # page of Windows, which garbles e.g. "·" or "ä" in the log (E22 review)
    env['PYTHONIOENCODING'] = 'utf-8'
    return env


@st.cache_data(show_spinner=False, max_entries=2)
def cached_analyzed_photos(cache_key, signature, scan_key, _scan):
    """quick_scope of the photo scan _scan: (photos analyzed, not analyzed, partners searched
    through another file of their shot), counted again only when the cache file (cache_key:
    file_key, or None without one), the settings or the photo count (scan_key) change (F3
    review).

    The quick search is counted as the engine counts it, with the RAW files analyzed in place
    of their partner (E61); its first count is also the photos with a row of their own, which
    the search's disk space estimate needs. The modification times and sizes are the scan's
    (A44), so a photo edited after the count counts as analyzed until "Recount", as an added
    photo is missing until then (A27).
    """
    done = (analyzed_paths(cache_key[0], signature, [*_scan.paths, *_scan.raw_pairs], _scan.stats)
            if cache_key else set())
    return quick_scope(_scan, done)


@st.cache_data(show_spinner=False, max_entries=4, ttl=LOW_SPACE_TTL)
def low_space_warning(photos, top, profile_count, model, person_detection, analyzed=0, analysis=False):
    """Return a warning if a search with these settings may leave little free disk space (F3), else None.

    Counts cache rows for the photos not analyzed yet (analyzed: those with cache rows of
    these settings) and thumbnails in results/, and the downloads of a model or detector
    weights not in the cache folders the engine uses yet (engine_cache_env: .cache/ or a
    folder of the user's cache variables, A36), on the drives they are on (app_search_needs). A drive that does not answer within SPACE_CHECK_TIMEOUT is left out. An
    estimate: a warning, never a block; a check that fails (OSError, ValueError) gives none.
    analysis: the warning of "Analyze photos now" (F18 review), which writes no gallery
    thumbnails (profile_count 0).
    """
    try:
        low = low_space(app_search_needs(BASE, RESULTS, os.environ, photos, top, profile_count, MODELS[model],
                                         person_detection, analyzed))
    except (OSError, ValueError):
        return None
    if not low:
        return None
    run = 'analysis' if analysis else 'search'
    return (f'Little free disk space. This {run} writes about this much on the drive of\n\n'
            + '\n'.join(f'- {plain(line)}' for line in low_space_lines(low))
            + '\n\nIt stores the analyses of new photos in the feature cache'
            + ('' if analysis else ' and the gallery thumbnails') + ', and '
            f'downloads a search model or the person detector the first time it is used. A full disk can make the '
            f'{run} fail or leave a model download or the cache incomplete. Free some disk space'
            + ('' if analysis else ' or lower "' + AI_LABELS['top'] + '"') + f'. You can still start the {run}.')


@st.fragment(run_every='2s')
def show_state_line(active, photos):
    """The one-line run state next to the title, on every tab, read again every 2 s (F27).

    active: the page run's; photos: the photos counted in the listed folders (None without an
    existing one), as the page run counted them. When a run starts or ends, the whole page
    runs again, as in show_status, so the line never says idle while the tabs show a run or
    the other way round (review).
    """
    # the state of this page run, read once at its top; fragment-only reruns read it again
    fresh = st.session_state.pop('state_line_state', None)
    now_active, status = fresh if fresh else run_state()
    if now_active != active:
        st.rerun()  # a search started or ended, also in another tab: update the whole page
    st.caption(plain(state_line(now_active, status, photos, cleanup=now_active and cleanup_running(RESULTS))))


@st.fragment(run_every='2s')
def show_status(active):
    """The run status, its progress and the live log, read again every 2 s (A4, A5); active: the page run's."""
    # the state of this page run, read once at its top; fragment-only reruns read it again (review)
    fresh = st.session_state.pop('page_run_state', None)
    now_active, status = fresh if fresh else run_state()
    if now_active != active:
        st.rerun()  # a search started or ended, also in another tab: update the whole page
    if now_active and cleanup_running(RESULTS):
        # "Clean up storage" of another tab holds the run lock, no search runs (review)
        st.info('The storage is being cleaned up or the cache checked in another tab or window. You can start '
                'a search again when it is done.')
    elif now_active:
        # an analysis without a search (F18) is named as such: it writes no results
        what = 'analysis' if analysis_only(status) else 'search'
        st.info(f'{what.capitalize()} running. You can reload this page or close the tab: the {what} continues '
                'and is shown again when you come back. Photos that are already analyzed are kept in the cache.'
                + (' The results below stay as they are.' if what == 'analysis' else ''))
    elif status:
        phase = status.get('phase')
        message = status.get('message')
        name = run_name(status)  # "search run" or "analysis" (F18)
        if phase == 'finished':
            finished_at = str(status.get('updated', '')).replace('T', ' ')[:19]
            st.success(f'The last {name} finished successfully ({finished_at}).'
                       + (' ' + analysis_result_text(status) if analysis_only(status) else ''))
            if message:  # e.g. photos the cache could not be read for (E50, review)
                st.warning(message)
        elif phase == 'interrupted':
            st.warning(f"The last {name} was interrupted{': ' + message if message else '.'} "
                       'Photos analyzed so far are in the cache; start again to resume.')
        elif phase in FINAL_PHASES:
            st.warning(f"The last {name} failed (exit code {status.get('exit_code')})"
                       f"{': ' + message if message else ''}. See the log for details.")
        else:
            st.warning(f"The last {name} ended during the phase \"{PHASE_LABELS.get(phase, phase)}\" "
                       'without finishing (stopped or crashed). Photos analyzed so far are in the cache; '
                       'see the log for details.')
    if status and status.get('phase') != 'finished':
        # the phase and its progress: analysis, scoring and gallery export (A5)
        fraction = status_fraction(status)
        text = status_text(status)
        # only for a running search: a run that crashed keeps its last rate (F12)
        left = remaining_text(status) if now_active else None
        if left:
            text += f' · {left}'
        if fraction is None:
            st.caption(text + (' …' if now_active else ''))
        else:
            st.progress(fraction, text=text)
    if LOG.exists():
        lines = LOG.read_text(encoding='utf-8', errors='replace').splitlines()
        with st.expander('Live log', expanded=now_active):
            st.code('\n'.join(lines[-35:]) or 'No output yet', language='text')
