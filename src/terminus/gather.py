import pint

from terminus.evaluate import Measurement

UNITS = pint.UnitRegistry()


def unit_problem(unit: str):
    try:
        UNITS.Quantity(1.0, unit)
    except Exception as error:
        return f"unit {unit!r} cannot be parsed: {error}"
    return None


def _convert(value: float, uncertainty: float, unit: str, target: str):
    try:
        converted = UNITS.Quantity(value, unit).to(target).magnitude
        spread = UNITS.Quantity(uncertainty, unit).to(target).magnitude
    except Exception:
        return value, uncertainty, f"unit {unit!r} cannot be converted to {target!r}"
    return float(converted), float(spread), None


def _realization_reason(realization, case: dict, policy: dict):
    if realization is None:
        return "no realization record"
    allowed = {"exact"} | ({"approximate"} if policy["accept_approximate"] else set())
    for facet in ("physical", "material", "observation"):
        fidelity = realization["facets"][facet]
        if fidelity in allowed:
            continue
        if facet == "material" and fidelity == "model_dependent" and case["purpose"] == "validation":
            continue
        return f"realization {facet} is {fidelity}"
    return None


def _provenance_reason(store, observations_digest: str, result: dict, case: dict, policy: dict):
    observations = store.get(observations_digest)
    execution = store.get(observations["execution"])
    realizations = store.find("realization", execution=observations["execution"])
    consulted = {observations_digest, observations["execution"], execution["adapter"], *(d for d, _ in realizations)}
    for field in ("case", "artifact"):
        if execution[field] != result[field]:
            return f"measurement {field} does not match its execution", consulted
    if execution["outcome"] != "succeeded":
        return f"execution outcome {execution['outcome']}", consulted
    if len(realizations) > 1:
        return "conflicting realization records", consulted
    reason = _realization_reason(realizations[0][1] if realizations else None, case, policy)
    if reason:
        return reason, consulted
    adapter = store.get(execution["adapter"])
    artifact = store.get(execution["artifact"])
    if adapter["publisher"] == artifact["publisher"] and not policy["first_party_allowed"]:
        return "first-party adapter not accepted by the scheme", consulted
    return None, consulted


def gather(store, scheme: dict, requirement: dict, artifact_digest: str) -> list:
    measurand = store.get(requirement["measurand"])
    policy = scheme["adapter_policy"]
    calibrations = [d for d, _ in store.find("calibration", target_artifact=artifact_digest)]
    calibrated = {item for d in calibrations for item in store.get(d)["data"]}
    found = []
    for digest, result in store.find("measurement_result", measurand=requirement["measurand"], artifact=artifact_digest):
        if result["case"] not in requirement["cases"]:
            continue
        case = store.get(result["case"])
        consulted = set(calibrations)
        sources = [d for d in result["was_derived_from"] if store.has(d) and store.get(d)["kind"] == "observations"]
        if sources:
            reason, seen = _provenance_reason(store, sources[0], result, case, policy)
            consulted |= seen
        else:
            reason = "not derived from observations"
        overlap = sorted(calibrated & set(result.get("reference_data", [])))
        if reason is None and overlap:
            reason = f"reference data {overlap[0]} was used in calibration"
        value, uncertainty, unit_reason = _convert(result["value"], result["uncertainty"], result["unit"], measurand["unit"])
        reason = reason or unit_reason
        found.append(Measurement(digest, result["case"], value, uncertainty, reason is None, reason or "", tuple(sorted(consulted))))
    return found
