import argparse
import json
import os
import uuid
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="verb", required=True)
    run = sub.add_parser("run")
    for flag in ("--project", "--repo", "--commit", "--on", "--name"):
        run.add_argument(flag, required=True)
    run.add_argument("--param", action="append", default=[])
    run.add_argument("--memory", type=int)
    run.add_argument("command", nargs=argparse.REMAINDER)
    a = parser.parse_args()
    params = dict(p.split("=", 1) for p in a.param)
    case = json.loads(params["case"])
    mode = os.environ.get("FAKELAB_MODE", "")
    job = f"{a.project}-{a.name}-{uuid.uuid4().hex[:8]}"
    alloc = "f" + uuid.uuid4().hex
    runs = Path(os.environ["FAKELAB_RESULTS"]) / a.project / "runs"
    folder = runs / alloc
    (folder / "out").mkdir(parents=True)
    if mode == "rescheduled":
        first = runs / ("0" + uuid.uuid4().hex)
        (first / "out").mkdir(parents=True)
        (first / "run.json").write_text(json.dumps({
            "project": a.project, "run": first.name, "job": job, "outcome": "failed", "parameters": params,
            "commit": a.commit, "next_run": alloc}), encoding="utf-8")
    if mode == "wrong-case":
        params["case"] = json.dumps({**case, "version": "other"})
    record = {"project": a.project, "run": alloc, "job": job, "outcome": "succeeded", "parameters": params,
              "commit": "0" * 40 if mode == "wrong-commit" else a.commit, "command": a.command, "next_run": None,
              "memory": a.memory}
    (folder / "run.json").write_text(json.dumps(record), encoding="utf-8")
    expected = case["problem"]["expected"]
    (folder / "out" / "observed.json").write_text(json.dumps({"value": expected * 1.01, "uncertainty": 0.001}), encoding="utf-8")
    facets = {"physical": "exact", "material": "exact", "observation": "exact"}
    (folder / "out" / "realization.json").write_text(json.dumps({"facets": facets}), encoding="utf-8")
    print(job)


main()
