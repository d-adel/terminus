import importlib
import io
import json
import math
import subprocess
import sys
import tarfile
import tempfile

from terminus.gather import unit_problem
from terminus.sign import attest

RUNNER = (
    "import importlib, json, sys\n"
    "request = json.load(sys.stdin)\n"
    "sys.path.insert(0, request['path'])\n"
    "module, _, function = request['entry'].partition(':')\n"
    "output = getattr(importlib.import_module(module), function)("
    "files=request['files'], problem=request['problem'], measurand=request['measurand'])\n"
    "json.dump(output, sys.stdout)\n"
)


class ProcedureError(RuntimeError):
    pass


def load_entry(entry: str):
    module, _, function = entry.partition(":")
    if not module or not function:
        raise ProcedureError(f"procedure entry {entry!r} is not module:function")
    try:
        return getattr(importlib.import_module(module), function)
    except (ImportError, AttributeError) as error:
        raise ProcedureError(f"procedure entry {entry!r} cannot be loaded: {error}") from error


def _from_source(store, source: str, entry: str, files: dict, problem, measurand: dict) -> dict:
    module, _, function = entry.partition(":")
    if not module or not function:
        raise ProcedureError(f"procedure entry {entry!r} is not module:function")
    with tempfile.TemporaryDirectory() as folder:
        try:
            with tarfile.open(fileobj=io.BytesIO(store.read_blob(source))) as tar:
                tar.extractall(folder, filter="data")
        except (tarfile.TarError, OSError) as error:
            raise ProcedureError(f"procedure source {source} cannot be unpacked: {error}") from error
        request = {"path": folder, "entry": entry, "files": {k: str(v) for k, v in files.items()},
                   "problem": problem, "measurand": measurand}
        done = subprocess.run([sys.executable, "-I", "-c", RUNNER], input=json.dumps(request),
                              capture_output=True, text=True)
    if done.returncode != 0:
        lines = done.stderr.strip().splitlines()
        raise ProcedureError(f"procedure {entry} failed: {lines[-1] if lines else 'exit code ' + str(done.returncode)}")
    try:
        return json.loads(done.stdout)
    except ValueError as error:
        raise ProcedureError(f"procedure {entry} printed no JSON result") from error


def run_procedure(store, observations_digest: str, measurand_digest: str, entry: str, source=None):
    observations = store.get(observations_digest)
    if observations["kind"] != "observations":
        raise ValueError(f"{observations_digest} is a {observations['kind']}, expected observations")
    execution = store.get(observations["execution"])
    case = store.get(execution["case"])
    measurand = store.get(measurand_digest)
    files = {item["name"]: store.blob_path(item["blob"]) for item in observations["files"]}
    if source is None:
        output = load_entry(entry)(files=files, problem=case["problem"], measurand=measurand)
    else:
        output = _from_source(store, source, entry, files, case["problem"], measurand)
    if not isinstance(output, dict):
        raise ProcedureError(f"procedure {entry} returned {type(output).__name__}, not a mapping")
    for key in ("value", "uncertainty", "unit"):
        if key not in output:
            raise ProcedureError(f"procedure {entry} returned no {key!r}")
    for key in ("value", "uncertainty"):
        number = output[key]
        if not isinstance(number, (int, float)) or not math.isfinite(number):
            raise ProcedureError(f"procedure {entry} returned {key} {number!r}, not a finite number")
    problem = unit_problem(output["unit"]) if isinstance(output["unit"], str) else f"unit {output['unit']!r} is not a string"
    if problem:
        raise ProcedureError(f"procedure {entry} returned an unusable unit: {problem}")
    return output, execution


def measure(store, signer, publisher: str, observations_digest: str, measurand_digest: str, procedure: dict) -> str:
    output, execution = run_procedure(store, observations_digest, measurand_digest, procedure["entry"], procedure.get("source"))
    result = {
        "kind": "measurement_result", "publisher": publisher, "measurand": measurand_digest,
        "case": execution["case"], "artifact": execution["artifact"],
        "value": float(output["value"]), "uncertainty": float(output["uncertainty"]), "unit": output["unit"],
        "procedure": procedure, "was_derived_from": [observations_digest],
    }
    if output.get("reference_data"):
        result["reference_data"] = sorted(output["reference_data"])
    digest = store.put(result)
    attest(store, signer, publisher, digest, "measurement_result")
    return digest
