"""The start of the app (F22): one app per project folder, a free port of 127.0.0.1."""
import json
import socket
from pathlib import Path

import pytest

import framescout_core as core
from framescout_core import (APP_HOST, APP_PORTS, INSTANCE_DIR, INSTANCE_FILE, INSTANCE_LOCK, AppInstance, RunLock,
                             app_url, free_port, launch, port_answers, port_free, streamlit_args)

ROOT = Path(__file__).resolve().parents[1]


def listening_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((APP_HOST, 0))
    sock.listen()
    return sock


def unused_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((APP_HOST, 0))
        return sock.getsockname()[1]


def test_the_app_only_ever_uses_the_local_address():
    assert APP_HOST == '127.0.0.1'
    assert app_url(8503) == 'http://127.0.0.1:8503'
    args = streamlit_args('app.py', 8504)
    assert args[:2] == ['run', 'app.py']
    assert args[args.index('--server.address') + 1] == '127.0.0.1'
    assert args[args.index('--server.port') + 1] == '8504'
    assert args[args.index('--server.headless') + 1] == 'false'
    assert args[args.index('--browser.gatherUsageStats') + 1] == 'false'


def test_the_ports_are_8501_and_the_next_nine():
    assert APP_PORTS == tuple(range(8501, 8511))


def test_a_listening_port_answers_and_is_not_free():
    with listening_socket() as sock:
        port = sock.getsockname()[1]
        assert port_answers(port)
        assert not port_free(port)


def test_a_bound_port_is_not_free():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((APP_HOST, 0))
        assert not port_free(sock.getsockname()[1])


def test_an_unused_port_is_free_and_does_not_answer():
    port = unused_port()
    assert port_free(port)
    assert not port_answers(port)


def test_free_port_takes_the_first_free_one():
    assert free_port((1, 2, 3), free=lambda port: port >= 2) == 2
    assert free_port((1, 2, 3), free=lambda port: False) is None


class Launch:
    """launch() with fake ports, browser and app; records what happened."""

    def __init__(self, folder, free=lambda port: True, answers=lambda port: True, result=0):
        self.folder, self.free, self.answers, self.result = folder, free, answers, result
        self.lines, self.opened, self.ran = [], [], []
        self.time = 0.0

    def run_app(self, port):
        # while the app runs, the folder's instance is held and names its port
        assert core.lock_held(self.folder / INSTANCE_DIR / INSTANCE_LOCK)
        self.ran.append((port, json.loads((self.folder / INSTANCE_DIR / INSTANCE_FILE).read_text(encoding='utf-8'))))
        return self.result

    def sleep(self, seconds):
        self.time += seconds

    def __call__(self, **more):
        return launch(self.folder, self.run_app, open_browser=self.opened.append, out=self.lines.append,
                      free=self.free, answers=self.answers, clock=lambda: self.time, sleep=self.sleep, **more)


def test_a_first_start_runs_the_app_on_8501(tmp_path):
    start = Launch(tmp_path, result=0)
    assert start() == 0
    assert start.ran == [(8501, {'port': 8501})]
    assert start.opened == [] and start.lines == []
    # a clean exit leaves no instance file and no lock behind
    assert not (tmp_path / INSTANCE_DIR / INSTANCE_FILE).exists()
    assert not core.lock_held(tmp_path / INSTANCE_DIR / INSTANCE_LOCK)


def test_the_exit_code_of_the_app_is_returned(tmp_path):
    assert Launch(tmp_path, result=1)() == 1


def test_a_busy_8501_starts_the_app_on_the_next_free_port(tmp_path):
    start = Launch(tmp_path, free=lambda port: port not in (8501, 8502))
    assert start() == 0
    assert start.ran == [(8503, {'port': 8503})]
    assert any('8501' in line and 'another program' in line and 'http://127.0.0.1:8503' in line
               for line in start.lines), start.lines


def test_all_ports_busy_stops_with_a_message(tmp_path):
    start = Launch(tmp_path, free=lambda port: False)
    assert start() == 1
    assert start.ran == [] and start.opened == []
    assert any('8501' in line and '8510' in line for line in start.lines), start.lines
    assert not core.lock_held(tmp_path / INSTANCE_DIR / INSTANCE_LOCK)


def hold_instance(folder, port):
    """Another start of the app of folder (in this process: two RunLocks conflict)."""
    other = AppInstance(folder)
    assert other.claim()
    if port is not None:
        other.publish(port)
    return other


def test_a_running_app_of_this_folder_is_opened_in_the_browser(tmp_path):
    other = hold_instance(tmp_path, 8505)
    try:
        start = Launch(tmp_path, answers=lambda port: port == 8505)
        assert start() == 0
        assert start.opened == ['http://127.0.0.1:8505']
        assert start.ran == []
        assert any('already runs' in line for line in start.lines), start.lines
        # the running app keeps its instance file
        assert other.running_port() == 8505
    finally:
        other.release()


def test_a_running_app_that_does_not_answer_yet_is_waited_for(tmp_path):
    other = hold_instance(tmp_path, 8502)
    try:
        start = Launch(tmp_path)
        start.answers = lambda port: start.time >= 5
        assert start() == 0
        assert start.opened == ['http://127.0.0.1:8502']
    finally:
        other.release()


def test_a_running_app_that_never_answers_stops_with_a_message(tmp_path):
    other = hold_instance(tmp_path, None)  # e.g. it stopped before naming its port
    try:
        start = Launch(tmp_path, answers=lambda port: False)
        assert start(wait=10) == 1
        assert start.opened == [] and start.ran == []
        assert start.time >= 10
        assert any('another window' in line for line in start.lines), start.lines
    finally:
        other.release()


def test_an_app_that_ends_while_waited_for_is_replaced_by_this_start(tmp_path):
    other = hold_instance(tmp_path, None)
    start = Launch(tmp_path)

    def sleep(seconds):
        start.time += seconds
        other.release()
    start.sleep = sleep
    assert start() == 0
    assert start.ran == [(8501, {'port': 8501})]


def test_a_stale_instance_file_is_ignored(tmp_path):
    # a killed app leaves its file, but the operating system released its lock (no PID check
    # needed, so a reused PID cannot make it look alive)
    (tmp_path / INSTANCE_DIR).mkdir()
    (tmp_path / INSTANCE_DIR / INSTANCE_FILE).write_text('{"port": 8507}', encoding='utf-8')
    start = Launch(tmp_path)
    assert start() == 0
    assert start.opened == [] and start.ran == [(8501, {'port': 8501})]


@pytest.mark.parametrize('content', ['', '{', '[]', '{"port": "8501"}', '{"port": 0}', '{"port": 70000}',
                                     '{"port": true}', '{}'])
def test_running_port_is_none_for_an_unusable_file(tmp_path, content):
    instance = AppInstance(tmp_path)
    (tmp_path / INSTANCE_DIR).mkdir()
    (tmp_path / INSTANCE_DIR / INSTANCE_FILE).write_text(content, encoding='utf-8')
    assert instance.running_port() is None


def test_running_port_is_none_without_a_file(tmp_path):
    assert AppInstance(tmp_path).running_port() is None


def test_release_of_an_unclaimed_instance_keeps_the_running_apps_file(tmp_path):
    other = hold_instance(tmp_path, 8501)
    try:
        mine = AppInstance(tmp_path)
        assert not mine.claim()
        mine.release()
        assert other.running_port() == 8501
    finally:
        other.release()


def test_the_lock_is_a_run_lock_of_the_operating_system(tmp_path):
    instance = AppInstance(tmp_path)
    assert isinstance(instance.lock, RunLock)
    assert instance.lock.path == tmp_path / INSTANCE_DIR / INSTANCE_LOCK


def test_start_bat_starts_through_the_launcher():
    text = (ROOT / 'Start-FrameScout.bat').read_text(encoding='utf-8')
    commands = [line for line in text.splitlines() if 'python.exe' in line and not line.lstrip().startswith('if')]
    assert commands == ['".venv\\Scripts\\python.exe" framescout_start.py']
    # the port is the launcher's choice now
    assert not [line for line in text.splitlines() if '8501' in line and not line.startswith('rem ')]


def test_a_claim_removes_the_instance_file_of_a_killed_app(tmp_path):
    # between claim() and publish() another start must not read the dead app's port (review)
    (tmp_path / INSTANCE_DIR).mkdir()
    (tmp_path / INSTANCE_DIR / INSTANCE_FILE).write_text('{"port": 8507}', encoding='utf-8')
    mine = AppInstance(tmp_path)
    assert mine.claim()
    try:
        assert AppInstance(tmp_path).running_port() is None
    finally:
        mine.release()


def test_a_claim_waits_briefly_for_a_lock_that_is_only_probed(tmp_path):
    # running() of a waiting start takes the lock for a moment; a claim at that moment
    # must not fail (review)
    (tmp_path / INSTANCE_DIR).mkdir()
    probe = RunLock(tmp_path / INSTANCE_DIR / INSTANCE_LOCK)
    assert probe.acquire()
    now = [0.0]

    def sleep(seconds):
        now[0] += seconds
        probe.release()
    mine = AppInstance(tmp_path)
    try:
        assert mine.claim(clock=lambda: now[0], sleep=sleep)
    finally:
        mine.release()
        probe.release()


def test_a_lock_file_that_cannot_be_opened_stops_with_its_name(tmp_path, monkeypatch):
    # e.g. a virus scanner keeps it open: a message with a way out, no traceback (review)
    def refuse(self, *args, **kwargs):
        raise PermissionError(13, 'Permission denied')
    monkeypatch.setattr(RunLock, 'acquire', refuse)
    start = Launch(tmp_path)
    assert start() == 1
    assert start.ran == [] and start.opened == []
    assert any(str(Path(INSTANCE_DIR) / INSTANCE_LOCK) in line and 'delete' in line for line in start.lines), \
        start.lines


def test_the_message_of_an_app_that_never_answers_names_the_lock_file(tmp_path):
    other = hold_instance(tmp_path, None)
    try:
        start = Launch(tmp_path, answers=lambda port: False)
        assert start(wait=1) == 1
        assert any(str(Path(INSTANCE_DIR) / INSTANCE_LOCK) in line and 'delete' in line for line in start.lines), \
            start.lines
    finally:
        other.release()
