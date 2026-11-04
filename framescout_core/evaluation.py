"""Search-model evaluation (E32, E20): scores file, labels, candidate pool and AP@k.

The engine writes the raw per-crop similarities of a search to a scores file
(--scores-file); the evaluation tool framescout_eval.py ranks them with the engine's
scoring, pools the top photos of every model per profile for labelling, and computes the
average precision of each model's ranking against the user's labels. Everything here is
standard library only, so it is tested without torch or a model.
"""
import json
import math
import random
import re
from pathlib import Path

from ._common import _read_json_object, _replace_atomically

SCORES_FORMAT = 1
LABELS_FORMAT = 1
# AP@40, as in the first evaluation (PR #11): about the first page of a gallery
EVAL_K = 40
# digits kept of each similarity in the scores file (the cache stores float16 anyway)
SCORE_DIGITS = 6
_COLLECTION_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}')
# folder names Windows reserves for devices, also with a suffix-free name like "con"
_RESERVED = {'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(1, 10)), *(f'lpt{i}' for i in range(1, 10))}


def collection_name_problem(name):
    """Return why name cannot name an evaluation collection (a plain folder name), or None."""
    if not isinstance(name, str) or not _COLLECTION_NAME.fullmatch(name):
        return (f'Invalid collection name {name!r}: use 1-64 letters, digits, "-" or "_", '
                'starting with a letter or digit.')
    if name.lower() in _RESERVED:
        return f'Invalid collection name {name!r}: Windows reserves it.'
    return None


def _rounded(rows):
    return [[round(float(value), SCORE_DIGITS) for value in row] for row in rows]


def scores_document(model, signature, photos, profiles):
    """Return the content of a scores file.

    model: the search model key; signature: the feature signature of the cache rows;
    photos: [(path, mtime_ns, crop labels)] of every scored photo; profiles: dicts with
    "name", "prompts", "references" (paths as strings), "text" (one list of per-crop scores
    per photo) and "visual" (the same for the reference images, or None). Raises
    ValueError if a profile's scores do not match the photos' crops.
    """
    crops = [len(labels) for _, _, labels in photos]
    entries = []
    for profile in profiles:
        for key in ('text', 'visual'):
            rows = profile[key]
            if key == 'visual' and rows is None:
                continue
            if [len(row) for row in rows] != crops:
                raise ValueError(f'{key} scores of profile {profile["name"]!r} do not match the crops of the photos')
        entries.append({'name': profile['name'], 'prompts': list(profile['prompts']),
                        'references': [str(ref) for ref in profile['references']],
                        'text': _rounded(profile['text']),
                        'visual': None if profile['visual'] is None else _rounded(profile['visual'])})
    return {'format': SCORES_FORMAT, 'model': model, 'signature': signature,
            'photos': [{'path': str(path), 'mtime_ns': int(mtime), 'crops': list(labels)}
                       for path, mtime, labels in photos],
            'profiles': entries}


def write_document(path, document, indent=None):
    """Write the JSON object document to path atomically (its folder is created).

    ValueError for NaN or infinity, which standard JSON cannot hold (review).
    """
    path = Path(path)
    text = json.dumps(document, ensure_ascii=False, indent=indent, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    _replace_atomically(path, (text + '\n').encode('utf-8'))


def read_document(path, what, version):
    """Return the JSON object of path if its "format" is version, None if path is missing.

    Anything else (not JSON, not an object, another format) raises ValueError naming what.
    """
    if not Path(path).exists():
        return None
    try:
        document = _read_json_object(path, what)
    except json.JSONDecodeError as exc:
        raise ValueError(f'{path} is not a readable {what}: {exc}') from None
    if document.get('format') != version:
        raise ValueError(f'{path} is not a {what} of format {version}')
    return document


def write_scores(path, document):
    """Write a scores document to path atomically (its folder is created)."""
    write_document(path, document)


def read_scores(path):
    """Return the validated scores document of path; ValueError if it is missing or not a usable one."""
    document = read_document(path, 'scores file', SCORES_FORMAT)
    if document is None:
        raise ValueError(f'Scores file not found: {path}')
    photos, profiles = document.get('photos'), document.get('profiles')
    if not isinstance(document.get('model'), str) or not isinstance(photos, list) or not isinstance(profiles, list):
        raise ValueError(f'{path}: model, photos or profiles missing')
    try:
        crops = [len(photo['crops']) for photo in photos]
        for photo in photos:
            if not isinstance(photo['path'], str) or not isinstance(photo['mtime_ns'], int):
                raise ValueError
        for profile in profiles:
            if not isinstance(profile['name'], str):
                raise ValueError
            for key in ('text', 'visual'):
                rows = profile[key]
                if key == 'visual' and rows is None:
                    continue
                if [len(row) for row in rows] != crops:
                    raise ValueError
                # finite numbers only: json reads NaN and Infinity, which would break the ranking
                if not all(type(value) in (int, float) and math.isfinite(value) for row in rows for value in row):
                    raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ValueError(f'{path}: the scores do not match the photos and their crops') from None
    return document


def read_labels(path):
    """Return {profile: {photo path: True (match) or False (no match)}} of a labels file.

    A missing file has no labels; any other unreadable content raises ValueError, so the
    labelling page never saves over labels it could not read.
    """
    document = read_document(path, 'labels file', LABELS_FORMAT)
    if document is None:
        return {}
    labels = document.get('labels')
    if not isinstance(labels, dict) or not all(
            isinstance(photos, dict) and all(isinstance(value, bool) for value in photos.values())
            for photos in labels.values()):
        raise ValueError(f'{path} is not a labels file of format {LABELS_FORMAT}')
    return labels


def save_labels(path, labels, motifs=None):
    """Write labels ({profile: {photo path: bool}}) to path atomically (its folder is created).

    motifs ({profile: motif}, record_motif) are saved with them if there are any (E36).
    """
    document = {'format': LABELS_FORMAT, 'labels': labels}
    if motifs:
        document['motifs'] = motifs
    write_document(path, document, indent=1)


# what a profile's motif is made of, in the order changed_motifs names them, with its label
_MOTIF_FIELDS = (('context', 'context'), ('features', 'features'), ('references', 'reference images'))


def motif(context, features, references):
    """Return the motif a profile describes: its context, features and reference images (E36).

    Its prompts are left out: they may be reworded under the same name to compare wordings
    on the same labels.
    """
    return {'context': context or '', 'features': features or '', 'references': [str(r) for r in references]}


def read_motifs(path):
    """Return {profile: motif} of a labels file: the motif each profile's labels were made for (E36).

    A missing file, or one of an earlier version without motifs, has none; motifs that are
    not readable raise ValueError, like unreadable labels.
    """
    document = read_document(path, 'labels file', LABELS_FORMAT)
    motifs = {} if document is None else document.get('motifs', {})
    if not isinstance(motifs, dict) or not all(
            isinstance(entry, dict) and set(entry) == {'context', 'features', 'references'}
            and isinstance(entry['context'], str) and isinstance(entry['features'], str)
            and isinstance(entry['references'], list) and all(isinstance(r, str) for r in entry['references'])
            for entry in motifs.values()):
        raise ValueError(f'{path} is not a labels file of format {LABELS_FORMAT}: unreadable motifs')
    return motifs


def record_motif(motifs, labels, profile, current):
    """Return a copy of motifs after a label of profile was set or cleared (labels: all labels after it).

    A profile with labels and no motif yet gets current, the motif of the label just set; a
    recorded one is kept, so labels of an earlier motif under the same name stay visible
    (changed_motifs) until they are cleared. Profiles without labels lose their motif.
    """
    result = {name: entry for name, entry in motifs.items() if name in labels}
    if profile in labels:
        result.setdefault(profile, current)
    return result


def changed_motifs(motifs, current):
    """Return {profile: [what changed]} of the recorded motifs that differ from the current ones.

    Profiles without a current motif (no model run scored them) are left out.
    """
    changes = {}
    for name, recorded in motifs.items():
        if name in current:
            fields = [label for key, label in _MOTIF_FIELDS if recorded[key] != current[name][key]]
            if fields:
                changes[name] = fields
    return changes


def set_label(labels, profile, photo, value):
    """Return a copy of labels with photo of profile labelled value (True, False, or None to clear it)."""
    if value is not None and not isinstance(value, bool):
        raise ValueError(f'A label is true, false or null, not {value!r}')
    result = {name: dict(photos) for name, photos in labels.items()}
    photos = result.setdefault(profile, {})
    if value is None:
        photos.pop(photo, None)
    else:
        photos[photo] = value
    if not photos:
        del result[profile]
    return result


def average_precision(ranked, relevant, k=EVAL_K):
    """Return AP@k of the ranked photo list against the set of relevant photos, or None without any.

    The precision at each relevant photo among the first k is averaged over min(number of
    relevant photos, k), so a relevant photo the ranking misses counts as a miss.
    """
    if not relevant:
        return None
    hits, total = 0, 0.0
    for rank, photo in enumerate(ranked[:k], 1):
        if photo in relevant:
            hits += 1
            total += hits / rank
    return total / min(len(relevant), k)


def build_pool(rankings, depth, seed):
    """Return the candidate photos to label: the union of the first depth of every ranking.

    The order is shuffled reproducibly with seed (the profile name), independent of the
    order of the rankings, so the labeller cannot tell which model ranked a photo how high.
    """
    if depth < 1:
        raise ValueError('The pool depth must be at least 1.')
    pool = sorted({photo for ranking in rankings for photo in ranking[:depth]})
    random.Random(seed).shuffle(pool)
    return pool
