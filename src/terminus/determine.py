from terminus import __version__
from terminus.digest import digest_of
from terminus.evaluate import evaluate
from terminus.gather import gather
from terminus.sign import attest

EVALUATOR = {"name": "terminus", "version": __version__}


def _argument(publisher: str, claim: str, role: str, pattern: str, premises: list, witness=None) -> dict:
    argument = {
        "kind": "argument", "publisher": publisher, "claim": claim, "role": role, "pattern": pattern,
        "premises": premises, "author": publisher, "admissibility": "scheme",
    }
    if witness is not None:
        argument["witness"] = witness
    return argument


def _composite(store, publisher, scheme_digest, scheme, composite, artifact_digest, claim_digest, evaluator):
    produced, children = [], []
    for child_id in composite["all_of"]:
        child_claim, child_arguments, child_determination, child_produced = build(
            store, publisher, scheme_digest, child_id, artifact_digest, evaluator)
        produced += [*child_produced, child_claim, *child_arguments, child_determination]
        children.append((digest_of(child_determination), child_determination))
    statuses = [child["status"] for _, child in children]
    notes, arguments = [], []
    if "all_of" not in scheme["inference_patterns"]:
        status = "NOT_ESTABLISHED"
        notes.append("the scheme does not admit the all_of pattern")
    elif "FAILED" in statuses:
        status = "FAILED"
        witness = next(digest for digest, child in children if child["status"] == "FAILED")
        arguments.append(_argument(publisher, claim_digest, "refutes", "all_of", [witness], witness=witness))
    elif all(s == "SUPPORTED" for s in statuses):
        status = "SUPPORTED"
        arguments.append(_argument(publisher, claim_digest, "supports", "all_of", [d for d, _ in children]))
    else:
        status = "NOT_ESTABLISHED"
    requested = sorted({case for _, child in children for case in child["requested_scope"]})
    established = sorted({case for _, child in children for case in child["established_scope"]}) if status == "SUPPORTED" else []
    determination = {
        "kind": "determination", "publisher": publisher, "claim": claim_digest, "status": status,
        "requested_scope": requested, "established_scope": established,
        "arguments": [digest_of(a) for a in arguments],
        "used": sorted({scheme_digest, artifact_digest, *(d for d, _ in children)}),
        "reasons": [{"claim": digest, "finding": child["status"]} for digest, child in children],
        "notes": notes, "evaluator": evaluator,
    }
    return arguments, determination, produced


def build(store, publisher: str, scheme_digest: str, requirement_id: str, artifact_digest: str, evaluator=None):
    evaluator = evaluator or EVALUATOR
    scheme = store.get(scheme_digest)
    claim = {"kind": "claim", "publisher": publisher, "scheme": scheme_digest, "requirement": requirement_id, "artifact": artifact_digest}
    claim_digest = digest_of(claim)
    composite = next((c for c in scheme.get("claims", []) if c["id"] == requirement_id), None)
    if composite is not None:
        arguments, determination, produced = _composite(
            store, publisher, scheme_digest, scheme, composite, artifact_digest, claim_digest, evaluator)
        return claim, arguments, determination, produced
    requirement = next((r for r in scheme["requirements"] if r["id"] == requirement_id), None)
    if requirement is None:
        determination = {
            "kind": "determination", "publisher": publisher, "claim": claim_digest, "status": "OUT_OF_SCOPE",
            "requested_scope": [], "established_scope": [], "arguments": [], "used": sorted({scheme_digest, artifact_digest}),
            "reasons": [], "notes": [f"scheme has no requirement {requirement_id!r}"], "evaluator": evaluator,
        }
        return claim, [], determination, []
    measurements = gather(store, scheme, requirement, artifact_digest)
    result = evaluate(requirement, measurements, scheme["inference_patterns"])
    arguments = []
    if result.status == "SUPPORTED":
        arguments.append(_argument(publisher, claim_digest, "supports", "all_cases_conform", result.support))
    for case, measurement in result.refutations:
        arguments.append(_argument(publisher, claim_digest, "refutes", "counterexample", [measurement], witness=case))
    pending = sorted(d for d, _ in store.find("argument", claim=claim_digest, admissibility="pending_review"))
    notes = list(result.notes)
    if pending:
        notes.append(f"{len(pending)} argument(s) pending review, not evaluated")
    used = {scheme_digest, artifact_digest, requirement["measurand"], *requirement["cases"], *pending}
    for measurement in measurements:
        used.add(measurement.digest)
        used.update(measurement.consulted)
    determination = {
        "kind": "determination", "publisher": publisher, "claim": claim_digest, "status": result.status,
        "requested_scope": list(requirement["cases"]), "established_scope": result.established_scope,
        "arguments": [digest_of(a) for a in arguments], "used": sorted(used),
        "reasons": [{"case": case, "finding": finding} for case, finding in result.reasons],
        "notes": notes, "evaluator": evaluator,
    }
    return claim, arguments, determination, []


def determine(store, signer, publisher: str, scheme_digest: str, requirement_id: str, artifact_digest: str) -> str:
    claim, arguments, determination, produced = build(store, publisher, scheme_digest, requirement_id, artifact_digest)
    for obj in (*produced, claim, *arguments, determination):
        attest(store, signer, publisher, store.put(obj), obj["kind"])
    return digest_of(determination)
