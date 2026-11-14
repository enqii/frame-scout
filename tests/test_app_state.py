"""The state line next to the app's title and what a search needs at the Start button (F27)."""
from framescout_core import (NOTHING_NEW, START_NEEDS_TAB, start_blocked_text, start_needs, start_needs_line,
                             state_line)

POINTER = 'progress and Stop in the tab "Search & results"'


# --- state_line: one line on every tab ---

def test_a_running_search_shows_its_phase_progress_and_where_to_follow_it():
    status = {'phase': 'analyzing', 'done': 250, 'total': 1000, 'new': 200, 'cached': 50, 'errors': 0}
    assert state_line(True, status, 1000) == f'Search running · Analyzing photos 250/1,000 (25%) · {POINTER}'


def test_a_running_analysis_is_named_as_such():
    status = {'phase': 'analyzing', 'analyze_only': True, 'done': 1, 'total': 3}
    assert state_line(True, status, 3) == f'Analysis running · Analyzing photos 1/3 (33%) · {POINTER}'


def test_a_running_phase_without_a_count_shows_only_its_name():
    assert state_line(True, {'phase': 'loading'}, 10) == f'Search running · Loading the AI models · {POINTER}'
    assert state_line(True, {'phase': 'starting', 'analyze_only': True}, 10) == \
        f'Analysis running · Starting the analysis · {POINTER}'


def test_a_running_search_without_a_readable_status_still_says_it_runs():
    assert state_line(True, None, 10) == f'Search running · {POINTER}'


def test_a_cleanup_holding_the_run_lock_is_no_search():
    assert state_line(True, None, 10, cleanup=True) == \
        'Storage cleanup or cache check running · searches can start again when it is done'


def test_idle_shows_the_last_search_and_the_photo_count():
    status = {'phase': 'finished', 'updated': '2026-11-13T14:02:31+01:00', 'message': None}
    assert state_line(False, status, 12345) == \
        'Idle · last search finished 2026-11-13 14:02 · 12,345 photos in the photo folders'


def test_idle_names_a_last_analysis_and_how_the_last_run_ended():
    analysis = {'phase': 'finished', 'analyze_only': True, 'updated': '2026-11-13T09:00:00'}
    assert state_line(False, analysis, 1) == \
        'Idle · last analysis finished 2026-11-13 09:00 · 1 photo in the photo folders'
    assert state_line(False, {'phase': 'interrupted', 'updated': '2026-11-13T09:00:00'}, 2) == \
        'Idle · last search interrupted 2026-11-13 09:00 · 2 photos in the photo folders'
    assert state_line(False, {'phase': 'failed', 'updated': '2026-11-13T09:00:00'}, 2) == \
        'Idle · last search failed 2026-11-13 09:00 · 2 photos in the photo folders'
    # a status that is not final once its process is gone: stopped or crashed (A4)
    assert state_line(False, {'phase': 'analyzing', 'updated': '2026-11-13T09:00:00'}, 2) == \
        'Idle · last search ended without finishing 2026-11-13 09:00 · 2 photos in the photo folders'


def test_idle_without_a_search_or_a_readable_time():
    assert state_line(False, None, 0) == 'Idle · no search yet · 0 photos in the photo folders'
    assert state_line(False, {'phase': 'finished', 'updated': 5}, 3) == \
        'Idle · last search finished · 3 photos in the photo folders'


def test_idle_without_an_existing_photo_folder():
    assert state_line(False, None, None) == 'Idle · no search yet · no existing photo folder'


def test_the_message_of_a_run_is_left_to_the_search_tab():
    status = {'phase': 'scoring', 'done': 1, 'total': 4, 'message': NOTHING_NEW}
    assert state_line(True, status, 4) == f'Search running · Scoring photos 1/4 (25%) · {POINTER}'


# --- start_needs: profiles, photos and the search model ---

def test_everything_a_search_needs_is_there():
    needs = start_needs(3, 12345, True, 'OpenCLIP ViT-B-32', None)
    assert needs == [('profiles', True, '3 search profiles'),
                     ('photos', True, '12,345 photos'),
                     ('model', True, 'search model "OpenCLIP ViT-B-32"')]
    assert start_blocked_text(needs) is None
    assert start_needs_line(needs) == \
        'A search needs: ✓ 3 search profiles · ✓ 12,345 photos · ✓ search model "OpenCLIP ViT-B-32"'


def test_what_is_missing_names_the_tab_to_fix_it_in():
    needs = start_needs(0, None, False, 'M', 'The search model M needs the Python package x.')
    assert needs == [('profiles', False, f'no search profile (tab "{START_NEEDS_TAB["profiles"]}")'),
                     ('photos', False, f'no photo folder (tab "{START_NEEDS_TAB["photos"]}")'),
                     ('model', False, f'the search model "M" cannot be used (tab "{START_NEEDS_TAB["model"]}")')]
    assert start_blocked_text(needs) == ('Start is not available because: no search profile (tab "Search profiles"); '
                                         'no photo folder (tab "Photo source"); the search model "M" cannot be used '
                                         '(tab "AI settings").')
    assert start_needs_line(needs) == ('A search needs: ✗ no search profile (tab "Search profiles") · ✗ no photo '
                                       'folder (tab "Photo source") · ✗ the search model "M" cannot be used '
                                       '(tab "AI settings")')


def test_listed_folders_that_do_not_exist():
    needs = start_needs(1, None, True, 'M', None)
    assert needs[0] == ('profiles', True, '1 search profile')
    assert needs[1] == ('photos', False, 'none of the listed photo folders exists (tab "Photo source")')
    assert start_blocked_text(needs) == \
        'Start is not available because: none of the listed photo folders exists (tab "Photo source").'


def test_an_existing_folder_is_enough_since_a_search_reads_the_folders_again():
    # the count is the one remembered for the browser session (A27); Start is not gated on it
    assert start_needs(1, 0, True, 'M', None)[1] == ('photos', True, '0 photos')
    assert start_needs(1, 1, True, 'M', None)[1] == ('photos', True, '1 photo')


def test_a_running_search_or_cleanup_comes_first():
    needs = start_needs(0, None, False, 'M', None)
    assert start_blocked_text(needs, active=True) == \
        'Start is not available because a search or an analysis is running.'
    assert start_blocked_text(needs, active=True, cleanup=True) == \
        'Start is not available because the storage is being cleaned up or the cache checked.'
