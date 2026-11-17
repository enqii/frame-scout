"""Progress lines the engine writes to run.log for people reading the log.

The app reads the progress from the status file instead (test_run_status.py).
"""
from framescout_core.pipeline import progress_line


def test_progress_line_format():
    assert progress_line(25, 4997, 20, 4, 1) == 'Progress: 25/4997 | New: 20 | Cached: 4 | Errors: 1'
