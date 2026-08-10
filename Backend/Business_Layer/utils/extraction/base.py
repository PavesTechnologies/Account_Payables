# Backend/Business_Layer/utils/extraction/base.py
"""Shared candidate model and extractor base class.

Every field extractor follows the same two-step pipeline: collect
every plausible candidate first (never stop at the first match), then
rank them with one shared point-based scorer. Subclasses only
implement ``collect_candidates`` — ranking, confidence, and the
``FieldExtractionMeta`` contract live here once, so adding a new field
never means touching this file.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Optional

from Backend.API_Layer.interface.invoice_process_interface import DocumentResult, FieldExtractionMeta
from Backend.Business_Layer.utils.extraction import geometry, scoring

# Candidate.relation values
SAME_LINE = "SAME_LINE"
BELOW = "BELOW"
NEAREST = "NEAREST"
FALLBACK = "FALLBACK"

# Candidate.context_polarity values
AVOID_BUYER = "AVOID_BUYER"
PREFER_BUYER = "PREFER_BUYER"

_RELATION_POINTS = {
    SAME_LINE: scoring.SCORE_SAME_LINE + scoring.SCORE_RIGHT_OF_ANCHOR,
    BELOW: scoring.SCORE_BELOW_ANCHOR,
    NEAREST: scoring.SCORE_NEAREST_FALLBACK,
    FALLBACK: scoring.SCORE_WHOLE_DOC_FALLBACK,
}


@dataclass
class Candidate:
    """One plausible value for a field, before ranking.

    ``value`` must already be the correctly-typed parsed value (a
    ``date``/``Decimal``/``str``) or ``None`` when parsing failed —
    :meth:`BaseFieldExtractor.extract` never returns a candidate whose
    value is ``None``, no matter how it scores.
    """

    value: Any
    raw_text: str
    page_number: int
    line: Optional[geometry.Line] = None
    anchor_text: Optional[str] = None
    has_anchor: bool = True
    relation: str = SAME_LINE
    valid_format: bool = True
    near_buyer: bool = False
    near_ship_to: bool = False
    near_seller: bool = False
    inside_table: bool = False
    context_polarity: str = AVOID_BUYER
    # Which anchor occurrence (line) this candidate came from, when it
    # differs from ``line`` (e.g. a BELOW candidate's value sits on a
    # different line than the label it belongs to). Lets callers group
    # a SAME_LINE and a BELOW candidate that both trace back to the
    # same labelled occurrence, instead of treating them as two
    # independent tax-slab occurrences. ``None`` when not applicable.
    anchor_line_index: Optional[int] = None
    # Free-form adjustment for domain-specific signals (company suffix,
    # top-of-page position, GSTIN checksum, ...) that don't fit the
    # generic anchor/relation/context categories below. This is the
    # engine's extensibility point: new nuance lives here, never in
    # score_candidate() itself.
    score_bonus: float = 0.0
    score: float = 0.0
    method_tags: List[str] = field(default_factory=list)


def score_candidate(candidate: Candidate) -> float:
    """Apply the shared point system to one candidate and tag how it was found."""
    points = scoring.SCORE_NEAR_ANCHOR if candidate.has_anchor else 0.0
    points += _RELATION_POINTS.get(candidate.relation, 0.0)

    if candidate.context_polarity == PREFER_BUYER:
        if candidate.near_buyer:
            points -= scoring.PENALTY_NEAR_BUYER
        elif candidate.near_ship_to:
            points += scoring.BONUS_NEAR_SHIP_TO_AS_BUYER
        if candidate.near_seller:
            points += scoring.PENALTY_NEAR_BUYER
    else:
        if candidate.near_buyer:
            points += scoring.PENALTY_NEAR_BUYER
        if candidate.near_ship_to:
            points += scoring.PENALTY_NEAR_SHIP_TO

    if candidate.inside_table:
        points += scoring.PENALTY_INSIDE_TABLE
    if not candidate.valid_format:
        points += scoring.PENALTY_INVALID_FORMAT

    points += candidate.score_bonus

    tags = [candidate.relation]
    if candidate.has_anchor:
        tags.append("ANCHOR")
    tags.append("GEOMETRY" if candidate.line is not None else "REGEX")
    candidate.method_tags = sorted(set(tags))

    return points


def rank_candidates(candidates: List[Candidate]) -> List[Candidate]:
    """Score every candidate and return them sorted highest-first."""
    for candidate in candidates:
        candidate.score = score_candidate(candidate)
    return sorted(candidates, key=lambda c: c.score, reverse=True)


class BaseFieldExtractor(ABC):
    """Base for every rule-based field extractor.

    Subclasses implement ``collect_candidates`` only; ranking and the
    output contract are shared here so every extractor behaves
    identically once candidates exist.
    """

    field_name: str = ""

    @abstractmethod
    def collect_candidates(self, document: DocumentResult) -> List[Candidate]:
        """Return every plausible candidate for this field. Never stop at the first match."""

    def extract_candidates(self, document: DocumentResult) -> List[Candidate]:
        """Every valid candidate for this field, ranked highest-first.

        Unlike :meth:`extract`, does not stop at the first acceptable
        candidate or apply ``MIN_ACCEPT_SCORE`` — used by cross-field
        reconciliation (see ``extraction.registry``) to consider
        alternates when the single best-ranked candidate contradicts
        another field's independently-extracted value.
        """
        candidates = self.collect_candidates(document)
        return [c for c in rank_candidates(candidates) if c.value is not None]

    def extract(self, document: DocumentResult) -> FieldExtractionMeta:
        candidates = self.collect_candidates(document)
        if not candidates:
            return FieldExtractionMeta()

        for candidate in rank_candidates(candidates):
            if candidate.value is None:
                continue
            if candidate.score < scoring.MIN_ACCEPT_SCORE:
                break
            return FieldExtractionMeta(
                value=candidate.value,
                confidence=scoring.confidence_from_score(candidate.score),
                matched_anchor=candidate.anchor_text,
                page=candidate.page_number,
                method="+".join(candidate.method_tags) or "NONE",
            )

        return FieldExtractionMeta()
