import json
from pathlib import Path

import yaml

MEASURAND = {
    "kind": "measurand", "publisher": "p", "name": "relative-error", "version": "1", "unit": "dimensionless",
    "definition": "Absolute difference between the computed and the reference value, divided by the reference value.",
}

ARTIFACT = {"kind": "artifact", "publisher": "p", "name": "solver", "repo": "example/solver", "commit": "1" * 40}

ADAPTER = {
    "kind": "adapter", "publisher": "p", "name": "solver-adapter", "version": "1",
    "repo": "example/solver", "commit": "1" * 40, "artifact_name": "solver",
}

PROCEDURE = {"repo": "example/pack", "commit": "2" * 40, "entry": "fixturepack:relative_error"}


def write_doc(directory, name, doc) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return path


def case_doc(name, expected) -> dict:
    return {
        "kind": "case", "publisher": "p", "name": name, "version": "1", "purpose": "verification",
        "problem": {"expected": expected}, "observables": ["value"],
    }


def scheme_doc(case_names, limit=0.05, allow_zero=False, patterns=("all_cases_conform",), first_party=True, accept_approximate=False) -> dict:
    return {
        "kind": "scheme", "publisher": "p", "name": "reference", "version": "1",
        "requirements": [{
            "id": "accuracy",
            "measurand": "ref:p/relative-error@1",
            "predicate": {"operator": "le", "limit": limit},
            "quantifier": "enumerated",
            "cases": [f"ref:p/{name}@1" for name in case_names],
            "decision_rule": {"type": "guard_band", "allow_zero_uncertainty": allow_zero},
        }],
        "inference_patterns": list(patterns),
        "adapter_policy": {"first_party_allowed": first_party, "accept_approximate": accept_approximate},
    }


def publish_world(store, signer, directory, cases=(("case-a", 2.0), ("case-b", 4.0)), **scheme_options) -> dict:
    from terminus.publish import publish

    world = {"measurand": publish(store, signer, "p", write_doc(directory, "measurand", MEASURAND))["object"]}
    for name, expected in cases:
        world[name] = publish(store, signer, "p", write_doc(directory, name, case_doc(name, expected)))["object"]
    scheme = scheme_doc([name for name, _ in cases], **scheme_options)
    world["scheme"] = publish(store, signer, "p", write_doc(directory, "scheme", scheme))["object"]
    world["artifact"] = publish(store, signer, "p", write_doc(directory, "artifact", ARTIFACT))["object"]
    world["adapter"] = publish(store, signer, "p", write_doc(directory, "adapter", ADAPTER))["object"]
    return world


def make_run(directory, name, value, uncertainty=0.01, outcome="succeeded", facets=None, realization=True) -> Path:
    run = Path(directory) / name
    out = run / "out"
    out.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"project": "terminus-test", "run": f"alloc-{name}", "outcome": outcome}), encoding="utf-8")
    (out / "observed.json").write_text(json.dumps({"value": value, "uncertainty": uncertainty}), encoding="utf-8")
    if realization:
        declared = facets or {"physical": "exact", "material": "exact", "observation": "exact"}
        (out / "realization.json").write_text(json.dumps({"facets": declared}), encoding="utf-8")
    return run


def qualify(store, signer, directory, world, observed, artifact=None, entry=None) -> None:
    from terminus.ingest import ingest_run
    from terminus.measure import measure

    procedure = {**PROCEDURE, "entry": entry} if entry else PROCEDURE
    for case, options in observed.items():
        run = make_run(directory, f"{case}-{(artifact or world['artifact'])[-8:]}", **options)
        result = ingest_run(store, signer, "p", run, world[case], artifact or world["artifact"], world["adapter"])
        measure(store, signer, "p", result["observations"], world["measurand"], procedure)
