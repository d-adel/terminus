import json
from importlib import resources

import jsonschema

CLASS_OF_KIND = {
    "measurand": "Measurand",
    "case": "Case",
    "scheme": "Scheme",
    "artifact": "Artifact",
    "adapter": "Adapter",
    "execution": "Execution",
    "realization": "Realization",
    "observations": "Observations",
    "calibration": "Calibration",
    "measurement_result": "MeasurementResult",
    "claim": "Claim",
    "argument": "Argument",
    "determination": "Determination",
    "release": "Release",
}


class InvalidObject(ValueError):
    pass


_SCHEMA = json.loads(resources.files("terminus.model").joinpath("model.schema.json").read_text(encoding="utf-8"))
_VALIDATORS = {}


def _validator(cls: str):
    if cls not in _VALIDATORS:
        schema = {"$schema": _SCHEMA["$schema"], "$defs": _SCHEMA["$defs"], "$ref": f"#/$defs/{cls}"}
        _VALIDATORS[cls] = jsonschema.Draft201909Validator(schema)
    return _VALIDATORS[cls]


def validate(obj: dict) -> None:
    kind = obj.get("kind") if isinstance(obj, dict) else None
    if kind not in CLASS_OF_KIND:
        raise InvalidObject(f"unknown kind: {kind!r}")
    errors = sorted(error.message for error in _validator(CLASS_OF_KIND[kind]).iter_errors(obj))
    if errors:
        raise InvalidObject(f"invalid {kind}: " + "; ".join(errors))
