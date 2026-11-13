"""The result galleries of the last search and of the last quick search (A12, P4, F10, F11, A46)."""
from pathlib import Path

import streamlit as st

from framescout_core import (GALLERY_PAGE_SIZE, MARKS_FILE, MARK_OPEN, MODELS, QUICK_DIR, QUICK_GALLERY, hidden_text,
                             hide_no_match, mark_style, page_cards, page_count, profile_fingerprints, profile_state,
                             progress_text, query_caption, query_summary, quick_folders_differ, quick_note,
                             read_results, results_model, review_progress)

from .common import (PROFILES, QUICK_THUMBS, RESULTS, RESULTS_JSON, THUMBS, file_key, open_gallery, open_photo,
                     open_quick_folder, open_quick_gallery, open_results_folder, plain, show_photo, widget_id)

from .marks import MARK_LABELS, load_marks, marks_backup_offer, restore_marks_backup, set_mark
from .copy_export import show_copy, show_export


GALLERY_COLUMNS = 4


def go_to_page(key, page):
    """Show page of the gallery whose page box has key (on_click of "Go to the first undecided photo", F20)."""
    st.session_state[key] = page


@st.cache_data(show_spinner=False, max_entries=4)  # the profiles' and the quick search's (F10)
def cached_results(path, mtime_ns, size):
    """read_results, read again only when the file changes (mtime_ns and size are the cache key)."""
    return read_results(Path(path))


@st.cache_data(show_spinner=False, max_entries=2)
def cached_fingerprints(path, mtime_ns, size):
    """profile_fingerprints, computed again only when profiles.json changes (review: not on every click)."""
    return profile_fingerprints(Path(path))


@st.cache_data(show_spinner=False, max_entries=4)
def cached_bytes(path, mtime_ns, size):
    """The content of a file, read again only when it changes (the gallery's HTML download)."""
    return Path(path).read_bytes()


def load_results(path=RESULTS_JSON):
    """Return (results of the last search or None, error or None) (A12); path: QUICK_JSON for the quick search (F10)."""
    try:
        stat = path.stat()
        return cached_results(str(path), stat.st_mtime_ns, stat.st_size), None
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError) as exc:
        return None, exc


def run_date(results):
    return str(results.get('finished', '')).replace('T', ' ')[:16]


def find_similar_button(card, key, disabled):
    """The button "Find similar" of a gallery card (F11): asks the next page run to start it.

    A fragment cannot start the engine (start_engine reruns the whole page), so the click
    stores the photo and the part shown on the card and reruns the page, which starts it.
    A missing model package does not disable it: it loads no model (review). disabled: while
    a search runs or no photo folder exists (the page run's state).
    """
    if st.button('Find similar', key=key, width='stretch', disabled=disabled,
                 help='Finds photos similar to this one (the part named on the card) among the photos analyzed with '
                      'the current AI settings, without analyzing anything. The result replaces the last quick '
                      'search.'):
        st.session_state.find_similar = (card['path'], card['label'])
        st.rerun()


@st.fragment
def show_results(results, photo_folders, model, find_disabled):
    """The galleries of the last search as a grid of thumbnails; its buttons rerun only this part (P4).

    With a mark per photo and copying of the matches (A17); photo_folders: the folders a
    copy target must not be in. model: the search model the AI settings choose now;
    find_disabled: whether "Find similar" is disabled (find_similar_button).
    """
    entries = results['profiles']
    if not entries:
        st.caption('The last search wrote no galleries.')
        return
    try:
        fingerprints = cached_fingerprints(*file_key(PROFILES))
    except (OSError, ValueError):
        fingerprints = {}
    states = {e['name']: profile_state(e, fingerprints) for e in entries}
    names = [e['name'] for e in entries]
    if st.session_state.get('results_profile') not in names:
        st.session_state.pop('results_profile', None)  # e.g. a profile of an earlier search
    # the options are the plain names: a state note in them would give the widget a new
    # identity in Streamlit versions that do not use the key as its identity and jump back
    # to the first profile whenever a profile is edited (review); the notes are shown below
    name = st.selectbox('Search profile', names, key='results_profile')
    entry = entries[names.index(name)]
    # the settings of that search, not the app's settings
    run_settings = results.get('settings') if isinstance(results.get('settings'), dict) else {}
    folders = results['photo_folders']  # also for a format 1 file (A25)
    model_key = results_model(run_settings)  # the default for a search before E22
    result_model = MODELS.get(model_key) if model_key else None
    st.caption(f"Search from {run_date(results)} · photo folder{'s' if len(folders) > 1 else ''} "
               f"{plain('; '.join(folders))} · "
               + (f'search model {plain(result_model.label)} · ' if result_model else '') +
               f"{len(entry['cards']):,} photos (at most {run_settings.get('top', '?')}), best first. "
               'A ranking by similarity, not a guaranteed identification.')
    # which of the profile's texts the photos were closest to (F17); none for older results
    if summary := query_summary(entry):
        st.caption(plain(summary))
    if model_key != model:
        # E22 review: the gallery must not look like one of the model chosen now
        made_with = f'the search model {plain(result_model.label)}' if result_model else 'another search model'
        st.info(f'These results were made with {made_with}; the AI settings now choose '
                f"{plain(MODELS[model].label)}. Start the search again for its results.")
    if states[name] == 'changed':
        st.info(f'"{plain(name)}" was changed after this search (search texts or reference images), so these '
                'results may not fit it any more. Start the search again to update them.')
    elif states[name] == 'missing':
        st.info(f'"{plain(name)}" is no longer one of your search profiles (renamed or deleted). These are its '
                f'results from the search of {run_date(results)}. Its photos cannot be marked here, nor its copy '
                'target folder changed: a renamed '
                "profile took its marks along, and they appear with the next search's results; deleting "
                'a profile deletes its marks too.')
    others = {state: [plain(n) for n in names if n != name and states[n] == state] for state in ('changed', 'missing')}
    if others['changed'] or others['missing']:
        st.caption(' · '.join(text + ', '.join(found) for text, found in (
            ('Changed since this search: ', others['changed']),
            ('No longer search profiles: ', others['missing'])) if found))
    c1, c2, c3 = st.columns(3)
    c1.button('Open gallery in browser', on_click=open_gallery, args=(entry['gallery'],), width='stretch',
              help=f"Opens {entry['gallery']} from the results folder in your web browser.")
    c2.button('Open results folder', on_click=open_results_folder, width='stretch')
    page_file = RESULTS / entry['gallery']
    try:
        # cached: a click on Open or Folder reruns this fragment (review)
        c3.download_button('Download HTML (without thumbnails)', cached_bytes(*file_key(page_file)), file_name=page_file.name,
                           mime='text/html', width='stretch', key='dl_results_gallery')
    except OSError:
        pass  # deleted or in use: the other buttons still work
    if st.session_state.get('gallery_notice'):
        st.warning(plain(st.session_state.pop('gallery_notice')))  # paths: no Markdown
    # read on every run of this part: another tab or session may have marked photos (A17)
    all_marks, marks_error = load_marks()
    if 'marks_notice' in st.session_state:
        kind, text = st.session_state.pop('marks_notice')
        (st.success if kind == 'success' else st.warning)(plain(text))
    # also for a missing marks.json whose backup holds marks, e.g. removed by hand (A40)
    offer = marks_backup_offer(marks_error)
    if marks_error:
        advice = ('Restore the backup below, or fix the file in the results folder' if offer
                  else 'Fix or remove it in the results folder')
        st.warning(f'{MARKS_FILE} cannot be read, so marks are not shown and cannot be changed; FrameScout does not '
                   f'change the file. {advice}.\n\nDetails: {plain(str(marks_error))}')
    if offer:
        st.caption(plain(offer))
        st.button('Restore marks from backup', on_click=restore_marks_backup, key='restore_marks')
    marks = all_marks.get(name, {})
    can_mark = marks_error is None and states[name] != 'missing'
    hide = st.checkbox('Hide photos marked as no match', key='hide_rejected',
                       help='Hides them on the page shown; every page keeps its photos, so the ranks of a page '
                            'stay the same.')
    pages = page_count(len(entry['cards']), GALLERY_PAGE_SIZE)
    key = 'results_page_' + name
    if st.session_state.get(key, 1) not in range(1, pages + 1):
        # a page of a longer list of an earlier search; dropped before the jump button below
        # compares the page shown with its target (F20 review)
        st.session_state.pop(key, None)
    # review progress (F20), only where photos can be marked: without readable marks every
    # photo would count as undecided, and a renamed profile took its marks along
    progress = review_progress(entry['cards'], marks, GALLERY_PAGE_SIZE) if can_mark else None
    if progress and (text := progress_text(progress, pages > 1)):
        st.caption(text)
    if progress and progress.first_open_page and pages > 1:
        # a callback: it sets the page box below before the run that draws it
        st.button('Go to the first undecided photo', key='first_open_' + widget_id(name),
                  on_click=go_to_page, args=(key, progress.first_open_page),
                  disabled=st.session_state.get(key, 1) == progress.first_open_page,
                  help=f'Shows page {progress.first_open_page}, which holds #{progress.first_open_rank}, '
                       'the best-ranked photo not yet marked as Match or No match.')
    # the whole ranked list is paginated and the rejects are hidden within the page shown
    # (A24): filtering first pulled the photos of the following pages up into this one
    page = 1
    if pages > 1:
        page = st.selectbox(f'Page (of {pages})', range(1, pages + 1), key=key)
    shown, hidden = hide_no_match(page_cards(entry['cards'], page, GALLERY_PAGE_SIZE), marks if hide else {})
    if hidden:
        st.caption(hidden_text(hidden, len(shown), page < pages))
    mark_keys = {}
    for card in shown:
        # the saved mark, set before the control is drawn (never as its default): the file
        # is the truth, also for marks made in another tab
        mark_keys[card['rank']] = key = 'mark_' + widget_id(name, card['path'])
        st.session_state[key] = MARK_LABELS[marks.get(card['path'], MARK_OPEN)]
    colors = mark_style({mark_keys[card['rank']]: marks.get(card['path'], MARK_OPEN) for card in shown})
    # the style block rides in this caption, which is drawn anyway: an element of its own took
    # a layout slot with the block gap above the cards (A38); replaced on every run like it
    st.caption((colors + '\n\n' if colors else '') +
               '"Open" and "Folder" use the programs of the computer FrameScout runs on. Mark each photo you have '
               'checked as Match or No match; marks are kept for this profile across searches.',
               unsafe_allow_html=bool(colors))
    # a new container for every profile, page and card count: in a fragment rerun with fewer
    # cards (the shorter last page) the rows of the previous page stayed in the browser
    # (checked in Edge with Streamlit 1.66; a st.empty placeholder did not help)
    with st.container(key=f'gallery_{names.index(name)}_{page}_{len(shown)}'):
        for start in range(0, len(shown), GALLERY_COLUMNS):
            for column, card in zip(st.columns(GALLERY_COLUMNS), shown[start:start + GALLERY_COLUMNS]):
                with column:
                    thumb = THUMBS / card['thumbnail']  # a plain file name, checked by read_results
                    if thumb.is_file():
                        st.image(str(thumb))
                    else:
                        st.caption('No thumbnail')
                    st.markdown(f"**#{card['rank']}** · {plain(card['caption'])} · {plain(card['label'])}")
                    closest = card.get('best_query')  # F17: only with several texts
                    st.caption(f"{plain(card['detail'])}  \n"
                               + (f'{plain(query_caption(closest))}  \n' if closest else '')
                               + plain(card['relative']))
                    b1, b2 = st.columns(2)
                    b1.button('Open', key=f"open_{card['rank']}", on_click=open_photo, args=(card['path'],),
                              width='stretch', help='Opens the photo in your image viewer.')
                    b2.button('Folder', key=f"reveal_{card['rank']}", on_click=show_photo, args=(card['path'],),
                              width='stretch', help='Shows the photo in its folder.')
                    find_similar_button(card, f"similar_{card['rank']}", find_disabled)
                    key = mark_keys[card['rank']]
                    st.segmented_control('Mark', list(MARK_LABELS.values()), key=key, on_change=set_mark,
                                         args=(name, card['path'], key), disabled=not can_mark,
                                         label_visibility='collapsed')
    show_copy(name, entry, marks, photo_folders, states[name] != 'missing')
    show_export(name, entry, marks, marks_error)


@st.fragment
def show_quick_results(results, folders, model, find_disabled):
    """The gallery of the last quick search (F10) as a grid of thumbnails; no marks, copying or export.

    folders: the photo folders chosen now, to tell whether it searched others; model and
    find_disabled as in show_results. Its buttons rerun only this part, as in show_results.
    """
    entries = results['profiles']
    if not entries:
        st.caption('The last quick search wrote no gallery.')
        return
    entry = entries[0]
    run_settings = results.get('settings') if isinstance(results.get('settings'), dict) else {}
    model_key = results_model(run_settings)
    result_model = MODELS.get(model_key) if model_key else None
    searched_folders = results['photo_folders']  # also for a format 1 file (A25)
    quick = results.get('quick') if isinstance(results.get('quick'), dict) else {}
    # "Find similar" (F11) names its photo (by its file name, as the gallery title does, review)
    # and the part compared
    like = quick.get('like') if isinstance(quick.get('like'), str) else None
    part = quick.get('part') if isinstance(quick.get('part'), str) else None
    what = (f"Photos similar to {plain(Path(like).name)}" + (f' ({plain(part)})' if part else '') if like
            else f"Quick search for \"{plain(entry['name'])}\"")
    st.caption(f"{what} from {run_date(results)} · photo "
               f"folder{'s' if len(searched_folders) > 1 else ''} {plain('; '.join(searched_folders))} · "
               + (f'search model {plain(result_model.label)} · ' if result_model else '') +
               f"{len(entry['cards']):,} photos (at most {run_settings.get('top', '?')}), best first. "
               'A ranking by similarity, not a guaranteed identification.')
    searched, not_analyzed = quick.get('searched'), quick.get('not_analyzed')
    if all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in (searched, not_analyzed)):
        st.caption(quick_note(searched, not_analyzed, like=bool(like)))
    if quick_folders_differ(searched_folders, [folder for folder in folders if folder.is_dir()]):
        # review: the profile galleries name their folders; these may be of a folder no longer chosen
        st.info('This quick search searched other photo folders than the ones chosen now. Start it again for the '
                'current folders.')
    if model_key != model:
        made_with = f'the search model {plain(result_model.label)}' if result_model else 'another search model'
        st.info(f'This quick search was made with {made_with}; the AI settings now choose '
                f"{plain(MODELS[model].label)}.")
    c1, c2 = st.columns(2)
    c1.button('Open gallery in browser', on_click=open_quick_gallery, width='stretch', key='quick_open_gallery',
              help=f'Opens {QUICK_GALLERY} from the folder {QUICK_DIR} in the results folder in your web browser.')
    c2.button('Open quick search folder', on_click=open_quick_folder, width='stretch', key='quick_open_folder')
    if st.session_state.get('gallery_notice'):
        st.warning(plain(st.session_state.pop('gallery_notice')))  # paths: no Markdown
    pages = page_count(len(entry['cards']), GALLERY_PAGE_SIZE)
    page = 1
    if pages > 1:
        if st.session_state.get('quick_page', 1) not in range(1, pages + 1):
            st.session_state.pop('quick_page', None)  # a page of a longer list of an earlier quick search
        page = st.selectbox(f'Page (of {pages})', range(1, pages + 1), key='quick_page')
    shown = page_cards(entry['cards'], page, GALLERY_PAGE_SIZE)
    # a new container for every page and card count, as in show_results
    with st.container(key=f'quick_gallery_{page}_{len(shown)}'):
        for start in range(0, len(shown), GALLERY_COLUMNS):
            for column, card in zip(st.columns(GALLERY_COLUMNS), shown[start:start + GALLERY_COLUMNS]):
                with column:
                    thumb = QUICK_THUMBS / card['thumbnail']  # a plain file name, checked by read_results
                    if thumb.is_file():
                        st.image(str(thumb))
                    else:
                        st.caption('No thumbnail')
                    st.markdown(f"**#{card['rank']}** · {plain(card['caption'])} · {plain(card['label'])}")
                    st.caption(f"{plain(card['detail'])}  \n{plain(card['relative'])}")
                    b1, b2 = st.columns(2)
                    b1.button('Open', key=f"quick_open_{card['rank']}", on_click=open_photo, args=(card['path'],),
                              width='stretch', help='Opens the photo in your image viewer.')
                    b2.button('Folder', key=f"quick_reveal_{card['rank']}", on_click=show_photo,
                              args=(card['path'],), width='stretch', help='Shows the photo in its folder.')
                    find_similar_button(card, f"quick_similar_{card['rank']}", find_disabled)
