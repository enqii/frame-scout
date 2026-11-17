"""Start the FrameScout app of this folder: Start-FrameScout.bat runs it.

    python framescout_start.py

Runs the app with Streamlit on 127.0.0.1, port 8501, or the next free one of 8502-8510 if
another program holds it. If the app of this folder already runs (in another window), it
opens the browser on that one instead of starting a second app (framescout_core.app_instance.launch).
Streamlit runs in this process, so the lock that marks the running app is held exactly as
long as the app runs.
"""
import sys
import webbrowser
from pathlib import Path

from framescout_core.app_instance import launch, streamlit_args

ROOT = Path(__file__).resolve().parent


def run_app(port):
    """Run app.py with Streamlit on port until it ends; return its exit code."""
    from streamlit.web import cli
    try:
        cli.main(args=streamlit_args(ROOT / 'app.py', port), prog_name='streamlit')
    except SystemExit as exc:
        if exc.code is None or isinstance(exc.code, int):
            return exc.code or 0
        print(exc.code, file=sys.stderr)
        return 1
    return 0


def main():
    try:
        return launch(ROOT, run_app, open_browser=webbrowser.open)
    except KeyboardInterrupt:
        # Ctrl+C in the start window is a normal stop: no traceback, and no pause of the .bat;
        # launch has given the lock back on the way out
        return 0


if __name__ == '__main__':
    sys.exit(main())
