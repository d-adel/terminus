import json
from pathlib import Path

import pytest

from terminus.validate import InvalidObject, validate

D = "sha256:" + "a" * 64
MODEL = Path(__file__).parents[1] / "src" / "terminus" / "model"


def test_valid_case():
    validate({
        "kind": "case", "publisher": "p", "name": "n", "version": "1",
        "purpose": "verification", "problem": {"a": [1, {"b": 2}]}, "observables": ["stress"],
    })


@pytest.mark.parametrize("obj, message", [
    ({"kind": "nope"}, "unknown kind"),
    ({"kind": "case", "publisher": "p", "name": "n", "version": "1", "purpose": "x", "problem": {}, "observables": []}, "is not one of"),
    ({"kind": "claim", "publisher": "p", "scheme": "sha256:xyz", "requirement": "r", "artifact": D}, "does not match"),
    ({"kind": "claim", "publisher": "p", "scheme": D, "requirement": "r", "artifact": D, "extra": 1}, "Additional properties"),
    ({"kind": "claim", "publisher": "p", "scheme": D, "artifact": D}, "'requirement' is a required property"),
])
def test_invalid_objects(obj, message):
    with pytest.raises(InvalidObject, match=message):
        validate(obj)


def test_generated_schema_is_current():
    from linkml.generators.jsonschemagen import JsonSchemaGenerator

    generated = json.loads(JsonSchemaGenerator(str(MODEL / "model.yaml")).serialize())
    stored = json.loads((MODEL / "model.schema.json").read_text(encoding="utf-8"))
    generated.pop("metamodel_version", None)
    stored.pop("metamodel_version", None)
    assert generated == stored


def test_scheme_with_claims_and_procedure_source_are_valid():
    validate({
        "kind": "scheme", "publisher": "p", "name": "s", "version": "1",
        "requirements": [{
            "id": "r", "measurand": D, "predicate": {"operator": "le", "limit": 1.0}, "quantifier": "enumerated",
            "cases": [D], "decision_rule": {"type": "guard_band", "allow_zero_uncertainty": False},
        }],
        "claims": [{"id": "root", "all_of": ["r"]}],
        "inference_patterns": ["all_cases_conform", "all_of"],
        "adapter_policy": {"first_party_allowed": True, "accept_approximate": False},
    })
    validate({
        "kind": "measurement_result", "publisher": "p", "measurand": D, "case": D, "artifact": D,
        "value": 0.0, "uncertainty": 0.0, "unit": "dimensionless",
        "procedure": {"repo": "r", "commit": "c", "entry": "m:f", "source": D}, "was_derived_from": [D],
    })


def test_reason_may_name_a_child_claim():
    validate({
        "kind": "determination", "publisher": "p", "claim": D, "status": "SUPPORTED",
        "requested_scope": [D], "established_scope": [D], "arguments": [], "used": [D],
        "reasons": [{"claim": D, "finding": "SUPPORTED"}], "notes": [],
        "evaluator": {"name": "terminus", "version": "0.1.0"},
    })
