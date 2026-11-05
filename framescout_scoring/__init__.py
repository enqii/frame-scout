"""Scoring of the search engine (E4, E5): needs numpy, not torch (I30).

A package of its own next to framescout_core, which stays standard library only. This
file re-exports the public names of its modules, so "from framescout_scoring import
<name>" works as with the former single file framescout_scoring.py.
"""
from .ranking import (MIN_SCORES, MIN_SPREAD, Match, best_scores, photo_scores, rank_photos, score_caption, spread,
                      text_queries)
