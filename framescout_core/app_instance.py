"""The start of the app (F22): one app per project folder, on a free port of 127.0.0.1.

Start-FrameScout.bat runs framescout_start.py, which calls launch(). The app of a project
folder holds an operating-system lock (RunLock) on .tmp/app-instance.lock while it runs
and names its port in .tmp/app-instance.json. The lock, not a process ID, tells whether
that app still runs: the operating system releases it when the process ends in any way,
so a file a killed app left behind is ignored, and a reused process ID cannot make it
look alive. A second start of the same folder opens the browser on the running app; a
port another program holds is skipped for the next free one of APP_PORTS.
"""
import json
import os
import socket
import time
from functools import partial
from pathlib import Path

from ._common import _publish_via_temp, _retry
from .locks import RunLock, lock_held

# the only address the app listens on and the browser opens: never a wider one
APP_HOST = '127.0.0.1'
# Streamlit's default port first, then the next nine
APP_PORTS = tuple(range(8501, 8511))
# the folder of the instance files, below the project folder (temporary files, deleted by the uninstaller)
INSTANCE_DIR = '.tmp'
INSTANCE_FILE = 'app-instance.json'
INSTANCE_LOCK = 'app-instance.lock'
# seconds a start waits for the running app of the folder to answer (it may be starting)
INSTANCE_WAIT = 30.0
_POLL = 0.5
# seconds a connection to a port may take: a local port answers at once or refuses
_CONNECT_TIMEOUT = 0.5


def app_url(port):
    """The address of the app on port, for the browser."""
    return f'http://{APP_HOST}:{port}'


def streamlit_args(script, port):
    """The arguments of "streamlit" that run the app script on port of 127.0.0.1 and open the browser."""
    return ['run', str(script), '--server.address', APP_HOST, '--server.port', str(port),
            '--server.headless', 'false', '--browser.gatherUsageStats', 'false']


def port_answers(port):
    """Return True if a program accepts connections on port of 127.0.0.1."""
    try:
        with socket.create_connection((APP_HOST, port), timeout=_CONNECT_TIMEOUT):
            return True
    except OSError:
        return False


def port_free(port):
    """Return True if the app can listen on port of 127.0.0.1: nothing answers there, and it can be bound.

    Both are checked: on Windows, a program listening on all addresses of the port does not
    always keep another from binding 127.0.0.1 alone, but it answers. Another program can
    still take the port before the app does; Streamlit then stops with its own message.
    """
    if port_answers(port):
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((APP_HOST, port))
        except OSError:
            return False
    return True


def free_port(ports=APP_PORTS, free=port_free):
    """The first of ports that is free, or None."""
    return next((port for port in ports if free(port)), None)


class AppInstance:
    """The lock and the instance file of the app of one project folder."""

    def __init__(self, folder):
        folder = Path(folder) / INSTANCE_DIR
        self.lock = RunLock(folder / INSTANCE_LOCK)
        self.file = folder / INSTANCE_FILE

    def claim(self):
        """Take the lock without waiting; return False if the app of this folder runs already."""
        self.file.parent.mkdir(parents=True, exist_ok=True)
        return self.lock.acquire()

    def running(self):
        """Return True if an app holds the lock of this folder (this object's own claim included)."""
        return self.lock.held or lock_held(self.lock.path)

    def publish(self, port):
        """Name port as the running app's in the instance file (only after claim())."""
        data = json.dumps({'port': port}).encode('utf-8')
        # a start of the same folder may be reading the file, which Windows lets no one replace then
        _retry(partial(_publish_via_temp, self.file, lambda tmp: tmp.write_bytes(data), os.replace, durable=False),
               attempts=10, retry_delay=0.1)

    def running_port(self):
        """The port the instance file names, or None if there is none or it is unusable."""
        try:
            data = json.loads(self.file.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
        port = data.get('port') if isinstance(data, dict) else None
        if type(port) is not int or not 0 < port < 65536:
            return None
        return port

    def release(self):
        """Remove the instance file and give the lock back; nothing happens without a claim."""
        if not self.lock.held:
            return
        try:
            self.file.unlink(missing_ok=True)
        except OSError:
            pass  # ignored by the next start: the lock is free
        self.lock.release()


def _wait_for_running(instance, answers, wait, clock, sleep):
    """The port of the folder's running app once it answers; None if it ended or did not answer within wait seconds."""
    deadline = clock() + wait
    while True:
        if not instance.running():
            return None
        port = instance.running_port()
        if port is not None and answers(port):
            return port
        if clock() >= deadline:
            return None
        sleep(_POLL)


def launch(folder, run_app, open_browser, out=print, ports=APP_PORTS, free=port_free, answers=port_answers,
           wait=INSTANCE_WAIT, clock=time.monotonic, sleep=time.sleep):
    """Start the app of the project folder, or open the browser on the one that runs; return an exit code.

    run_app(port) runs the app on port of 127.0.0.1 until it ends and returns its exit code;
    open_browser(url) opens a browser; out(text) shows a message. Without a free one of ports,
    or if the folder's running app does not answer within wait seconds, nothing starts (1).
    """
    instance = AppInstance(folder)
    while not instance.claim():
        port = _wait_for_running(instance, answers, wait, clock, sleep)
        if port is not None:
            url = app_url(port)
            out(f'FrameScout already runs from this folder in another window. Opening it in the browser: {url}')
            open_browser(url)
            return 0
        if instance.running():
            out('FrameScout already runs from this folder in another window, but does not answer. '
                'Close that window (or wait until it has started), then run Start-FrameScout.bat again.')
            return 1
        # the other app ended meanwhile: this start takes over
    try:
        port = free_port(ports, free)
        if port is None:
            out(f'Ports {ports[0]} to {ports[-1]} are all in use by other programs, so FrameScout cannot start. '
                'Close one of them, then run Start-FrameScout.bat again.')
            return 1
        if port != ports[0]:
            out(f'Port {ports[0]} is in use by another program. FrameScout uses port {port}: {app_url(port)}')
        instance.publish(port)
        return run_app(port)
    finally:
        instance.release()
