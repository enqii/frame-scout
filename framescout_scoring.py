"""Scoring of image features against a search profile (E4, E5); needs numpy, not torch.

A profile's text queries are the average of its generated prompt templates (one
normalized vector, the usual CLIP prompt ensemble) followed by its custom prompts, and a
crop's text score is its best cosine similarity with one of these queries (E4). Text
scores (about 0.2-0.35 with CLIP) and image-to-image scores (about 0.5-0.9) have different
scales, so per profile and run both are z-scored over all crops of the searched photos
before the reference weight combines them (E5). A score is then "standard deviations
above the average crop of this search", a relative ranking value, not a probability.
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


def spread(arrays):
    """(mean, standard deviation) over all values of arrays, or None if it cannot normalize."""
    values = np.concatenate(arrays) if arrays else np.empty(0)
    if values.size < MIN_SCORES:
        return None
    mean, std = float(values.mean()), float(values.std())
    return (mean, std) if np.isfinite(std) and std >= MIN_SPREAD else None


def rank_photos(text, visual, weight):
    """Score every photo of a search for one profile.

    text: one array per photo with the text score of each crop; visual: the same for the
    reference images, or None for a profile without them; weight: the reference weight.
    Returns (normalized, matches): matches holds one Match per photo in input order;
    normalized is False if the raw scores had to be used (too few crops, no spread).
    """
    stats = [spread(text)] + ([spread(visual)] if visual is not None else [])
    normalized = all(s is not None for s in stats)
    matches = []
    for photo, text_scores in enumerate(text):
        text_scores = np.asarray(text_scores, dtype=np.float64)
        combined = (text_scores - stats[0][0]) / stats[0][1] if normalized else text_scores
        if visual is not None:
            visual_scores = np.asarray(visual[photo], dtype=np.float64)
            scaled = (visual_scores - stats[1][0]) / stats[1][1] if normalized else visual_scores
            combined = (1 - weight) * combined + weight * scaled
        crop = int(np.argmax(combined))
        matches.append(Match(float(combined[crop]), crop, float(text_scores[crop]),
                             None if visual is None else float(visual_scores[crop])))
    return normalized, matches
