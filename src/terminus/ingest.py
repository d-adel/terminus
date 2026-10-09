import json
from pathlib import Path

from terminus.sign import attest

REALIZATION_FILE = "realization.json"


def _expect(store, digest: str, kind: str) -> None:
    obj = store.get(digest)
    if obj["kind"] != kind:
        raise ValueError(f"{digest} is a {obj['kind']}, expected {kind}")


def _put(store, signer, publisher: str, obj: dict) -> str:
    digest = store.put(obj)
    attest(store, signer, publisher, digest, obj["kind"])
    return digest


def ingest_run(store, signer, publisher: str, run_dir, case: str, artifact: str, adapter: str) -> dict:
    run_dir = Path(run_dir)
    for digest, kind in ((case, "case"), (artifact, "artifact"), (adapter, "adapter")):
        _expect(store, digest, kind)
    record = (run_dir / "run.json").read_bytes()
    run = json.loads(record)
    execution = {
        "kind": "execution", "publisher": publisher, "case": case, "artifact": artifact, "adapter": adapter,
        "outcome": run["outcome"], "run_record": store.put_blob(record), "lab_run_id": run["run"],
    }
    result = {"execution": _put(store, signer, publisher, execution)}
    out = run_dir / "out"
    realization_path = out / REALIZATION_FILE
    if realization_path.exists():
        declared = json.loads(realization_path.read_text(encoding="utf-8"))
        realization = {"kind": "realization", "publisher": publisher, "execution": result["execution"], "facets": declared["facets"]}
        if declared.get("notes"):
            realization["notes"] = declared["notes"]
        result["realization"] = _put(store, signer, publisher, realization)
    files = []
    if out.is_dir():
        for path in sorted(out.rglob("*")):
            if path.is_file() and path != realization_path:
                files.append({"name": path.relative_to(out).as_posix(), "blob": store.put_blob(path.read_bytes())})
    observations = {"kind": "observations", "publisher": publisher, "execution": result["execution"], "files": files}
    result["observations"] = _put(store, signer, publisher, observations)
    return result
