"""Start the FrameScout app of this folder (F22): Start-FrameScout.bat runs it.

    python framescout_start.py

Runs the app with Streamlit on 127.0.0.1, port 8501, or the next free one of 8502-8510 if
another program holds it. If the app of this folder already runs (in another window), it
opens the browser on that one instead of starting a second app (framescout_core.launch).
Streamlit runs in this process, so the lock that marks the running app is held exactly as
long as the app runs.
"""
import sys
import webbrowser
from pathlib import Path

# I35: a script of a version with the packages framescout_core and framescout_scoring, which
# load for it next to an older version's leftover single files (framescout_core.layout); set
# before the first FrameScout import.
FRAMESCOUT_PACKAGES = True

from framescout_core import launch, streamlit_args

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
    return launch(ROOT, run_app, open_browser=webbrowser.open)


if __name__ == '__main__':
    sys.exit(main())
