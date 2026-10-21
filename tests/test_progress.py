"""Progress lines the engine writes to run.log and the app reads back (A11)."""
from framescout_core import parse_progress, progress_line


def test_progress_line_format():
    assert progress_line(25, 4997, 20, 4, 1) == 'Progress: 25/4997 | New: 20 | Cached: 4 | Errors: 1'


def test_progress_line_round_trips():
    assert parse_progress(progress_line(3, 7, 1, 2, 0) + '\n') == (3, 7, 1, 2, 0)


def test_the_last_progress_line_wins_and_other_lines_are_ignored():
    log = '\n'.join([
        '50 photos; 1 search profiles; CLIP: cpu; YOLO: False',
        progress_line(25, 50, 25, 0, 0),
        'ERROR C:\\photos\\broken.jpg: cannot identify image file',
        progress_line(50, 50, 49, 0, 1),
        'Red car: C:\\results\\red-car.html',
    ])
    assert parse_progress(log) == (50, 50, 49, 0, 1)


def test_windows_line_endings_are_accepted():
    log = progress_line(1, 2, 1, 0, 0) + '\r\n' + progress_line(2, 2, 2, 0, 0) + '\r\n'
    assert parse_progress(log) == (2, 2, 2, 0, 0)


def test_no_progress_line_returns_none():
    assert parse_progress('') is None
    assert parse_progress('Model weights are downloaded on the first start.\n') is None


def test_progress_after_other_output_on_the_same_line_is_found():
    # stderr shares run.log; a warning or a progress bar written without a final newline
    # (digits included) must not hide the progress line that follows (review)
    log = 'model.safetensors: 100%|#####| 605M/605M\r' + progress_line(25, 50, 25, 0, 0) + '\n'
    assert parse_progress(log) == (25, 50, 25, 0, 0)
    log = 'UserWarning: foo 12' + progress_line(30, 50, 30, 0, 0) + '\n'
    assert parse_progress(log) == (30, 50, 30, 0, 0)
