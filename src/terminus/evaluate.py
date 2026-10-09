from dataclasses import dataclass

CONFORMING = "conforming"
NONCONFORMING = "nonconforming"
INCONCLUSIVE = "inconclusive"
ALL_CASES_CONFORM = "all_cases_conform"


@dataclass(frozen=True)
class Measurement:
    digest: str
    case: str
    value: float
    uncertainty: float
    admissible: bool
    reason: str
    consulted: tuple = ()


@dataclass
class Evaluation:
    status: str
    established_scope: list
    reasons: list
    support: list
    refutations: list
    notes: list


def _bounds(predicate: dict):
    operator = predicate["operator"]
    if operator == "le":
        lower, upper = None, predicate.get("limit")
    elif operator == "ge":
        lower, upper = predicate.get("limit"), None
    elif operator == "between":
        lower, upper = predicate.get("lower"), predicate.get("upper")
    else:
        raise ValueError(f"unknown operator {operator!r}")
    missing = (lower is None or upper is None) if operator == "between" else (lower is None and upper is None)
    if missing:
        raise ValueError(f"predicate {predicate!r} is missing its limits")
    return lower, upper


def classify(value: float, uncertainty: float, predicate: dict, decision_rule: dict) -> str:
    lower, upper = _bounds(predicate)
    if uncertainty < 0 or (uncertainty == 0 and not decision_rule["allow_zero_uncertainty"]):
        return INCONCLUSIVE
    low, high = value - uncertainty, value + uncertainty
    if (upper is not None and low > upper) or (lower is not None and high < lower):
        return NONCONFORMING
    if (upper is None or high <= upper) and (lower is None or low >= lower):
        return CONFORMING
    return INCONCLUSIVE


def evaluate(requirement: dict, measurements: list, inference_patterns: list) -> Evaluation:
    cases = list(requirement["cases"])
    by_case = {case: [] for case in cases}
    for measurement in measurements:
        if measurement.case in by_case:
            by_case[measurement.case].append(measurement)
    reasons, refutations, conforming, notes = [], [], {}, []
    for case in cases:
        found = by_case[case]
        admissible = [x for x in found if x.admissible]
        if not found:
            reasons.append((case, "no measurement"))
            continue
        if not admissible:
            reasons.append((case, "inadmissible: " + "; ".join(sorted({x.reason for x in found}))))
            continue
        findings = {
            x.digest: classify(x.value, x.uncertainty, requirement["predicate"], requirement["decision_rule"])
            for x in admissible
        }
        bad = sorted(d for d, finding in findings.items() if finding == NONCONFORMING)
        good = sorted(d for d, finding in findings.items() if finding == CONFORMING)
        if bad:
            refutations.append((case, bad[0]))
            reasons.append((case, NONCONFORMING))
        elif good:
            conforming[case] = good
            reasons.append((case, CONFORMING))
        else:
            reasons.append((case, INCONCLUSIVE))
    established = [case for case in cases if case in conforming]
    complete = bool(cases) and len(established) == len(cases)
    if not cases:
        notes.append("requirement lists no cases")
    if refutations:
        status = "FAILED"
    elif complete and ALL_CASES_CONFORM in inference_patterns:
        status = "SUPPORTED"
    else:
        status = "NOT_ESTABLISHED"
        if complete:
            notes.append("all cases conform, but the scheme does not admit the all_cases_conform pattern")
    support = sorted(d for case in established for d in conforming[case]) if status == "SUPPORTED" else []
    return Evaluation(status, established, reasons, support, refutations, notes)
