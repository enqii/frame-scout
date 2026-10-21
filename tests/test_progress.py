"""Progress lines the engine writes to run.log for people reading the log (A11).

The app reads the progress from the status file instead (test_run_status.py, A5).
"""
from framescout_core import progress_line


def test_progress_line_format():
    assert progress_line(25, 4997, 20, 4, 1) == 'Progress: 25/4997 | New: 20 | Cached: 4 | Errors: 1'
