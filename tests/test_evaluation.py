"""Shared logic of the search-model evaluation (framescout_core.evaluation, E32/E20)."""
import json

import pytest

from framescout_core import (EVAL_K, LABELS_FORMAT, SCORES_FORMAT, average_precision, build_pool,
                             collection_name_problem, read_document, read_labels, read_scores, save_labels,
                             scores_document, set_label, write_document, write_scores)


def sample_document():
    return scores_document(
        'vit-b-32-openai', 'sig',
        [('C:/p/a.jpg', 11, ['Full image', 'Person 1']), ('C:/p/b.jpg', 22, ['Full image'])],
        [{'name': 'Red car', 'prompts': ['A photograph of Red car.'], 'references': [],
          'text': [[0.21234567, 0.3], [0.25]], 'visual': None},
         {'name': 'Dog', 'prompts': ['A photograph of Dog.'], 'references': ['C:/r/dog.jpg'],
          'text': [[0.1, 0.2], [0.3]], 'visual': [[0.5, 0.6], [0.7]]}])


# --- AP@k ---

def test_ap_at_40_is_the_default_cut_off():
    assert EVAL_K == 40


def test_average_precision_of_a_perfect_ranking_is_one():
    assert average_precision(['a', 'b', 'c'], {'a', 'b'}, 40) == 1.0


def test_average_precision_averages_the_precision_at_each_hit():
    # hits at ranks 1 and 3: (1/1 + 2/3) / 2
    assert average_precision(['a', 'x', 'b', 'y'], {'a', 'b'}, 40) == pytest.approx((1 + 2 / 3) / 2)


def test_average_precision_counts_hits_missing_from_the_ranking():
    # a relevant photo the model did not rank in its top k lowers the value
    assert average_precision(['a', 'x'], {'a', 'b'}, 40) == pytest.approx(0.5)


def test_average_precision_is_cut_at_k_and_normalized_by_at_most_k():
    ranked = ['a', 'b', 'c', 'd']
    assert average_precision(ranked, {'a', 'b', 'c', 'd'}, 2) == 1.0  # min(4 hits, k=2)
    assert average_precision(['x', 'x2', 'a'], {'a'}, 2) == 0.0


def test_average_precision_without_any_hit_is_undefined():
    assert average_precision(['a', 'b'], set(), 40) is None


# --- candidate pool ---

def test_the_pool_is_the_union_of_each_ranking_down_to_depth():
    pool = build_pool([['a', 'b', 'c'], ['b', 'd', 'e']], depth=2, seed='Red car')
    assert sorted(pool) == ['a', 'b', 'd']


def test_the_pool_order_does_not_reveal_the_models_and_is_reproducible():
    rankings = [[f'p{i:03}' for i in range(100)], [f'p{i:03}' for i in range(50, 150)]]
    pool = build_pool(rankings, depth=100, seed='Red car')
    assert pool == build_pool(list(reversed(rankings)), depth=100, seed='Red car')
    assert sorted(pool) == [f'p{i:03}' for i in range(150)]
    assert pool != sorted(pool)  # shuffled, so the labeller cannot tell the rank


def test_a_depth_below_one_is_refused():
    with pytest.raises(ValueError):
        build_pool([['a']], depth=0, seed='x')


# --- collection names ---

@pytest.mark.parametrize('name', ['cosplay', 'outdoor-2026', 'Pets_1'])
def test_simple_collection_names_are_accepted(name):
    assert collection_name_problem(name) is None


@pytest.mark.parametrize('name', ['', '..', 'a/b', 'a\\b', 'con', ' x', 'x.', 'ä', 'a' * 65])
def test_collection_names_that_are_no_plain_folder_name_are_refused(name):
    assert collection_name_problem(name)


# --- scores file (written by the engine's --scores-file) ---

def test_the_scores_document_lists_photos_and_per_crop_scores_per_profile():
    document = sample_document()
    assert document['format'] == SCORES_FORMAT
    assert document['model'] == 'vit-b-32-openai' and document['signature'] == 'sig'
    assert document['photos'] == [{'path': 'C:/p/a.jpg', 'mtime_ns': 11, 'crops': ['Full image', 'Person 1']},
                                  {'path': 'C:/p/b.jpg', 'mtime_ns': 22, 'crops': ['Full image']}]
    car, dog = document['profiles']
    assert car['text'] == [[0.212346, 0.3], [0.25]]  # rounded to keep the file small
    assert car['visual'] is None and dog['visual'] == [[0.5, 0.6], [0.7]]
    assert dog['references'] == ['C:/r/dog.jpg']


def test_the_scores_document_refuses_scores_that_do_not_match_the_crops():
    with pytest.raises(ValueError):
        scores_document('m', 's', [('a.jpg', 1, ['Full image'])],
                        [{'name': 'X', 'prompts': [], 'references': [], 'text': [[0.1, 0.2]], 'visual': None}])
    with pytest.raises(ValueError):
        scores_document('m', 's', [('a.jpg', 1, ['Full image'])],
                        [{'name': 'X', 'prompts': [], 'references': [], 'text': [[0.1]], 'visual': []}])


def test_a_scores_file_is_written_and_read_back(tmp_path):
    path = tmp_path / 'scores' / 'vit-b-32-openai.json'  # the folder is created
    write_scores(path, sample_document())
    assert read_scores(path) == sample_document()
    assert list(path.parent.iterdir()) == [path]  # no temporary file left


@pytest.mark.parametrize('content', ['', '[]', '{"format": 99}', '{"format": 1, "photos": [], "profiles": {}}',
                                     '{"format": 1, "model": "m", "photos": [{"path": "a", "mtime_ns": 1, '
                                     '"crops": ["Full image"]}], "profiles": [{"name": "X", "text": [[0.1, 0.2]], '
                                     '"visual": null}]}'])
def test_an_unusable_scores_file_raises_value_error(tmp_path, content):
    path = tmp_path / 'm.json'
    path.write_text(content, encoding='utf-8')
    with pytest.raises(ValueError):
        read_scores(path)


def test_a_missing_scores_file_is_reported(tmp_path):
    with pytest.raises(ValueError, match='not found'):
        read_scores(tmp_path / 'm.json')


# --- JSON documents (collection, pool) ---

def test_a_document_is_written_and_read_back_by_its_format(tmp_path):
    path = tmp_path / 'a' / 'pool.json'
    write_document(path, {'format': 1, 'x': 'ä'})
    assert read_document(path, 'pool file', 1) == {'format': 1, 'x': 'ä'}
    with pytest.raises(ValueError, match='pool file of format 2'):
        read_document(path, 'pool file', 2)


def test_a_missing_document_is_none_and_a_broken_one_raises(tmp_path):
    assert read_document(tmp_path / 'pool.json', 'pool file', 1) is None
    (tmp_path / 'pool.json').write_text('{', encoding='utf-8')
    with pytest.raises(ValueError):
        read_document(tmp_path / 'pool.json', 'pool file', 1)


# --- labels ---

def test_a_missing_labels_file_has_no_labels(tmp_path):
    assert read_labels(tmp_path / 'labels.json') == {}


def test_labels_are_set_per_profile_and_photo_and_saved(tmp_path):
    path = tmp_path / 'eval' / 'labels.json'
    labels = set_label({}, 'Red car', 'C:/p/a.jpg', True)
    labels = set_label(labels, 'Red car', 'C:/p/b.jpg', False)
    labels = set_label(labels, 'Dog', 'C:/p/a.jpg', False)
    save_labels(path, labels)
    assert read_labels(path) == {'Red car': {'C:/p/a.jpg': True, 'C:/p/b.jpg': False}, 'Dog': {'C:/p/a.jpg': False}}
    stored = json.loads(path.read_text(encoding='utf-8'))
    assert stored['format'] == LABELS_FORMAT


def test_clearing_a_label_removes_it_and_an_empty_profile():
    labels = set_label({}, 'Red car', 'a.jpg', True)
    assert set_label(labels, 'Red car', 'a.jpg', None) == {}
    assert labels == {'Red car': {'a.jpg': True}}  # the input is not changed


def test_only_yes_no_or_clear_are_labels():
    with pytest.raises(ValueError):
        set_label({}, 'Red car', 'a.jpg', 'yes')


@pytest.mark.parametrize('content', ['', 'not json', '[]', '{"format": 2, "labels": {}}',
                                     '{"format": 1, "labels": {"X": {"a.jpg": "yes"}}}'])
def test_an_unreadable_labels_file_raises_and_is_not_replaced(tmp_path, content):
    path = tmp_path / 'labels.json'
    path.write_text(content, encoding='utf-8')
    with pytest.raises(ValueError):
        read_labels(path)
    assert path.read_text(encoding='utf-8') == content
