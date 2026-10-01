# Backend/tests/test_tds_rate_condition.py
"""Unit tests for the TDS rate-condition grammar and rule-variant selection
(Business_Layer/utils/tds_rate_condition.py). Pure functions - no DB."""
from __future__ import annotations

import pytest

from Backend.Business_Layer.utils.tds_rate_condition import (
    RateCondition,
    match_specificity,
    parse_rate_condition,
    rate_conditions_from_rows,
    render_rate_condition,
    select_rule_variant,
)
from Backend.Data_Access_Layer.models.master import TaxRule, TaxRuleCondition


def _cond(condition_type, operator, value, group=1, seq=2):
    return TaxRuleCondition(condition_type=condition_type, operator=operator, condition_value=value, logical_group=group, sequence_no=seq)


def _rule(rule_id, *conditions, priority=100):
    rule = TaxRule(tax_rule_id=rule_id, rule_code=f"R{rule_id}", priority=priority)
    rule.conditions = [_cond("PAYMENT_NATURE", "EQUALS", "CONTRACTOR", seq=1), *conditions]
    return rule


# ---------------------------------------------------------------------------
# parse / render
# ---------------------------------------------------------------------------

def test_blank_rate_condition_means_no_condition():
    assert parse_rate_condition(None) == []
    assert parse_rate_condition("   ") == []
    assert render_rate_condition([]) is None


def test_parse_is_canonical_uppercase_sorted_and_deduplicated():
    parsed = parse_rate_condition("entity_type in huf, Individual ,HUF")
    assert parsed == [RateCondition("ENTITY_TYPE", "IN", ("HUF", "INDIVIDUAL"))]
    assert render_rate_condition(parsed) == "ENTITY_TYPE IN HUF,INDIVIDUAL"


def test_parse_multiple_clauses_and_operator_aliases():
    parsed = parse_rate_condition("RESIDENCY_TYPE = RESIDENT and ENTITY_TYPE not in INDIVIDUAL,HUF")
    assert render_rate_condition(parsed) == "ENTITY_TYPE NOT_IN HUF,INDIVIDUAL AND RESIDENCY_TYPE EQUALS RESIDENT"


def test_round_trip_through_condition_rows():
    parsed = parse_rate_condition("ENTITY_TYPE NOT_IN INDIVIDUAL,HUF")
    rows = [_cond(c.condition_type, c.operator, c.condition_value) for c in parsed]
    rows.append(_cond("PAYMENT_NATURE", "EQUALS", "CONTRACTOR", seq=1))
    assert render_rate_condition(rate_conditions_from_rows(rows)) == "ENTITY_TYPE NOT_IN HUF,INDIVIDUAL"


@pytest.mark.parametrize("text, message", [
    ("ASSET_CLASS EQUALS PLANT", "not supported"),
    ("ENTITY_TYPE LIKE COMPANY", "not in the form"),
    ("ENTITY_TYPE EQUALS COMPANY,HUF", "exactly one value"),
    ("ENTITY_TYPE IN ALIEN", "Invalid ENTITY_TYPE"),
    ("RESIDENCY_TYPE EQUALS MARS", "Invalid RESIDENCY_TYPE"),
    ("ENTITY_TYPE IN HUF AND ENTITY_TYPE IN COMPANY", "more than once"),
    ("garbage", "not in the form"),
])
def test_invalid_rate_conditions_are_rejected(text, message):
    with pytest.raises(ValueError, match=message):
        parse_rate_condition(text)


# ---------------------------------------------------------------------------
# evaluation / variant selection
# ---------------------------------------------------------------------------

def test_rule_without_rate_condition_matches_everyone_with_specificity_zero():
    assert match_specificity(_rule(1).conditions, {"ENTITY_TYPE": "COMPANY"}) == 0


def test_in_and_not_in_evaluate_against_vendor_facts():
    individual = _rule(1, _cond("ENTITY_TYPE", "IN", "HUF,INDIVIDUAL"))
    other = _rule(2, _cond("ENTITY_TYPE", "NOT_IN", "HUF,INDIVIDUAL"))
    assert match_specificity(individual.conditions, {"ENTITY_TYPE": "INDIVIDUAL"}) == 1
    assert match_specificity(individual.conditions, {"ENTITY_TYPE": "COMPANY"}) is None
    assert match_specificity(other.conditions, {"ENTITY_TYPE": "COMPANY"}) == 1
    assert match_specificity(other.conditions, {"ENTITY_TYPE": "HUF"}) is None


def test_unknown_vendor_fact_never_matches_either_way():
    individual = _rule(1, _cond("ENTITY_TYPE", "IN", "HUF,INDIVIDUAL"))
    other = _rule(2, _cond("ENTITY_TYPE", "NOT_IN", "HUF,INDIVIDUAL"))
    assert match_specificity(individual.conditions, {"ENTITY_TYPE": None}) is None
    assert match_specificity(other.conditions, {"ENTITY_TYPE": None}) is None


def test_unsupported_condition_type_fails_closed():
    rule = _rule(1, _cond("SAC", "EQUALS", "997331"))
    assert match_specificity(rule.conditions, {"ENTITY_TYPE": "COMPANY"}) is None


def test_logical_groups_are_ored():
    rule = _rule(
        1,
        _cond("ENTITY_TYPE", "EQUALS", "INDIVIDUAL", group=1),
        _cond("ENTITY_TYPE", "EQUALS", "HUF", group=2),
    )
    assert match_specificity(rule.conditions, {"ENTITY_TYPE": "HUF"}) == 1
    assert match_specificity(rule.conditions, {"ENTITY_TYPE": "COMPANY"}) is None


def test_most_specific_variant_wins_over_catch_all():
    catch_all = _rule(1)
    individual = _rule(2, _cond("ENTITY_TYPE", "IN", "HUF,INDIVIDUAL"))
    chosen, _ = select_rule_variant([catch_all, individual], {"ENTITY_TYPE": "INDIVIDUAL"})
    assert chosen is individual
    chosen, _ = select_rule_variant([catch_all, individual], {"ENTITY_TYPE": "COMPANY"})
    assert chosen is catch_all


def test_explicit_priority_beats_specificity():
    catch_all = _rule(1, priority=10)
    individual = _rule(2, _cond("ENTITY_TYPE", "IN", "HUF,INDIVIDUAL"), priority=100)
    chosen, _ = select_rule_variant([individual, catch_all], {"ENTITY_TYPE": "INDIVIDUAL"})
    assert chosen is catch_all


def test_no_variant_matches_returns_unmatched_for_explanation():
    individual = _rule(1, _cond("ENTITY_TYPE", "IN", "HUF,INDIVIDUAL"))
    chosen, unmatched = select_rule_variant([individual], {"ENTITY_TYPE": "COMPANY"})
    assert chosen is None
    assert unmatched == [individual]


def test_tie_is_broken_deterministically_by_rule_id():
    a = _rule(5)
    b = _rule(3)
    chosen, _ = select_rule_variant([a, b], {})
    assert chosen is b
