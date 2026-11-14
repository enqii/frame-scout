"""The state line next to the app's title and what a search needs at the Start button (F27)."""
import ast

from app_source import app_files, page_tree
from framescout_core import (APP_TABS, NOTHING_NEW, RESULTS_TAB, RUN_TAB, START_NEEDS_TAB, start_blocked_text,
                             start_needs, start_needs_line, state_line)

POINTER = 'progress and Stop in the tab "Search"'


# --- the app's five tabs (F28) ---

def test_the_app_has_five_tabs_in_this_order():
    assert APP_TABS == ('Search profiles', 'Photo source', 'Settings', 'Search', 'Results')
    assert (START_NEEDS_TAB['profiles'], START_NEEDS_TAB['photos'], START_NEEDS_TAB['model'], RUN_TAB,
            RESULTS_TAB) == APP_TABS


def tab_blocks():
    """{tab label: the source of its with-blocks} of app.py, which makes the tabs in one st.tabs(APP_TABS) call.

    Every with-block of a tab counts, also one nested in an if or a function (review); the
    key None holds the whole page, for only_in to see code outside every tab.
    """
    page = page_tree()
    [tabs] = [node for node in page.body if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
              and ast.unparse(node.value.func) == 'st.tabs']
    assert ast.unparse(tabs.value) == 'st.tabs(list(APP_TABS))'
    names = [ast.unparse(target) for target in tabs.targets[0].elts]
    blocks = {name: '' for name in names}
    for node in ast.walk(page):
        if isinstance(node, ast.With) and ast.unparse(node.items[0].context_expr) in blocks:
            blocks[ast.unparse(node.items[0].context_expr)] += ast.unparse(node)
    return {**dict(zip(APP_TABS, blocks.values())), None: ast.unparse(page)}


def only_in(blocks, tab, text):
    """Whether text is in the tab's blocks and nowhere else in app.py: not in another tab, not outside the tabs."""
    return text in blocks[tab] and blocks[None].count(text) == blocks[tab].count(text)


def test_only_in_sees_code_outside_the_tabs_and_nested_tab_blocks(monkeypatch):
    # review: a widget drifting out of its tab, into an if or a helper at module level, must
    # fail the check; a tab block nested in an if still counts for its tab
    source = ("p_tab, f_tab, settings_tab, search_tab, results_tab = st.tabs(list(APP_TABS))\n"
              "with search_tab:\n    st.button('A')\n"
              "if x:\n    st.button('A')\n    with results_tab:\n        show_results()\n"
              "def helper():\n    st.button('B')\n")
    monkeypatch.setitem(globals(), 'page_tree', lambda: ast.parse(source))
    blocks = tab_blocks()
    assert not only_in(blocks, 'Search', "st.button('A')")
    assert only_in(blocks, 'Results', 'show_results(')
    assert not only_in(blocks, 'Search', "st.button('B')")


def test_each_tab_holds_its_own_jobs():
    blocks = tab_blocks()
    assert only_in(blocks, 'Search profiles', 'show_profiles(')
    assert only_in(blocks, 'Photo source', "setting_key('photo_folders')")
    # storage maintenance belongs to the settings, not to the results
    for call in ('show_ai_settings(', 'show_cleanup(', 'show_cache_check('):
        assert only_in(blocks, 'Settings', call), call
    # start, "Analyze ahead", progress and Stop in one place
    for text in ("'▶ Start search'", "'■ Stop search'", "'Analyze photos now'", 'show_status(', "'quick_search'"):
        assert only_in(blocks, 'Search', text), text
    # the results on their own
    for call in ('show_results(', 'show_quick_results('):
        assert only_in(blocks, 'Results', call), call


def test_the_note_of_a_start_that_failed_is_shown_in_the_tab_of_its_button():
    # review: start_engine stores it under the key its caller names (tests/test_quick.py);
    # Start, Stop, the quick search and "Analyze photos now" are in "Search", "Find similar"
    # is on the cards in "Results"
    blocks = tab_blocks()
    for key, tab in (('run_notice', 'Search'), ('analyze_notice', 'Search'), ('like_notice', 'Results')):
        assert only_in(blocks, tab, f"st.warning(st.session_state.pop('{key}'))"), key


def test_no_text_of_the_app_names_a_tab_that_no_longer_exists():
    for path in app_files():
        source = path.read_text(encoding='utf-8')
        for old in ('Search & results', 'tab "AI settings"', "tab 'AI settings'"):
            assert old not in source, (path.name, old)


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


def test_a_count_that_is_not_a_whole_number_shows_only_the_phase():
    # the 2 s fragment must not fail on a status it cannot count (review)
    for done, total in ((5.0, 10), ('5', 10), (True, 10), (5, None), (None, 10), (5, 0), (5, -1)):
        status = {'phase': 'analyzing', 'done': done, 'total': total}
        assert state_line(True, status, 10) == f'Search running · Analyzing photos · {POINTER}'


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
                                         '(tab "Settings").')
    assert start_needs_line(needs) == ('A search needs: ✗ no search profile (tab "Search profiles") · ✗ no photo '
                                       'folder (tab "Photo source") · ✗ the search model "M" cannot be used '
                                       '(tab "Settings")')


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
