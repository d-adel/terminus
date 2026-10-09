import json
import subprocess
from pathlib import Path

import pytest

import fixturepack
from helpers import publish_world
from terminus.run import RunError, requirements_under, run

LAB = Path(__file__).parent / "fakelab.py"
SHA = "a" * 40


def _pack(tmp_path, manifest="procedures:\n  relative-error@1: runpack:relative_error\n"):
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "pack.yaml").write_text(manifest, encoding="utf-8")
    (pack / "runpack.py").write_text(Path(fixturepack.__file__).read_text(encoding="utf-8"), encoding="utf-8")
    git = ["git", "-C", str(pack), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q", str(pack)], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "pack"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    return pack, commit


def _run(store, signer, tmp_path, monkeypatch, mode="", claim="accuracy", manifest=None, memory=None, **scheme_options):
    world = publish_world(store, signer, tmp_path / "docs", **scheme_options)
    pack, commit = _pack(tmp_path, manifest) if manifest else _pack(tmp_path)
    results = tmp_path / "results"
    monkeypatch.setenv("FAKELAB_RESULTS", str(results))
    monkeypatch.setenv("FAKELAB_MODE", mode)
    digest = run(store, signer, "p", world["scheme"], claim, f"example/solver@{SHA}", "solver-adapter@1",
                 pack, "example/pack", commit, "spare", lab_cli=LAB, results=results, timeout=30.0, poll=0.05,
                 memory=memory)
    return world, digest


def test_run_ingests_measures_and_determines(store, signer, tmp_path, monkeypatch):
    world, digest = _run(store, signer, tmp_path, monkeypatch)
    determination = store.get(digest)
    assert determination["status"] == "SUPPORTED"
    measurements = [store.get(d) for d in determination["used"] if store.has(d) and store.get(d)["kind"] == "measurement_result"]
    assert len(measurements) == 2
    assert all(m["procedure"]["source"] for m in measurements)
    artifact = store.get(store.get(determination["claim"])["artifact"])
    assert (artifact["repo"], artifact["commit"]) == ("example/solver", SHA)


def test_run_asks_the_lab_for_the_memory_it_was_given(store, signer, tmp_path, monkeypatch):
    _run(store, signer, tmp_path, monkeypatch, memory=8192)
    records = [json.loads(p.read_text(encoding="utf-8")) for p in (tmp_path / "results").rglob("run.json")]
    assert records and all(record["memory"] == 8192 for record in records)


def test_run_leaves_the_lab_default_memory_alone(store, signer, tmp_path, monkeypatch):
    _run(store, signer, tmp_path, monkeypatch)
    records = [json.loads(p.read_text(encoding="utf-8")) for p in (tmp_path / "results").rglob("run.json")]
    assert records and all(record["memory"] is None for record in records)


def test_run_refuses_a_run_at_another_commit(store, signer, tmp_path, monkeypatch):
    with pytest.raises(RunError, match="ran commit"):
        _run(store, signer, tmp_path, monkeypatch, mode="wrong-commit")


def test_run_refuses_a_run_of_another_case(store, signer, tmp_path, monkeypatch):
    with pytest.raises(RunError, match="does not match case"):
        _run(store, signer, tmp_path, monkeypatch, mode="wrong-case")


def test_requirements_under_a_composite_claim():
    scheme = {"requirements": [{"id": "a"}, {"id": "b"}], "claims": [{"id": "root", "all_of": ["a", "b"]}]}
    assert [r["id"] for r in requirements_under(scheme, "root")] == ["a", "b"]
    with pytest.raises(RunError, match="no requirement or claim"):
        requirements_under(scheme, "missing")


def test_run_uses_the_final_attempt_of_a_rescheduled_job(store, signer, tmp_path, monkeypatch):
    world, digest = _run(store, signer, tmp_path, monkeypatch, mode="rescheduled")
    assert store.get(digest)["status"] == "SUPPORTED"


def test_run_uses_the_procedure_named_for_the_measurand_version(store, signer, tmp_path, monkeypatch):
    manifest = "procedures:\n  relative-error@0: runpack:returns_nan\n  relative-error@1: runpack:relative_error\n"
    world, digest = _run(store, signer, tmp_path, monkeypatch, manifest=manifest)
    assert store.get(digest)["status"] == "SUPPORTED"


def test_run_refuses_a_procedure_named_without_a_version(store, signer, tmp_path, monkeypatch):
    with pytest.raises(RunError, match="no procedure for measurand relative-error@1"):
        _run(store, signer, tmp_path, monkeypatch, manifest="procedures:\n  relative-error: runpack:relative_error\n")
