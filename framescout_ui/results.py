"""The result galleries of the last search and of the last quick search."""
from pathlib import Path

import streamlit as st

from framescout_core.marks import (CARD_KEY_PREFIX, CARD_STYLE, CARD_WIDTH, MARKS_FILE, MARK_OPEN, PHOTO_KEY_PREFIX,
                                   PREVIEW_KEY_PREFIX, hidden_text, hide_no_match, mark_counts_text, mark_style,
                                   progress_text, review_progress)
from framescout_core.models import MODELS, results_model
from framescout_core.quick import (QUICK_DIR, QUICK_GALLERY, quick_entry_label, quick_folders_differ, quick_note,
                                   quick_result_id, results_choice)
from framescout_core.results import (GALLERY_PAGE_SIZE, card_text, has_closest_line, page_cards, page_count,
                                     profile_fingerprints, profile_state, query_summary, read_results)

from .common import (PROFILES, QUICK_THUMBS, RESULTS, RESULTS_JSON, THUMBS, close_popover, file_key, open_gallery,
                     open_photo, open_quick_folder, open_quick_gallery, open_results_folder, plain, show_photo,
                     widget_id)

from .marks import MARK_LABELS, load_marks, marks_backup_offer, restore_marks_backup, set_mark
from .copy_export import run_copy_request, show_copy, show_export
from .review import close_review, find_similar_button, open_review, show_review


# the cell of a card without a thumbnail, as tall as one with a photo (CARD_STYLE); the
# margin is the one a Markdown paragraph has: Streamlit (1.66.1) gives every Markdown
# container margin-bottom -1rem (its spacing "lg") to cancel its last paragraph's 1rem, which
# a div lacks (checked in headless Edge: the text starts at the same height as on a photo card)
NO_THUMBNAIL = ('<div style="aspect-ratio:1/1;display:flex;align-items:center;justify-content:center;'
                'opacity:0.6;background:rgba(128, 128, 128, 0.12);border-radius:4px;margin-bottom:1rem">'
                'No thumbnail</div>')
# the widths of the boxes of the toolbar row above the photos in pixels; the other
# controls of the row take the width of their content
TOOLBAR_SELECT_WIDTH = 280
TOOLBAR_PAGE_WIDTH = 130
# the width of the content of the popover "Export and copy" in pixels: fixed, so a long
# caption or folder path wraps instead of widening it to about 700 px
EXPORT_POPOVER_WIDTH = 440
# the key of the popover "Export and copy", which its buttons close (close_popover)
EXPORT_POPOVER = 'export_copy'


def go_to_page(key, page):
    """Show page of the gallery whose page box has key (on_click of the pager below the grid)."""
    st.session_state[key] = page


@st.cache_data(show_spinner=False, max_entries=4)  # the profiles' and the quick search's
def cached_results(path, mtime_ns, size):
    """read_results, read again only when the file changes (mtime_ns and size are the cache key)."""
    return read_results(Path(path))


@st.cache_data(show_spinner=False, max_entries=2)
def cached_fingerprints(path, mtime_ns, size):
    """profile_fingerprints, computed again only when profiles.json changes, not on every click."""
    return profile_fingerprints(Path(path))


@st.cache_data(show_spinner=False, max_entries=4)
def cached_bytes(path, mtime_ns, size):
    """The content of a file, read again only when it changes (the gallery's HTML download)."""
    return Path(path).read_bytes()


def load_results(path=RESULTS_JSON):
    """Return (results of the last search or None, error or None); path: QUICK_JSON for the quick search."""
    try:
        stat = path.stat()
        return cached_results(str(path), stat.st_mtime_ns, stat.st_size), None
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError) as exc:
        return None, exc


def run_date(results):
    return str(results.get('finished', '')).replace('T', ' ')[:16]


def card_key(card, profile=None):
    """The key of the container of card in the gallery of profile, or of the quick search for None."""
    parts = ('quick', card['path']) if profile is None else ('profile', profile, card['path'])
    return CARD_KEY_PREFIX + widget_id(*parts)


def draw_cards(cards, thumbs, key, find_disabled, with_closest, profile=None, can_mark=False):
    """The gallery cards of one page in the container key, as many in a row as the window has room for.

    One card for both views: thumbnails (from the folder thumbs) fitted into equal cells by
    CARD_STYLE, which the view draws; the card text (card_text, with_closest from
    has_closest_line of the whole gallery); the mark control "Match" / "No" of the gallery of profile
    (None: the quick search, which has no marks), disabled unless can_mark; the other
    actions in the popover "More". The cards have a fixed width and wrap, so a wide window
    shows more of them in a row. find_disabled as in show_results.
    """
    prefix = 'quick_' if profile is None else ''
    with st.container(key=key, horizontal=True, gap='small'):
        for card in cards:
            with st.container(key=card_key(card, profile), width=CARD_WIDTH, border=True, gap='small'):
                photo_id = widget_id(*(('quick',) if profile is None else ('profile', profile)), card['path'])
                # a click on the photo opens the review dialog there: the invisible button
                # laid over the photo by CARD_STYLE
                with st.container(key=PHOTO_KEY_PREFIX + photo_id, gap=None):
                    thumb = thumbs / card['thumbnail']  # a plain file name, checked by read_results
                    if thumb.is_file():
                        st.image(str(thumb), width='stretch')
                    else:
                        st.markdown(NO_THUMBNAIL, unsafe_allow_html=True)
                    st.button('Large preview', key=PREVIEW_KEY_PREFIX + photo_id, on_click=open_review,
                              args=(profile, card['path']))
                st.markdown(card_text(card, with_closest), unsafe_allow_html=True)
                with st.container(horizontal=True, vertical_alignment='center', gap='small'):
                    if profile is not None:
                        mark_key = 'mark_' + widget_id(profile, card['path'])
                        st.segmented_control('Mark', list(MARK_LABELS.values()), key=mark_key, on_change=set_mark,
                                             args=(profile, card['path'], mark_key), disabled=not can_mark,
                                             label_visibility='collapsed',
                                             help='Neither pressed: undecided. A second click takes the mark back.')
                    # closed by each of its buttons, so it does not cover the cards below;
                    # tracking its state costs a rerun per open and close
                    more_key = 'more_' + photo_id
                    with st.popover('More', help='Open the photo or show it in its folder, with the programs of the '
                                                 'computer FrameScout runs on, or find similar photos.',
                                    key=more_key, on_change='rerun'):
                        st.button('Open photo', key=f"{prefix}open_{card['rank']}", on_click=close_popover,
                                  args=(more_key, open_photo, card['path']), width='stretch',
                                  help='Opens the photo in your image viewer.')
                        st.button('Show in folder', key=f"{prefix}reveal_{card['rank']}", on_click=close_popover,
                                  args=(more_key, show_photo, card['path']), width='stretch',
                                  help='Shows the photo in its folder.')
                        find_similar_button(card, f"{prefix}similar_{card['rank']}", find_disabled, close=more_key)


def bottom_pager(key, page, pages, prefix, progress=None):
    """The pager below the grid: previous and next page, and the jump to the first undecided photo.

    key is the key of the page box of the toolbar; the buttons set it in a callback, before
    the run that draws it (go_to_page). prefix tells the buttons of the views apart.
    progress: the ReviewProgress of a profile whose photos can be marked, or None.
    """
    jump = progress is not None and progress.first_open_page and pages > 1
    if pages > 1 or jump:
        with st.container(horizontal=True, vertical_alignment='center', gap='small'):
            if pages > 1:
                st.button('Previous page', key=prefix + 'previous_page', on_click=go_to_page, args=(key, page - 1),
                          disabled=page <= 1)
                st.markdown(f'Page {page} of {pages}', width='content')
                st.button('Next page', key=prefix + 'next_page', on_click=go_to_page, args=(key, page + 1),
                          disabled=page >= pages)
            if jump:
                st.button('Go to the first undecided photo', key=prefix + 'first_open',
                          on_click=go_to_page, args=(key, progress.first_open_page),
                          disabled=page == progress.first_open_page,
                          help=f'Shows page {progress.first_open_page}, which holds #{progress.first_open_rank}, '
                               'the best-ranked photo not yet marked as Match or No match.')
    if progress is not None and (text := progress_text(progress, pages > 1)):
        st.caption(text)


def show_notice(key):
    """Show and drop the notice a callback left under key in the session state: (kind, text) or a warning text."""
    if not st.session_state.get(key):
        return
    notice = st.session_state.pop(key)
    kind, text = notice if isinstance(notice, tuple) else ('warning', notice)
    (st.success if kind == 'success' else st.warning)(plain(text))  # paths: no Markdown


@st.fragment
def show_results(results, quick, photo_folders, folders, model, find_disabled):
    """The results of the last search and of the last quick search, one at a time; its buttons rerun only this part.

    A selector offers the galleries of the last search and, as an entry of its own, the
    last quick search or "Find similar", which it shows at once when it is new. It is
    the first control of one toolbar row above the photos, which the views fill.
    results, quick: their result files (either may be None); photo_folders: the folders a
    copy target must not be in (show_profile_results); folders: the photo folders chosen now
    (show_quick_results); model: the search model the AI settings choose now;
    find_disabled: whether "Find similar" is disabled (find_similar_button).
    """
    # taken in every run of this part, also one that shows no profile gallery: a copy
    # request is never kept to copy photos in a later, unrelated run
    copy_request = st.session_state.pop('copy_request', None)
    entries = results['profiles'] if results else []
    if not entries and not quick:
        close_review()  # no list to review
        if results:
            st.caption('The last search wrote no galleries.')
        return
    names = [e['name'] for e in entries]
    quick_option = quick_entry_label(quick, names) if quick else None
    # the options are the plain names: a state note in them would give the widget a new
    # identity in Streamlit versions that do not use the key as its identity and jump back
    # to the first profile whenever a profile is edited; the notes are shown below
    options = names + ([quick_option] if quick_option else [])
    # a quick result this browser session has not seen yet is shown at once; one that was
    # there at the session's first page run is not (it is the result of an earlier visit)
    quick_id = quick_result_id(quick) if quick else None
    quick_new = 'quick_seen' in st.session_state and st.session_state.quick_seen != quick_id
    st.session_state.quick_seen = quick_id
    chosen = results_choice(options, st.session_state.get('results_profile'), quick_option, quick_new)
    if chosen is None:
        st.session_state.pop('results_profile', None)  # e.g. a profile of an earlier search
    else:
        st.session_state.results_profile = chosen
    # the toolbar row; bottom: the boxes with a label above and the buttons line up
    toolbar = st.container(horizontal=True, vertical_alignment='bottom', gap='small')
    with toolbar:
        name = st.selectbox('Results of', options, key='results_profile', width=TOOLBAR_SELECT_WIDTH)
    if name == quick_option:
        show_quick_results(quick, folders, model, find_disabled, toolbar)
    else:
        show_profile_results(results, name, photo_folders, model, find_disabled, toolbar, copy_request)


def show_profile_results(results, name, photo_folders, model, find_disabled, toolbar, copy_request):
    """The gallery of the profile name of the last search as a grid of thumbnails.

    With a mark per photo and copying of the matches; photo_folders: the folders a
    copy target must not be in; model and find_disabled as in show_results. toolbar: the
    row above the photos, which gets the counts of the marks, "Hide no match", the page
    box and the popover "Export and copy"; the notes for exceptional states follow below it
    only when they apply, a second pager below the grid. copy_request: the copy the
    button "Copy marked photos" asked for (request_copy), or None.
    """
    entries = results['profiles']
    try:
        fingerprints = cached_fingerprints(*file_key(PROFILES))
    except (OSError, ValueError):
        fingerprints = {}
    states = {e['name']: profile_state(e, fingerprints) for e in entries}
    names = [e['name'] for e in entries]
    entry = entries[names.index(name)]
    # the settings of that search, not the app's settings
    run_settings = results.get('settings') if isinstance(results.get('settings'), dict) else {}
    folders = results['photo_folders']  # also for a format 1 file
    model_key = results_model(run_settings)  # the default for results that do not name their search model
    result_model = MODELS.get(model_key) if model_key else None
    # read on every run of this part: another tab or session may have marked photos
    all_marks, marks_error = load_marks()
    marks = all_marks.get(name, {})
    can_mark = marks_error is None and states[name] != 'missing'
    pages = page_count(len(entry['cards']), GALLERY_PAGE_SIZE)
    key = 'results_page_' + name
    if st.session_state.get(key, 1) not in range(1, pages + 1):
        # a page of a longer list of an earlier search; dropped before the pagers below
        # compare the page shown with their targets
        st.session_state.pop(key, None)
    # review progress, only where photos can be marked: without readable marks every
    # photo would count as undecided, and a renamed profile took its marks along
    progress = review_progress(entry['cards'], marks, GALLERY_PAGE_SIZE) if can_mark else None
    # below the toolbar, in this order: the caption of the search, the notes, the notices
    # (drawn into later)
    head = st.container(gap='small')
    notices = st.container(gap='small')
    with toolbar:
        if progress and (counts := mark_counts_text(progress)):
            st.markdown(counts, width='content',
                        help='Mark each photo you have checked as Match or No; a second click takes the mark back. '
                             'Marks are kept for this profile across searches.')
        # persist_state: kept while another entry of the selector is shown, which does not draw
        # the box
        hide = st.checkbox('Hide no match', key='hide_rejected', persist_state='page',
                           help='Hides the photos marked as no match on the page shown; every page keeps its '
                                'photos, so the ranks of a page stay the same.')
        # the whole ranked list is paginated and the rejects are hidden within the page shown
        # filtering first would pull the photos of the following pages up into this one
        page = 1
        if pages > 1:
            # persist_state: kept while another entry of the selector is shown
            page = st.selectbox(f'Page (of {pages})', range(1, pages + 1), key=key, persist_state='page',
                                width=TOOLBAR_PAGE_WIDTH)
        # from the first undecided photo of the whole list
        st.button('Review one by one', key='review_open_list', on_click=open_review, args=(name, None),
                  disabled=not can_mark or not entry['cards'],
                  help='Shows one photo at a time, large, starting with the first undecided one: mark it as Match or '
                       'No match, or skip it, and the next undecided photo follows. A click on a photo opens it there '
                       'too.' + ('' if can_mark else ' The photos of this list cannot be marked here.'))
        # closed by each of its buttons, so it does not cover the notices below the toolbar;
        # its content is drawn only while it is open
        with st.popover('Export and copy', help='Open or download the gallery, copy the photos marked as match '
                                                'to a folder or export the result list.',
                        key=EXPORT_POPOVER, on_change='rerun'), st.container(width=EXPORT_POPOVER_WIDTH):
            show_gallery_actions(entry, EXPORT_POPOVER)
            st.divider()
            show_copy(name, entry, marks, photo_folders, states[name] != 'missing', EXPORT_POPOVER)
            st.divider()
            show_export(name, entry, marks, marks_error, EXPORT_POPOVER)
    with notices:
        # the copy the popover's button asked for, with its progress bar, and the export's result
        run_copy_request(copy_request, name, photo_folders)
        show_notice('export_notice')
    shown, hidden = hide_no_match(page_cards(entry['cards'], page, GALLERY_PAGE_SIZE), marks if hide else {})
    for card in shown:
        # the saved mark, set before the control is drawn (never as its default): the file
        # is the truth, also for marks made in another tab; None (neither button) is undecided
        st.session_state['mark_' + widget_id(name, card['path'])] = MARK_LABELS.get(marks.get(card['path']))
    colors = mark_style({card_key(card, name): marks.get(card['path'], MARK_OPEN) for card in shown})
    with head:
        # the style blocks ride in this caption, which is drawn anyway: an element of its own
        # would take a layout slot with the block gap above the cards; replaced on every run
        # like it. Which of the profile's texts the photos were closest to follows on
        # the same line; none for older results
        summary = query_summary(entry)
        st.caption(CARD_STYLE + colors + '\n\n'
                   + f"Search from {run_date(results)} · photo folder{'s' if len(folders) > 1 else ''} "
                     f"{plain('; '.join(folders))} · "
                   + (f'search model {plain(result_model.label)} · ' if result_model else '')
                   + f"{len(entry['cards']):,} photos (at most {run_settings.get('top', '?')}), best first. "
                     'A ranking by similarity, not a guaranteed identification.'
                   + (f' {plain(summary)}' if summary else ''), unsafe_allow_html=True)
        if model_key != model:
            # the gallery must not look like one of the model chosen now
            made_with = f'the search model {plain(result_model.label)}' if result_model else 'another search model'
            st.info(f'These results were made with {made_with}; the AI settings now choose '
                    f"{plain(MODELS[model].label)}. Start the search again for its results.")
        if states[name] == 'changed':
            st.info(f'"{plain(name)}" was changed after this search (search texts or reference images), so these '
                    'results may not fit it any more. Start the search again to update them.')
        elif states[name] == 'missing':
            st.info(f'"{plain(name)}" is no longer one of your search profiles (renamed or deleted). These are its '
                    f'results from the search of {run_date(results)}. Its photos cannot be marked here, nor its '
                    'copy target folder changed: a renamed '
                    "profile took its marks along, and they appear with the next search's results; deleting "
                    'a profile deletes its marks too.')
        others = {state: [plain(n) for n in names if n != name and states[n] == state]
                  for state in ('changed', 'missing')}
        if others['changed'] or others['missing']:
            st.caption(' · '.join(text + ', '.join(found) for text, found in (
                ('Changed since this search: ', others['changed']),
                ('No longer search profiles: ', others['missing'])) if found))
        # also for a missing marks.json whose backup holds marks, e.g. removed by hand
        offer = marks_backup_offer(marks_error)
        if marks_error:
            advice = ('Restore the backup below, or fix the file in the results folder' if offer
                      else 'Fix or remove it in the results folder')
            st.warning(f'{MARKS_FILE} cannot be read, so marks are not shown and cannot be changed; FrameScout does '
                       f'not change the file. {advice}.\n\nDetails: {plain(str(marks_error))}')
        if offer:
            st.caption(plain(offer))
            st.button('Restore marks from backup', on_click=restore_marks_backup, key='restore_marks')
    with notices:
        show_notice('gallery_notice')
        show_notice('marks_notice')
        if hidden:
            st.caption(hidden_text(hidden, len(shown), page < pages))
    show_review(entry['cards'], THUMBS, name, can_mark, find_disabled)  # the review dialog, while it is open
    # a new container for every profile, page and card count: in a fragment rerun with fewer
    # cards (the shorter last page) the cards of the previous page stayed in the browser
    # (checked in Edge with Streamlit 1.66; a st.empty placeholder did not help)
    draw_cards(shown, THUMBS, f'gallery_{names.index(name)}_{page}_{len(shown)}', find_disabled,
               has_closest_line(entry['cards']), profile=name, can_mark=can_mark)
    bottom_pager(key, page, pages, 'results_' + widget_id(name) + '_', progress)


def show_gallery_actions(entry, popover):
    """The buttons of the HTML gallery of a profile in the popover "Export and copy", which they close."""
    st.markdown('**Gallery**')
    st.button('Open gallery in browser', on_click=close_popover, args=(popover, open_gallery, entry['gallery']),
              width='stretch', help=f"Opens {entry['gallery']} from the results folder in your web browser.")
    page_file = RESULTS / entry['gallery']
    try:
        # cached: a click on another button reruns this fragment
        st.download_button('Download HTML (without thumbnails)', cached_bytes(*file_key(page_file)),
                           file_name=page_file.name, mime='text/html', width='stretch', key='dl_results_gallery')
    except OSError:
        pass  # deleted or in use: the other buttons still work
    st.button('Open results folder', on_click=close_popover, args=(popover, open_results_folder), width='stretch')


def show_quick_results(results, folders, model, find_disabled, toolbar):
    """The gallery of the last quick search as a grid of thumbnails; no marks, copying or export.

    folders: the photo folders chosen now, to tell whether it searched others; model and
    find_disabled as in show_results, whose entry it is. toolbar: the row above the
    photos, which gets the page box and the popover "Gallery and folder".
    """
    entries = results['profiles']
    if not entries:
        close_review()  # no list to review
        st.caption('The last quick search wrote no gallery.')
        return
    entry = entries[0]
    run_settings = results.get('settings') if isinstance(results.get('settings'), dict) else {}
    model_key = results_model(run_settings)
    result_model = MODELS.get(model_key) if model_key else None
    searched_folders = results['photo_folders']  # also for a format 1 file
    quick = results.get('quick') if isinstance(results.get('quick'), dict) else {}
    pages = page_count(len(entry['cards']), GALLERY_PAGE_SIZE)
    if st.session_state.get('quick_page', 1) not in range(1, pages + 1):
        st.session_state.pop('quick_page', None)  # a page of a longer list of an earlier quick search
    with toolbar:
        page = 1
        if pages > 1:
            page = st.selectbox(f'Page (of {pages})', range(1, pages + 1), key='quick_page',
                                persist_state='page', width=TOOLBAR_PAGE_WIDTH)  # kept while a profile is shown
        with st.popover('Gallery and folder', help='Open the gallery of this quick search or its folder.'):
            st.button('Open gallery in browser', on_click=open_quick_gallery, width='stretch', key='quick_open_gallery',
                      help=f'Opens {QUICK_GALLERY} from the folder {QUICK_DIR} in the results folder in your web '
                           'browser.')
            st.button('Open quick search folder', on_click=open_quick_folder, width='stretch', key='quick_open_folder')
    # "Find similar" names its photo (by its file name, as the gallery title does)
    # and the part compared
    like = quick.get('like') if isinstance(quick.get('like'), str) else None
    part = quick.get('part') if isinstance(quick.get('part'), str) else None
    what = (f"Photos similar to {plain(Path(like).name)}" + (f' ({plain(part)})' if part else '') if like
            else f"Quick search for \"{plain(entry['name'])}\"")
    # the style block rides in this caption, as in show_profile_results
    st.caption(CARD_STYLE + f"\n\n{what} from {run_date(results)} · photo "
               f"folder{'s' if len(searched_folders) > 1 else ''} {plain('; '.join(searched_folders))} · "
               + (f'search model {plain(result_model.label)} · ' if result_model else '') +
               f"{len(entry['cards']):,} photos (at most {run_settings.get('top', '?')}), best first. "
               'A ranking by similarity, not a guaranteed identification.', unsafe_allow_html=True)
    searched, not_analyzed = quick.get('searched'), quick.get('not_analyzed')
    if all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in (searched, not_analyzed)):
        st.caption(quick_note(searched, not_analyzed, like=bool(like)))
    if quick_folders_differ(searched_folders, [folder for folder in folders if folder.is_dir()]):
        # as the profile galleries name their folders: these may be of a folder no longer chosen
        st.info('This quick search searched other photo folders than the ones chosen now. Start it again for the '
                'current folders.')
    if model_key != model:
        made_with = f'the search model {plain(result_model.label)}' if result_model else 'another search model'
        st.info(f'This quick search was made with {made_with}; the AI settings now choose '
                f"{plain(MODELS[model].label)}.")
    show_notice('gallery_notice')
    shown = page_cards(entry['cards'], page, GALLERY_PAGE_SIZE)
    show_review(entry['cards'], QUICK_THUMBS, None, False, find_disabled)  # the large preview, without marks
    # a new container for every page and card count, as in show_profile_results
    draw_cards(shown, QUICK_THUMBS, f'quick_gallery_{page}_{len(shown)}', find_disabled,
               has_closest_line(entry['cards']))
    bottom_pager('quick_page', page, pages, 'quick_')
