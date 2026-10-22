"""Prompt ensemble and per-profile score normalization (framescout_scoring, E4, E5)."""
import numpy as np
import pytest

from framescout_scoring import MIN_SCORES, Match, best_scores, rank_photos, spread, text_queries


def unit(*rows):
    vectors = np.asarray(rows, dtype=np.float32)
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def test_generated_templates_are_averaged_into_one_unit_vector_custom_prompts_stay_apart():
    prompts = unit([1, 0, 0], [0, 1, 0], [0, 0, 1])
    queries = text_queries(prompts, generated=2)
    assert queries.shape == (2, 3)
    np.testing.assert_allclose(queries[0], unit([1, 1, 0])[0], rtol=1e-6)
    np.testing.assert_allclose(queries[1], prompts[2])
    np.testing.assert_allclose(np.linalg.norm(queries, axis=1), 1, rtol=1e-6)


def test_only_custom_prompts_are_kept_as_they_are():
    prompts = unit([1, 0], [0, 1])
    np.testing.assert_allclose(text_queries(prompts, generated=0), prompts)


def test_one_generic_template_no_longer_dominates():
    # crop a matches one template strongly and the others not at all; crop b matches all
    # templates moderately: the maximum prefers a, the averaged ensemble prefers b (E4)
    prompts = unit([1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0])
    crops = unit([0.9, 0, 0, 0.44], [0.5, 0.5, 0.5, 0.5])
    assert (crops @ prompts.T).max(axis=1).argmax() == 0
    assert best_scores(crops, text_queries(prompts, generated=3)).argmax() == 1


def test_best_scores_take_the_best_query_per_crop():
    crops = unit([1, 0], [0, 1])
    queries = unit([1, 1], [1, 0])
    np.testing.assert_allclose(best_scores(crops, queries), [1, np.sqrt(.5)], rtol=1e-6)


def test_spread_is_the_mean_and_standard_deviation_over_all_crops():
    arrays = [np.array([1., 2.]), np.array([3.])] + [np.array([4., 5., 6., 7., 8., 9., 10.])]
    mean, std = spread(arrays)
    values = np.arange(1., 11.)
    assert mean == pytest.approx(values.mean()) and std == pytest.approx(values.std())


def test_spread_is_none_for_too_few_crops_or_no_spread():
    assert spread([np.arange(MIN_SCORES - 1, dtype=float)]) is None
    assert spread([np.full(MIN_SCORES * 3, .25)]) is None
    assert spread([]) is None


def photos(*scores):
    return [np.asarray(s, dtype=float) for s in scores]


TEXT = photos([.20, .31], [.25], [.22, .24, .23], [.28], [.21], [.26], [.27, .20], [.23])
VISUAL = photos([.60, .55], [.90], [.50, .70, .52], [.58], [.65], [.62], [.61, .80], [.59])


def z(arrays, value):
    values = np.concatenate(arrays)
    return (value - values.mean()) / values.std()


def test_text_only_scores_are_z_scores_of_the_best_crop():
    normalized, matches = rank_photos(TEXT, None, .35)
    assert normalized
    assert [m.crop for m in matches] == [1, 0, 1, 0, 0, 0, 0, 0]
    assert matches[0] == Match(pytest.approx(z(TEXT, .31)), 1, pytest.approx(.31), None)
    # a monotonic transformation: the order of text-only results is that of the raw scores
    order = sorted(range(len(TEXT)), key=lambda i: -matches[i].score)
    assert order == sorted(range(len(TEXT)), key=lambda i: -TEXT[i].max())


def test_text_and_visual_scores_are_normalized_separately_before_they_are_combined():
    weight = .35
    normalized, matches = rank_photos(TEXT, VISUAL, weight)
    assert normalized
    for photo, match in enumerate(matches):
        combined = [(1 - weight) * z(TEXT, t) + weight * z(VISUAL, v) for t, v in zip(TEXT[photo], VISUAL[photo])]
        assert match.crop == int(np.argmax(combined))
        assert match.score == pytest.approx(max(combined))
        assert match.text == pytest.approx(TEXT[photo][match.crop])
        assert match.visual == pytest.approx(VISUAL[photo][match.crop])


def test_the_wide_visual_scale_no_longer_outweighs_the_text_score():
    # photo 0: by far the best text score, an average visual score; photo 1: an average
    # text score, a visual score that is high in raw terms but common in this folder (E5)
    text = photos([.35], [.25]) + photos(*[[.25 + d] for d in (-.05, .05, -.05, .05, -.05, .05, -.05, .05)])
    visual = photos([.70], [.90]) + photos(*[[.70 + d] for d in (-.2, .2, -.2, .2, -.2, .2, -.2, .2)])
    weight = .35
    raw = [(1 - weight) * t[0] + weight * v[0] for t, v in zip(text, visual)]
    assert raw[1] > raw[0]
    _, matches = rank_photos(text, visual, weight)
    assert matches[0].score > matches[1].score


@pytest.mark.parametrize('weight, expected', [(0, 'text'), (1, 'visual')])
def test_weight_zero_and_one_use_one_channel(weight, expected):
    _, matches = rank_photos(TEXT, VISUAL, weight)
    channel = TEXT if expected == 'text' else VISUAL
    assert [m.score for m in matches] == pytest.approx([max(z(channel, s) for s in c) for c in channel])


def test_too_few_crops_fall_back_to_the_raw_combination():
    text, visual = TEXT[:2], VISUAL[:2]
    assert sum(len(t) for t in text) < MIN_SCORES
    normalized, matches = rank_photos(text, visual, .35)
    assert not normalized
    assert matches[1] == Match(pytest.approx(.65 * .25 + .35 * .90), 0, pytest.approx(.25), pytest.approx(.90))


def test_no_visual_spread_falls_back_to_raw_scores_for_both_channels():
    flat = [np.full(len(t), .6) for t in TEXT]
    normalized, matches = rank_photos(TEXT, flat, .35)
    assert not normalized
    assert matches[3].score == pytest.approx(.65 * .28 + .35 * .6)


def test_no_photos():
    assert rank_photos([], None, .35) == (False, [])
