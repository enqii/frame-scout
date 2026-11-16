"""The review dialog: one photo of a result list at a time with a large preview (F19)."""
from pathlib import Path

import streamlit as st

from framescout_core.marks import MARKS_FILE, MARK_MATCH, MARK_NO_MATCH, save_marks
from framescout_core.results import card_text, has_closest_line, openable_photo
from framescout_core.review import (REVIEW_PHOTO_KEY, REVIEW_PREVIEW_SIZE, REVIEW_STYLE, first_undecided,
                                    next_undecided, review_index, review_position, review_shown, review_state_text)
from framescout_images import render_preview

from .common import MARKS, PROFILES, file_key, open_photo, plain
from .marks import load_marks


def find_similar_button(card, key, disabled):
    """The button "Find similar" of a gallery card and of the review dialog (F11, F19).

    A fragment cannot start the engine (start_engine reruns the whole page), so the click
    stores the photo and the part shown on the card and reruns the page, which starts it;
    it closes the review dialog first. A missing model package does not disable it: it
    loads no model (review). disabled: while a search runs or no photo folder exists (the
    page run's state).
    """
    if st.button('Find similar', key=key, width='stretch', disabled=disabled,
                 help='Finds photos similar to this one (the part named on the card) among the photos analyzed with '
                      'the current AI settings, without analyzing anything. The result replaces the last quick '
                      'search.'):
        st.session_state.pop('review', None)
        st.session_state.find_similar = (card['path'], card['label'])
        st.rerun()


def open_review(profile, path):
    """Open the review dialog of the gallery of profile (None: the quick search) at the photo path, or None (F19).

    on_click of "Review one by one" (path None: the first undecided photo) and of a card's photo.
    """
    st.session_state.review = {'profile': profile, 'path': path}


def close_review():
    """Close the review dialog (on_dismiss: its "X", Esc or a click outside)."""
    st.session_state.pop('review', None)


def _show(path, notice=None):
    st.session_state.review = {**st.session_state.get('review', {}), 'path': path, 'notice': notice}


def _still_shown(path):
    """Whether the dialog still shows the photo path, for which the button pressed was drawn.

    A second press before the dialog is drawn again (e.g. M pressed twice quickly) arrives
    with the arguments of the photo before: it is ignored, so it neither saves that photo
    again nor acts on the next one, which the user has not seen yet (review).
    """
    return st.session_state.get('review', {}).get('path') == path


def review_step(cards, path, step):
    """Show the photo step places from the photo path (on_click of "Previous" and "Next")."""
    if not _still_shown(path):
        return
    index = review_index(cards, {}, path)
    _show(cards[min(max(index + step, 0), len(cards) - 1)]['path'])


def review_choice(profile, cards, path, state):
    """Save state for the photo path and show the next undecided photo (on_click of "Match", "No match", "Skip").

    state None is "Skip": the photo stays as it is. A mark is saved through save_marks, only
    for a profile that still exists, as on a card (set_mark). If marks.json cannot be read
    (now), no mark is saved, and Skip moves to the next photo, since every photo counts as
    undecided then.
    """
    if not _still_shown(path):
        return
    index = review_index(cards, {}, path)
    all_marks, marks_error = load_marks()
    marks = dict(all_marks.get(profile, {}))
    if marks_error is not None and state is not None:
        _show(path, ('warning', f'{MARKS_FILE} cannot be read, so the mark is not saved: {marks_error}'))
        return
    if state is not None:
        try:
            save_marks(MARKS, profile, {path: state}, profiles_file=PROFILES)
        except (OSError, ValueError) as exc:
            _show(path, ('warning', f'The mark could not be saved: {exc}'))
            return
        marks[path] = state
    following = next_undecided(cards, marks, index)
    if following is not None:
        _show(cards[following]['path'])
    elif state is None:
        _show(path, ('info', 'No other photo of this list is undecided.'))
    else:
        _show(path, ('success', 'Every photo of this list is marked.'))


@st.cache_data(show_spinner=False, max_entries=8)
def cached_preview(path, mtime_ns, size):
    """render_preview of the photo path, decoded again only when the file changes (mtime_ns and size are the key)."""
    return render_preview(path, REVIEW_PREVIEW_SIZE)


def show_preview(card, thumbs):
    """The large preview of the photo of card, or its thumbnail (from the folder thumbs) with the reason."""
    photo = openable_photo(card['path'])
    problem = 'The photo is no longer there, so its thumbnail is shown.'
    if photo is not None:
        # only the decoding is caught: an error after the container below was drawn would
        # draw a second one with the same key in the fallback (review)
        try:
            with st.spinner('Loading the photo…'):
                data = cached_preview(*file_key(photo))
        except Exception as exc:  # any decoder error: the dialog stays usable
            problem = f'The photo cannot be shown ({plain(str(exc))}), so its thumbnail is shown.'
        else:
            with st.container(key=REVIEW_PHOTO_KEY):
                st.image(data, width='stretch')
            return
    st.caption(problem)
    thumb = thumbs / card['thumbnail']  # a plain file name, checked by read_results
    if thumb.is_file():
        with st.container(key=REVIEW_PHOTO_KEY):
            st.image(str(thumb), width='stretch')


@st.dialog('Review one by one', width='large', on_dismiss=close_review)
def review_dialog(cards, thumbs, profile, can_mark, find_disabled):
    """One photo of cards at a time with a large preview (F19); its buttons rerun only the dialog.

    profile: the profile of the gallery, whose marks it shows and saves; None for the quick
    search, which has no marks. can_mark and find_disabled as in draw_cards. "Match", "No
    match" and "Skip" show the next undecided photo; "Previous" and "Next" go through the
    whole ranked list, also through photos hidden on the page by "Hide no match". The
    gallery behind shows the new marks once the dialog is closed (it reruns the page).
    """
    state = st.session_state.get('review', {})
    marks = load_marks()[0].get(profile, {}) if profile is not None else {}
    index = review_index(cards, marks, state.get('path'))
    card = cards[index]
    if state.get('path') != card['path']:
        # the photo shown (the first undecided one, or another if the list changed), which
        # the buttons below act on (_still_shown)
        state = st.session_state.review = {**state, 'path': card['path'], 'notice': None}
    saved = marks.get(card['path'])
    # the style block rides in this caption, which is drawn anyway, as CARD_STYLE does in the
    # gallery: an element of its own takes a layout slot with the block gap (A38)
    st.caption(REVIEW_STYLE + '\n\n' + review_position(index, len(cards))
               # no saved mark where the photos cannot be marked: without readable marks, or for
               # a profile that is gone (it took its marks along), every photo would look undecided
               + (f' · {review_state_text(saved)}' if profile is not None and can_mark else '')
               + ' · A ranking by similarity, not a guaranteed identification.', unsafe_allow_html=True)
    show_preview(card, thumbs)
    st.markdown(card_text(card, has_closest_line(cards)), unsafe_allow_html=True)
    notice = state.get('notice')
    if notice:
        kind, text = notice
        {'success': st.success, 'info': st.info}.get(kind, st.warning)(plain(text))
    if profile is not None:
        with st.container(horizontal=True, gap='small'):
            st.button('Match', key='review_match', on_click=review_choice,
                      args=(profile, cards, card['path'], MARK_MATCH), shortcut='M', disabled=not can_mark,
                      help='Saves this photo as a match and shows the next undecided one.')
            st.button('No match', key='review_no_match', on_click=review_choice,
                      args=(profile, cards, card['path'], MARK_NO_MATCH), shortcut='N', disabled=not can_mark,
                      help='Saves this photo as no match and shows the next undecided one.')
            st.button('Skip', key='review_skip', on_click=review_choice, args=(profile, cards, card['path'], None),
                      shortcut='S', help='Leaves this photo as it is and shows the next undecided one.')
        if not can_mark:
            st.caption('The photos of this list cannot be marked here (see the note above the gallery).')
    with st.container(horizontal=True, gap='small'):
        st.button('Previous', key='review_previous', on_click=review_step, args=(cards, card['path'], -1),
                  shortcut='Left', disabled=index == 0)
        st.button('Next', key='review_next', on_click=review_step, args=(cards, card['path'], 1),
                  shortcut='Right', disabled=index == len(cards) - 1)
        st.button('Open photo', key='review_open', on_click=open_photo, args=(card['path'],), shortcut='O',
                  help='Opens the photo in your image viewer.')
        with st.container(width=160):
            find_similar_button(card, 'review_similar', find_disabled)


def show_review(cards, thumbs, profile, can_mark, find_disabled):
    """Open the review dialog if its state names the gallery of profile (None: the quick search), on every run.

    The dialog is called again on each run of the results, so a rerun of the page keeps it open.
    A state of another list (or of an empty one) is dropped (review_shown).
    """
    state = st.session_state.get('review')
    if not review_shown(state, profile, cards):
        close_review()
        return
    review_dialog(cards, Path(thumbs), profile, can_mark, find_disabled)
