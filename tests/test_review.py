"""The review dialog of a result list: one photo at a time with a large preview (F19)."""
import ast
import re

from framescout_core import (CARD_STYLE, MARK_MATCH, MARK_NO_MATCH, MARK_OPEN, PHOTO_KEY_PREFIX, PREVIEW_KEY_PREFIX,
                             REVIEW_PREVIEW_SIZE, REVIEW_STYLE, first_undecided, next_undecided, review_index,
                             review_position, review_shown, review_state_text)

from app_source import app_tree, page_tree


def cards(*paths):
    return [{'rank': rank, 'path': path} for rank, path in enumerate(paths, 1)]


LIST = cards('a.jpg', 'b.jpg', 'c.jpg', 'd.jpg')


def test_review_one_by_one_starts_at_the_first_undecided_photo():
    assert first_undecided(LIST, {}) == 0
    assert first_undecided(LIST, {'a.jpg': MARK_MATCH, 'b.jpg': MARK_NO_MATCH}) == 2
    # a state other than match or no match counts as undecided, as in the gallery
    assert first_undecided(LIST, {'a.jpg': MARK_OPEN}) == 0
    assert first_undecided(LIST, {'a.jpg': 'unknown'}) == 0
    # every photo marked: the first photo of the list
    assert first_undecided(LIST, {p['path']: MARK_MATCH for p in LIST}) == 0


def test_the_next_undecided_photo_follows_the_one_shown_and_wraps_around():
    assert next_undecided(LIST, {}, 0) == 1
    assert next_undecided(LIST, {'b.jpg': MARK_MATCH, 'c.jpg': MARK_NO_MATCH}, 0) == 3
    # after the last photo, the search goes on at the top of the list
    assert next_undecided(LIST, {'a.jpg': MARK_MATCH}, 3) == 1
    # the photo shown is not its own next one (Skip leaves it undecided)
    assert next_undecided(LIST, {'a.jpg': MARK_MATCH, 'b.jpg': MARK_MATCH, 'd.jpg': MARK_MATCH}, 2) is None
    assert next_undecided(LIST, {p['path']: MARK_MATCH for p in LIST}, 1) is None
    assert next_undecided(cards('a.jpg'), {}, 0) is None


def test_the_photo_shown_is_found_again_by_its_path():
    # the list may change while the dialog is open (a new search): the photo is looked up by
    # its path, and a photo no longer in the list starts at the first undecided one
    assert review_index(LIST, {}, 'c.jpg') == 2
    assert review_index(LIST, {'a.jpg': MARK_MATCH}, 'gone.jpg') == 1
    assert review_index(LIST, {}, None) == 0


def test_the_dialog_is_shown_only_for_the_list_its_state_names():
    assert review_shown({'profile': 'Cars', 'path': 'a.jpg'}, 'Cars', LIST)
    assert review_shown({'profile': None, 'path': None}, None, LIST)
    # another list is shown (the selector switched, e.g. to a new quick search), or the
    # list is empty: the state is dropped, so the dialog cannot pop up later (review)
    assert not review_shown({'profile': 'Cars', 'path': 'a.jpg'}, None, LIST)
    assert not review_shown({'profile': None, 'path': 'a.jpg'}, 'Cars', LIST)
    assert not review_shown({'profile': 'Cars', 'path': 'a.jpg'}, 'Cars', [])
    assert not review_shown(None, 'Cars', LIST)


def test_a_review_state_of_another_list_is_dropped():
    functions = app_functions()
    show_review = ast.unparse(functions['show_review'])
    assert 'review_shown(' in show_review and 'close_review()' in show_review
    # the results that end before a view draws its list drop it too
    for function in ('show_results', 'show_quick_results'):
        assert 'close_review' in calls_in(functions[function])
    page = ast.unparse(page_tree())
    assert 'close_review()' in page


def test_the_position_and_the_saved_mark_are_named():
    assert review_position(0, 4) == 'Photo 1 of 4'
    assert review_position(1233, 2000) == 'Photo 1,234 of 2,000'
    assert review_state_text(MARK_MATCH) == 'Marked as match'
    assert review_state_text(MARK_NO_MATCH) == 'Marked as no match'
    assert review_state_text(None) == 'Undecided'
    assert review_state_text('unknown') == 'Undecided'


def test_the_preview_is_large_but_downscaled():
    # larger than the dialog's photo area, far smaller than a camera photo
    assert 1000 <= REVIEW_PREVIEW_SIZE <= 2000


def test_a_click_on_a_card_photo_reaches_the_button_laid_over_it():
    # the button that opens the dialog covers the photo of a card, invisible, so a click on
    # the photo opens the dialog (Streamlit has no clickable image)
    assert f'[class*="st-key-{PHOTO_KEY_PREFIX}"]{{position:relative' in CARD_STYLE
    rule = re.search(r'\[class\*="st-key-' + re.escape(PREVIEW_KEY_PREFIX) + r'"\]\{([^}]*)\}', CARD_STYLE)
    assert rule and 'position:absolute' in rule.group(1) and 'inset:0' in rule.group(1)
    assert 'opacity:0' in CARD_STYLE and 'cursor:zoom-in' in CARD_STYLE
    # neither prefix contains the one of the cards, whose style would apply to them too
    assert 'fscard-' not in PHOTO_KEY_PREFIX + PREVIEW_KEY_PREFIX


def test_the_dialog_fits_a_portrait_photo_into_the_window():
    assert REVIEW_STYLE.startswith('<style>') and 'max-height:' in REVIEW_STYLE and 'object-fit:contain' in REVIEW_STYLE


def app_functions():
    return {node.name: node for node in app_tree().body if isinstance(node, ast.FunctionDef)}


def buttons(function):
    """{label: keywords source} of the st.button calls in function."""
    found = {}
    for node in ast.walk(function):
        if isinstance(node, ast.Call) and ast.unparse(node.func) == 'st.button' and isinstance(node.args[0], ast.Constant):
            found[node.args[0].value] = {k.arg: ast.unparse(k.value) for k in node.keywords}
    return found


def test_the_review_dialog_is_a_streamlit_dialog_with_its_buttons():
    functions = app_functions()
    dialog = functions['review_dialog']
    assert any(ast.unparse(d).startswith('st.dialog(') for d in dialog.decorator_list)
    found = buttons(dialog)
    # each choice saves through save_marks (review_choice) and shows the next undecided photo
    for label, state in (('Match', 'MARK_MATCH'), ('No match', 'MARK_NO_MATCH'), ('Skip', 'None')):
        assert found[label]['on_click'] == 'review_choice'
        assert found[label]['args'].endswith(f', {state})')
        assert 'shortcut' in found[label]
    for label in ('Previous', 'Next'):
        assert found[label]['on_click'] == 'review_step' and 'shortcut' in found[label]
    assert found['Open photo']['on_click'] == 'open_photo'
    assert 'find_similar_button' in {ast.unparse(n.func) for n in ast.walk(dialog) if isinstance(n, ast.Call)}
    assert 'save_marks' in {ast.unparse(n.func) for n in ast.walk(functions['review_choice']) if isinstance(n, ast.Call)}


def calls_in(node):
    return {ast.unparse(n.func) for n in ast.walk(node) if isinstance(n, ast.Call)}


def test_only_decoding_the_preview_falls_back_to_the_thumbnail():
    # review: an error of st.image after its container was drawn would draw a second
    # container with the same key in the fallback (a duplicate-key error), so the try covers
    # the decoding only and the preview is drawn after it
    show_preview = app_functions()['show_preview']
    tries = [n for n in ast.walk(show_preview) if isinstance(n, ast.Try)]
    assert len(tries) == 1
    assert 'cached_preview' in calls_in(tries[0])
    assert not {'st.image', 'st.container'} & set().union(*(calls_in(n) for n in tries[0].body))
    assert 'st.image' in calls_in(show_preview)


def test_a_press_acts_only_on_the_photo_still_shown():
    # review: a second press of M before the dialog was drawn again must neither save the
    # photo twice nor mark the next one, which the user has not seen: the buttons name the
    # photo they were drawn for, the callbacks do nothing once another photo is shown, and
    # the dialog keeps the photo it shows in its state
    functions = app_functions()
    found = buttons(functions['review_dialog'])
    for label in ('Match', 'No match', 'Skip', 'Previous', 'Next'):
        assert "card['path']" in found[label]['args'] and 'index' not in found[label]['args']
    for callback in ('review_choice', 'review_step'):
        first = functions[callback].body[1]  # after the docstring
        assert isinstance(first, ast.If) and ast.unparse(first.test) == 'not _still_shown(path)'
        assert isinstance(first.body[0], ast.Return)
    assert "state = st.session_state.review = {**state, 'path': card['path'], 'notice': None}" in ast.unparse(functions['review_dialog'])


def test_unreadable_marks_are_neither_named_nor_written_against():
    # review: without readable marks (or for a profile that is gone) every photo would look
    # undecided, so the dialog names no saved mark there, and a choice does not save one
    functions = app_functions()
    choice = functions['review_choice']
    assert 'load_marks()[0]' not in ast.unparse(choice)
    guards = [n for n in ast.walk(choice) if isinstance(n, ast.If) and 'marks_error' in ast.unparse(n.test)]
    assert guards and isinstance(guards[0].body[-1], ast.Return) and 'save_marks' not in calls_in(guards[0])
    assert guards[0].lineno < next(n.lineno for n in ast.walk(choice)
                                   if isinstance(n, ast.Call) and ast.unparse(n.func) == 'save_marks')
    named = [n for n in ast.walk(functions['review_dialog'])
             if isinstance(n, ast.IfExp) and 'review_state_text' in calls_in(n.body)]
    assert len(named) == 1 and 'can_mark' in ast.unparse(named[0].test)


def test_the_dialog_shows_the_card_text_as_the_gallery_does():
    # the row of the closest search text as in the gallery: for all cards of the list, so the
    # text keeps its height from photo to photo (review)
    texts = [ast.unparse(n) for n in ast.walk(app_functions()['review_dialog'])
             if isinstance(n, ast.Call) and ast.unparse(n.func) == 'card_text']
    assert texts == ['card_text(card, has_closest_line(cards))']


def test_the_review_dialog_is_opened_from_the_toolbar_and_from_a_card_photo():
    functions = app_functions()
    assert buttons(functions['show_profile_results'])['Review one by one']['on_click'] == 'open_review'
    assert any(keywords.get('on_click') == 'open_review' for keywords in buttons(functions['draw_cards']).values())
    # both views open it when its state names them, the quick search without marks
    calls = {view: [ast.unparse(n) for n in ast.walk(functions[view])
                    if isinstance(n, ast.Call) and ast.unparse(n.func) == 'show_review']
             for view in ('show_profile_results', 'show_quick_results')}
    assert calls == {'show_profile_results': ["show_review(entry['cards'], THUMBS, name, can_mark, find_disabled)"],
                     'show_quick_results': ["show_review(entry['cards'], QUICK_THUMBS, None, False, find_disabled)"]}
    assert 'review_dialog' in {ast.unparse(n.func) for n in ast.walk(functions['show_review'])
                               if isinstance(n, ast.Call)}
    # "Find similar" closes the dialog before it reruns the page
    assert "st.session_state.pop('review', None)" in ast.unparse(functions['find_similar_button'])
