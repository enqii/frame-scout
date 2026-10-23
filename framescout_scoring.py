"""Scoring of image features against a search profile (E4, E5); needs numpy, not torch.

A profile's text queries are the average of its generated prompt templates (one
normalized vector, the usual CLIP prompt ensemble) followed by its custom prompts, and a
crop's text score is its best cosine similarity with one of these queries (E4). Text
scores (about 0.2-0.35 with CLIP) and image-to-image scores (about 0.5-0.9) have different
scales, so per profile and run both are z-scored over all crops of the searched photos
before the reference weight combines them (E5). A text-only score is then "standard
deviations above the average crop of this search"; with reference images it is the
weighted sum of both z-scores. A relative ranking value, not a probability.
"""
from typing import NamedTuple, Optional

import numpy as np

# Fewer crops than this in a run (or a spread of about 0): the raw cosine similarities are
# combined as before, since the mean and spread of a handful of scores are noise.
MIN_SCORES = 10
MIN_SPREAD = 1e-6


class Match(NamedTuple):
    """Best crop of one photo: combined score, crop index, raw text and visual similarity."""
    score: float
    crop: int
    text: float
    visual: Optional[float]


def _unit(vectors):
    vectors = np.asarray(vectors, dtype=np.float32)
    return vectors / np.maximum(np.linalg.norm(vectors, axis=-1, keepdims=True), 1e-8)


def text_queries(prompt_vectors, generated):
    """Query vectors of a profile: the averaged first `generated` prompts, then the others.

    prompt_vectors: one row per prompt in the order of load_profiles (generated templates
    first, then the custom prompts).
    """
    vectors = _unit(prompt_vectors)
    if not generated:
        return vectors
    ensemble = _unit(vectors[:generated].mean(axis=0, keepdims=True))
    return np.concatenate([ensemble, vectors[generated:]])


def best_scores(features, queries):
    """Best cosine similarity of each crop (row of features) with one of the queries."""
    return (features @ queries.T).max(axis=1)


def photo_scores(features, labels, profile_vectors):
    """Per-crop text and reference scores of one cached photo for every profile.

    features: the photo's normalized crop vectors; labels: its crop labels;
    profile_vectors: {name: (queries, reference vectors or None)}. Returns (text, visual):
    {name: scores per crop}, visual only for profiles with reference images. Raises
    ValueError for a broken cache row (labels and vectors do not match, no crop, scores
    that are not finite); the engine skips such a photo, so it cannot break a search.
    """
    if len(labels) != len(features) or not len(features):
        raise ValueError(f'{len(labels)} crop labels for {len(features)} feature vectors')
    text = {name: best_scores(features, queries) for name, (queries, _) in profile_vectors.items()}
    visual = {name: best_scores(features, refs) for name, (_, refs) in profile_vectors.items() if refs is not None}
    if not all(np.isfinite(scores).all() for scores in (*text.values(), *visual.values())):
        raise ValueError('the cached feature vectors give scores that are not finite')
    return text, visual


def spread(arrays):
    """(mean, standard deviation) over the finite values of arrays, or None if it cannot normalize."""
    values = np.concatenate(arrays) if arrays else np.empty(0)
    values = values[np.isfinite(values)]
    if values.size < MIN_SCORES:
        return None
    mean, std = float(values.mean()), float(values.std())
    return (mean, std) if std >= MIN_SPREAD else None


def rank_photos(text, visual, weight):
    """Score every photo of a search for one profile.

    text: one array per photo with the text score of each crop; visual: the same for the
    reference images, or None for a profile without them; weight: the reference weight.
    Returns (normalized, matches): matches holds one Match per photo in input order;
    normalized is False if the raw scores had to be used (too few crops, no spread). Only
    a channel that counts (weight above 0) needs a spread: with weight 0 the reference
    images and with weight 1 the text do not decide the ranking.
    """
    channels = [(text, 1.0 if visual is None else 1 - weight)] + ([(visual, weight)] if visual is not None else [])
    stats = [spread(scores) if share > 0 else None for scores, share in channels]
    normalized = all(s is not None for s, (_, share) in zip(stats, channels) if share > 0)
    matches = []
    for photo in range(len(text)):
        combined = 0.0
        for (scores, share), stat in zip(channels, stats):
            if share > 0:
                values = np.asarray(scores[photo], dtype=np.float64)
                combined = combined + share * ((values - stat[0]) / stat[1] if normalized else values)
        crop = int(np.argmax(combined))
        matches.append(Match(float(combined[crop]), crop, float(text[photo][crop]),
                             None if visual is None else float(visual[photo][crop])))
    return normalized, matches


def score_caption(match, normalized):
    """(main line, detail line) of a gallery card: the score and the raw similarities."""
    main = f'Score {match.score:+.2f}' if normalized else f'Similarity {match.score:.3f}'
    detail = f'text {match.text:.3f}' + ('' if match.visual is None else f' · image {match.visual:.3f}')
    return main, detail
