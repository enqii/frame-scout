"""The registry of search models the engine's --model and the app's model choice offer (E22)."""
import re

import pytest

from framescout_core import (DEFAULT_MODEL, MODEL_KEYS, MODELS, SearchModel, missing_packages, model_label,
                             model_problem, results_model)


def test_the_default_is_openai_clip_vit_b_32_with_quickgelu():
    # user decision in PR #13: the default stays; its cache rows stay valid (test_signature.py)
    default = MODELS[DEFAULT_MODEL]
    assert (default.name, default.pretrained) == ('ViT-B-32-quickgelu', 'openai')
    assert MODEL_KEYS[0] == DEFAULT_MODEL


def test_the_offered_models_are_the_chosen_candidates():
    # user decision for E22: the default plus ViT-B-16, ViT-L-14 (DataComp-XL) and SigLIP B/16
    assert [(m.name, m.pretrained) for m in MODELS.values()] == [
        ('ViT-B-32-quickgelu', 'openai'),
        ('ViT-B-16', 'datacomp_xl_s13b_b90k'),
        ('ViT-L-14', 'datacomp_xl_s13b_b90k'),
        ('ViT-B-16-SigLIP', 'webli'),
    ]
    assert MODEL_KEYS == tuple(MODELS)


def test_registry_entries_are_consistent():
    for key, model in MODELS.items():
        assert isinstance(model, SearchModel)
        assert model.key == key
        # a stable key for the command line and settings.json: lowercase, no spaces
        assert re.fullmatch(r'[a-z0-9]+(-[a-z0-9]+)*', key), key
        assert model.label and model.download and model.cpu_factor
        assert model.image_size > 0 and model.embedding_size > 0
    assert len({(m.name, m.pretrained) for m in MODELS.values()}) == len(MODELS)


def test_only_the_default_counts_as_evaluated():
    # the other candidates are offered before their evaluation (user decision: two PRs)
    assert [key for key, model in MODELS.items() if model.evaluated] == [DEFAULT_MODEL]


def test_siglip_needs_transformers_and_the_others_nothing_extra():
    assert {key: model.requires for key, model in MODELS.items()} == {
        'vit-b-32-openai': (), 'vit-b-16-datacomp': (), 'vit-l-14-datacomp': (), 'vit-b-16-siglip': ('transformers',)}


def test_no_offered_model_is_multilingual_yet():
    # the "in English" hint of the app holds for every offered model (E3, E21)
    assert not any(model.multilingual for model in MODELS.values())


def test_labels_name_the_cpu_factor_the_download_and_the_evaluation():
    assert 'default' in model_label(DEFAULT_MODEL)
    assert 'not evaluated' not in model_label(DEFAULT_MODEL)
    for key in MODEL_KEYS[1:]:
        label = model_label(key)
        assert MODELS[key].cpu_factor in label and MODELS[key].download in label
        assert 'not evaluated' in label


def test_missing_packages_and_problem():
    def none_installed(name):
        return None

    def all_installed(name):
        return object()

    assert missing_packages('vit-b-16-siglip', none_installed) == ['transformers']
    assert missing_packages('vit-b-16-siglip', all_installed) == []
    assert missing_packages(DEFAULT_MODEL, none_installed) == []
    problem = model_problem('vit-b-16-siglip', none_installed)
    assert 'transformers' in problem and 'Install-FrameScout.bat' in problem
    assert model_problem('vit-b-16-siglip', all_installed) is None
    assert model_problem(DEFAULT_MODEL, none_installed) is None


def test_the_model_of_a_search_comes_from_its_results_settings():
    # E22 review: the app notes results of another model than the chosen one
    assert results_model({'model': 'vit-b-16-siglip', 'top': 150}) == 'vit-b-16-siglip'
    assert results_model({'top': 150}) == DEFAULT_MODEL  # a search before E22
    assert results_model({}) == DEFAULT_MODEL and results_model(None) == DEFAULT_MODEL
    assert results_model({'model': 'removed-later'}) == 'removed-later'  # e.g. trimmed from the list (E32)
    assert results_model({'model': ['x']}) is None and results_model({'model': None}) is None


def test_unknown_model_keys_are_refused():
    with pytest.raises(ValueError, match='Unknown search model'):
        model_label('ViT-B-32')
    with pytest.raises(ValueError, match='Unknown search model'):
        model_problem('nope')


# --- checked against open_clip's config tables (project venv only; CI has no torch) ---

def open_clip_or_skip():
    # reads open_clip's config tables only, no model download
    return pytest.importorskip('open_clip')


@pytest.mark.parametrize('key', MODEL_KEYS)
def test_open_clip_knows_the_model_and_its_weights(key):
    open_clip = open_clip_or_skip()
    from open_clip.pretrained import get_pretrained_cfg
    model = MODELS[key]
    assert open_clip.get_model_config(model.name), model.name
    assert get_pretrained_cfg(model.name, model.pretrained), (model.name, model.pretrained)


@pytest.mark.parametrize('key', MODEL_KEYS)
def test_model_config_matches_the_activation_of_the_weights(key):
    # open_clip warns about a "QuickGELU mismatch" exactly when these two values differ (E1)
    open_clip = open_clip_or_skip()
    from open_clip.pretrained import get_pretrained_cfg
    model = MODELS[key]
    weights = get_pretrained_cfg(model.name, model.pretrained)
    assert open_clip.get_model_config(model.name).get('quick_gelu', False) == weights.get('quick_gelu', False)


@pytest.mark.parametrize('key', MODEL_KEYS)
def test_input_and_embedding_size_match_the_open_clip_config(key):
    # the engine drafts JPEGs with the input size (draft_size): a 256/384 px model must
    # never be drafted for 224 px
    open_clip = open_clip_or_skip()
    model = MODELS[key]
    config = open_clip.get_model_config(model.name)
    size = config['vision_cfg'].get('image_size', 224)
    assert (max(size) if isinstance(size, (tuple, list)) else size) == model.image_size
    assert config['embed_dim'] == model.embedding_size


@pytest.mark.parametrize('key', MODEL_KEYS)
def test_a_hugging_face_tokenizer_is_declared_as_an_extra_package(key):
    open_clip = open_clip_or_skip()
    model = MODELS[key]
    uses_hf = bool(open_clip.get_model_config(model.name)['text_cfg'].get('hf_tokenizer_name'))
    assert ('transformers' in model.requires) == uses_hf
