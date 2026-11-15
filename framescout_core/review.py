"""The review dialog of a result list: one photo at a time with a large preview (F19)."""
from .marks import MARK_MATCH, MARK_NO_MATCH

# the longer edge of the preview in pixels: decoded at reduced scale and downscaled in
# memory (framescout_images.render_preview), larger than the dialog's photo area
REVIEW_PREVIEW_SIZE = 1600
# the key of the dialog's container of the preview
REVIEW_PHOTO_KEY = 'fsreview-photo'
# the preview fits into the window, centered, also a portrait photo, with room for the
# dialog's title, the card text and the buttons below it (about 24rem, checked in headless
# Edge with Streamlit 1.66.1, whose internals it relies on: the data-testid of the frame
# around an image, see MARK_STYLE_STREAMLIT): the dialog is as wide as the window allows, so a photo shown
# at its width would be taller than the window
REVIEW_STYLE = (f'<style>.st-key-{REVIEW_PHOTO_KEY} [data-testid="stFullScreenFrame"] > div{{margin:0 auto}}'
                f'.st-key-{REVIEW_PHOTO_KEY} img{{max-height:max(240px, calc(100vh - 24rem));width:auto!important;'
                'max-width:100%;object-fit:contain}</style>')
_STATE_TEXTS = {MARK_MATCH: 'Marked as match', MARK_NO_MATCH: 'Marked as no match'}


def _undecided(cards, marks, index):
    return marks.get(cards[index]['path']) not in (MARK_MATCH, MARK_NO_MATCH)


def first_undecided(cards, marks):
    """Return the index of the first photo of cards not marked as match or no match, or 0 if every one is.

    cards: the ranked result cards of one list; marks: that profile's marks of read_marks. A
    state other than match or no match counts as undecided, as in the gallery.
    """
    return next((index for index in range(len(cards)) if _undecided(cards, marks, index)), 0)


def next_undecided(cards, marks, index):
    """Return the index of the next undecided photo after the one at index, or None if no other one is.

    The search goes on at the top of the list after its last photo; the photo at index is
    never its own next one (Skip leaves it undecided).
    """
    total = len(cards)
    return next((other % total for other in range(index + 1, index + total)
                 if _undecided(cards, marks, other % total)), None)


def review_index(cards, marks, path):
    """Return the index of the photo path in cards, or first_undecided if it is no longer there.

    The dialog keeps the photo it shows by its path: the list may change while it is open
    (a new search finished).
    """
    found = next((index for index, card in enumerate(cards) if path is not None and card['path'] == path), None)
    return first_undecided(cards, marks) if found is None else found


def review_shown(state, profile, cards):
    """Whether the review state (st.session_state.review, or None) opens the dialog over the list cards of profile.

    profile: the profile of the gallery shown (None: the quick search). The dialog is shown
    only while its state names the list shown and that list has photos; a state of another
    list must be dropped then (the selector may switch, e.g. to a new quick search, without
    the dialog's on_dismiss), or the dialog would pop up later unprompted.
    """
    return state is not None and bool(cards) and state.get('profile') == profile


def review_position(index, total):
    """Return where the photo at index is in a list of total photos, e.g. "Photo 3 of 150"."""
    return f'Photo {index + 1:,} of {total:,}'


def review_state_text(state):
    """Return the saved mark of the photo shown, as the dialog names it."""
    return _STATE_TEXTS.get(state, 'Undecided')
