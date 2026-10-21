"""CLIP model choice and the feature cache signature (E1)."""
import pytest

from framescout_core import CLIP_MODEL, CLIP_PRETRAINED, ENGINE, feature_signature

DEFAULTS = dict(person_detection=True, max_persons=12, person_confidence=.3, yolo_model='yolo11n.pt')
# Signature of the default settings in v1.1 (ENGINE v4, GELU embeddings)
V1_1_DEFAULT_SIGNATURE = '552c0464be05f62156f4acb048eb1555db8e3bc80f63416f9909695dc59c20b4'
# Signature without person detection from E1 until E2 (full-resolution decoding)
PRE_E2_NO_DETECTION_SIGNATURE = '943924600aec2d9c711312c59c8db2ae7e33864857967169edc8f87ea2bdcb76'


def test_model_config_matches_the_activation_of_the_weights():
    # Runs only where open_clip is installed (the project venv); CI has no torch and skips
    # it. Reads open_clip's config tables only, no model download. open_clip warns about a
    # "QuickGELU mismatch" exactly when these two values differ: the OpenAI weights were
    # trained with QuickGELU, the plain "ViT-B-32" config uses GELU (E1).
    open_clip = pytest.importorskip('open_clip')
    from open_clip.pretrained import get_pretrained_cfg
    weights = get_pretrained_cfg(CLIP_MODEL, CLIP_PRETRAINED)
    assert weights, f'open_clip has no {CLIP_PRETRAINED!r} weights for {CLIP_MODEL!r}'
    assert open_clip.get_model_config(CLIP_MODEL).get('quick_gelu', False) == weights.get('quick_gelu', False)


def test_engine_names_the_clip_model():
    # a different CLIP model must never reuse cached embeddings of another one
    assert CLIP_MODEL in ENGINE and CLIP_PRETRAINED in ENGINE


def test_signature_values_are_pinned():
    # Golden values: any change to ENGINE, the config list or its serialization makes every
    # user's cache invalid, so it must be deliberate and update these values.
    # with person detection: unchanged since E1 (photos are still decoded at full resolution)
    assert feature_signature(**DEFAULTS) == 'ff0961b445ea26b7f0a4c5ea39a078d1297927da627246d962cef5c1e698fa47'
    # without person detection: changed by E2 (Image.draft), see the test below
    assert feature_signature(**{**DEFAULTS, 'person_detection': False}) == (
        '89ce5cc619f616f3e72ac6787db2739ed86dbf77a6abb820b6e5bc7f5128c08c')
    # the GELU rows of v1.1 are never reused, so every photo is analyzed once more
    assert feature_signature(**DEFAULTS) != V1_1_DEFAULT_SIGNATURE


def test_drafted_decoding_gets_its_own_signature():
    # E2 decodes JPEGs at reduced scale (Image.draft) when person detection is off. Its
    # rows must not mix with the full-resolution rows written before (user decision in the
    # PR #7 review): the first run without detection after the update analyzes every photo
    # once more, while caches of runs with detection stay valid.
    assert feature_signature(**{**DEFAULTS, 'person_detection': False}) != (
        PRE_E2_NO_DETECTION_SIGNATURE)


def test_every_detector_setting_changes_the_signature():
    changes = dict(person_detection=False, max_persons=5, person_confidence=.5, yolo_model='yolo11s.pt')
    base = feature_signature(**DEFAULTS)
    for key, value in changes.items():
        assert feature_signature(**{**DEFAULTS, key: value}) != base, key


def test_detector_settings_are_ignored_without_person_detection():
    # without detection only the full image is embedded, so moving e.g. the confidence
    # slider must not force a complete re-analysis
    off = {**DEFAULTS, 'person_detection': False}
    base = feature_signature(**off)
    for key, value in dict(max_persons=5, person_confidence=.5, yolo_model='yolo11s.pt').items():
        assert feature_signature(**{**off, key: value}) == base, key
