import pytest

from terminus.evaluate import CONFORMING, INCONCLUSIVE, NONCONFORMING, Measurement, classify, evaluate

LE = {"operator": "le", "limit": 0.05}
RULE = {"type": "guard_band", "allow_zero_uncertainty": False}
REQ = {"id": "r", "measurand": "x", "predicate": LE, "quantifier": "enumerated", "cases": ["A", "B"], "decision_rule": RULE}
PATTERNS = ["all_cases_conform"]


def m(case, value, u=0.01, admissible=True, reason=""):
    return Measurement(f"m-{case}-{value}", case, value, u, admissible, reason)


@pytest.mark.parametrize("value, u, expected", [
    (0.03, 0.01, CONFORMING),
    (0.039, 0.01, CONFORMING),
    (0.045, 0.01, INCONCLUSIVE),
    (0.055, 0.01, INCONCLUSIVE),
    (0.07, 0.01, NONCONFORMING),
    (0.03, 0.0, INCONCLUSIVE),
    (0.03, -0.01, INCONCLUSIVE),
])
def test_guard_band_upper_limit(value, u, expected):
    assert classify(value, u, LE, RULE) == expected


def test_zero_uncertainty_when_the_scheme_allows_it():
    assert classify(0.05, 0.0, LE, {**RULE, "allow_zero_uncertainty": True}) == CONFORMING


def test_lower_limit_and_interval():
    ge = {"operator": "ge", "limit": 1.0}
    assert classify(1.2, 0.1, ge, RULE) == CONFORMING
    assert classify(0.8, 0.1, ge, RULE) == NONCONFORMING
    between = {"operator": "between", "lower": 0.0, "upper": 1.0}
    assert classify(0.5, 0.1, between, RULE) == CONFORMING
    assert classify(1.5, 0.1, between, RULE) == NONCONFORMING
    assert classify(0.95, 0.1, between, RULE) == INCONCLUSIVE


@pytest.mark.parametrize("predicate", [
    {"operator": "between", "lower": 0.0},
    {"operator": "le"},
    {"operator": "eq", "limit": 1.0},
])
def test_malformed_predicates(predicate):
    with pytest.raises(ValueError):
        classify(1.0, 0.1, predicate, RULE)


def test_all_cases_conform_is_supported():
    result = evaluate(REQ, [m("A", 0.01), m("B", 0.02)], PATTERNS)
    assert result.status == "SUPPORTED"
    assert result.established_scope == ["A", "B"]
    assert result.support == ["m-A-0.01", "m-B-0.02"]
    assert result.refutations == []


def test_one_counterexample_fails_even_with_support():
    result = evaluate(REQ, [m("A", 0.01), m("A", 0.09), m("B", 0.02)], PATTERNS)
    assert result.status == "FAILED"
    assert result.refutations == [("A", "m-A-0.09")]
    assert result.support == []


def test_missing_case_is_not_established():
    result = evaluate(REQ, [m("A", 0.01)], PATTERNS)
    assert result.status == "NOT_ESTABLISHED"
    assert result.established_scope == ["A"]
    assert ("B", "no measurement") in result.reasons


def test_inconclusive_is_not_failed():
    result = evaluate(REQ, [m("A", 0.01), m("B", 0.045)], PATTERNS)
    assert result.status == "NOT_ESTABLISHED"
    assert ("B", INCONCLUSIVE) in result.reasons


def test_inadmissible_evidence_counts_for_nothing():
    bad = m("B", 0.09, admissible=False, reason="realization material is unsupported")
    result = evaluate(REQ, [m("A", 0.01), bad], PATTERNS)
    assert result.status == "NOT_ESTABLISHED"
    assert ("B", "inadmissible: realization material is unsupported") in result.reasons


def test_pattern_not_admitted_by_the_scheme():
    result = evaluate(REQ, [m("A", 0.01), m("B", 0.02)], [])
    assert result.status == "NOT_ESTABLISHED"
    assert any("all_cases_conform" in note for note in result.notes)


def test_requirement_without_cases_is_never_supported():
    result = evaluate({**REQ, "cases": []}, [], PATTERNS)
    assert result.status == "NOT_ESTABLISHED"
    assert result.notes == ["requirement lists no cases"]


def test_measurements_for_other_cases_are_ignored():
    result = evaluate(REQ, [m("A", 0.01), m("B", 0.01), m("Z", 0.9)], PATTERNS)
    assert result.status == "SUPPORTED"
