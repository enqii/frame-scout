"""Scoring of the search engine (E4, E5): needs numpy, not torch (I30).

A package of its own next to framescout_core, which stays standard library only. This
file re-exports the public names of its modules, so "from framescout_scoring import
<name>" works as with the former single file framescout_scoring.py.
"""
from .layout import PACKAGE, LAYOUT_MARKER, scoring_leftover_message, scoring_import_refused, refuse_scoring_leftover

# First of all (I36): next to framescout_scoring.py of an older version, the importing engine
# may be that older version's, which must not score with this newer code.
refuse_scoring_leftover(__file__)

from .ranking import (MIN_SCORES, MIN_SPREAD, Match, best_matches, best_scores, photo_scores, rank_photos, rank_similar,
                      score_caption, spread, text_queries)
