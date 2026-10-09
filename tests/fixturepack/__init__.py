import json
from pathlib import Path


def _observed(files):
    return json.loads(Path(files["observed.json"]).read_text(encoding="utf-8"))


def relative_error(files, problem, measurand):
    observed = _observed(files)
    expected = problem["expected"]
    value = abs(observed["value"] - expected) / abs(expected)
    return {"value": value, "uncertainty": observed["uncertainty"], "unit": "dimensionless"}


def relative_error_percent(files, problem, measurand):
    result = relative_error(files, problem, measurand)
    return {"value": result["value"] * 100, "uncertainty": result["uncertainty"] * 100, "unit": "percent"}


def relative_error_metres(files, problem, measurand):
    result = relative_error(files, problem, measurand)
    return {**result, "unit": "m"}


def returns_nan(files, problem, measurand):
    return {"value": float("nan"), "uncertainty": 0.0, "unit": "dimensionless"}


def returns_nothing(files, problem, measurand):
    return {"value": 1.0}


def relative_error_bad_unit(files, problem, measurand):
    result = relative_error(files, problem, measurand)
    return {**result, "unit": "m)"}
