"""The remaining-time estimate of a search and the summary before its start (F12, F16)."""
from datetime import datetime, timedelta, timezone

import pytest

from framescout_core import (FINISHING_MIN_ITEMS, FINISHING_MIN_SECONDS, RATE_MIN_PHOTOS, RATE_MIN_SECONDS,
                             RATE_STALE, RATE_WINDOW, THROUGHPUT_KEPT, THROUGHPUT_MIN_SECONDS, AnalysisRate, StepSpeed,
                             analysis_summary, duration_text,
                             finishing_minutes,
                             gallery_thumbnails, known_throughput, remaining_text, remember_finishing,
                             remember_throughput, run_throughput, start_summary, stored_finishing, stored_throughput)


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

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone(timedelta(hours=1)))


def analyzing(**fields):
    return {'phase': 'analyzing', 'done': 100, 'total': 1100, 'rate': 40.0,
            'updated': (NOW - timedelta(seconds=5)).isoformat(timespec='seconds'), **fields}


def test_remaining_text_from_the_rate_and_the_photos_left():
    assert remaining_text(analyzing(), NOW) == 'about 25 min left for the analysis'


# an earlier search scored 1,000 photos and rendered 20 thumbnails per minute (F16)
FINISHING = {'scoring': 1000.0, 'thumbnails': 20.0}


def test_remaining_text_of_the_analysis_adds_scoring_and_thumbnails():
    # 1,000 photos left at 40 per minute, then 1,100 photos to score (1.1 min) and 300
    # thumbnails to render (15 min): the estimate no longer ends with the analysis (F16)
    status = analyzing(finishing=FINISHING, thumbnails=300)
    assert remaining_text(status, NOW) == 'about 40 min left'


def test_remaining_text_names_the_analysis_alone_without_earlier_speeds():
    # a first search knows no speed of scoring and galleries yet: the time is the analysis's
    assert remaining_text(analyzing(thumbnails=300), NOW) == 'about 25 min left for the analysis'
    partial = {'scoring': 1000.0}
    assert remaining_text(analyzing(thumbnails=300, finishing=partial), NOW) == 'about 25 min left for the analysis'
    # nor a status without the planned thumbnails (an older engine)
    assert remaining_text(analyzing(finishing=FINISHING), NOW) == 'about 25 min left for the analysis'


def scoring(**fields):
    return {**analyzing(phase='scoring', done=100, total=1100, finishing=FINISHING, thumbnails=300), **fields}


def test_remaining_text_while_scoring_and_writing_the_galleries():
    assert remaining_text(scoring(), NOW) == 'about 15 min left'  # 1 min of scoring, 15 of thumbnails
    exporting = scoring(phase='exporting', done=140, total=300)  # 160 cards left
    assert remaining_text(exporting, NOW) == 'about 8 min left'
    # the rate of the analysis does not matter after it
    assert remaining_text(scoring(rate=None), NOW) == 'about 15 min left'


def test_remaining_text_once_every_photo_is_analyzed_or_scored():
    # the analysis is over (or all photos came from the cache, without a rate), but scoring
    # and the thumbnails still take their time (review)
    for status in (analyzing(done=1100, finishing=FINISHING, thumbnails=300),
                   analyzing(done=1100, rate=None, finishing=FINISHING, thumbnails=300)):
        assert remaining_text(status, NOW) == 'about 15 min left'  # 1 min of scoring, 15 of thumbnails
    assert remaining_text(scoring(done=1100), NOW) == 'about 15 min left'  # the thumbnails alone
    # without earlier speeds there is nothing to estimate
    assert remaining_text(analyzing(done=1100, thumbnails=300), NOW) is None


@pytest.mark.parametrize('status', [
    scoring(finishing=None), scoring(finishing={'scoring': 1000.0}), scoring(thumbnails=None),
    scoring(phase='exporting', done=300, total=300), scoring(phase='exporting', finishing={'scoring': 1000.0}),
    scoring(updated=(NOW - timedelta(seconds=RATE_STALE + 1)).isoformat()), scoring(done='x'),
])
def test_no_remaining_text_after_the_analysis_without_earlier_speeds(status):
    assert remaining_text(status, NOW) is None


def test_no_remaining_text_while_the_analysis_stalls():
    # the rate changes only when the engine stores photos: a status that has not changed
    # for a while keeps a rate that no longer says anything (review)
    stalled = (NOW - timedelta(seconds=RATE_STALE + 1)).isoformat(timespec='seconds')
    assert remaining_text(analyzing(updated=stalled), NOW) is None
    recent = (NOW - timedelta(seconds=RATE_STALE - 1)).isoformat(timespec='seconds')
    assert remaining_text(analyzing(updated=recent), NOW) == 'about 25 min left for the analysis'
    # the same moment in another time zone
    other_zone = (NOW - timedelta(seconds=5)).astimezone(timezone.utc).isoformat()
    assert remaining_text(analyzing(updated=other_zone), NOW) == 'about 25 min left for the analysis'


def test_remaining_text_uses_the_current_time_by_default():
    assert remaining_text(analyzing(updated=datetime.now().astimezone().isoformat())) == 'about 25 min left for the analysis'


@pytest.mark.parametrize('status', [
    analyzing(rate=None), analyzing(rate=0), analyzing(rate=-3.0), analyzing(rate='fast'), analyzing(rate=True),
    analyzing(rate=float('nan')), analyzing(rate=float('inf')), analyzing(done=1100), analyzing(done=None),
    analyzing(total=0), analyzing(phase='scoring'), analyzing(phase='finished'), {},
    analyzing(updated=None), analyzing(updated='yesterday'), analyzing(updated='2026-11-03T12:00:00'),
])
def test_no_remaining_text_without_a_usable_rate_or_outside_the_analysis(status):
    assert remaining_text(status, NOW) is None


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


def measured(seconds, per_minute=60.0):
    rate = AnalysisRate()
    rate.add(0, 0.0)
    rate.add(int(per_minute * seconds / 60), float(seconds))
    return rate


def test_run_throughput_waits_for_a_measurement():
    assert run_throughput([], 's', 'cpu', AnalysisRate()) is None
    assert run_throughput([], 's', 'cpu', measured(RATE_MIN_SECONDS - 1)) is None


def test_run_throughput_stores_the_first_speed_of_its_settings_at_once():
    records = run_throughput([{'signature': 'other', 'device': 'cpu', 'per_minute': 5.0}], 's', 'cpu',
                             measured(RATE_MIN_SECONDS))
    assert records[0] == {'signature': 's', 'device': 'cpu', 'per_minute': pytest.approx(60.0)}
    assert len(records) == 2


def test_a_short_run_does_not_replace_the_speed_of_a_longer_one():
    # a search stopped after its first minute measured too little to replace the record
    # of a whole earlier analysis (review)
    earlier = [{'signature': 's', 'device': 'cpu', 'per_minute': 30.0}]
    assert run_throughput(earlier, 's', 'cpu', measured(THROUGHPUT_MIN_SECONDS - 1)) is None
    records = run_throughput(earlier, 's', 'cpu', measured(THROUGHPUT_MIN_SECONDS))
    assert records == [{'signature': 's', 'device': 'cpu', 'per_minute': pytest.approx(60.0)}]
    # the record of another device does not count as one of these settings
    assert run_throughput(earlier, 's', 'cuda', measured(RATE_MIN_SECONDS))[0]['device'] == 'cuda'


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


# --- the speed of scoring and of the gallery thumbnails, kept in the status file (F16) ---

def test_remember_finishing_needs_enough_items():
    assert remember_finishing({}, 'scoring', FINISHING_MIN_ITEMS - 1, 10.0) is None
    assert remember_finishing({}, 'scoring', FINISHING_MIN_ITEMS, 0.0) is None
    assert remember_finishing({}, 'thumbnails', 30, 60.0) == {'thumbnails': pytest.approx(30.0)}


def test_a_short_measurement_does_not_replace_a_stored_speed():
    # a small search measured too little to replace the speed of an earlier one (review);
    # the first speed of a step is stored at once
    before = {'scoring': 500.0, 'thumbnails': 10.0}
    assert remember_finishing(before, 'thumbnails', 100, FINISHING_MIN_SECONDS - 1) is None
    assert remember_finishing(before, 'thumbnails', 100, FINISHING_MIN_SECONDS) == {
        'scoring': 500.0, 'thumbnails': pytest.approx(100 * 60 / FINISHING_MIN_SECONDS)}
    assert remember_finishing({'scoring': 500.0}, 'thumbnails', 100, 1.0) == {
        'scoring': 500.0, 'thumbnails': pytest.approx(6000.0)}
    assert remember_finishing({'thumbnails': 0}, 'thumbnails', 100, 1.0) == {'thumbnails': pytest.approx(6000.0)}


def test_remember_finishing_replaces_one_step_and_keeps_the_other():
    before = {'scoring': 500.0, 'thumbnails': 10.0}
    assert remember_finishing(before, 'scoring', 2000, 60.0) == {'scoring': 2000.0, 'thumbnails': 10.0}
    assert before == {'scoring': 500.0, 'thumbnails': 10.0}  # its input is not changed


def test_stored_finishing_drops_what_is_not_a_speed():
    assert stored_finishing({'scoring': 5.0, 'thumbnails': 0, 'other': 3.0}) == {'scoring': 5.0}
    assert stored_finishing({'scoring': True, 'thumbnails': float('nan')}) == {}
    for value in (None, 'x', [], 3):
        assert stored_finishing(value) == {}


def test_step_speed_counts_the_calls_that_return():
    ticks = iter(range(0, 1000, 3))  # every call takes 3 seconds of this clock
    speed = StepSpeed(clock=lambda: next(ticks))
    render = speed.timed(lambda path, target: f'{path}->{target}')
    assert render('a.jpg', target='t.jpg') == 'a.jpg->t.jpg'

    def broken(path):
        raise OSError('cannot decode')
    with pytest.raises(OSError):
        speed.timed(broken)('b.jpg')
    assert (speed.items, speed.seconds) == (1, 3)
    assert speed.remember({}, 'thumbnails') is None  # too few
    for _ in range(FINISHING_MIN_ITEMS):
        render('c.jpg', 'd.jpg')
    assert speed.remember({'scoring': 9.0}, 'thumbnails') == {'scoring': 9.0, 'thumbnails': pytest.approx(20.0)}


def test_finishing_minutes():
    assert finishing_minutes(FINISHING, 2000, 100) == pytest.approx(2 + 5)
    assert finishing_minutes(FINISHING, 0, 0) == 0
    assert finishing_minutes({'thumbnails': 20.0}, 0, 100) == pytest.approx(5)  # no photo left to score
    assert finishing_minutes({'thumbnails': 20.0}, 1, 100) is None
    assert finishing_minutes(None, 1, 0) is None


def test_gallery_thumbnails_count_each_photo_once():
    # a photo in several galleries has one thumbnail; on the safe side, every one is new
    assert gallery_thumbnails(5000, 150, 3) == 450
    assert gallery_thumbnails(200, 150, 3) == 200
    assert gallery_thumbnails(0, 150, 3) == 0


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
    assert 'about' not in text  # no speed of scoring and galleries known


def test_start_summary_adds_scoring_and_galleries_at_the_speed_of_earlier_searches():
    # F16: the duration also covers what follows the analysis, as an upper bound
    text = start_summary(5000, 3200, 20.0, 15.0)
    assert 'about 1 h 30 min' in text
    assert 'up to about 15 min more' in text
    text = start_summary(5000, 5000, 20.0, 15.0)
    assert 'all already analyzed' in text and 'up to about 15 min' in text
    # without the speed of the analysis, the time after it is not named alone either
    assert 'about' not in start_summary(5000, 0, None, 15.0)


def test_start_summary_of_one_photo():
    assert '1 photo found' in start_summary(1, 0, None)


def test_start_summary_without_photos_does_not_call_them_analyzed():
    # folders that hold no supported photo (review)
    text = start_summary(0, 0, 20.0)
    assert 'No supported photos found' in text
    assert 'analyzed' not in text and 'about' not in text


# --- an analysis without a search (F18) ---

def test_remaining_text_of_an_analysis_is_the_analysis_alone():
    # nothing is scored or rendered after it: no "for the analysis", no time for galleries
    assert remaining_text(analyzing(analyze_only=True), NOW) == 'about 25 min left'
    status = analyzing(analyze_only=True, finishing=FINISHING, thumbnails=300)
    assert remaining_text(status, NOW) == 'about 25 min left'
    # once every photo is analyzed there is nothing left to estimate
    assert remaining_text(analyzing(analyze_only=True, done=1100, finishing=FINISHING), NOW) is None
    assert remaining_text(analyzing(analyze_only=True, rate=None), NOW) is None


def test_analysis_summary_with_a_known_speed():
    text = analysis_summary(5000, 3200, 20.0)
    assert '5,000 photos found' in text and '3,200 already analyzed' in text and '1,800 to analyze' in text
    assert 'about 1 h 30 min' in text and 'rough' in text
    # nothing about rankings or galleries: the analysis writes none
    assert 'galler' not in text and 'scor' not in text


def test_analysis_summary_without_a_known_speed():
    text = analysis_summary(5000, 0, None)
    assert '5,000 to analyze' in text and 'about' not in text


def test_analysis_summary_with_everything_analyzed_or_no_photos():
    text = analysis_summary(5000, 5000, 20.0)
    assert 'All 5,000 photos are analyzed with these settings already' in text
    assert 'to analyze' not in text and 'about' not in text
    assert analysis_summary(1, 1, None).startswith('The photo is analyzed with these settings already')
    assert 'No supported photos found' in analysis_summary(0, 0, 20.0)
