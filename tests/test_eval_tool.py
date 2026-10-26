"""The search-model evaluation tool framescout_eval.py (E32, E20), without torch or a model."""
import http.server
import json
from pathlib import Path

import numpy as np
import pytest

import framescout_eval as ev
from framescout_core import (DEFAULT_MODEL, MODEL_KEYS, read_labels, save_labels, scores_document, thumbnail_name,
                             write_scores)
from framescout_scoring import rank_photos

PHOTOS = ['a.jpg', 'b.jpg', 'c.jpg', 'd.jpg', 'e.jpg']


def write_model_scores(collection, model, car, dog_text=None, dog_visual=None, photos=PHOTOS):
    """A scores file with one crop per photo: profile Car (text only) and optionally Dog (references)."""
    profiles = [{'name': 'Car', 'prompts': ['A photograph of Car.'], 'references': [],
                 'text': [[s] for s in car], 'visual': None}]
    if dog_text is not None:
        profiles.append({'name': 'Dog', 'prompts': ['A photograph of Dog.'], 'references': [str(collection.root / 'dog.jpg')],
                         'text': [[s] for s in dog_text], 'visual': [[s] for s in dog_visual]})
    document = scores_document(model, 'sig', [(str(collection.root / 'photos' / p), 7, ['Full image']) for p in photos],
                               profiles)
    write_scores(collection.scores_file(model), document)
    return document


def photo(collection, name):
    return str(collection.root / 'photos' / name)


@pytest.fixture
def collection(tmp_path):
    return ev.Collection(tmp_path / 'eval', 'cosplay')


# --- collections ---

def test_a_collection_keeps_its_files_in_one_folder(collection, tmp_path):
    root = tmp_path / 'eval' / 'cosplay'
    assert collection.root == root
    assert collection.scores_file('vit-b-32-openai') == root / 'scores' / 'vit-b-32-openai.json'
    assert collection.engine_output('vit-b-32-openai') == root / 'engine' / 'vit-b-32-openai'
    assert collection.pool_file == root / 'pool.json' and collection.labels_file == root / 'labels.json'


def test_an_invalid_collection_name_is_refused(tmp_path):
    with pytest.raises(ValueError):
        ev.Collection(tmp_path, '../x')


def test_the_default_folder_is_ignored_by_git():
    assert ev.DEFAULT_DIR == Path(ev.__file__).resolve().parent / '.tmp' / 'eval'


def test_the_scores_are_read_in_registry_order(collection):
    for model in reversed(MODEL_KEYS[:2]):
        write_model_scores(collection, model, [0.1] * 5)
    assert list(collection.scores()) == list(MODEL_KEYS[:2])


# --- ranking: the engine's scoring ---

def test_a_ranking_orders_the_photos_like_the_engine(collection):
    document = write_model_scores(collection, DEFAULT_MODEL, [0.9, 0.8, 0.1, 0.2, 0.3],
                                  [0.9, 0.1, 0.5, 0.4, 0.0], [0.1, 0.9, 0.5, 0.4, 0.0])
    car, dog = document['profiles']
    assert ev.ranking(document, car, 0.3) == [photo(collection, p) for p in ['a.jpg', 'b.jpg', 'e.jpg', 'd.jpg', 'c.jpg']]
    for weight in (0.0, 0.3, 0.6, 1.0):
        _, matches = rank_photos([np.asarray(r) for r in dog['text']], [np.asarray(r) for r in dog['visual']], weight)
        expected = [document['photos'][i]['path'] for i in sorted(range(5), key=lambda i: -matches[i].score)]
        assert ev.ranking(document, dog, weight) == expected
    assert ev.ranking(document, dog, 0.0)[0] == photo(collection, 'a.jpg')
    assert ev.ranking(document, dog, 1.0)[0] == photo(collection, 'b.jpg')


# --- run: the engine once per model ---

@pytest.fixture
def setup(tmp_path, monkeypatch):
    photos = tmp_path / 'photos'; photos.mkdir()
    profiles = tmp_path / 'profiles.json'
    profiles.write_text(json.dumps({'profiles': [{'name': 'Car'}]}), encoding='utf-8')
    calls = []

    class Done:
        returncode = 0

    def fake_run(command, env=None, **kwargs):
        calls.append((command, env))
        return Done()

    monkeypatch.setattr(ev.subprocess, 'run', fake_run)
    monkeypatch.setattr(ev, 'model_problem', lambda key: None)
    return photos, profiles, calls


def option(command, name):
    return command[command.index(name) + 1]


def test_run_starts_the_engine_for_every_registered_model(tmp_path, setup):
    photos, profiles, calls = setup
    assert ev.main(['run', 'cosplay', str(photos), '--profiles', str(profiles), '--dir', str(tmp_path / 'eval'),
                    '--device', 'cpu', '--no-person-detection']) == 0
    assert [option(command, '--model') for command, _ in calls] == list(MODEL_KEYS)
    command, env = calls[0]
    collection = ev.Collection(tmp_path / 'eval', 'cosplay')
    assert command[1] == str(ev.ENGINE) and command[2] == str(photos.resolve())
    assert option(command, '--profiles') == str(profiles.resolve())
    assert option(command, '--output') == str(collection.engine_output(MODEL_KEYS[0]))
    assert option(command, '--scores-file') == str(collection.scores_file(MODEL_KEYS[0]))
    assert option(command, '--device') == 'cpu' and option(command, '--top') == str(ev.DEFAULT_TOP)
    assert '--no-person-detection' in command
    # the model downloads and caches go where the app keeps them
    assert env['TORCH_HOME'] == str(ev.ROOT / '.cache' / 'torch') and env['PYTHONIOENCODING'] == 'utf-8'
    assert env['HF_HOME'] == str(ev.ROOT / '.cache' / 'huggingface')


def test_run_remembers_folders_and_profiles_of_the_collection(tmp_path, setup):
    photos, profiles, calls = setup
    ev.main(['run', 'cosplay', str(photos), '--profiles', str(profiles), '--dir', str(tmp_path / 'eval'),
             '--models', DEFAULT_MODEL])
    calls.clear()
    assert ev.main(['run', 'cosplay', '--dir', str(tmp_path / 'eval'), '--models', MODEL_KEYS[1]]) == 0
    [(command, _)] = calls
    assert command[2] == str(photos.resolve()) and option(command, '--profiles') == str(profiles.resolve())
    assert '--no-person-detection' not in command


def test_run_without_folders_or_profiles_for_a_new_collection_fails(tmp_path, setup, capsys):
    assert ev.main(['run', 'cosplay', '--dir', str(tmp_path / 'eval')]) == 2
    assert 'photo folder' in capsys.readouterr().err


@pytest.mark.parametrize('content', [{'format': 1}, {'format': 1, 'folders': 'x', 'profiles': 'p.json'},
                                     {'format': 1, 'folders': ['x']}])
def test_an_incomplete_collection_file_is_an_error_not_a_traceback(tmp_path, setup, capsys, content):
    photos, profiles, calls = setup
    collection = ev.Collection(tmp_path / 'e', 'c')
    collection.root.mkdir(parents=True)
    collection.config_file.write_text(json.dumps(content), encoding='utf-8')
    assert ev.main(['run', 'c', str(photos), '--profiles', str(profiles), '--dir', str(tmp_path / 'e')]) == 2
    assert 'collection file' in capsys.readouterr().err and calls == []
    assert json.loads(collection.config_file.read_text(encoding='utf-8')) == content


def test_run_refuses_unknown_models_and_missing_folders(tmp_path, setup, capsys):
    photos, profiles, calls = setup
    assert ev.main(['run', 'c', str(photos), '--profiles', str(profiles), '--dir', str(tmp_path / 'e'),
                    '--models', 'nope']) == 2
    assert ev.main(['run', 'c', str(tmp_path / 'missing'), '--profiles', str(profiles),
                    '--dir', str(tmp_path / 'e')]) == 2
    assert calls == []


def test_run_skips_a_model_whose_package_is_missing_and_reports_failures(tmp_path, setup, monkeypatch, capsys):
    photos, profiles, calls = setup
    monkeypatch.setattr(ev, 'model_problem', lambda key: 'needs transformers' if key == MODEL_KEYS[1] else None)
    assert ev.main(['run', 'c', str(photos), '--profiles', str(profiles), '--dir', str(tmp_path / 'e'),
                    '--models', ','.join(MODEL_KEYS[:2])]) == 1
    assert [option(command, '--model') for command, _ in calls] == [MODEL_KEYS[0]]
    assert 'needs transformers' in capsys.readouterr().out


def test_a_skipped_or_failed_model_keeps_no_scores_of_an_older_run(tmp_path, setup, monkeypatch):
    photos, profiles, calls = setup
    collection = ev.Collection(tmp_path / 'e', 'c')
    for model in MODEL_KEYS[:3]:
        write_model_scores(collection, model, [0.1] * 5)

    class Failed:
        returncode = 1

    def fake_run(command, env=None, **kwargs):
        calls.append((command, env))
        model = option(command, '--model')
        write_model_scores(collection, model, [0.2] * 5)  # a failure after the scores file was written
        return Failed() if model == MODEL_KEYS[1] else type('Done', (), {'returncode': 0})()

    monkeypatch.setattr(ev.subprocess, 'run', fake_run)
    monkeypatch.setattr(ev, 'model_problem', lambda key: 'needs transformers' if key == MODEL_KEYS[2] else None)
    assert ev.main(['run', 'c', str(photos), '--profiles', str(profiles), '--dir', str(tmp_path / 'e'),
                    '--models', ','.join(MODEL_KEYS[:3])]) == 1
    assert list(collection.scores()) == [MODEL_KEYS[0]]
    assert collection.scores()[MODEL_KEYS[0]]['profiles'][0]['text'][0] == [0.2]


def test_a_photo_changed_between_the_model_runs_is_warned_about(collection):
    write_model_scores(collection, MODEL_KEYS[0], [0.1] * 5)
    document = write_model_scores(collection, MODEL_KEYS[1], [0.1] * 5)
    document['photos'][0]['mtime_ns'] = 8
    write_scores(collection.scores_file(MODEL_KEYS[1]), document)
    [warning] = ev.run_warnings(collection.scores())
    assert 'different photos' in warning


# --- pool ---

def test_pool_holds_the_union_of_every_models_top_photos(collection, tmp_path):
    collection.save_config([str(tmp_path)], str(tmp_path / 'profiles.json'))
    write_model_scores(collection, MODEL_KEYS[0], [0.9, 0.8, 0.1, 0.2, 0.3])
    write_model_scores(collection, MODEL_KEYS[1], [0.1, 0.8, 0.9, 0.2, 0.3])
    assert ev.main(['pool', 'cosplay', '--dir', str(collection.root.parent), '--depth', '2']) == 0
    pool = json.loads(collection.pool_file.read_text(encoding='utf-8'))
    [car] = pool['profiles']
    assert car['name'] == 'Car'
    assert sorted(p['path'] for p in car['photos']) == [photo(collection, p) for p in ['a.jpg', 'b.jpg', 'c.jpg']]
    assert pool['models'] == list(MODEL_KEYS[:2]) and pool['depth'] == 2


def test_pool_adds_the_rankings_of_further_reference_weights(collection, tmp_path):
    write_model_scores(collection, DEFAULT_MODEL, [0.9, 0.8, 0.1, 0.2, 0.3],
                       [0.9, 0.1, 0.5, 0.4, 0.0], [0.1, 0.9, 0.5, 0.4, 0.0])
    ev.main(['pool', 'cosplay', '--dir', str(collection.root.parent), '--depth', '1', '--weights', '0,1'])
    pool = json.loads(collection.pool_file.read_text(encoding='utf-8'))
    dog = next(p for p in pool['profiles'] if p['name'] == 'Dog')
    assert sorted(p['path'] for p in dog['photos']) == [photo(collection, 'a.jpg'), photo(collection, 'b.jpg')]
    assert dog['references'] == [str(collection.root / 'dog.jpg')]


def test_pool_takes_context_and_features_from_the_profiles_file(collection, tmp_path):
    profiles = tmp_path / 'profiles.json'
    profiles.write_text(json.dumps({'profiles': [{'name': 'Car', 'franchise': 'Vehicles', 'features': 'red'}]}),
                        encoding='utf-8')
    collection.save_config([str(tmp_path)], str(profiles))
    write_model_scores(collection, DEFAULT_MODEL, [0.9, 0.8, 0.1, 0.2, 0.3])
    ev.main(['pool', 'cosplay', '--dir', str(collection.root.parent)])
    [car] = json.loads(collection.pool_file.read_text(encoding='utf-8'))['profiles']
    assert (car['context'], car['features']) == ('Vehicles', 'red')


def test_the_pool_covers_text_only_the_default_and_a_stronger_reference_weight():
    assert ev.POOL_WEIGHTS == tuple(sorted({0.0, ev.DEFAULT_REFERENCE_WEIGHT, 0.6}))


def test_runs_that_do_not_compare_the_same_are_warned_about(collection):
    write_model_scores(collection, MODEL_KEYS[0], [0.1] * 5)
    write_model_scores(collection, MODEL_KEYS[1], [0.1] * 5)
    assert ev.run_warnings(collection.scores()) == []
    write_model_scores(collection, MODEL_KEYS[1], [0.1] * 4, photos=PHOTOS[:4])
    document = write_model_scores(collection, MODEL_KEYS[2], [0.1] * 5)
    document['profiles'][0]['prompts'] = ['A photograph of a red car.']
    write_scores(collection.scores_file(MODEL_KEYS[2]), document)
    warnings = ev.run_warnings(collection.scores())
    assert len(warnings) == 2 and 'Car has changed' in warnings[0] and 'different photos' in warnings[1]


def test_pool_without_scores_fails(collection, capsys):
    assert ev.main(['pool', 'cosplay', '--dir', str(collection.root.parent)]) == 2
    assert 'run' in capsys.readouterr().err


# --- metrics ---

def labelled(collection, profile, **marks):
    labels = read_labels(collection.labels_file)
    labels.setdefault(profile, {}).update({photo(collection, name + '.jpg'): value for name, value in marks.items()})
    save_labels(collection.labels_file, labels)


def test_metrics_compute_ap_per_profile_and_model(collection):
    write_model_scores(collection, MODEL_KEYS[0], [0.9, 0.8, 0.1, 0.2, 0.0])
    write_model_scores(collection, MODEL_KEYS[1], [0.1, 0.8, 0.9, 0.2, 0.95])
    labelled(collection, 'Car', a=True, b=True, c=False, d=False)
    result = ev.evaluate(collection.scores(), read_labels(collection.labels_file), k=2, weight=0.3, sweep=())
    car = result['profiles']['Car']
    assert car['hits'] == 2
    assert car['models'][MODEL_KEYS[0]] == {'ap': 1.0, 'unlabelled': 0}
    # e (unlabelled) and c (no match) lead: no hit in the top 2
    assert car['models'][MODEL_KEYS[1]] == {'ap': 0.0, 'unlabelled': 1}
    assert result['mean'][MODEL_KEYS[0]] == 1.0


def test_metrics_sweep_the_reference_weight_per_model(collection):
    write_model_scores(collection, DEFAULT_MODEL, [0.9, 0.8, 0.1, 0.2, 0.0],
                       [0.9, 0.1, 0.5, 0.4, 0.0], [0.1, 0.9, 0.5, 0.4, 0.0])
    labelled(collection, 'Dog', a=False, b=True, c=False, d=False, e=False)
    result = ev.evaluate(collection.scores(), read_labels(collection.labels_file), k=1, weight=0.3,
                         sweep=(0.0, 0.3, 0.6, 1.0))
    sweep = result['sweep'][DEFAULT_MODEL]
    assert {w: v['ap'] for w, v in sweep.items()} == {'0.0': 0.0, '0.3': 0.0, '0.6': 1.0, '1.0': 1.0}
    assert {v['unlabelled'] for v in sweep.values()} == {0}
    assert result['sweep_profiles'] == ['Dog']


def test_a_profile_without_hits_has_no_ap(collection):
    write_model_scores(collection, DEFAULT_MODEL, [0.9, 0.8, 0.1, 0.2, 0.0])
    labelled(collection, 'Car', a=False)
    result = ev.evaluate(collection.scores(), read_labels(collection.labels_file), k=2, weight=0.3, sweep=())
    assert result['profiles']['Car']['models'][DEFAULT_MODEL]['ap'] is None
    assert result['mean'][DEFAULT_MODEL] is None


def test_the_metrics_command_prints_tables_and_writes_json(collection, tmp_path, capsys):
    write_model_scores(collection, MODEL_KEYS[0], [0.9, 0.8, 0.1, 0.2, 0.0],
                       [0.9, 0.1, 0.5, 0.4, 0.0], [0.1, 0.9, 0.5, 0.4, 0.0])
    labelled(collection, 'Car', a=True, b=True, c=False, d=False)
    labelled(collection, 'Dog', b=True)
    other = ev.Collection(collection.root.parent, 'outdoor')
    write_model_scores(other, MODEL_KEYS[0], [0.9, 0.8, 0.1, 0.2, 0.0])
    labelled(other, 'Car', a=True)
    out = tmp_path / 'metrics.json'
    assert ev.main(['metrics', 'cosplay', 'outdoor', '--dir', str(collection.root.parent), '--k', '2',
                    '--json', str(out)]) == 0
    text = capsys.readouterr().out
    assert 'AP@2' in text and MODEL_KEYS[0] in text and 'cosplay' in text and 'outdoor' in text
    assert 'Reference weight' in text and 'All collections' in text
    data = json.loads(out.read_text(encoding='utf-8'))
    assert set(data['collections']) == {'cosplay', 'outdoor'}
    assert data['collections']['outdoor']['profiles']['Car']['models'][MODEL_KEYS[0]]['ap'] == 1.0
    assert data['k'] == 2


# --- labelling page ---

@pytest.fixture
def session(collection, tmp_path):
    (collection.root / 'photos').mkdir(parents=True)
    for name in PHOTOS:
        (collection.root / 'photos' / name).write_bytes(b'original ' + name.encode())
    (collection.root / 'dog.jpg').write_bytes(b'reference')
    write_model_scores(collection, DEFAULT_MODEL, [0.9, 0.8, 0.1, 0.2, 0.0],
                       [0.9, 0.1, 0.5, 0.4, 0.0], [0.1, 0.9, 0.5, 0.4, 0.0])
    ev.main(['pool', 'cosplay', '--dir', str(collection.root.parent), '--depth', '3'])
    return ev.LabelSession(collection)


def get(session, route, token=None):
    return session.handle('GET', f'/{token or session.token}/{route}', b'')


def test_the_page_and_its_state_need_the_session_token(session):
    status, kind, body = get(session, '')
    assert status == 200 and kind.startswith('text/html') and b'FrameScout' in body
    assert get(session, '', token='wrong')[0] == 404
    assert session.handle('GET', '/', b'')[0] == 404
    # without the trailing slash: forwarded, so the relative links keep the token
    status, _, body = session.handle('GET', f'/{session.token}', b'')
    assert status == 200 and f'url={session.token}/'.encode() in body


def test_the_state_lists_the_profiles_photos_and_labels(session, collection):
    first = session.pool['profiles'][0]['photos'][0]['path']
    save_labels(collection.labels_file, {'Car': {first: True}})
    session = ev.LabelSession(collection)  # resumes with the saved labels
    status, kind, body = get(session, 'state')
    state = json.loads(body)
    assert status == 200 and kind == 'application/json'
    car, dog = state['profiles']
    assert car['name'] == 'Car' and len(car['photos']) == 3 and car['labels'][0] is True
    assert car['labels'][1:] == [None, None] and dog['references'] == 1
    assert state['collection'] == 'cosplay'


def test_a_label_is_saved_right_away_and_can_be_cleared(session, collection):
    target = session.pool['profiles'][1]['photos'][2]['path']
    body = json.dumps({'profile': 1, 'photo': 2, 'value': False}).encode()
    status, _, answer = session.handle('POST', f'/{session.token}/label', body)
    assert status == 200 and json.loads(answer) == {'ok': True}
    assert read_labels(collection.labels_file) == {'Dog': {target: False}}
    session.handle('POST', f'/{session.token}/label', json.dumps({'profile': 1, 'photo': 2, 'value': None}).encode())
    assert read_labels(collection.labels_file) == {}


@pytest.mark.parametrize('body', [b'not json', b'{"profile": 9, "photo": 0, "value": true}',
                                  b'{"profile": 0, "photo": 0, "value": "yes"}', b'[]'])
def test_an_invalid_label_request_is_refused(session, collection, body):
    assert session.handle('POST', f'/{session.token}/label', body)[0] == 400
    assert not collection.labels_file.exists()


def test_a_photo_is_shown_by_its_gallery_thumbnail_or_else_the_original(session, collection):
    entry = session.pool['profiles'][0]['photos'][0]
    status, kind, body = get(session, 'photo/0/0')
    assert status == 200 and kind == 'image/jpeg' and body == b'original ' + Path(entry['path']).name.encode()
    # the page prefetches only photos with a thumbnail, not the (possibly large) originals
    assert json.loads(get(session, 'state')[2])['profiles'][0]['photos'][0]['thumb'] is False
    thumbs = collection.engine_output(DEFAULT_MODEL) / 'thumbnails'
    thumbs.mkdir(parents=True)
    (thumbs / thumbnail_name(Path(entry['path']), entry['mtime_ns'])).write_bytes(b'thumb')
    assert get(session, 'photo/0/0')[2] == b'thumb'
    assert [p['thumb'] for p in json.loads(get(session, 'state')[2])['profiles'][0]['photos']] == [True, False, False]
    assert get(session, 'original/0/0')[2].startswith(b'original')
    assert get(session, 'reference/1/0')[2] == b'reference'


@pytest.mark.parametrize('route', ['photo/0/99', 'photo/5/0', 'photo/x/0', 'reference/0/0', 'nothing'])
def test_only_pool_photos_and_references_are_served(session, route):
    assert get(session, route)[0] == 404


def test_the_page_refuses_to_start_on_an_unreadable_labels_file(session, collection):
    collection.labels_file.write_text('{broken', encoding='utf-8')
    with pytest.raises(ValueError):
        ev.LabelSession(collection)
    assert collection.labels_file.read_text(encoding='utf-8') == '{broken'


def test_a_port_in_use_is_an_error_not_a_traceback(session, collection, capsys):
    first = ev.LabelServer(('127.0.0.1', 0), http.server.BaseHTTPRequestHandler)
    try:
        port = first.server_address[1]
        # also on Windows, where SO_REUSEADDR would let the second page share the port
        with pytest.raises(OSError):
            ev.LabelServer(('127.0.0.1', port), http.server.BaseHTTPRequestHandler).server_close()
        assert ev.main(['label', 'cosplay', '--dir', str(collection.root.parent), '--no-browser',
                        '--port', str(port)]) == 2
        assert '--port' in capsys.readouterr().err
    finally:
        first.server_close()


def test_a_port_out_of_range_is_refused(session, collection, capsys):
    assert ev.main(['label', 'cosplay', '--dir', str(collection.root.parent), '--no-browser', '--port', '70000']) == 2
    assert '--port' in capsys.readouterr().err


def test_the_page_needs_a_pool(collection, capsys):
    assert ev.main(['label', 'cosplay', '--dir', str(collection.root.parent), '--no-browser']) == 2
    assert 'pool' in capsys.readouterr().err
