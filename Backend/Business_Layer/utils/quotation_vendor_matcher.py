# Backend/Business_Layer/utils/quotation_vendor_matcher.py

"""
Vendor resolution utilities for quotation extraction.

Resolves an extracted quotation vendor name to an existing Vendor
Master record.

Important:
    - This module is READ-ONLY.
    - It never creates or modifies a vendor.
    - Matching is performed using:
        1. Exact database name match
        2. Normalized name match
        3. Legal-suffix-normalized match
        4. Token-overlap fuzzy match
    - Ambiguous/weak fuzzy matches are rejected instead of guessing.

The pure matching functions are independently testable and do not
require a database session.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from Backend.Data_Access_Layer.dao.vendor_dao import VendorDAO


# ============================================================
# Confidence levels
# ============================================================

EXACT_MATCH_CONFIDENCE = 100.0
NORMALIZED_MATCH_CONFIDENCE = 95.0
LEGAL_SUFFIX_MATCH_CONFIDENCE = 90.0

FUZZY_MATCH_MIN_CONFIDENCE = 75.0
FUZZY_MATCH_MAX_CONFIDENCE = 95.0

# Minimum fraction of the shorter vendor name's significant tokens
# that must be present in the longer name.
FUZZY_MIN_OVERLAP_RATIO = 0.80

# Minimum confidence gap between the best and second-best fuzzy
# candidates. If candidates are too close, do not guess.
FUZZY_MIN_CONFIDENCE_GAP = 5.0


# ============================================================
# Legal entity suffixes
# ============================================================

_LEGAL_SUFFIX_WORDS = {
    "private",
    "limited",
    "pvt",
    "ltd",
    "public",
    "llp",
    "llc",
    "inc",
    "incorporated",
    "corporation",
    "corp",
    "company",
    "co",
}


# ============================================================
# Regex helpers
# ============================================================

_NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9\s]")

_MULTI_SPACE_PATTERN = re.compile(r"\s+")


# ============================================================
# Result model
# ============================================================

@dataclass(frozen=True)
class VendorMatchResult:
    vendor_id: Optional[int]
    vendor_name: Optional[str]
    confidence: float


# ============================================================
# Name normalization
# ============================================================

def normalize_vendor_name(name: str) -> str:
    """
    Basic vendor-name normalization.

    Examples:

        "ABC Technologies Pvt Ltd"
            ->
        "abc technologies pvt ltd"

        "  ABC   Technologies   Pvt Ltd  "
            ->
        "abc technologies pvt ltd"
    """

    if not name:
        return ""

    return " ".join(
        str(name).strip().casefold().split()
    )


def _normalize_for_comparison(name: str) -> str:
    """
    Stronger normalization used for matching.

    Removes punctuation while preserving word boundaries.

    Example:

        "A.B.C. Technologies Pvt. Ltd."
            ->
        "a b c technologies pvt ltd"
    """

    normalized = normalize_vendor_name(name)

    if not normalized:
        return ""

    cleaned = _NON_ALNUM_PATTERN.sub(" ", normalized)

    return _MULTI_SPACE_PATTERN.sub(
        " ",
        cleaned,
    ).strip()


def _strip_legal_suffix_words(name: str) -> str:
    """
    Removes trailing legal-entity words.

    Examples:

        "abc technologies pvt ltd"
            ->
        "abc technologies"

        "abc technologies private limited"
            ->
        "abc technologies"

        "abc technologies llp"
            ->
        "abc technologies"
    """

    tokens = _normalize_for_comparison(name).split()

    while tokens and tokens[-1] in _LEGAL_SUFFIX_WORDS:
        tokens.pop()

    return " ".join(tokens)


def names_match_normalized(
    name_a: str,
    name_b: str,
) -> bool:
    """
    Returns True when vendor names match after normalization.

    Handles:

        Case differences
        Whitespace differences
        Punctuation differences
        Legal-entity suffix differences
    """

    normalized_a = _normalize_for_comparison(name_a)
    normalized_b = _normalize_for_comparison(name_b)

    if not normalized_a or not normalized_b:
        return False

    # Strong normalized equality.
    if normalized_a == normalized_b:
        return True

    # Compare without legal suffixes.
    stripped_a = _strip_legal_suffix_words(normalized_a)
    stripped_b = _strip_legal_suffix_words(normalized_b)

    return (
        bool(stripped_a)
        and bool(stripped_b)
        and stripped_a == stripped_b
    )


# ============================================================
# Token matching
# ============================================================

def _name_tokens(name: str) -> set[str]:
    """
    Returns significant vendor-name tokens.

    Legal-entity words are ignored for fuzzy matching because:

        Pvt
        Ltd
        Private
        Limited
        LLP
        etc.

    do not identify the actual vendor.
    """

    normalized = _normalize_for_comparison(name)

    if not normalized:
        return set()

    return {
        token
        for token in normalized.split()
        if len(token) > 1
        and token not in _LEGAL_SUFFIX_WORDS
    }


def name_overlap_ratio(
    name_a: str,
    name_b: str,
) -> float:
    """
    Fraction of the shorter vendor name's significant tokens that
    also occur in the longer vendor name.

    Returns 0.0 when either name has no significant tokens.
    """

    tokens_a = _name_tokens(name_a)
    tokens_b = _name_tokens(name_b)

    if not tokens_a or not tokens_b:
        return 0.0

    shorter, longer = sorted(
        [tokens_a, tokens_b],
        key=len,
    )

    return len(shorter & longer) / len(shorter)


# ============================================================
# Pure matching core
# ============================================================

def find_best_match(
    extracted_name: str,
    candidates: Sequence[Tuple[int, str]],
) -> Optional[Tuple[int, str, float]]:
    """
    Pure matching core.

    Matching order:

        1. Normalized exact match
        2. Legal-suffix-normalized match
        3. Token-overlap fuzzy match

    Returns:

        (vendor_id, vendor_name, confidence)

    or None when no safe match exists.

    Ambiguous fuzzy matches are deliberately rejected.
    """

    if not extracted_name or not extracted_name.strip():
        return None

    cleaned_extracted_name = extracted_name.strip()

    # --------------------------------------------------------
    # First pass: normalized exact match
    # --------------------------------------------------------

    extracted_normalized = _normalize_for_comparison(
        cleaned_extracted_name
    )

    for candidate_id, candidate_name in candidates:
        candidate_normalized = _normalize_for_comparison(
            candidate_name
        )

        if (
            extracted_normalized
            and extracted_normalized == candidate_normalized
        ):
            return (
                candidate_id,
                candidate_name,
                NORMALIZED_MATCH_CONFIDENCE,
            )

    # --------------------------------------------------------
    # Second pass: legal suffix normalized match
    # --------------------------------------------------------

    extracted_without_suffix = _strip_legal_suffix_words(
        extracted_normalized
    )

    if extracted_without_suffix:
        for candidate_id, candidate_name in candidates:
            candidate_without_suffix = _strip_legal_suffix_words(
                candidate_name
            )

            if (
                candidate_without_suffix
                and extracted_without_suffix
                == candidate_without_suffix
            ):
                return (
                    candidate_id,
                    candidate_name,
                    LEGAL_SUFFIX_MATCH_CONFIDENCE,
                )

    # --------------------------------------------------------
    # Third pass: fuzzy token overlap
    # --------------------------------------------------------

    fuzzy_candidates: List[
        Tuple[int, str, float, float]
    ] = []

    for candidate_id, candidate_name in candidates:

        overlap = name_overlap_ratio(
            cleaned_extracted_name,
            candidate_name,
        )

        if overlap < FUZZY_MIN_OVERLAP_RATIO:
            continue

        confidence = round(
            min(
                FUZZY_MATCH_MAX_CONFIDENCE,
                FUZZY_MATCH_MIN_CONFIDENCE
                + (
                    overlap
                    - FUZZY_MIN_OVERLAP_RATIO
                )
                * 100,
            ),
            2,
        )

        fuzzy_candidates.append(
            (
                candidate_id,
                candidate_name,
                confidence,
                overlap,
            )
        )

    if not fuzzy_candidates:
        return None

    # Highest confidence first.
    fuzzy_candidates.sort(
        key=lambda item: item[2],
        reverse=True,
    )

    best = fuzzy_candidates[0]

    # --------------------------------------------------------
    # Ambiguity protection
    # --------------------------------------------------------

    if len(fuzzy_candidates) > 1:

        second_best = fuzzy_candidates[1]

        confidence_gap = (
            best[2] - second_best[2]
        )

        if confidence_gap < FUZZY_MIN_CONFIDENCE_GAP:
            return None

    return (
        best[0],
        best[1],
        best[2],
    )


# ============================================================
# Database search anchor
# ============================================================

def _search_term(name: str) -> Optional[str]:
    """
    Returns the first meaningful token to use as the DAO search
    anchor.

    Legal-entity words and very short tokens are ignored.

    Example:

        "ABC Technologies Private Limited"
            ->
        "abc"

        "Amazon Web Services India Private Limited"
            ->
        "amazon"
    """

    tokens = _name_tokens(name)

    if not tokens:
        return None

    normalized_tokens = _normalize_for_comparison(name).split()

    for token in normalized_tokens:
        if (
            len(token) >= 3
            and token in tokens
        ):
            return token

    return None


# ============================================================
# Database-backed vendor matching
# ============================================================

def match_vendor(
    vendor_name: Optional[str],
    db: Session,
) -> VendorMatchResult:
    """
    Resolves an extracted quotation vendor name against Vendor Master.

    READ-ONLY:
        This function never creates or updates a vendor.

    Matching ladder:

        1. Exact DB name
        2. Normalized name
        3. Legal suffix normalized
        4. Fuzzy token overlap

    If no safe match is found, vendor_id is None while the original
    extracted vendor_name is preserved.
    """

    if not vendor_name or not vendor_name.strip():
        return VendorMatchResult(
            vendor_id=None,
            vendor_name=None,
            confidence=0.0,
        )

    cleaned_name = vendor_name.strip()

    vendor_dao = VendorDAO(db)

    # --------------------------------------------------------
    # 1. Exact DB lookup
    # --------------------------------------------------------

    exact = vendor_dao.get_vendor_by_name(
        cleaned_name
    )

    if exact is not None:
        return VendorMatchResult(
            vendor_id=exact.vendor_id,
            vendor_name=exact.vendor_name,
            confidence=EXACT_MATCH_CONFIDENCE,
        )

    # --------------------------------------------------------
    # 2. Candidate search
    # --------------------------------------------------------

    search_term = _search_term(
        cleaned_name
    )

    candidates: List[
        Tuple[int, str]
    ] = []

    if search_term:

        vendors = vendor_dao.get_all_vendors(
            search=search_term,
            limit=50,
        )

        candidates = [
            (
                vendor.vendor_id,
                vendor.vendor_name,
            )
            for vendor in vendors
            if vendor.vendor_id is not None
            and vendor.vendor_name
        ]

    # --------------------------------------------------------
    # 3. Pure matching
    # --------------------------------------------------------

    match = find_best_match(
        cleaned_name,
        candidates,
    )

    if match is None:
        return VendorMatchResult(
            vendor_id=None,
            vendor_name=cleaned_name,
            confidence=0.0,
        )

    matched_id, matched_name, confidence = match

    return VendorMatchResult(
        vendor_id=matched_id,
        vendor_name=matched_name,
        confidence=confidence,
    )