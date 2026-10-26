"""The CLIP model, the feature cache signature and the cache tables (E11)."""
import hashlib
import json
import math

from .pipeline import DRAFT_DECODING
from .settings import SETTING_RANGES, SETTING_STEPS


# OpenCLIP model and weights. The OpenAI CLIP weights were trained with QuickGELU;
# the plain "ViT-B-32" config uses GELU, loads them with only a warning and yields
# degraded embeddings (E1). Same weights file, so switching needs no new download.
CLIP_MODEL = 'ViT-B-32-quickgelu'
CLIP_PRETRAINED = 'openai'
# Part of the feature cache signature: change it whenever cached embeddings become
# incompatible (other model, weights, preprocessing or crops). v4 was ViT-B-32 with GELU.
ENGINE = f'v5-clip-{CLIP_MODEL}-{CLIP_PRETRAINED}-crop-features-1'


def feature_signature(person_detection, max_persons, person_confidence, yolo_model):
    """Return the cache signature of the image features for these engine settings.

    Cached rows are reused only under the same signature, so any setting that changes
    the stored embeddings or crops belongs here, and nothing else: without person
    detection only the full image is embedded, so the detector settings are left out.
    Without person detection JPEGs are decoded at reduced scale (draft_size, E2), so that
    signature also names the decoding; with detection photos keep full resolution and the
    signature is the same as before E2, so those cached rows stay valid.
    """
    config = [ENGINE, bool(person_detection)]
    if person_detection:
        config += [max_persons, person_confidence, yolo_model]
    else:
        config.append(DRAFT_DECODING)
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


# The feature cache in the output folder, and the engine's default person detector.
CACHE_FILE = 'cache.sqlite3'
DEFAULT_YOLO_MODEL = 'yolo11n.pt'


def _signature_settings(person_detection, max_persons, person_confidence, yolo_model):
    """The settings feature_signature hashes, as stored in the signatures table."""
    if not person_detection:
        return {'person_detection': False}
    return {'person_detection': True, 'max_persons': max_persons, 'person_confidence': person_confidence,
            'yolo_model': yolo_model}


def prepare_cache(con, person_detection, max_persons, person_confidence, yolo_model):
    """Create the tables of the feature cache (sqlite3 connection con) if needed; return this run's signature.

    The features table holds the embeddings per photo path and signature. The signatures
    table records which ENGINE and settings each signature stands for (E11): the signature
    is a hash, so without it the cleanup could not tell rows of an older engine version from
    rows of other settings. The features table is unchanged, so older versions keep reading
    the same file and ignore the side table.
    """
    signature = feature_signature(person_detection, max_persons, person_confidence, yolo_model)
    con.execute('''CREATE TABLE IF NOT EXISTS features (
        path TEXT NOT NULL, signature TEXT NOT NULL, mtime_ns INTEGER NOT NULL,
        size INTEGER NOT NULL, labels TEXT NOT NULL, vectors BLOB NOT NULL,
        PRIMARY KEY(path, signature))''')
    con.execute('''CREATE TABLE IF NOT EXISTS signatures (
        signature TEXT PRIMARY KEY, engine TEXT NOT NULL, settings TEXT NOT NULL)''')
    settings = _signature_settings(person_detection, max_persons, person_confidence, yolo_model)
    con.execute('INSERT OR IGNORE INTO signatures VALUES (?,?,?)',
                (signature, ENGINE, json.dumps(settings, sort_keys=True)))
    con.commit()
    return signature


# float neighbors (units in the last place) of each slider step known_signatures also counts:
# a slider value can carry rounding noise from any arithmetic path (e.g. 0.1 + 4 * 0.05 =
# 0.30000000000000004, one ULP above 0.3); several ULPs cover every such path (review)
SLIDER_NOISE_ULPS = 8


def _slider_values(name):
    """The values the app's slider of setting name can return: each step and its float noise."""
    low, high = SETTING_RANGES[name]
    step = SETTING_STEPS[name]
    values, n = set(), 0
    while low + n * step <= high + 1e-9:
        exact = round(low + n * step, 4)
        for start, toward in ((exact, math.inf), (exact, -math.inf)):
            value = start
            for _ in range(SLIDER_NOISE_ULPS + 1):
                values.add(value)
                value = math.nextafter(value, toward)
        n += 1
    return values


def known_signatures(yolo_model=DEFAULT_YOLO_MODEL):
    """Return the signatures of the current ENGINE for every value of the app's widgets (E11).

    For cached rows written before the signatures table existed: a row whose signature is
    neither recorded there nor one of these is of an older engine version or of settings
    only the CLI offers (e.g. another --yolo-model).
    """
    known = {feature_signature(False, 0, 0, yolo_model)}
    low, high = SETTING_RANGES['max_persons']
    confidences = _slider_values('person_confidence')
    for max_persons in range(low, high + 1):
        for confidence in confidences:
            known.add(feature_signature(True, max_persons, confidence, yolo_model))
    return known


def classify_signatures(signatures, recorded, current, known=None):
    """Return {signature: 'current' | 'other' | 'old'} for the signatures of cached rows (E11).

    recorded: {signature: engine} of the signatures table; current: the signature of the
    current settings; known: known_signatures() (computed if None). 'other' is a signature of
    the current ENGINE with other settings, 'old' one of an older engine version or unknown.
    """
    result = {}
    for signature in signatures:
        if signature == current:
            result[signature] = 'current'
            continue
        if signature in recorded:
            result[signature] = 'other' if recorded[signature] == ENGINE else 'old'
            continue
        if known is None:
            known = known_signatures()
        result[signature] = 'other' if signature in known else 'old'
    return result
