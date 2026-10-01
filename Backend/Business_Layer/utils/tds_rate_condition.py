# Backend/Business_Layer/utils/tds_rate_condition.py
"""TDS "Rate Condition" - the discriminator between variants of one legal
section (e.g. 194C Individual/HUF 1% vs. everyone else 2%).

Stored in the existing generic ap.tax_rule_condition table, never a separate
condition engine: a TDS rule variant is

    PAYMENT_NATURE EQUALS <code>          (sequence_no 1 - the "Nature of Payment")
    + zero or more rate conditions        (sequence_no 2..)

all in logical_group 1 (AND). Rows in different logical_groups are OR'ed,
so the table can express richer rules later without a schema change.

Text form (the frontend "Rate Condition" field and the Excel column) is one
or more clauses joined by AND:

    ENTITY_TYPE IN INDIVIDUAL,HUF
    ENTITY_TYPE NOT_IN INDIVIDUAL,HUF AND RESIDENCY_TYPE EQUALS RESIDENT

Blank means "no extra condition" (the rule applies to every vendor of that
payment nature). Only condition types the determination engine can actually
evaluate against a vendor's TDS profile are accepted - anything else is a
validation error, never silently ignored.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence

PAYMENT_NATURE_CONDITION_TYPE = "PAYMENT_NATURE"

# The 4th character of a valid Indian PAN encodes the holder's entity type
# (Income Tax Dept spec). Owned here so rate conditions and
# TDSDeterminationService's PAN-derived default use the same vocabulary.
ENTITY_TYPE_BY_PAN_CODE = {
    "P": "INDIVIDUAL",
    "C": "COMPANY",
    "H": "HUF",
    "F": "FIRM",
    "A": "AOP",
    "T": "TRUST",
    "B": "BOI",
    "L": "LOCAL_AUTHORITY",
    "J": "ARTIFICIAL_JURIDICAL_PERSON",
    "G": "GOVERNMENT",
}

RESIDENCY_TYPES = ("RESIDENT", "NON_RESIDENT")

# condition_type -> allowed values (VendorTdsProfile field of the same name).
SUPPORTED_CONDITION_VALUES: dict[str, frozenset[str]] = {
    "ENTITY_TYPE": frozenset(ENTITY_TYPE_BY_PAN_CODE.values()),
    "RESIDENCY_TYPE": frozenset(RESIDENCY_TYPES),
}

OPERATOR_EQUALS = "EQUALS"
OPERATOR_NOT_EQUALS = "NOT_EQUALS"
OPERATOR_IN = "IN"
OPERATOR_NOT_IN = "NOT_IN"
_SINGLE_VALUE_OPERATORS = {OPERATOR_EQUALS, OPERATOR_NOT_EQUALS}
_OPERATOR_ALIASES = {
    "EQUALS": OPERATOR_EQUALS, "=": OPERATOR_EQUALS, "==": OPERATOR_EQUALS,
    "NOT_EQUALS": OPERATOR_NOT_EQUALS, "!=": OPERATOR_NOT_EQUALS, "<>": OPERATOR_NOT_EQUALS,
    "IN": OPERATOR_IN,
    "NOT_IN": OPERATOR_NOT_IN, "NOT IN": OPERATOR_NOT_IN,
}

_AND_SPLIT = re.compile(r"\s+AND\s+", re.IGNORECASE)
_CLAUSE = re.compile(r"^\s*([A-Za-z_]+)\s+(NOT\s+IN|NOT_IN|NOT_EQUALS|EQUALS|IN|==|!=|<>|=)\s+(.+?)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class RateCondition:
    condition_type: str
    operator: str
    values: tuple[str, ...]

    @property
    def condition_value(self) -> str:
        return ",".join(self.values)

    def render(self) -> str:
        return f"{self.condition_type} {self.operator} {self.condition_value}"


def parse_rate_condition(text: Optional[str]) -> list[RateCondition]:
    """Parses the text form into canonical conditions (types/values upper-cased,
    values de-duplicated and sorted, clauses sorted by type). Raises ValueError
    with a user-facing message on anything the engine could not evaluate."""
    if text is None or not str(text).strip():
        return []

    conditions: list[RateCondition] = []
    seen_types: set[str] = set()
    for clause in _AND_SPLIT.split(str(text).strip()):
        match = _CLAUSE.match(clause)
        if not match:
            raise ValueError(
                f"Rate condition clause '{clause.strip()}' is not in the form "
                f"'<TYPE> <EQUALS|NOT_EQUALS|IN|NOT_IN> <VALUE[,VALUE...]>'"
            )
        condition_type = match.group(1).upper()
        operator = _OPERATOR_ALIASES[re.sub(r"\s+", " ", match.group(2).upper())]
        values = tuple(sorted({v.strip().upper().replace(" ", "_") for v in match.group(3).split(",") if v.strip()}))

        allowed = SUPPORTED_CONDITION_VALUES.get(condition_type)
        if allowed is None:
            raise ValueError(
                f"Rate condition type '{condition_type}' is not supported "
                f"(supported: {', '.join(sorted(SUPPORTED_CONDITION_VALUES))})"
            )
        if condition_type in seen_types:
            raise ValueError(f"Rate condition type '{condition_type}' is specified more than once")
        seen_types.add(condition_type)
        if not values:
            raise ValueError(f"Rate condition '{clause.strip()}' has no value")
        if operator in _SINGLE_VALUE_OPERATORS and len(values) != 1:
            raise ValueError(f"Operator {operator} takes exactly one value - use IN/NOT_IN for a list")
        invalid = [v for v in values if v not in allowed]
        if invalid:
            raise ValueError(
                f"Invalid {condition_type} value(s) {', '.join(invalid)} "
                f"(allowed: {', '.join(sorted(allowed))})"
            )
        conditions.append(RateCondition(condition_type, operator, values))

    return sorted(conditions, key=lambda c: c.condition_type)


def render_rate_condition(conditions: Iterable[RateCondition]) -> Optional[str]:
    rendered = [c.render() for c in sorted(conditions, key=lambda c: c.condition_type)]
    return " AND ".join(rendered) if rendered else None


def rate_conditions_from_rows(rows: Iterable) -> list[RateCondition]:
    """tax_rule_condition rows -> canonical RateConditions, excluding the
    PAYMENT_NATURE row (that's the rule's "Nature of Payment", not a rate
    condition). Used to render a stored rule back to text."""
    result = []
    for row in rows:
        if row.condition_type == PAYMENT_NATURE_CONDITION_TYPE:
            continue
        values = tuple(sorted(v.strip() for v in (row.condition_value or "").split(",") if v.strip()))
        result.append(RateCondition(row.condition_type, row.operator, values))
    return sorted(result, key=lambda c: c.condition_type)


def _condition_holds(condition_type: str, operator: str, raw_value: str, facts: Mapping[str, Optional[str]]) -> bool:
    if condition_type not in SUPPORTED_CONDITION_VALUES:
        # A condition this engine can't evaluate never matches (fail closed) -
        # it must not silently widen a rule to vendors it wasn't meant for.
        return False
    fact = facts.get(condition_type)
    if fact is None:
        # Unknown vendor fact: neither "is X" nor "is not X" can be asserted.
        return False
    fact = fact.upper()
    values = {v.strip().upper() for v in (raw_value or "").split(",") if v.strip()}
    if operator in (OPERATOR_EQUALS, OPERATOR_IN):
        return fact in values
    if operator in (OPERATOR_NOT_EQUALS, OPERATOR_NOT_IN):
        return fact not in values
    return False


def match_specificity(condition_rows: Sequence, facts: Mapping[str, Optional[str]]) -> Optional[int]:
    """None if the rule's rate conditions do not hold for these vendor facts,
    otherwise how many rate conditions the matching group had (0 = a
    catch-all variant). Groups (logical_group) are OR'ed, rows within a
    group AND'ed. PAYMENT_NATURE rows are ignored - the DAO already filtered
    candidates by payment nature."""
    groups: dict[int, list] = {}
    for row in condition_rows:
        if row.condition_type == PAYMENT_NATURE_CONDITION_TYPE:
            continue
        groups.setdefault(row.logical_group or 1, []).append(row)

    if not groups:
        return 0

    best: Optional[int] = None
    for rows in groups.values():
        if all(_condition_holds(r.condition_type, r.operator, r.condition_value, facts) for r in rows):
            best = max(best or 0, len(rows))
    return best


def select_rule_variant(rules: Sequence, facts: Mapping[str, Optional[str]]):
    """Picks the one applicable variant among candidate rules for a payment
    nature: lowest priority value first, then the most specific matching
    rate condition, then lowest tax_rule_id (deterministic). Returns
    (rule_or_None, [rules whose rate conditions did not match])."""
    matched = []
    unmatched = []
    for rule in rules:
        specificity = match_specificity(rule.conditions or [], facts)
        if specificity is None:
            unmatched.append(rule)
        else:
            matched.append((rule.priority if rule.priority is not None else 100, -specificity, rule.tax_rule_id or 0, rule))
    if not matched:
        return None, unmatched
    matched.sort(key=lambda item: item[:3])
    return matched[0][3], unmatched
