"""The remaining-time estimate of a search and the summary before its start (F12)."""
import pytest

from framescout_core import (RATE_MIN_PHOTOS, RATE_MIN_SECONDS, RATE_WINDOW, THROUGHPUT_KEPT, AnalysisRate,
                             duration_text, known_throughput, remaining_text, remember_throughput, start_summary,
                             stored_throughput)


# --- AnalysisRate: photos per minute of the analysis, measured in the engine ---

def test_no_rate_before_enough_photos_and_time():
    rate = AnalysisRate()
    rate.add(8, 0.0)
    assert rate.per_minute() is None and rate.overall() is None
    rate.add(8 + RATE_MIN_PHOTOS, RATE_MIN_SECONDS - 1)  # enough photos, too short
    assert rate.per_minute() is None and rate.overall() is None
    rate.add(8 + RATE_MIN_PHOTOS, RATE_MIN_SECONDS)
    assert rate.per_minute() == pytest.approx(RATE_MIN_PHOTOS)
    assert rate.overall() == pytest.approx(RATE_MIN_PHOTOS)


def test_few_photos_over_a_long_time_give_no_rate():
    rate = AnalysisRate()
    rate.add(1, 0.0)
    rate.add(RATE_MIN_PHOTOS, 10 * RATE_MIN_SECONDS)  # one photo short
    assert rate.per_minute() is None and rate.overall() is None


def test_the_first_sample_starts_the_measurement():
    # the time before the first stored group (model warm-up, detector load) is not counted
    rate = AnalysisRate()
    rate.add(10, 100.0)
    rate.add(130, 160.0)
    assert rate.overall() == pytest.approx(120)


def test_the_moving_rate_follows_the_last_minutes_and_overall_keeps_the_whole_run():
    rate = AnalysisRate()
    t, photos = 0.0, 0
    rate.add(photos, t)
    for _ in range(int(RATE_WINDOW // 10) * 2):  # 60 photos per minute for two windows
        t += 10
        photos += 10
        rate.add(photos, t)
    assert rate.per_minute() == pytest.approx(60)
    for _ in range(int(RATE_WINDOW // 10) * 2):  # then 30 photos per minute (the PC got busy)
        t += 10
        photos += 5
        rate.add(photos, t)
    assert rate.per_minute() == pytest.approx(30)
    assert rate.overall() == pytest.approx(45)


def test_the_moving_rate_covers_at_least_the_window():
    rate = AnalysisRate()
    for second in range(0, 1000, 10):
        rate.add(second, float(second))
    first = rate.samples[0][0]
    assert rate.samples[-1][0] - first >= RATE_WINDOW
    assert len(rate.samples) <= RATE_WINDOW // 10 + 2


def test_a_window_with_too_few_photos_falls_back_to_the_whole_run():
    rate = AnalysisRate()
    rate.add(0, 0.0)
    rate.add(600, 600.0)  # 60 per minute
    rate.add(601, 600.0 + 2 * RATE_WINDOW)  # nearly stalled: one photo in the last window
    assert rate.per_minute() == pytest.approx(601 / ((600 + 2 * RATE_WINDOW) / 60))


# --- duration_text: rounded generously, never seconds ---

@pytest.mark.parametrize('minutes, text', [
    (0.1, 'under 2 min'), (1.9, 'under 2 min'), (2.2, 'about 2 min'), (7.4, 'about 7 min'),
    (9.6, 'about 10 min'), (23, 'about 25 min'), (57.6, 'about 1 h'), (61, 'about 1 h'), (80, 'about 1 h 30 min'),
    (100, 'about 1 h 30 min'), (110, 'about 2 h'), (299, 'about 5 h'), (310, 'about 5 h'), (450, 'about 8 h'), (2000, 'about 33 h'),
])
def test_duration_text(minutes, text):
    assert duration_text(minutes) == text


def test_duration_text_never_names_seconds():
    for tenth in range(0, 50000, 7):
        assert 'sec' not in duration_text(tenth / 10)


# --- remaining_text: the line the app adds to the progress of a running search ---

def analyzing(**fields):
    return {'phase': 'analyzing', 'done': 100, 'total': 1100, 'rate': 40.0, **fields}


def test_remaining_text_from_the_rate_and_the_photos_left():
    assert remaining_text(analyzing()) == 'about 25 min left'


@pytest.mark.parametrize('status', [
    analyzing(rate=None), analyzing(rate=0), analyzing(rate=-3.0), analyzing(rate='fast'), analyzing(rate=True),
    analyzing(rate=float('nan')), analyzing(rate=float('inf')), analyzing(done=1100), analyzing(done=None),
    analyzing(total=0), analyzing(phase='scoring'), analyzing(phase='finished'), {},
])
def test_no_remaining_text_without_a_usable_rate_or_outside_the_analysis(status):
    assert remaining_text(status) is None


# --- throughput of earlier searches, kept in the status file ---

def test_remember_throughput_puts_the_newest_first_and_replaces_the_same_settings():
    records = remember_throughput([], 'sig-a', 'cpu', 30.0)
    records = remember_throughput(records, 'sig-b', 'cuda', 300.0)
    records = remember_throughput(records, 'sig-a', 'cpu', 20.0)
    assert records == [{'signature': 'sig-a', 'device': 'cpu', 'per_minute': 20.0},
                       {'signature': 'sig-b', 'device': 'cuda', 'per_minute': 300.0}]


def test_remember_throughput_keeps_a_few_records_and_does_not_change_its_input():
    records = []
    for n in range(THROUGHPUT_KEPT + 3):
        records = remember_throughput(records, f'sig-{n}', 'cpu', float(n + 1))
    assert len(records) == THROUGHPUT_KEPT
    assert records[0]['signature'] == f'sig-{THROUGHPUT_KEPT + 2}'
    before = list(records)
    remember_throughput(records, 'new', 'cpu', 1.0)
    assert records == before


def test_stored_throughput_drops_what_is_not_a_record():
    good = {'signature': 's', 'device': 'cpu', 'per_minute': 12.5}
    assert stored_throughput([good, {'signature': 's'}, {'signature': 1, 'device': 'cpu', 'per_minute': 1.0},
                              {'signature': 's', 'device': 'cpu', 'per_minute': 0},
                              {'signature': 's', 'device': 'cpu', 'per_minute': True},
                              {'signature': 's', 'device': 'cpu', 'per_minute': float('nan')}, 'x', None]) == [good]
    for value in (None, 'x', {}, 3):
        assert stored_throughput(value) == []
    assert len(stored_throughput([good] * (THROUGHPUT_KEPT + 5))) == THROUGHPUT_KEPT


def test_known_throughput_matches_signature_and_device():
    status = {'throughput': [{'signature': 'a', 'device': 'cuda', 'per_minute': 300.0},
                             {'signature': 'a', 'device': 'cpu', 'per_minute': 30.0},
                             {'signature': 'b', 'device': 'cpu', 'per_minute': 10.0}]}
    assert known_throughput(status, 'a', 'cpu') == 30.0
    assert known_throughput(status, 'a', 'cuda') == 300.0
    assert known_throughput(status, 'a', None) == 300.0  # unknown device: the newest of these settings
    assert known_throughput(status, 'b', 'cuda') is None
    assert known_throughput(status, 'c', None) is None
    assert known_throughput(None, 'a', 'cpu') is None
    assert known_throughput({'throughput': 'broken'}, 'a', 'cpu') is None


# --- start_summary: what the run tab says before "Start search" ---

def test_start_summary_with_a_known_speed():
    text = start_summary(5000, 3200, 20.0)
    assert '5,000 photos found' in text
    assert '3,200 already analyzed' in text
    assert '1,800 to analyze' in text
    assert 'about 1 h 30 min' in text
    assert 'rough' in text


def test_start_summary_without_a_known_speed():
    text = start_summary(5000, 0, None)
    assert '5,000 to analyze' in text
    assert 'about' not in text
    assert 'first minutes' in text


def test_start_summary_with_everything_analyzed():
    text = start_summary(5000, 5000, 20.0)
    assert 'all already analyzed' in text
    assert 'to analyze' not in text


def test_start_summary_of_one_photo():
    assert '1 photo found' in start_summary(1, 0, None)
