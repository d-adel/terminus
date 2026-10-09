import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

from terminus.determine import determine
from terminus.digest import canonical, digest_of
from terminus.ingest import ingest_run
from terminus.measure import ProcedureError, measure
from terminus.publish import resolve_ref
from terminus.sign import attest

BUILD = "cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build build --target {name} && ./build/{name}"


class RunError(RuntimeError):
    pass


def requirements_under(scheme: dict, claim_id: str) -> list:
    requirements = {r["id"]: r for r in scheme["requirements"]}
    claims = {c["id"]: c for c in scheme.get("claims", [])}
    found, stack = [], [claim_id]
    while stack:
        current = stack.pop()
        if current in requirements:
            if requirements[current] not in found:
                found.append(requirements[current])
        elif current in claims:
            stack.extend(reversed(claims[current]["all_of"]))
        else:
            raise RunError(f"scheme has no requirement or claim {current!r}")
    return found


def _split(spec: str):
    repo, _, commit = spec.rpartition("@")
    if not repo or len(commit) != 40:
        raise RunError(f"expected OWNER/NAME@FULLSHA, got {spec!r}")
    return repo, commit


def _put(store, signer, publisher: str, obj: dict) -> str:
    digest = store.put(obj)
    attest(store, signer, publisher, digest, obj["kind"])
    return digest


def _git(pack, *args) -> bytes:
    return subprocess.run(["git", "-C", str(pack), *args], check=True, capture_output=True).stdout


def submit(lab_cli, repo: str, commit: str, on: str, name: str, case_json: str, command: str, memory=None) -> str:
    sized = ["--memory", str(memory)] if memory else []
    done = subprocess.run(
        [sys.executable, str(lab_cli), "run", "--project", "terminus", "--repo", repo, "--commit", commit,
         "--on", on, "--name", name, "--param", f"case={case_json}", *sized, "--", "sh", "-c", command],
        capture_output=True, text=True)
    if done.returncode != 0 or not done.stdout.strip():
        raise RunError(f"lab run failed for {name}: {done.stderr.strip() or done.stdout.strip()}")
    return done.stdout.splitlines()[0].strip()


def locate(results, job: str):
    runs = Path(results) / "terminus" / "runs"
    if not runs.is_dir():
        return None
    for record in runs.glob("*/run.json"):
        try:
            run_record = json.loads(record.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if run_record.get("job") == job and not run_record.get("next_run"):
            return record.parent
    return None


def wait(results, jobs: dict, timeout: float, poll: float) -> dict:
    deadline = time.monotonic() + timeout
    found = {}
    while True:
        for case, job in jobs.items():
            if case not in found:
                folder = locate(results, job)
                if folder is not None:
                    found[case] = folder
        if len(found) == len(jobs):
            return found
        if time.monotonic() > deadline:
            missing = sorted(job for case, job in jobs.items() if case not in found)
            raise RunError(f"timed out waiting for lab runs: {', '.join(missing)}")
        time.sleep(poll)


def check_run(folder, commit: str, case_digest: str) -> None:
    record = json.loads((Path(folder) / "run.json").read_text(encoding="utf-8"))
    if record.get("commit") != commit:
        raise RunError(f"{folder}: ran commit {record.get('commit')}, expected {commit}")
    try:
        sent = json.loads((record.get("parameters") or {}).get("case", ""))
    except ValueError as error:
        raise RunError(f"{folder}: the case parameter is not JSON") from error
    if not isinstance(sent, dict) or digest_of(sent) != case_digest:
        raise RunError(f"{folder}: the case parameter does not match case {case_digest}")


def run(store, signer, publisher: str, scheme_ref: str, claim_id: str, artifact_spec: str, adapter_spec: str,
        pack, pack_repo: str, pack_commit: str, on: str, *, lab_cli, results, timeout: float = 1800.0,
        poll: float = 10.0, command=None, memory=None) -> str:
    scheme_digest = resolve_ref(store, scheme_ref) if scheme_ref.startswith("ref:") else scheme_ref
    requirements = requirements_under(store.get(scheme_digest), claim_id)
    repo, commit = _split(artifact_spec)
    adapter_name, _, adapter_version = adapter_spec.partition("@")
    if not adapter_name or not adapter_version:
        raise RunError(f"expected ADAPTER@VERSION, got {adapter_spec!r}")
    artifact_name = repo.rpartition("/")[2]
    artifact = _put(store, signer, publisher, {
        "kind": "artifact", "publisher": publisher, "name": artifact_name, "repo": repo, "commit": commit})
    adapter = _put(store, signer, publisher, {
        "kind": "adapter", "publisher": publisher, "name": adapter_name, "version": adapter_version,
        "repo": repo, "commit": commit, "artifact_name": artifact_name})
    manifest = yaml.safe_load(_git(pack, "show", f"{pack_commit}:pack.yaml"))
    source = store.put_blob(_git(pack, "archive", "--format=tar", pack_commit))
    cases = []
    for requirement in requirements:
        cases += [case for case in requirement["cases"] if case not in cases]
    build_command = command or BUILD.format(name=adapter_name)
    jobs = {case: submit(lab_cli, repo, commit, on, store.get(case)["name"],
                         canonical(store.get(case)).decode("utf-8"), build_command, memory) for case in cases}
    folders = wait(results, jobs, timeout, poll)
    observations = {}
    for case in cases:
        check_run(folders[case], commit, case)
        observations[case] = ingest_run(store, signer, publisher, folders[case], case, artifact, adapter)["observations"]
    for requirement in requirements:
        measurand = store.get(requirement["measurand"])
        name = measurand["name"]
        procedures = manifest.get("procedures") or {}
        entry = procedures.get(f"{name}@{measurand['version']}")
        if entry is None:
            raise RunError(f"pack.yaml names no procedure for measurand {name}@{measurand['version']}")
        procedure = {"repo": pack_repo, "commit": pack_commit, "entry": entry, "source": source}
        for case in requirement["cases"]:
            try:
                measure(store, signer, publisher, observations[case], requirement["measurand"], procedure)
            except ProcedureError as error:
                print(f"terminus: no measurement for {store.get(case)['name']}: {error}", file=sys.stderr)
    return determine(store, signer, publisher, scheme_digest, claim_id, artifact)
