# Backend/Business_Layer/utils/extraction/scoring.py
"""Shared point-scoring rules for every anchor+geometry candidate.

Every extractor's candidates are scored with the same point system so
behavior is predictable and documented in one place: a candidate wins
by being close to its anchor and away from buyer/ship-to context and
item tables — never by simply being "the biggest number on the page".
"""
from __future__ import annotations

SCORE_NEAR_ANCHOR = 40.0
SCORE_SAME_LINE = 20.0
SCORE_RIGHT_OF_ANCHOR = 15.0
SCORE_BELOW_ANCHOR = 10.0

# No anchor was found at all; the value was recovered from a
# distinctive-format, whole-document scan (GSTIN) or a pure-geometry
# heuristic (vendor name). Trusted far less than any anchor hit.
SCORE_NEAREST_FALLBACK = 30.0
SCORE_WHOLE_DOC_FALLBACK = -5.0

PENALTY_NEAR_BUYER = -20.0
PENALTY_NEAR_SHIP_TO = -20.0
PENALTY_INSIDE_TABLE = -15.0
PENALTY_INVALID_FORMAT = -30.0

# Under PREFER_BUYER polarity (buyer_gstin), a Ship-To/consignee
# association is a weaker signal than an actual Buyer/Bill-To heading:
# the consignee receiving goods is not necessarily the same legal
# entity as the buyer being billed, so a ship-to GSTIN must never
# fully tie with — and outrank on a technicality — the real buyer's.
BONUS_NEAR_SHIP_TO_AS_BUYER = 8.0

MIN_ACCEPT_SCORE = 15.0


def confidence_from_score(score: float) -> float:
    """Clamp a raw point score into a 0-98 confidence percentage.

    98 (never 100) reflects that this is a heuristic rule-based read,
    not a verified value.
    """
    return max(0.0, min(98.0, round(score, 2)))
