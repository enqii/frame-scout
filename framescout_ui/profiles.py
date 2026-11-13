"""The tab "Search profiles": editing, adding and deleting profiles and their reference images (A13, A22, A46)."""
from pathlib import Path

import streamlit as st

from framescout_core import (MARKS_FILE, MARK_MATCH, ProfilesChangedError, count_text, delete_marks,
                             finish_reference_move, forget_copy_folder, profiles_changed_notice, reference_folder,
                             rename_copy_folder, rename_marks, save_profiles, stage_reference_move,
                             undo_reference_move, update_backup_references, write_new_file)

from .common import BASE, MARKS, PROFILES, REFS, RESULTS, SETTINGS, SUPPORTED, UPLOAD_TYPES, plain, version_key
from .marks import load_marks
from .copy_export import cached_copy_folders


# labels of the profile fields, shared by the edit and the new-profile form (review);
# search terms are English only (E3)
LABEL_NAME = 'Search motif (in English)'
LABEL_CONTEXT = 'Context / origin (optional, in English)'
LABEL_FEATURES = 'Distinctive features (optional, in English)'
LABEL_PROMPTS = 'Custom search texts (optional, in English; one per line)'


def store(build, uploads=(), name='', others=(), keep=(), move=False, *, profiles_shown):
    """Save the profile list build(reference_paths) with the profile's reference images.

    reference_paths are the paths in keep (moved into the folder of name if move is set,
    i.e. after a rename) plus copies of the uploads. Returns True on success. On an error
    nothing changes: the message is shown, the new files and names made for this save are
    removed again and the caller keeps its unchanged profile list, which still matches
    the file on disk. The save is refused if profiles.json changed since this page showed
    the profiles the user edited (profiles_shown, A13): then the page is run again with
    emptied edit forms and the message at the top of the profile tab. profiles_shown: the
    version of profiles.json the forms of the last complete page showed (show_profiles).
    """
    written, staged, refs, new_folder = [], [], list(keep), None
    try:
        if uploads or move:
            # one folder per profile, never one holding references of another profile (A1),
            # named after the profile: a rename moves the profile's files along
            folder = reference_folder(REFS, name, others, BASE)
            new_folder = None if folder.exists() else folder
            if move:
                # old and new names both exist until the save succeeded (crash safety)
                refs, staged = stage_reference_move(refs, folder, REFS, BASE, others)
            # write_new_file never overwrites leftover files in the folder
            for f in uploads:
                suffix = Path(f.name).suffix.lower()
                if suffix in SUPPORTED:
                    written.append(write_new_file(folder, 'reference', suffix, f.getvalue()))
        # keeps the previous file as profiles.json.bak (A2); never overwrites a change made in
        # another tab, session or by hand since the page showed the edited profiles (A13).
        # The next save is based on this saved file, also if the rerun that shows it is
        # interrupted before the forms (review)
        st.session_state.profiles_shown = save_profiles(
            PROFILES, build(refs + [x.relative_to(BASE).as_posix() for x in written]), expected=profiles_shown)
    except (OSError, ValueError) as exc:  # ValueError: e.g. a path that cannot be made relative
        undo_reference_move(staged)
        for x in written:
            try:
                x.unlink()
            except OSError:
                pass
        if new_folder:
            try:
                new_folder.rmdir()  # the folder made for this save; only removed if empty
            except OSError:
                pass
        if isinstance(exc, ProfilesChangedError):
            # the profile at this form's place may now be another one: new widget keys, so
            # that its uploads and "Remove" checkbox are not kept for that profile, and the
            # message at the top of the tab, since the expander of this form may be redrawn
            # closed or no longer exist (review)
            st.session_state.saves = st.session_state.get('saves', 0) + 1
            st.session_state.profile_error = (
                f'Your changes were not saved: {exc}. The page now shows the current search profiles: please '
                'check them and make your changes again. (The input of a new profile is kept.)')
            st.rerun()
        st.error(f'Could not save the search profiles: {exc}. Your changes were not saved.')
        return False
    try:
        # profiles.json.bak still lists the old paths: point it to the new names before the
        # old ones are removed, so restoring the backup keeps working (review)
        update_backup_references(PROFILES, staged, BASE)
    except OSError as exc:
        # keep the old names too, so the backup still points to existing files
        # the next save replaces the backup: the old names are then offered by "Clean up
        # storage" as reference images no profile uses (A43)
        st.session_state.notice = (f'Saved. profiles.json.bak could not be updated ({exc}), so the moved '
                                   'reference images also keep their old names for now. After the next save of '
                                   'the search profiles, "Clean up storage" offers these old files as reference '
                                   'images no profile uses.')
    else:
        problems = finish_reference_move(staged, REFS)
        if problems:
            st.session_state.notice = ('Saved. Some reference images could not be removed from their old folder '
                                       'and now exist twice; the profile uses the new copy: ' + '; '.join(problems))
    # new widget keys for the edit forms: their uploaders would otherwise keep the saved
    # files and add them again on the next save, or pass them to the profile that moves
    # into a deleted profile's place (review)
    st.session_state.saves = st.session_state.get('saves', 0) + 1
    return True


def add_notice(text, first=''):
    """Add text to the one-shot notice at the top of the profile tab; first starts a new notice."""
    # names and error texts (paths) are shown as Markdown: escaped (review)
    st.session_state.notice = (st.session_state.notice + ' ' if 'notice' in st.session_state else first) + plain(text)


def change_name_data(marks_action, folder_action):
    """Run the changes of a renamed or deleted profile's marks and saved copy target folder (A17, A22).

    Both run, also if the first fails. Returns (the result of marks_action or None if it
    failed, the failed parts as text, e.g. "its marks (error)", or '' if none failed).
    """
    results, problems = {}, []
    for what, action in (('marks', marks_action), ('saved copy target folder', folder_action)):
        try:
            results[what] = action()
        except (OSError, ValueError) as exc:
            problems.append(f'its {what} ({exc})')
    return results.get('marks'), ' and '.join(problems)


def carry_over(old, new):
    """Give the marks and the saved target folder of the renamed profile old to its new name (A17)."""
    _, problems = change_name_data(lambda: rename_marks(MARKS, old, new),
                                   lambda: rename_copy_folder(SETTINGS, old, new))
    if problems:
        add_notice(f'The profile was renamed, but {problems} still belong to the old name "{old}".', first='Saved. ')


def deletion_consequences(p):
    """Return the confirmation of deleting the profile p: what happens to its data (A22).

    Returns (its Markdown lines, the number of marks they name, or None if marks.json
    cannot be read).
    """
    name = p['name']
    lines = []
    all_marks, marks_error = load_marks()
    marks = all_marks.get(name, {})
    if marks_error:
        lines.append(f'{MARKS_FILE} cannot be read, so its marks cannot be deleted now: they stay in the file and '
                     f'would pass to a new profile of the same name ({plain(str(marks_error))}).')
    elif marks:
        matches = sum(1 for state in marks.values() if state == MARK_MATCH)
        lines.append(f'Its {count_text(len(marks), "mark", "marks")} ({matches:,} match, {len(marks) - matches:,} '
                     f'no match) in {RESULTS.name}/{MARKS_FILE} {"is" if len(marks) == 1 else "are"} deleted with '
                     'it. This cannot be undone.')
    else:
        lines.append('It has no marks.')
    try:
        saved = cached_copy_folders(*version_key(SETTINGS)).get(name)
    except FileNotFoundError:
        saved = None
    except (OSError, ValueError) as exc:
        lines.append(f'{SETTINGS.name} cannot be read, so a saved copy target folder of it cannot be removed now '
                     f'({plain(str(exc))}).')
        saved = None
    # the folder typed in this session that settings.json could not save is used instead of
    # the saved one (copy_folder_value) and is forgotten as well (review)
    unsaved = st.session_state.get('copy_folders_unsaved', {}).get(name)
    if unsaved is not None:
        lines.append(f'The copy target folder {plain(unsaved) or "(empty)"} typed for it in this session (not saved '
                     f'in {SETTINGS.name}) is forgotten. The folder and the photos copied into it stay where they are.')
    if saved:
        lines.append(f'Its saved copy target folder {plain(saved)} is removed from the settings. The folder and the '
                     'photos copied into it stay where they are.')
    elif unsaved is None:
        lines.append('Photos copied for it stay where they are.')
    refs = p.get('reference_images', [])
    if refs:
        lines.append(f'Its {count_text(len(refs), "reference image", "reference images")} '
                     f'{"stays" if len(refs) == 1 else "stay"} in the references folder, since the backup '
                     'profiles.json.bak still names the profile; "Clean up storage" can delete '
                     f'{"it" if len(refs) == 1 else "them"} later.')
    return lines, None if marks_error else len(marks)


def forget_profile(name, named):
    """Delete the marks and the saved copy target folder of the deleted profile name (A22).

    Called after the deletion is saved; the folder itself and the copies in it are never
    touched. named: the number of marks the confirmation named (None: it could not read
    them). A different number of deleted marks (marked or unmarked since the question)
    and a part that cannot be removed are named in the notice at the top of the tab.
    """
    st.session_state.get('copy_folders_unsaved', {}).pop(name, None)
    deleted, problems = change_name_data(lambda: delete_marks(MARKS, name), lambda: forget_copy_folder(SETTINGS, name))
    if deleted is not None and deleted != (named or 0):
        add_notice(f'The profile "{name}" was deleted with {count_text(deleted, "mark", "marks")}: '
                   + (f'{MARKS_FILE} could not be read when you were asked, but could be read again by then.'
                      if named is None else
                      f'the question named {named:,}, but photos of it were marked or unmarked after it was shown '
                      '(in the gallery, another tab or another window).'))
    if problems:
        add_notice(f'The profile was deleted, but {problems} could not be removed: they still belong to the name '
                   f'"{name}" and would pass to a new profile of that name.')


def show_profiles(profiles, profiles_version, profiles_shown, active):
    """The tab "Search profiles": the saved profiles with their edit forms and the new-profile form.

    profiles and profiles_version: profiles.json as this page run read it; profiles_shown: the
    version the forms of the last complete page showed (A13); active: whether a search runs.
    """
    st.subheader('Saved search profiles')
    # first, so that a one-shot save notice is not missed below the static hint (review)
    if 'notice' in st.session_state:
        st.warning(st.session_state.pop('notice'))
    if 'profile_error' in st.session_state:  # a save refused by store() (A13)
        st.error(st.session_state.pop('profile_error'))
    elif profiles_notice := profiles_changed_notice(profiles_shown, profiles_version):
        # A31: the file changed since the last complete page, e.g. a profile was deleted in
        # another session: a click on a form this page no longer draws was dropped by
        # Streamlit, so say so (a click on a form still drawn is refused by store instead).
        # Only this first run after the change can carry such a click: it redraws the forms
        st.warning(profiles_notice)
    # hint only, no check of the input (user decision on E3: English search terms only);
    # one box with the call to action on an empty list (review)
    st.info(('Create a search profile first. ' if not profiles else '') +
            'Enter the search motif, context, features and custom search texts **in English**. The CLIP model '
            'FrameScout uses understands practically only English: a word in another language, e.g. German '
            '"Schwert" instead of "sword", can find completely different photos.')
    saves = st.session_state.get('saves', 0)
    # "Delete profile" asks first (A8, A22): the profile name and the save count of the click.
    # Any save since (also a refused one) or the profile's disappearance ends the question
    if st.session_state.get('delete_pending') not in [(p['name'], saves) for p in profiles]:
        st.session_state.pop('delete_pending', None)
    for index, p in enumerate(profiles):
        with st.expander(f"{p['name']}  ·  {p.get('franchise','')}"):
            with st.form(f'edit_{index}_{saves}'):
                edit_name = st.text_input(LABEL_NAME, value=p['name'])
                franchise = st.text_input(LABEL_CONTEXT, value=p.get('franchise', ''))
                features = st.text_area(LABEL_FEATURES, value=p.get('features', ''))
                prompts = st.text_area(LABEL_PROMPTS, value='\n'.join(p.get('prompts', [])))
                st.caption('Existing reference images: ' + (', '.join(p.get('reference_images', [])) or 'none'))
                refs_new = st.file_uploader('Add reference images', type=UPLOAD_TYPES, accept_multiple_files=True, key=f'edit_refs_{index}_{saves}')
                clear_refs = st.checkbox('Remove the existing reference images from this profile')
                c1,c2 = st.columns(2)
                update = c1.form_submit_button('Save changes', disabled=active)
                delete = c2.form_submit_button('Delete profile', disabled=active)
            if update:
                edit_name = edit_name.strip()
                if not edit_name or any(j != index and q['name'].strip().lower() == edit_name.lower() for j,q in enumerate(profiles)):
                    st.error('The profile name must be unique and must not be empty.')
                else:
                    def edited(refs, index=index, p=p):
                        # {**p, ...} keeps keys the form does not edit (A2)
                        return profiles[:index] + [{**p, 'name': edit_name, 'franchise': franchise.strip(),
                                'features': features.strip(), 'reference_images': refs,
                                'prompts': [x.strip() for x in prompts.splitlines() if x.strip()]}] + profiles[index+1:]
                    others = profiles[:index] + profiles[index+1:]
                    keep = [] if clear_refs else p.get('reference_images', [])
                    # a renamed profile's reference folder follows the new name (A1)
                    if store(edited, refs_new or [], edit_name, others, keep, move=edit_name != p['name'],
                             profiles_shown=profiles_shown):
                        if edit_name != p['name']:
                            carry_over(p['name'], edit_name)  # its marks and copy folder follow the name (A17)
                        st.rerun()
            if delete:
                # run again before any question is drawn: a question still open for a profile
                # above this one would otherwise be shown too in this run (review)
                st.session_state.delete_pending = (p['name'], saves)
                st.rerun()
            if st.session_state.get('delete_pending') == (p['name'], saves):
                question = st.container()  # filled below the buttons, see there
                c1, c2 = st.columns(2)
                confirmed = c1.button('Delete for good', type='primary', key=f'delete_yes_{index}_{saves}',
                                      disabled=active)
                c2.button('Cancel', key=f'delete_no_{index}_{saves}', on_click=st.session_state.pop,
                          args=('delete_pending', None))
                # new lists instead of changing profiles in place: after a failed save the page
                # keeps showing (and the search uses) exactly what is in profiles.json. A save
                # refused since profiles.json changed (A13) ends the question: the page shows
                # the current profiles, and the user decides again
                if confirmed and store(lambda _, index=index: profiles[:index] + profiles[index+1:],
                                       profiles_shown=profiles_shown):
                    # its marks and saved copy folder go with it (A22), compared with the number
                    # of marks the question the user answered named (review)
                    forget_profile(p['name'], st.session_state.get('delete_marks_named'))
                    st.rerun()
                # after the click is handled: the number the user saw is the one of the run before
                lines, st.session_state.delete_marks_named = deletion_consequences(p)
                question.warning(f'**Delete the profile "{plain(p["name"])}" for good?**\n\n'
                                 + '\n'.join('- ' + line for line in lines))
    st.divider()
    st.subheader('New search profile')
    # the form is emptied only after a successful save, by giving its widgets new keys;
    # after an error the input stays for another try
    form_id = st.session_state.setdefault('new_profile_form', 0)
    with st.form('new_profile'):
        name = st.text_input(LABEL_NAME + ' *', placeholder='e.g. red car, golden retriever, mountain landscape', key=f'new_name_{form_id}')
        franchise = st.text_input(LABEL_CONTEXT, placeholder='e.g. vehicles, pets, nature', key=f'new_context_{form_id}')
        features = st.text_area(LABEL_FEATURES, placeholder='red bodywork, black roof, parked on a street', key=f'new_features_{form_id}')
        prompts = st.text_area(LABEL_PROMPTS, key=f'new_prompts_{form_id}')
        uploads = st.file_uploader('Reference images (optional)', type=UPLOAD_TYPES, accept_multiple_files=True, key=f'new_refs_{form_id}')
        create = st.form_submit_button('Add profile', disabled=active)
    if create:
        name = name.strip()
        if not name or any(x['name'].strip().lower() == name.lower() for x in profiles):
            st.error('Please enter a unique name.')
        else:
            def added(refs):
                return profiles + [{'name':name, 'franchise':franchise.strip(), 'features':features.strip(),
                                    'prompts':[x.strip() for x in prompts.splitlines() if x.strip()], 'reference_images':refs}]
            if store(added, uploads or [], name, profiles, profiles_shown=profiles_shown):
                st.session_state.new_profile_form = form_id + 1
                st.rerun()
    st.caption('FrameScout automatically creates several English CLIP search texts from the name, context and features; '
               'it does not translate them. No language model is required.')
    # the forms above show this version now: the next submit is based on it (A13)
    st.session_state.profiles_shown = profiles_version
