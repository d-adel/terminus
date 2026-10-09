def _label(store, case: str) -> str:
    obj = store.get(case)
    return f"{obj['name']}@{obj['version']}"


def _children(store, determination: dict) -> list:
    return [store.get(r["claim"]) for r in determination["reasons"] if "claim" in r]


def _measurement_digests(store, determination: dict) -> set:
    found = set()
    for digest in determination["used"]:
        if store.has(digest) and store.get(digest)["kind"] == "measurement_result":
            found.add(digest)
    for child in _children(store, determination):
        found |= _measurement_digests(store, child)
    return found


def _measured(store, determination: dict) -> dict:
    found = {}
    for digest in _measurement_digests(store, determination):
        obj = store.get(digest)
        found.setdefault(obj["case"], []).append((obj["value"], obj["uncertainty"], obj["unit"]))
    return {case: sorted(values) for case, values in found.items()}


def _witnesses(store, determination: dict) -> set:
    found = set()
    for digest in determination["arguments"]:
        argument = store.get(digest)
        if argument["role"] != "refutes":
            continue
        if argument["pattern"] == "all_of":
            found |= _witnesses(store, store.get(argument["witness"]))
        else:
            found.add(argument["witness"])
    return found


def _format(values) -> str:
    if not values:
        return "none"
    return ", ".join(f"{value:.6g} ± {spread:.2g} {unit}" for value, spread, unit in values)


def diff(store, a: str, b: str) -> list:
    first, second = store.get(a), store.get(b)
    changes = []
    if first["status"] != second["status"]:
        changes.append(f"status {first['status']} -> {second['status']}")
    def _reason_label(reason):
        if "claim" in reason:
            return store.get(store.get(reason["claim"])["claim"])["requirement"]
        return _label(store, reason["case"])

    before = {_reason_label(r): r["finding"] for r in first["reasons"]}
    after = {_reason_label(r): r["finding"] for r in second["reasons"]}
    for label in sorted(set(before) | set(after)):
        if before.get(label) != after.get(label):
            changes.append(f"{label}: {before.get(label, 'absent')} -> {after.get(label, 'absent')}")
    measured_before, measured_after = _measured(store, first), _measured(store, second)
    for case in sorted(set(measured_before) | set(measured_after)):
        if measured_before.get(case) != measured_after.get(case):
            changes.append(f"{_label(store, case)}: measured {_format(measured_before.get(case))} -> {_format(measured_after.get(case))}")
    for case in sorted(_witnesses(store, second) - _witnesses(store, first)):
        changes.append(f"new counterexample: {_label(store, case)}")
    return changes
