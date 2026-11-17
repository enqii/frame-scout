"""The result file of a search (results.json) and the app's result gallery helpers."""
import ast
import json
import os
import re
from pathlib import Path

import pytest

from framescout_core.profiles import load_profiles
from framescout_core.results import (QUERY_NOTE, RESULTS_FILE, RESULTS_FORMAT, card_text, closest_query,
                                     has_closest_line, open_command, openable_photo, page_cards, page_count,
                                     profile_fingerprints, profile_state, publish_export, query_caption, query_summary,
                                     read_results, result_card, results_document, reveal_command, search_fingerprint)

from app_source import app_tree

THUMB = '1c6b57780fa2df6f925b878c.jpg'


def card(rank=1, **changes):
    return {**result_card(rank, Path(r'C:\photos\sub\a.jpg'), r'sub\a.jpg', 'Full image', 3.125, 0.31, None,
                          'Score +3.12', 'text 0.310', THUMB), **changes}


def document(cards=None, **profile):
    entry = {'name': 'Red car', 'fingerprint': 'abc', 'gallery': 'red-car.html', 'normalized': True,
             'cards': [card()] if cards is None else cards, **profile}
    return results_document('2026-10-23T14:00:00+02:00', '2026-10-23T14:02:00+02:00', [Path(r'C:\photos')],
                            {'top': 150}, 200, [entry])


def write_profiles(folder, profiles):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'profiles.json'
    path.write_text(json.dumps({'profiles': profiles}), encoding='utf-8')
    return path


def test_a_card_holds_what_the_app_shows_and_opens():
    # the relative path as the engine shows it in the HTML gallery, computed once
    c = result_card(2, Path('/photos/sub/a.jpg'), 'sub/a.jpg', 'Person 1', 1.5, 0.3, 0.8, 'Score +1.50',
                    'text 0.300 · image 0.800', THUMB)
    assert c == {'rank': 2, 'path': str(Path('/photos/sub/a.jpg')), 'relative': 'sub/a.jpg', 'label': 'Person 1',
                 'score': 1.5, 'text': 0.3, 'visual': 0.8, 'caption': 'Score +1.50',
                 'detail': 'text 0.300 · image 0.800', 'thumbnail': THUMB}


def test_a_card_names_its_closest_search_text_only_when_given():
    # an optional key; a card without it is one of an older search or of a single text
    c = result_card(1, Path('/photos/a.jpg'), 'a.jpg', 'Full image', 1.5, 0.3, None, 'Score +1.50', 'text 0.300',
                    THUMB, best_query='"a red sports car"')
    assert c['best_query'] == '"a red sports car"'
    assert 'best_query' not in card()


def test_the_caption_of_the_closest_search_text():
    assert query_caption('"a red sports car"') == 'Closest search text: "a red sports car"'


# --- the text of a card in the app ---

def text_lines(html):
    """The (title, shown text) of each line of card_text's HTML."""
    return re.findall(r'<div style="[^"]*" title="([^"]*)">(.*?)</div>', html)


def test_card_text_has_the_same_lines_for_every_card_of_a_view():
    # equal cells: a fixed number of one-line rows, whatever the card holds
    plain_card, with_text = card(), card(2, best_query='"a red car"')
    assert len(text_lines(card_text(plain_card, closest_line=False))) == 3
    assert len(text_lines(card_text(plain_card, closest_line=True))) == 4  # an empty row for the missing text
    assert len(text_lines(card_text(with_text, closest_line=True))) == 4
    for html in (card_text(plain_card, closest_line=True), card_text(with_text, closest_line=True)):
        # one line of HTML: a blank line would end the HTML block of the Markdown
        assert '\n' not in html
        # every row stays one line long and shows its whole text as a tooltip
        assert all('white-space:nowrap' in style and 'text-overflow:ellipsis' in style
                   for style in re.findall(r'style="([^"]*)"', html))


def test_the_closest_text_row_is_decided_for_the_whole_gallery():
    # a page whose cards name no closest text keeps the row if another page has one, so the
    # cards keep one height from page to page
    assert has_closest_line([card(1), card(2, best_query='"a red car"')])
    assert not has_closest_line([card(1), card(2)])
    assert not has_closest_line([])


def test_both_views_decide_the_closest_text_row_for_the_whole_gallery():
    calls = [node for node in ast.walk(app_tree()) if isinstance(node, ast.Call)
             and getattr(node.func, 'id', None) == 'draw_cards']
    assert len(calls) == 2
    # the fifth argument of draw_cards: from all cards of the entry, not from the page shown
    assert all(ast.unparse(call.args[4]) == "has_closest_line(entry['cards'])" for call in calls)


def app_functions():
    return {node.name: node for node in app_tree().body if isinstance(node, ast.FunctionDef)}


def with_blocks(function, context):
    """The source of the with blocks of function whose context expression starts with context."""
    return [ast.unparse(node) for node in ast.walk(function) if isinstance(node, ast.With)
            and ast.unparse(node.items[0].context_expr).startswith(context)]


def test_the_results_have_one_toolbar_row_above_the_photos():
    # the selector, the counts of the marks, "Hide no match", the page box and the popover
    # "Export and copy" in one row; the views draw into the row show_results starts
    functions = app_functions()
    selector = ast.unparse(functions['show_results'])
    assert "toolbar = st.container(horizontal=True, vertical_alignment='bottom', gap='small')" in selector
    [row] = with_blocks(functions['show_results'], 'toolbar')
    assert "st.selectbox('Results of'" in row
    assert 'show_quick_results(quick, folders, model, find_disabled, toolbar)' in selector
    assert 'show_profile_results(results, name, photo_folders, model, find_disabled, toolbar)' in selector
    [row] = with_blocks(functions['show_profile_results'], 'toolbar')
    order = ['mark_counts_text(progress)', "st.checkbox('Hide no match'", "st.selectbox(f'Page (of {pages})'",
             "st.popover('Export and copy'"]
    assert [row.index(text) for text in order] == sorted(row.index(text) for text in order)
    # copy, export and the gallery's buttons are in the popover, no longer below the grid
    [popover] = with_blocks(functions['show_profile_results'], "st.popover('Export and copy'")
    for call in ('show_gallery_actions(entry', 'show_copy(', 'show_export('):
        assert call in popover
    [row] = with_blocks(functions['show_quick_results'], 'toolbar')
    assert "st.selectbox(f'Page (of {pages})'" in row and "st.popover('Gallery and folder'" in row


def test_the_popover_more_of_a_card_closes_after_its_action():
    # Streamlit keeps a popover open after a button in it reruns the page; "More" tracks
    # its state under a key, and each of its buttons closes it in its callback
    functions = app_functions()
    [more] = [node for node in ast.walk(functions['draw_cards']) if isinstance(node, ast.With)
              and ast.unparse(node.items[0].context_expr).startswith("st.popover('More'")]
    keywords = {k.arg: ast.unparse(k.value) for k in more.items[0].context_expr.keywords}
    assert keywords['on_change'] == "'rerun'" and keywords['key'] == 'more_key'
    calls = [node for node in ast.walk(more) if isinstance(node, ast.Call)]
    for label, action in (('Open photo', 'open_photo'), ('Show in folder', 'show_photo')):
        [button] = [c for c in calls if ast.unparse(c.func) == 'st.button' and ast.unparse(c.args[0]) == repr(label)]
        found = {k.arg: ast.unparse(k.value) for k in button.keywords}
        assert found['on_click'] == 'close_popover'
        assert found['args'] == f"(more_key, {action}, card['path'])"
    [similar] = [c for c in calls if ast.unparse(c.func) == 'find_similar_button']
    assert {k.arg: ast.unparse(k.value) for k in similar.keywords} == {'close': 'more_key'}
    button = ast.unparse(functions['find_similar_button'])
    assert 'on_click=close_popover if close else None' in button and 'args=(close,)' in button
    closing = ast.unparse(functions['close_popover'])
    assert 'st.session_state[key] = False' in closing


def test_the_popover_export_and_copy_has_a_fixed_width():
    # its content has a fixed width, so the export caption no longer widens it
    functions = app_functions()
    [popover] = [node for node in ast.walk(functions['show_profile_results']) if isinstance(node, ast.With)
                 and ast.unparse(node.items[0].context_expr).startswith("st.popover('Export and copy'")]
    assert [ast.unparse(item.context_expr) for item in popover.items[1:]] == [
        'st.container(width=EXPORT_POPOVER_WIDTH)']


def test_the_results_have_a_pager_below_the_grid():
    # a second pager below the grid; in the profile results with "Go to the first undecided photo"
    functions = app_functions()
    for name, page_key, progress in (('show_profile_results', 'key', 'progress'),
                                     ('show_quick_results', "'quick_page'", None)):
        # the last two statements: the cards, then the pager with the page box of this view
        *_, cards, pager = [node.value for node in functions[name].body
                            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)]
        assert [call_name(cards), call_name(pager)] == ['draw_cards', 'bottom_pager']
        assert ast.unparse(pager.args[0]) == page_key
        assert (ast.unparse(pager.args[4]) if len(pager.args) > 4 else None) == progress
    # each button of the pager sets the page box through go_to_page, to its own page
    targets = {}
    for node in ast.walk(functions['bottom_pager']):
        if isinstance(node, ast.Call) and ast.unparse(node.func) == 'st.button':
            keywords = {keyword.arg: keyword.value for keyword in node.keywords}
            assert ast.unparse(keywords['on_click']) == 'go_to_page'
            targets[node.args[0].value] = ast.unparse(keywords['args'].elts[1])
    assert targets == {'Previous page': 'page - 1', 'Next page': 'page + 1',
                       'Go to the first undecided photo': 'progress.first_open_page'}


def call_name(call):
    return call.func.id if isinstance(call.func, ast.Name) else ast.unparse(call.func)


def test_the_popover_export_and_copy_closes_after_its_actions():
    # its notices are drawn below the toolbar, which the open popover would cover: like
    # "More", it tracks its state under a key and each of its buttons closes it
    functions = app_functions()
    [popover] = [node for node in ast.walk(functions['show_profile_results']) if isinstance(node, ast.With)
                 and ast.unparse(node.items[0].context_expr).startswith("st.popover('Export and copy'")]
    keywords = {k.arg: ast.unparse(k.value) for k in popover.items[0].context_expr.keywords}
    assert keywords['on_change'] == "'rerun'" and keywords['key'] == 'EXPORT_POPOVER'
    calls = {ast.unparse(node.func): node for node in ast.walk(popover) if isinstance(node, ast.Call)}
    for name in ('show_gallery_actions', 'show_copy', 'show_export'):
        assert ast.unparse(calls[name].args[-1]) == 'EXPORT_POPOVER'
        buttons = [node for node in ast.walk(functions[name]) if isinstance(node, ast.Call)
                   and ast.unparse(node.func) in ('st.button', 'c1.button', 'c2.button')]
        assert buttons
        for button in buttons:
            found = {k.arg: ast.unparse(k.value) for k in button.keywords}
            assert found['on_click'] == 'close_popover' and found['args'].startswith('(popover, ')


def test_the_notices_of_copy_and_export_are_shown_below_the_toolbar():
    # drawn into the container notices below the toolbar, after the popover closed; the
    # copy runs in the page run, with its progress bar there
    functions = app_functions()
    notices = [ast.unparse(block) for block in ast.walk(functions['show_profile_results'])
               if isinstance(block, ast.With) and ast.unparse(block.items[0].context_expr) == 'notices']
    assert any("show_notice('export_notice')" in block for block in notices)
    assert any('run_copy_request(name, photo_folders)' in block for block in notices)


def test_an_empty_row_of_card_text_keeps_its_line():
    # an empty div has no height: a card with an empty detail or path (read_results accepts
    # any string) would be shorter than the others
    lines = text_lines(card_text(card(detail='', relative=''), closest_line=True))
    assert len(lines) == 4
    assert all(shown for _, shown in lines)
    assert [shown for _, shown in lines[1:]] == ['&nbsp;'] * 3


def test_card_text_names_rank_score_part_detail_closest_text_and_path():
    lines = text_lines(card_text(card(7, best_query='"a red car"'), closest_line=True))
    assert [title for title, _ in lines] == ['#7 · Score +3.12 · Full image', 'text 0.310',
                                             'Closest search text: &quot;a red car&quot;', r'sub\a.jpg']
    assert lines[0][1] == '<b>#7</b> · Score +3.12 · Full image'
    assert lines[2] == ('Closest search text: &quot;a red car&quot;', 'Closest search text: &quot;a red car&quot;')
    # without a closest text in its view the card has no such row
    assert [title for title, _ in text_lines(card_text(card(7), closest_line=False))] == [
        '#7 · Score +3.12 · Full image', 'text 0.310', r'sub\a.jpg']


def test_card_text_escapes_what_a_photo_name_may_hold():
    # file names may hold any character: none of it may become HTML, Markdown or math
    html = card_text(card(relative=r'a<b>&"c" $x$ *y* `z`.jpg', label='<i>'), closest_line=False)
    assert '<b>&' not in html and '<i>' not in html and '$' not in html
    assert r'a&lt;b&gt;&amp;&quot;c&quot; &#36;x&#36; *y* `z`.jpg' in html
    assert '&lt;i&gt;' in html


def test_a_card_names_the_closest_text_only_among_several():
    queries = ['motif "Red car"', '"a red sports car"']
    assert closest_query(1, queries) == '"a red sports car"'
    # one text: it is always the closest, nothing to tell; no index: "Find similar"
    assert closest_query(0, queries[:1]) is None
    assert closest_query(None, queries) is None
    # the gallery note does not suggest that the other texts failed, and names the part of the
    # photo the text was compared with, not the whole photo
    assert 'small margin' in QUERY_NOTE and 'best-scoring part' in QUERY_NOTE
    assert 'a photo is most similar' not in QUERY_NOTE


QUERIES = ['motif "Red car"', '"a red sports car"', '"a car in the snow"']


def test_the_summary_counts_the_photos_each_text_was_closest_to():
    cards = [card(1, best_query=QUERIES[1]), card(2, best_query=QUERIES[1]), card(3, best_query=QUERIES[0])]
    summary = query_summary({'queries': QUERIES, 'cards': cards})
    # every text in profile order, also one that no photo was closest to
    assert summary.startswith('Closest search text of these 3 photos: motif "Red car" 1 · "a red sports car" 2 · '
                              '"a car in the snow" 0.')
    # a text closest to a photo can lead by a tiny margin: the others did not "fail"; it is the
    # text of the part the card names
    assert 'small margin' in summary and 'best-scoring part' in summary


def test_the_summary_lists_a_repeated_text_once():
    # load_profiles accepts the same custom text twice; the closest one is always the
    # first copy, and the counts add up to the listed photos
    queries = ['motif "Red car"', '"a red car"', '"a red car"']
    cards = [card(1, best_query=queries[1]), card(2, best_query=queries[0])]
    summary = query_summary({'queries': queries, 'cards': cards})
    assert summary.startswith('Closest search text of these 2 photos: motif "Red car" 1 · "a red car" 1. ')


@pytest.mark.parametrize('entry', [
    {'cards': [card()]},                                              # a search of an older version
    {'queries': ['"a red car"', '"a red car"'], 'cards': [card(best_query='"a red car"')]},  # one text, twice
    {'queries': QUERIES[:1], 'cards': [card()]},                      # a single text: nothing to compare
    {'queries': QUERIES, 'cards': [card()]},                          # no card names a text
    {'queries': QUERIES, 'cards': []},
])
def test_no_summary_without_texts_to_compare(entry):
    assert query_summary(entry) is None


def test_results_with_closest_search_texts_round_trip(tmp_path):
    path = tmp_path / RESULTS_FILE
    data = document(cards=[card(best_query=QUERIES[1])], queries=QUERIES)
    publish_export(tmp_path, [], data)
    assert read_results(path) == data


def test_the_document_names_the_run_and_its_profiles():
    data = document()
    assert data['format'] == RESULTS_FORMAT == 2
    assert data['started'] == '2026-10-23T14:00:00+02:00' and data['finished'] == '2026-10-23T14:02:00+02:00'
    # format 2 lists the photo folders; "photo_folder" of format 1 is gone
    assert data['photo_folders'] == [str(Path(r'C:\photos'))] and 'photo_folder' not in data
    assert data['settings'] == {'top': 150}
    assert data['photos'] == 200
    assert [p['name'] for p in data['profiles']] == ['Red car']


def test_the_document_lists_several_photo_folders():
    data = results_document('s', 'f', [Path(r'D:\a'), Path(r'E:\b')], {}, 3, [])
    assert data['photo_folders'] == [str(Path(r'D:\a')), str(Path(r'E:\b'))]


@pytest.mark.parametrize('folder, expected', [(r'C:\photos', [r'C:\photos']), ('', []), (None, [])])
def test_a_format_1_file_is_read_with_its_folder_as_a_list(tmp_path, folder, expected):
    # written by an older FrameScout version: the app shows it until the next search replaces it
    data = {**document(), 'format': 1, 'photo_folder': folder}
    del data['photo_folders']
    if folder is None:
        del data['photo_folder']
    path = tmp_path / RESULTS_FILE
    path.write_text(json.dumps(data), encoding='utf-8')
    read = read_results(path)
    assert read['photo_folders'] == expected and 'photo_folder' not in read
    assert read['profiles'] == document()['profiles']


@pytest.mark.parametrize('folders', [None, r'C:\photos', [r'C:\photos', 5]])
def test_format_2_needs_a_list_of_photo_folders(tmp_path, folders):
    data = document()
    if folders is None:
        del data['photo_folders']
    else:
        data['photo_folders'] = folders
    path = tmp_path / RESULTS_FILE
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError):
        read_results(path)


def test_results_round_trip(tmp_path):
    path = tmp_path / RESULTS_FILE
    publish_export(tmp_path, [], document())  # no galleries: only the result file
    assert read_results(path) == document()
    # written atomically: no temporary file is left
    assert [p.name for p in tmp_path.iterdir()] == [RESULTS_FILE]


# publishing the galleries together with results.json

def old_export(folder):
    (folder / 'red-car.html').write_text('old red car', encoding='utf-8')
    publish_export(folder, [], document(cards=[]))


def test_an_export_publishes_its_galleries_and_results_json(tmp_path):
    old_export(tmp_path)
    publish_export(tmp_path, [('red-car.html', 'new red car ✓'), ('cat.html', 'new cat')], document())
    assert (tmp_path / 'red-car.html').read_text(encoding='utf-8') == 'new red car ✓'
    assert (tmp_path / 'cat.html').read_text(encoding='utf-8') == 'new cat'
    assert read_results(tmp_path / RESULTS_FILE) == document()
    # no temporary file is left
    assert sorted(p.name for p in tmp_path.iterdir()) == ['cat.html', 'red-car.html', RESULTS_FILE]


def test_a_failed_export_publishes_nothing(tmp_path):
    old_export(tmp_path)
    # the second gallery cannot be written (its folder does not exist)
    with pytest.raises(OSError):
        publish_export(tmp_path, [('red-car.html', 'new'), ('missing/cat.html', 'new')], document())
    assert (tmp_path / 'red-car.html').read_text(encoding='utf-8') == 'old red car'
    assert read_results(tmp_path / RESULTS_FILE) == document(cards=[])
    assert sorted(p.name for p in tmp_path.iterdir()) == ['red-car.html', RESULTS_FILE]


def test_every_file_is_complete_before_the_first_is_published_and_results_json_comes_last(tmp_path):
    old_export(tmp_path)
    published = []

    def replace(tmp, target):
        if not published:  # all temporary files are written in full before the first rename
            temps = sorted(p.name for p in tmp_path.glob('*.tmp'))
            assert len(temps) == 3
            assert all(name.startswith(('red-car.html.', 'cat.html.', RESULTS_FILE + '.')) for name in temps)
        assert Path(tmp).parent == tmp_path and Path(tmp).name.endswith('.tmp')
        published.append(Path(target).name)
        os.replace(tmp, target)

    publish_export(tmp_path, [('red-car.html', 'new'), ('cat.html', 'new')], document(), replace=replace)
    assert published == ['red-car.html', 'cat.html', RESULTS_FILE]
    assert not list(tmp_path.glob('*.tmp'))


def test_a_file_that_is_open_is_published_on_a_retry(tmp_path):
    old_export(tmp_path)
    failed = []

    def replace(tmp, target):
        if Path(target).name == 'red-car.html' and not failed:
            failed.append(target)  # e.g. a virus scanner has the gallery open for a moment
            raise PermissionError('in use')
        os.replace(tmp, target)

    publish_export(tmp_path, [('red-car.html', 'new')], document(), replace=replace, retry_delay=0)
    assert failed and (tmp_path / 'red-car.html').read_text(encoding='utf-8') == 'new'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['red-car.html', RESULTS_FILE]


@pytest.mark.parametrize('held', ['dog.html', RESULTS_FILE])
def test_a_rename_that_fails_every_try_restores_what_was_published_before_it(tmp_path, held):
    # e.g. a virus scanner holds one file for longer than every retry: the run fails, but
    # the galleries and results.json of the previous search stay together
    old_export(tmp_path)
    (tmp_path / 'dog.html').write_text('old dog', encoding='utf-8')
    tries = []

    def replace(tmp, target):
        if Path(target).name == held and Path(tmp).name.startswith(held + '.'):
            tries.append(target)
            raise PermissionError('in use')
        os.replace(tmp, target)

    with pytest.raises(PermissionError):
        publish_export(tmp_path, [('red-car.html', 'new'), ('cat.html', 'new'), ('dog.html', 'new')], document(),
                       replace=replace, attempts=3, retry_delay=0)
    assert len(tries) == 3
    assert (tmp_path / 'red-car.html').read_text(encoding='utf-8') == 'old red car'
    assert (tmp_path / 'dog.html').read_text(encoding='utf-8') == 'old dog'
    assert not (tmp_path / 'cat.html').exists()  # new in this export: removed again
    assert read_results(tmp_path / RESULTS_FILE) == document(cards=[])
    assert sorted(p.name for p in tmp_path.iterdir()) == ['dog.html', 'red-car.html', RESULTS_FILE]


def test_a_restore_that_fails_too_is_skipped_and_the_rename_error_is_raised(tmp_path):
    old_export(tmp_path)
    renamed = []

    def replace(tmp, target):
        name = Path(target).name
        if name == 'dog.html':
            raise PermissionError('dog in use')
        if name in renamed:  # the restore of red-car.html fails as well
            raise PermissionError('red car in use')
        renamed.append(name)
        os.replace(tmp, target)

    with pytest.raises(PermissionError, match='dog in use'):
        publish_export(tmp_path, [('red-car.html', 'new'), ('cat.html', 'new'), ('dog.html', 'new')], document(),
                       replace=replace, attempts=2, retry_delay=0)
    assert (tmp_path / 'red-car.html').read_text(encoding='utf-8') == 'new'  # left replaced
    assert not (tmp_path / 'cat.html').exists()  # the other restores still ran
    assert read_results(tmp_path / RESULTS_FILE) == document(cards=[])
    assert not list(tmp_path.glob('*.tmp'))


def test_a_missing_result_file_is_none(tmp_path):
    assert read_results(tmp_path / RESULTS_FILE) is None


@pytest.mark.parametrize('content', [
    'not json',
    '[]',
    '{"format": 3, "profiles": [], "photo_folders": []}',
    '{"format": 1}',
    '{"format": 1, "profiles": {}}',
])
def test_an_unreadable_result_file_raises(tmp_path, content):
    path = tmp_path / RESULTS_FILE
    path.write_text(content, encoding='utf-8')
    with pytest.raises(ValueError):
        read_results(path)


@pytest.mark.parametrize('profile', [
    {'name': ''},
    {'gallery': '../outside.html'},
    {'gallery': r'sub\red-car.html'},
    {'gallery': 'red-car.exe'},
    {'cards': {}},
    {'cards': [card(thumbnail='../x.jpg')]},
    {'cards': [card(thumbnail='x.png')]},
    {'cards': [card(rank='1')]},
    {'cards': [card(path=5)]},
    {'cards': [card(caption=None)]},
    {'cards': [card(best_query=3)]},
    {'queries': 'motif "Red car"'},
    {'queries': ['motif "Red car"', None]},
])
def test_names_that_could_leave_the_results_folder_are_rejected(tmp_path, profile):
    # the app joins the gallery and thumbnail names to the results folder and opens them
    path = tmp_path / RESULTS_FILE
    data = document(**profile)
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError):
        read_results(path)


def test_duplicate_profile_names_are_rejected(tmp_path):
    # the app picks a profile by its name
    path = tmp_path / RESULTS_FILE
    data = document()
    data['profiles'].append(dict(data['profiles'][0]))
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='Red car'):
        read_results(path)


def test_the_fingerprint_follows_the_search_texts_and_the_reference_images(tmp_path):
    (tmp_path / 'r.jpg').write_bytes(b'x')
    base = {'name': 'Red car', 'franchise': 'Vehicles', 'features': 'red paint', 'prompts': ['a red car'],
            'reference_images': ['r.jpg']}

    def fingerprint(**changes):
        [profile] = load_profiles(write_profiles(tmp_path, [{**base, **changes}]), [])
        return search_fingerprint(profile, tmp_path)

    same = fingerprint()
    assert fingerprint() == same
    assert fingerprint(name='Red car ') == same  # the stored name is stripped
    assert fingerprint(features='blue paint') != same
    assert fingerprint(franchise='') != same
    assert fingerprint(prompts=[]) != same
    assert fingerprint(reference_images=[]) != same


def test_profile_fingerprints_of_the_apps_profile_file(tmp_path):
    path = write_profiles(tmp_path, [{'name': 'Red car'}, {'name': 'Bicycle', 'features': 'two wheels'}])
    fingerprints = profile_fingerprints(path)
    assert list(fingerprints) == ['Red car', 'Bicycle']
    assert fingerprints == {p['name']: search_fingerprint(p, tmp_path) for p in load_profiles(path, [])}
    assert profile_fingerprints(write_profiles(tmp_path, [])) == {}
    assert profile_fingerprints(tmp_path / 'missing.json') == {}


def test_a_moved_project_folder_keeps_the_fingerprints(tmp_path):
    # references inside the profile file's folder count by their path relative to it, so
    # moving the project folder does not mark every profile with references as changed
    profile = {'name': 'Red car', 'reference_images': ['references/red-car/reference-1.jpg']}
    before = profile_fingerprints(write_profiles(tmp_path / 'C' / 'FrameScout', [profile]))
    after = profile_fingerprints(write_profiles(tmp_path / 'D' / 'Tools' / 'FrameScout', [profile]))
    assert before == after
    # a reference outside it counts by its absolute path
    outside = {**profile, 'reference_images': [str(tmp_path / 'elsewhere.jpg')]}
    [loaded] = load_profiles(write_profiles(tmp_path / 'C' / 'FrameScout', [outside]), [])
    assert search_fingerprint(loaded, tmp_path / 'C' / 'FrameScout') != before['Red car']


def test_profile_state_compares_the_search_with_the_current_profile():
    entry = {'name': 'Red car', 'fingerprint': 'abc'}
    assert profile_state(entry, {'Red car': 'abc'}) == 'current'
    assert profile_state(entry, {'Red car': 'def'}) == 'changed'
    # renamed or deleted since the search
    assert profile_state(entry, {'red car': 'abc'}) == 'missing'


@pytest.mark.parametrize('cards,size,pages', [(0, 48, 1), (1, 48, 1), (48, 48, 1), (49, 48, 2), (150, 48, 4)])
def test_page_count(cards, size, pages):
    assert page_count(cards, size) == pages


def test_page_cards_returns_one_page_and_clamps_the_page_number():
    cards = list(range(100))
    assert page_cards(cards, 1, 48) == list(range(48))
    assert page_cards(cards, 3, 48) == [96, 97, 98, 99]
    # a page from a longer result list before a new search shows the last page
    assert page_cards(cards, 9, 48) == [96, 97, 98, 99]
    assert page_cards(cards, 0, 48) == list(range(48))
    assert page_cards([], 1, 48) == []


def test_open_and_reveal_commands_per_system():
    photo = Path('/photos/a b.jpg')
    assert open_command(photo, 'Darwin') == ['open', str(photo)]
    assert open_command(photo, 'Linux') == ['xdg-open', str(photo)]
    assert reveal_command(photo, 'Darwin') == ['open', '-R', str(photo)]
    # no file manager standard to select a file: its folder is opened
    assert reveal_command(photo, 'Linux') == ['xdg-open', str(photo.parent)]


def test_only_existing_image_files_can_be_opened(tmp_path):
    photo = tmp_path / 'a.JPG'
    photo.write_bytes(b'x')
    (tmp_path / 'tool.exe').write_bytes(b'x')
    assert openable_photo(str(photo)) == photo
    assert openable_photo(str(tmp_path / 'tool.exe')) is None  # never start a program
    assert openable_photo(str(tmp_path / 'missing.jpg')) is None
    assert openable_photo(str(tmp_path)) is None
    assert openable_photo('a.JPG') is None  # relative: depends on the app's working directory
