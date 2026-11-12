"""Quick search over the analyzed photos without a profile (F10, framescout_core.quick)."""
from pathlib import Path

import pytest

from framescout_core import (QUICK_DIR, QUICK_GALLERY, QUICK_QUERY_MAX, auto_cleanup, engine_command,
                             generic_prompts, quick_note, quick_photos, quick_profile, quick_scope_text,
                             read_results, results_document, publish_export, result_card, scan_cleanup)


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
    # one shot, one photo: the second partner does not take the RAW file again
    assert chosen == [raw]
    assert missing == [heic]


def test_quick_photos_counts_a_photo_whose_row_cannot_be_read_as_not_analyzed():
    def current(path):
        if path.name == 'bad.jpg':
            raise OSError('disk I/O error')
        return True
    problems = []
    chosen, missing = quick_photos([Path('ok.jpg'), Path('bad.jpg')], {}, current,
                                   lambda path, exc: problems.append((path.name, str(exc))))
    assert chosen == [Path('ok.jpg')]
    assert missing == [Path('bad.jpg')]
    assert problems == [('bad.jpg', 'disk I/O error')]


def test_quick_scope_text_names_the_photos_that_are_not_searched():
    assert quick_scope_text(0, 0) == 'No supported photos found in these folders: there is nothing to search.'
    assert quick_scope_text(10, 0) == ('None of the 10 photos is analyzed with these AI settings yet, so a quick '
                                       'search finds nothing. Start a search with your profiles first: it analyzes '
                                       'them.')
    assert quick_scope_text(1200, 1200) == 'All 1,200 photos are analyzed with these AI settings and searched.'
    assert quick_scope_text(1200, 1000) == ('1,000 of 1,200 photos are analyzed with these AI settings and searched; '
                                            'the other 200 are not searched until a search with your profiles '
                                            'analyzes them.')
    # a cache row count above the photos (e.g. counted at another time) is capped
    assert quick_scope_text(5, 7) == 'All 5 photos are analyzed with these AI settings and searched.'


def test_quick_note_says_how_many_photos_were_searched_and_that_scores_differ():
    note = quick_note(800, 200)
    assert note.startswith('Quick search over the 800 photos analyzed with these AI settings; 200 photos were not '
                           'analyzed and not searched.')
    assert 'differ from those of a search with profiles' in note
    assert 'not analyzed' not in quick_note(800, 0)


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


def test_engine_command_needs_profiles_or_a_quick_query():
    with pytest.raises(ValueError):
        command()
    with pytest.raises(ValueError):
        command(profiles=Path('p.json'), quick_query='dog')


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
