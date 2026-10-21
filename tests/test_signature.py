"""CLIP model choice and the feature cache signature (E1)."""
import hashlib
import json

from framescout_core import CLIP_MODEL, CLIP_PRETRAINED, ENGINE, feature_signature

DEFAULTS = dict(person_detection=True, max_persons=12, person_confidence=.3, yolo_model='yolo11n.pt')


def test_openai_weights_use_the_quickgelu_architecture():
    # the OpenAI CLIP weights were trained with QuickGELU; the plain "ViT-B-32" config
    # uses GELU, which loads the weights without error but degrades the embeddings
    assert CLIP_PRETRAINED == 'openai'
    assert CLIP_MODEL == 'ViT-B-32-quickgelu'


def test_engine_names_the_clip_model():
    # a different CLIP model must never reuse cached embeddings of another one
    assert CLIP_MODEL in ENGINE and CLIP_PRETRAINED in ENGINE


def test_signature_differs_from_the_gelu_cache_of_v1_1():
    # signature of the default settings before E1: these rows hold GELU embeddings and
    # must not be reused, so every photo is analyzed once more after the update
    old = ['v4-clip-vit-b-32-openai-yolo11n-crop-features-1', True, 12, .3, 'yolo11n.pt']
    old_signature = hashlib.sha256(json.dumps(old, sort_keys=True).encode()).hexdigest()
    assert feature_signature(**DEFAULTS) != old_signature


def test_signature_is_stable():
    assert feature_signature(**DEFAULTS) == feature_signature(**DEFAULTS)
    assert len(feature_signature(**DEFAULTS)) == 64


def test_every_detector_setting_changes_the_signature():
    changes = dict(person_detection=False, max_persons=5, person_confidence=.5, yolo_model='yolo11s.pt')
    base = feature_signature(**DEFAULTS)
    for key, value in changes.items():
        assert feature_signature(**{**DEFAULTS, key: value}) != base, key
