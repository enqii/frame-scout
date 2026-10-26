"""The signatures side table of the feature cache and the classification of cached rows (E11)."""
import json
import math
import sqlite3

from framescout_core import (DEFAULT_YOLO_MODEL, ENGINE, SETTING_RANGES, classify_signatures, engine_id,
                             feature_signature, known_signatures, prepare_cache)

DEFAULTS = dict(person_detection=True, max_persons=12, person_confidence=.3, yolo_model=DEFAULT_YOLO_MODEL)


def test_prepare_cache_creates_the_tables_and_records_the_signature(tmp_path):
    con = sqlite3.connect(tmp_path / 'cache.sqlite3')
    signature = prepare_cache(con, **DEFAULTS)
    assert signature == feature_signature(**DEFAULTS)
    # the features table keeps its schema (older versions read the same file)
    columns = [row[1] for row in con.execute('PRAGMA table_info(features)')]
    assert columns == ['path', 'signature', 'mtime_ns', 'size', 'labels', 'vectors']
    [(stored, engine, settings)] = con.execute('SELECT signature, engine, settings FROM signatures').fetchall()
    assert stored == signature and engine == ENGINE
    assert json.loads(settings) == DEFAULTS
    con.close()


def test_prepare_cache_is_idempotent_and_keeps_other_signatures(tmp_path):
    con = sqlite3.connect(tmp_path / 'cache.sqlite3')
    prepare_cache(con, **DEFAULTS)
    prepare_cache(con, **DEFAULTS)
    other = prepare_cache(con, **{**DEFAULTS, 'person_detection': False})
    rows = dict(con.execute('SELECT signature, settings FROM signatures').fetchall())
    assert set(rows) == {feature_signature(**DEFAULTS), other}
    # without person detection the detector settings do not belong to the signature
    assert json.loads(rows[other]) == {'person_detection': False}
    con.close()


def test_prepare_cache_adds_the_side_table_to_an_existing_cache(tmp_path):
    # a cache of an earlier version: rows, but no signatures table
    path = tmp_path / 'cache.sqlite3'
    con = sqlite3.connect(path)
    con.execute('''CREATE TABLE features (
        path TEXT NOT NULL, signature TEXT NOT NULL, mtime_ns INTEGER NOT NULL,
        size INTEGER NOT NULL, labels TEXT NOT NULL, vectors BLOB NOT NULL,
        PRIMARY KEY(path, signature))''')
    con.execute('INSERT INTO features VALUES (?,?,?,?,?,?)', ('a.jpg', 'old', 1, 2, '[]', b''))
    con.commit()
    prepare_cache(con, **DEFAULTS)
    assert con.execute('SELECT COUNT(*) FROM features').fetchone() == (1,)
    con.close()


def test_known_signatures_cover_every_value_of_the_app_widgets():
    known = known_signatures()
    assert feature_signature(**DEFAULTS) in known
    assert feature_signature(False, 12, .3, DEFAULT_YOLO_MODEL) in known
    low, high = SETTING_RANGES['max_persons']
    for max_persons in (low, high):
        for confidence in (0.1, 0.9, 0.55):
            assert feature_signature(True, max_persons, confidence, DEFAULT_YOLO_MODEL) in known
    # a slider returns e.g. 0.1 + 4 * 0.05 = 0.30000000000000004, which the app passes on as it is
    assert feature_signature(True, 12, 0.1 + 4 * 0.05, DEFAULT_YOLO_MODEL) in known
    # noise from other arithmetic paths, e.g. accumulated steps or n * step + low (review)
    accumulated = 0.1
    for n in range(1, 17):
        accumulated += 0.05
        assert feature_signature(True, 12, accumulated, DEFAULT_YOLO_MODEL) in known, accumulated
        for value in (n * 0.05 + 0.1, 0.1 + 0.05 * n, (0.1 * 20 + n) / 20,
                      math.nextafter(round(0.1 + n * 0.05, 2), 0)):
            assert feature_signature(True, 12, value, DEFAULT_YOLO_MODEL) in known, value
    for value in (0.15000000000000002, 0.35000000000000003):
        assert feature_signature(True, 12, value, DEFAULT_YOLO_MODEL) in known, value
    # another detector model or a value no widget offers is not known
    assert feature_signature(True, 12, .3, 'yolo11s.pt') not in known
    assert feature_signature(True, 12, .33, DEFAULT_YOLO_MODEL) not in known
    assert feature_signature(True, high + 1, .3, DEFAULT_YOLO_MODEL) not in known


def test_classify_signatures():
    current = feature_signature(**DEFAULTS)
    other_known = feature_signature(True, 5, .5, DEFAULT_YOLO_MODEL)
    cli = feature_signature(True, 12, .3, 'yolo11s.pt')
    recorded_old = 'a' * 64
    unknown = 'b' * 64
    recorded = {cli: ENGINE, recorded_old: 'v4-something'}
    result = classify_signatures([current, other_known, cli, recorded_old, unknown], recorded, current)
    assert result == {current: 'current', other_known: 'other', cli: 'other', recorded_old: 'old', unknown: 'old'}


def test_a_recorded_older_engine_wins_over_a_known_signature():
    # cannot happen with a real hash, but the side table is the more precise source
    sig = feature_signature(True, 5, .5, DEFAULT_YOLO_MODEL)
    assert classify_signatures([sig], {sig: 'v4'}, 'x') == {sig: 'old'}


# --- search models (E22) ---

def test_prepare_cache_records_the_engine_of_the_model(tmp_path):
    con = sqlite3.connect(tmp_path / 'cache.sqlite3')
    signature = prepare_cache(con, **DEFAULTS, model='vit-b-16-siglip')
    assert signature == feature_signature(**DEFAULTS, model='vit-b-16-siglip')
    [(stored, engine, settings)] = con.execute('SELECT signature, engine, settings FROM signatures').fetchall()
    assert stored == signature and engine == engine_id('vit-b-16-siglip')
    # the model is named by the engine column, the settings stay as before
    assert json.loads(settings) == DEFAULTS
    con.close()


def test_rows_of_other_registered_models_have_a_category_of_their_own():
    current = feature_signature(**DEFAULTS)
    b16 = feature_signature(**DEFAULTS, model='vit-b-16-datacomp')
    l14_other = feature_signature(True, 5, .5, DEFAULT_YOLO_MODEL, model='vit-l-14-datacomp')
    recorded = {b16: engine_id('vit-b-16-datacomp'), l14_other: engine_id('vit-l-14-datacomp')}
    result = classify_signatures([current, b16, l14_other], recorded, current)
    assert result == {current: 'current', b16: 'model', l14_other: 'model'}


def test_with_another_current_model_the_default_rows_count_as_another_model():
    current = feature_signature(**DEFAULTS, model='vit-b-16-datacomp')
    other_settings = feature_signature(True, 5, .5, DEFAULT_YOLO_MODEL, model='vit-b-16-datacomp')
    default_recorded = feature_signature(**DEFAULTS)
    # a row of the default model written before the side table existed (known_signatures)
    default_unrecorded = feature_signature(True, 5, .5, DEFAULT_YOLO_MODEL)
    recorded = {current: engine_id('vit-b-16-datacomp'), other_settings: engine_id('vit-b-16-datacomp'),
                default_recorded: ENGINE, 'a' * 64: 'v4-something'}
    result = classify_signatures([current, other_settings, default_recorded, default_unrecorded, 'a' * 64,
                                  'b' * 64], recorded, current, current_engine=engine_id('vit-b-16-datacomp'))
    assert result == {current: 'current', other_settings: 'other', default_recorded: 'model',
                      default_unrecorded: 'model', 'a' * 64: 'old', 'b' * 64: 'old'}
