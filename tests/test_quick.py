"""Quick search over the analyzed photos without a profile (F10, framescout_core.quick)."""
import ast
import collections
import os
from pathlib import Path

import pytest

from framescout_core import (FULL_IMAGE_LABEL, QUICK_DIR, QUICK_GALLERY, QUICK_QUERY_MAX, PhotoScan, auto_cleanup,
                             engine_command, generic_prompts, like_crop, like_labels_fit, like_profile, like_scan_path,
                             quick_folders_differ,
                             quick_note,
                             quick_photos, quick_profile, quick_scope, quick_scope_text, read_results,
                             results_document,
                             publish_export, result_card, scan_cleanup)

from app_source import app_tree, page_tree


def test_quick_results_go_to_their_own_folder_and_gallery():
    # the profile galleries, results.json and marks.json of results/ stay untouched (F10)
    assert QUICK_DIR == 'quick'
    assert QUICK_GALLERY == 'quick.html'


def test_quick_profile_uses_the_generated_prompts_of_a_profile_with_that_name():
    assert quick_profile('red car in the snow') == {
        'name': 'red car in the snow', 'prompts': generic_prompts('red car in the snow'),
        'generated': 4, 'refs': []}


def test_quick_profile_joins_white_space_and_keeps_a_bar():
    # no "NAME|CONTEXT|FEATURES" split as for --character: the text is searched as typed
    profile = quick_profile('  a dog |\n on the  beach ')
    assert profile['name'] == 'a dog | on the beach'
    assert profile['prompts'][0] == 'A photograph of a dog | on the beach.'


@pytest.mark.parametrize('query', ['', '   ', '\n\t'])
def test_quick_profile_refuses_an_empty_text(query):
    with pytest.raises(ValueError, match='empty'):
        quick_profile(query)


def test_quick_profile_refuses_a_text_that_is_too_long():
    quick_profile('x' * QUICK_QUERY_MAX)
    with pytest.raises(ValueError, match=str(QUICK_QUERY_MAX)):
        quick_profile('x' * (QUICK_QUERY_MAX + 1))


def test_quick_photos_takes_only_the_analyzed_photos_in_their_order():
    paths = [Path('a.jpg'), Path('b.jpg'), Path('c.jpg')]
    chosen, missing = quick_photos(paths, {}, lambda path: path.name != 'b.jpg')
    assert chosen == [Path('a.jpg'), Path('c.jpg')]
    assert missing == [Path('b.jpg')]


def test_quick_photos_takes_the_analyzed_raw_file_of_a_partner_without_a_row():
    # E30: a full search analyzed the RAW file in place of its broken JPEG
    jpeg, heic, raw = Path('shot.jpg'), Path('shot.heic'), Path('shot.cr3')
    rows = {raw}
    chosen, missing = quick_photos([jpeg, heic], {jpeg: raw, heic: raw}, rows.__contains__)
    # one shot, one photo: the second partner does not take the RAW file again, and it is
    # not counted as not analyzed either (E61)
    assert chosen == [raw]
    assert missing == []


def test_quick_photos_shows_a_shot_once_if_one_partner_and_its_raw_file_have_rows():
    # review: the RAW file stands in for a partner only if no other partner of the shot is
    # analyzed, as in a full search (E30); in either order of the partners. E61: the partner
    # without a row is not counted as not analyzed, since a full search would not analyze
    # the shot again through it either
    jpeg, heic, raw = Path('shot.jpg'), Path('shot.heic'), Path('shot.cr3')
    for rows in ({jpeg, raw}, {jpeg}):
        for paths in ([jpeg, heic], [heic, jpeg]):
            chosen, missing = quick_photos(paths, {jpeg: raw, heic: raw}, rows.__contains__)
            assert chosen == [jpeg]
            assert missing == []


def test_quick_photos_does_not_count_a_partner_whose_shot_is_searched_through_its_raw_file():
    # E61: the RAW file analyzed in place of one broken partner stands for the whole shot
    jpeg, heic, raw, other = Path('shot.jpg'), Path('shot.heic'), Path('shot.cr3'), Path('other.jpg')
    chosen, missing = quick_photos([jpeg, heic, other], {jpeg: raw, heic: raw}, {raw}.__contains__)
    assert chosen == [raw]
    assert missing == [other]


def test_quick_photos_counts_every_partner_of_a_shot_without_any_row():
    # a full search analyzes each of them: both are not analyzed
    jpeg, heic, raw = Path('shot.jpg'), Path('shot.heic'), Path('shot.cr3')
    chosen, missing = quick_photos([jpeg, heic], {jpeg: raw, heic: raw}, lambda path: False)
    assert (chosen, missing) == ([], [jpeg, heic])


def test_quick_photos_asks_about_each_photo_once():
    jpeg, heic, raw, other = Path('shot.jpg'), Path('shot.heic'), Path('shot.cr3'), Path('other.jpg')
    asked = []
    quick_photos([jpeg, heic, other], {jpeg: raw, heic: raw}, lambda path: asked.append(path) or False)
    assert sorted(asked) == sorted([jpeg, heic, other, raw])


def test_quick_photos_leaves_out_the_photo_of_find_similar():
    # F11: the chosen photo is neither compared with itself nor counted as not analyzed
    paths = [Path('a.jpg'), Path('b.jpg'), Path('c.jpg')]
    chosen, missing = quick_photos(paths, {}, lambda path: path.name != 'c.jpg', exclude=Path('a.jpg'))
    assert chosen == [Path('b.jpg')]
    assert missing == [Path('c.jpg')]


def test_quick_photos_leaves_out_the_whole_shot_of_find_similar():
    # the RAW file of the chosen JPEG is not shown as its best match, nor the partner whose
    # RAW file was chosen (E30)
    jpeg, raw, other = Path('shot.jpg'), Path('shot.cr3'), Path('other.jpg')
    chosen, missing = quick_photos([jpeg, other], {jpeg: raw}, {jpeg, raw, other}.__contains__, exclude=jpeg)
    assert (chosen, missing) == ([other], [])
    chosen, missing = quick_photos([jpeg, other], {jpeg: raw}, {raw, other}.__contains__, exclude=raw)
    assert (chosen, missing) == ([other], [])


def test_quick_photos_leaves_out_every_partner_of_the_shot_of_find_similar():
    # review: a partner with a row of its own is left out too, whether the chosen photo is
    # the RAW file (e.g. analyzed while the JPEG was broken) or another partner
    jpeg, heic, raw, other = Path('shot.jpg'), Path('shot.heic'), Path('shot.cr3'), Path('other.jpg')
    fallbacks = {jpeg: raw, heic: raw}
    rows = {jpeg, heic, raw, other}.__contains__
    for exclude in (raw, jpeg, heic):
        chosen, missing = quick_photos([jpeg, heic, other], fallbacks, rows, exclude=exclude)
        assert (chosen, missing) == ([other], []), exclude
    # a partner of the shot without a row is not counted as not analyzed either
    chosen, missing = quick_photos([jpeg, heic, other], fallbacks, {raw, other}.__contains__, exclude=raw)
    assert (chosen, missing) == ([other], [])


def test_quick_folders_differ_tells_a_search_of_other_folders(tmp_path):
    # review: the app notes quick results of folders no longer chosen; the order does not matter
    a, b = tmp_path / 'a', tmp_path / 'b'
    assert not quick_folders_differ([str(a), str(b)], [b, a])
    assert quick_folders_differ([str(a)], [a, b])
    assert quick_folders_differ([str(a), str(b)], [a])
    assert quick_folders_differ([], [a])


def test_quick_scope_text_names_the_photos_that_are_not_searched():
    assert quick_scope_text(0, 0, 0) == 'No supported photos found in these folders: there is nothing to search.'
    assert quick_scope_text(10, 0, 10) == ('None of the 10 photos is analyzed with these AI settings yet, so a quick '
                                           'search finds nothing. Start a search with your profiles first: it '
                                           'analyzes them.')
    assert quick_scope_text(1200, 1200, 0) == 'All 1,200 photos are analyzed with these AI settings and searched.'
    assert quick_scope_text(1200, 1000, 200) == ('1,000 of 1,200 photos are analyzed with these AI settings and '
                                                 'searched; the other 200 are not searched until a search with your '
                                                 'profiles analyzes them.')
    assert quick_scope_text(13, 12, 1) == ('12 of 13 photos are analyzed with these AI settings and searched; the '
                                           'other photo is not searched until a search with your profiles analyzes '
                                           'them.')
    # counts above the photos (e.g. counted at another time) are capped
    assert quick_scope_text(5, 7, 0) == 'All 5 photos are analyzed with these AI settings and searched.'


def test_quick_scope_text_names_the_partners_whose_shot_is_searched():
    # E61: a JPEG/HEIC partner without a row whose shot is searched through another file
    assert quick_scope_text(10, 8, 0, 2) == ('8 of 10 photos are analyzed with these AI settings and searched; the '
                                             'other 2 are not analyzed, but another file of their shots (the same '
                                             'picture in another format) is searched.')
    assert quick_scope_text(10, 6, 3, 1) == ('6 of 10 photos are analyzed with these AI settings and searched; 3 are '
                                             'not searched until a search with your profiles analyzes them; 1 other '
                                             'is not analyzed, but another file of its shot (the same picture in '
                                             'another format) is searched.')
    # review: only partners whose shot is searched through its RAW file, with or without
    # photos that are not analyzed; the count is given, not inferred from the others
    assert quick_scope_text(2, 0, 0, 2) == ('The 2 photos are not analyzed with these AI settings themselves, but '
                                            'another file of their shots (the same picture in another format) is '
                                            'searched.')
    assert quick_scope_text(1, 0, 0, 1) == ('The photo is not analyzed with these AI settings itself, but another '
                                            'file of its shot (the same picture in another format) is searched.')
    assert quick_scope_text(5, 0, 3, 2) == ('2 of 5 photos are not analyzed with these AI settings themselves, but '
                                            'another file of their shots (the same picture in another format) is '
                                            'searched; the other 3 are not searched until a search with your '
                                            'profiles analyzes them.')
    assert quick_scope_text(5, 0, 4, 1) == ('1 of 5 photos is not analyzed with these AI settings itself, but another '
                                            'file of its shot (the same picture in another format) is searched; the '
                                            'other 4 are not searched until a search with your profiles analyzes '
                                            'them.')


def test_quick_scope_counts_as_the_engine_does(tmp_path):
    # E61: the app counts a quick search with the RAW files of the scan, as the engine does;
    # a folder whose analyzed photos are all RAW files in place of their broken partner (E30)
    # has photos to search. Review: (searched, not analyzed, partners) count the scan's
    # photos, so they add up to them; searched are the photos with a row of their own
    jpeg, heic, raw, other = (tmp_path / name for name in ('a.jpg', 'a.heic', 'a.cr3', 'b.jpg'))
    scan = PhotoScan([jpeg, heic, other], [raw], collections.Counter(), 0, 0, {})
    assert quick_scope(scan, {raw}) == (0, 1, 2)
    assert quick_scope(scan, {jpeg, other}) == (2, 0, 1)
    assert quick_scope(scan, {jpeg, raw}) == (1, 1, 1)
    assert quick_scope(scan, set()) == (0, 3, 0)
    # a shot of a JPEG and a HEIC whose only row is its RAW file's: both are partners
    pair = PhotoScan([jpeg, heic], [raw], collections.Counter(), 0, 0, {})
    assert quick_scope(pair, {raw}) == (0, 0, 2)


def test_quick_note_says_how_many_photos_were_searched_and_that_scores_differ():
    note = quick_note(800, 200)
    assert note.startswith('Quick search over the 800 photos analyzed with these AI settings; 200 photos were not '
                           'analyzed and not searched.')
    assert 'differ from those of a search with profiles' in note
    assert 'not analyzed' not in quick_note(800, 0)


def test_quick_note_of_find_similar_names_the_photos_compared():
    # F11: the photo itself is not among them
    note = quick_note(799, 200, like=True)
    assert note.startswith('Photos similar to the chosen one among the other 799 photos analyzed with these AI '
                           'settings; 200 photos were not analyzed and not searched.')
    assert 'differ from those of a search with profiles' in note
    assert quick_note(1, 0, like=True).startswith('Photos similar to the chosen one among the other photo analyzed')


def test_like_profile_has_no_text_and_names_the_photo_and_its_part():
    # F11: ranked by the photo's cached vector alone, no search text
    photo = Path('D:/photos/IMG_0001.jpg')
    assert like_profile(photo, FULL_IMAGE_LABEL) == {'name': 'Similar to IMG_0001.jpg', 'prompts': [],
                                                     'generated': 0, 'refs': []}
    assert like_profile(photo, 'Person 2')['name'] == 'Similar to IMG_0001.jpg (Person 2)'


def test_like_crop_finds_the_part_shown_on_the_card():
    assert like_crop(['Full image', 'Person 1', 'Person 3'], 'Person 3') == 2
    assert like_crop(['Full image', 'Person 1'], FULL_IMAGE_LABEL) == 0
    # rows written before I7 carry the German label of the whole photo
    assert like_crop(['Gesamtbild', 'Person 1'], FULL_IMAGE_LABEL) == 0


def test_like_crop_refuses_a_part_the_photo_has_not():
    # e.g. a card of a search with person detection, compared with settings without it
    with pytest.raises(ValueError, match='Person 2.*Full image, Person 1'):
        like_crop(['Full image', 'Person 1'], 'Person 2')


def test_like_scan_path_names_the_photo_as_the_scan_does():
    # review: the cache row and the shot are found by the scan's path, also for a photo given
    # by another path to the same file (letter case, a link or junction, a mapped drive)
    scanned = [Path('C:/photos/a.jpg'), Path('C:/photos/Sub/IMG_1.JPG'), Path('C:/photos/Sub/IMG_1.CR3')]
    asked = []

    def same_file(path, photo):
        asked.append(path)
        return path.as_posix().casefold() == photo.as_posix().casefold().replace('d:/', 'c:/photos/')

    assert str(like_scan_path(Path('C:/photos/a.jpg'), scanned, same_file)) == str(scanned[0])
    assert asked == []  # the scan's own path is taken as it is
    assert str(like_scan_path(Path('c:/PHOTOS/sub/img_1.jpg'), scanned, same_file)) == str(scanned[1])
    assert str(like_scan_path(Path('D:/Sub/IMG_1.CR3'), scanned, same_file)) == str(scanned[2])
    # only the files of the same name are compared
    assert set(asked) <= {scanned[1], scanned[2]}
    # a photo the scan has not found (e.g. outside the searched folders) stays as given
    other = Path('E:/elsewhere/IMG_1.JPG')
    assert like_scan_path(other, scanned, lambda *_: False) == other


def test_like_scan_path_skips_files_it_cannot_compare(tmp_path):
    photo = tmp_path / 'b.jpg'
    photo.write_bytes(b'x')

    def same_file(path, _):
        if path.parent.name == 'gone':
            raise OSError('gone')
        return path == photo

    scanned = [tmp_path / 'gone' / 'b.jpg', photo]
    assert like_scan_path(tmp_path / '.' / 'b.jpg', scanned, same_file) == photo
    # the real comparison of the files: the same file by another path (letter case on Windows)
    if os.name == 'nt':
        assert str(like_scan_path(Path(str(photo).upper()), [photo])) == str(photo)


def test_like_labels_fit_only_one_text_per_vector():
    # review: a broken row of the chosen photo counts as not analyzed instead of crashing
    # with an IndexError (more labels than vectors) or a TypeError (labels that are no texts)
    assert like_labels_fit(['Full image', 'Person 1'], 2)
    assert not like_labels_fit(['Full image', 'Person 1'], 1)
    assert not like_labels_fit(['Full image'], 2)
    assert not like_labels_fit([], 0)
    assert not like_labels_fit({'Full image': 0}, 1)
    assert not like_labels_fit([['Full image']], 1)


def test_the_engine_checks_the_row_of_find_similar_before_like_crop():
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'framescout_engine.py').read_text(encoding='utf-8'))
    lines = {name: [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call)
                    and getattr(node.func, 'id', '') == name] for name in ('like_labels_fit', 'like_crop')}
    assert len(lines['like_labels_fit']) == 1 and len(lines['like_crop']) == 1
    assert lines['like_labels_fit'][0] < lines['like_crop'][0]


def test_the_engine_names_the_photo_of_find_similar_as_its_scan_does():
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'framescout_engine.py').read_text(encoding='utf-8'))
    [call] = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
              and getattr(node.func, 'id', '') == 'like_scan_path']
    assert ast.unparse(call) == 'like_scan_path(like_photo, [*paths, *scan.raw_pairs])'
    reads = [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call)
             and getattr(node.func, 'id', '') in ('cached_features', 'quick_photos')]
    assert reads and call.lineno < min(reads)


def command(**kwargs):
    settings = {'batch_size': 8, 'top': 150, 'max_persons': 12, 'person_confidence': 0.3, 'reference_weight': 0.3,
                'model': 'vit-b-32', 'person_detection': True, 'low_priority': False}
    settings.update(kwargs.pop('settings', {}))
    return engine_command('python', 'engine.py', [Path('D:/a'), Path('E:/b')], Path('results'), settings, 'auto',
                          **kwargs)


def test_engine_command_of_a_search_with_profiles():
    assert command(profiles=Path('profiles.json')) == [
        'python', '-u', 'engine.py', str(Path('D:/a')), str(Path('E:/b')), '--profiles', 'profiles.json',
        '--output', 'results', '--device', 'auto', '--batch-size', '8', '--top', '150', '--max-persons', '12',
        '--person-confidence', '0.3', '--reference-weight', '0.3', '--model', 'vit-b-32']


def test_engine_command_adds_the_switches_of_the_settings():
    cmd = command(profiles=Path('profiles.json'), settings={'person_detection': False, 'low_priority': True})
    assert cmd[-2:] == ['--no-person-detection', '--low-priority']


def test_engine_command_of_a_quick_search_passes_the_text_in_one_argument():
    # "--quick-query=<text>": a text starting with "-" is not taken for an option
    cmd = command(quick_query='-red car')
    assert '--profiles' not in cmd
    assert cmd[5] == '--quick-query=-red car'
    # the same settings, so the quick search uses the cache rows of the current settings
    assert cmd[6:] == command(profiles=Path('p.json'))[7:]


def test_engine_command_of_find_similar_passes_the_photo_and_its_part_in_one_argument_each():
    # F11: "--like=<path>" and "--like-part=<part>", so a name starting with "-" is no option
    photo = Path('D:/a/-shot.jpg')
    cmd = command(like=photo, like_part='Person 2')
    assert '--profiles' not in cmd and not any(arg.startswith('--quick-query') for arg in cmd)
    assert cmd[5:7] == [f'--like={photo}', '--like-part=Person 2']
    # the same settings, so it uses the cache rows of the current settings
    assert cmd[7:] == command(profiles=Path('p.json'))[7:]
    assert command(like=photo)[5:7] == [f'--like={photo}', '--output']


def test_engine_command_needs_profiles_or_a_quick_query():
    with pytest.raises(ValueError):
        command()
    with pytest.raises(ValueError):
        command(profiles=Path('p.json'), quick_query='dog')
    with pytest.raises(ValueError):
        command(quick_query='dog', like=Path('x.jpg'))
    with pytest.raises(ValueError):
        command(profiles=Path('p.json'), like_part='Person 1')


def test_engine_command_of_an_analysis_without_a_search():
    # F18: "Analyze photos now" analyzes with the current settings, without profiles
    cmd = command(analyze_only=True)
    assert cmd[5] == '--analyze-only'
    assert '--profiles' not in cmd
    assert not any(arg.startswith(('--quick-query', '--like')) for arg in cmd)
    # the same settings, so a later search with them finds the analyses in the cache
    assert cmd[6:] == command(profiles=Path('p.json'))[7:]
    with pytest.raises(ValueError):
        command(analyze_only=True, profiles=Path('p.json'))
    with pytest.raises(ValueError):
        command(analyze_only=True, quick_query='dog')
    with pytest.raises(ValueError):
        command(analyze_only=True, like_part='Person 1')
    # False is no analysis: still exactly one search is needed
    assert command(analyze_only=False, profiles=Path('p.json')) == command(profiles=Path('p.json'))


def quick_export(folder, thumbnail, query='dog'):
    folder.mkdir(parents=True, exist_ok=True)
    card = result_card(1, Path('x.jpg'), 'x.jpg', 'Full image', 1.0, 0.3, None, 'Score 1.00', 'detail', thumbnail)
    document = results_document('s', 'f', [Path('photos')], {}, 1,
                                [{'name': query, 'fingerprint': '', 'gallery': QUICK_GALLERY, 'normalized': True,
                                  'cards': [card]}])
    page = f'<!doctype html><title>FrameScout – {query}</title><img src="thumbnails/{thumbnail}">'
    publish_export(folder, [(QUICK_GALLERY, page)], document)
    return document


def test_the_cleanup_of_the_results_folder_leaves_the_quick_folder_alone(tmp_path):
    # the quick folder has its own thumbnails; a full search's auto_cleanup and the
    # "Clean up storage" scan of results/ neither delete nor offer them (F10)
    results = tmp_path / 'results'
    quick = results / QUICK_DIR
    name = 'a' * 24 + '.jpg'
    quick_export(quick, name)
    (quick / 'thumbnails').mkdir()
    (quick / 'thumbnails' / name).write_bytes(b'jpg')
    (tmp_path / 'profiles.json').write_text('{"profiles": []}', encoding='utf-8')
    auto_cleanup(results)
    assert (quick / 'thumbnails' / name).is_file()
    scan = scan_cleanup(results, tmp_path / 'profiles.json', tmp_path / 'references', 'sig', current_model='vit-b-32')
    offered = [p for key in ('thumbnails', 'galleries', 'temp_thumbnails') for p in scan[key]['items']]
    assert all(QUICK_DIR not in Path(p).parts for p in offered)


def test_auto_cleanup_of_the_quick_folder_keeps_only_what_its_gallery_links(tmp_path):
    quick = tmp_path / 'results' / QUICK_DIR
    linked, old = 'b' * 24 + '.jpg', 'c' * 24 + '.jpg'
    quick_export(quick, linked)
    (quick / 'thumbnails').mkdir()
    for name in (linked, old):
        (quick / 'thumbnails' / name).write_bytes(b'jpg')
    auto_cleanup(quick)
    assert sorted(p.name for p in (quick / 'thumbnails').iterdir()) == [linked]
    assert read_results(quick / 'results.json')['profiles'][0]['gallery'] == QUICK_GALLERY


def test_the_app_starts_both_searches_through_engine_command():
    # F10: the search with profiles and the quick search get the same settings
    tree = app_tree()
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and getattr(node.func, 'id', None) == 'start_engine']
    # and "Analyze photos now" (F18), whose note goes next to its button
    assert sorted(k.arg for call in calls for k in call.keywords) == [
        'analyze_only', 'like', 'like_part', 'notice', 'profiles', 'quick_query']
    assert "start_engine(notice='analyze_notice', analyze_only=True)" in [ast.unparse(call) for call in calls]
    assert [node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and getattr(node.func, 'id', None) == 'engine_command']
    # no second, hand-built command line
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Constant)
                and node.value in ('--profiles', '--analyze-only')]


def test_the_app_counts_partners_as_analyzed_for_an_analysis():
    # F18 review: a partner searched through another file of its shot never gets a row of its
    # own, so "Analyze photos now" must not keep calling it "to analyze"
    tree = app_tree()
    [summary] = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and getattr(node.func, 'id', None) == 'start_summary'
                 and any(k.arg == 'analysis_only' for k in node.keywords)]
    done = ast.unparse(summary.args[1])
    [assigned] = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == done for t in node.targets)]
    assert ast.unparse(assigned.value) == 'analyzed + quick_counts[2]'


def test_the_app_warns_of_low_disk_space_next_to_analyze_photos_now():
    # F18 review: the analysis writes the cache rows, but the search's warning is in another tab
    tree = app_tree()
    [call] = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
              and getattr(node.func, 'id', None) == 'low_space_warning'
              and any(k.arg == 'analysis' for k in node.keywords)]
    assert ast.unparse(call.args[2]) == '0'  # no profile: no gallery thumbnails
    assert ast.unparse(call.args[5]) == 'analysis_done'
    [area] = [node for node in ast.walk(tree) if isinstance(node, ast.With)
              and ast.unparse(node.items[0].context_expr) == 'analyze_area']
    assert 'st.warning(analysis_space)' in ast.unparse(area)


def test_every_result_card_of_the_app_offers_find_similar():
    # F11: on the cards of the profile results and of the quick search; the click passes the
    # card's photo and the part it names, and the page run (not the fragment) starts it
    tree = app_tree()
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for name in ('show_results', 'show_quick_results'):
        assert 'find_similar_button' in [getattr(call.func, 'id', None) for call in ast.walk(functions[name])
                                         if isinstance(call, ast.Call)]
    button = ast.unparse(functions['find_similar_button'])
    assert "st.session_state.find_similar = (card['path'], card['label'])" in button
    assert 'st.rerun()' in button
    [start] = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
               and getattr(node.func, 'id', None) == 'start_engine' and node.keywords[0].arg == 'like']
    assert ast.unparse(start) == 'start_engine(like=find_similar_request[0], like_part=find_similar_request[1])'
    # review: the request is taken from the session state first thing in the page run (before
    # any st.stop), and one that cannot start while a search runs gets a notice
    # (in app.py, whose page run it is: compared by its line numbers, A46)
    page = page_tree()
    pops = [node for node in tree.body if isinstance(node, ast.Assign) and 'find_similar' in ast.unparse(node)]
    assert [ast.unparse(node) for node in pops] == ["find_similar_request = st.session_state.pop('find_similar', None)"]
    pops = [node for node in page.body if isinstance(node, ast.Assign) and 'find_similar' in ast.unparse(node)]
    stops = [node.lineno for node in ast.walk(page) if isinstance(node, ast.Call)
             and ast.unparse(node.func) == 'st.stop']
    assert stops and pops[0].lineno < min(stops)
    [handled] = [node for node in ast.walk(tree) if isinstance(node, ast.If)
                 and ast.unparse(node.test) == 'find_similar_request']
    [branch] = handled.body
    assert ast.unparse(branch.test) == 'active' and 'run_notice' in ast.unparse(branch.body)
    # it loads no model, so a missing model package does not disable it
    assert 'model_missing' not in button
    # the quick result caption names the photo by its file name, as the gallery title does
    assert 'Photos similar to {plain(Path(like).name)}' in ast.unparse(functions['show_quick_results'])


def test_the_app_shows_the_quick_search_from_its_own_folder():
    tree = app_tree()
    assigned = {ast.unparse(node.targets[0]): ast.unparse(node.value) for node in tree.body
                if isinstance(node, ast.Assign) and len(node.targets) == 1}
    assert assigned['QUICK'] == 'RESULTS / QUICK_DIR'
    assert assigned['QUICK_JSON'] == 'QUICK / RESULTS_FILE'
    assert assigned['QUICK_THUMBS'] == "QUICK / 'thumbnails'"
    [show] = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'show_quick_results']
    source = ast.unparse(show)
    # no marks, copying or export: those belong to the profiles (marks.json)
    for name in ('load_marks', 'set_mark', 'show_copy', 'show_export', 'THUMBS /'):
        assert name not in source.replace('QUICK_THUMBS /', '')
