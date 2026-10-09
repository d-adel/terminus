import pytest

from helpers import make_run, publish_world
from terminus.ingest import ingest_run


def test_ingest_creates_execution_realization_and_observations(store, signer, tmp_path):
    world = publish_world(store, signer, tmp_path / "docs")
    run = make_run(tmp_path / "runs", "r1", 2.02)
    (run / "out" / "fields").mkdir()
    (run / "out" / "fields" / "u.bin").write_bytes(b"\x00\x01")
    result = ingest_run(store, signer, "p", run, world["case-a"], world["artifact"], world["adapter"])
    execution = store.get(result["execution"])
    assert execution["outcome"] == "succeeded"
    assert execution["lab_run_id"] == "alloc-r1"
    assert store.read_blob(execution["run_record"]) == (run / "run.json").read_bytes()
    assert store.get(result["realization"])["facets"]["material"] == "exact"
    names = [f["name"] for f in store.get(result["observations"])["files"]]
    assert names == ["fields/u.bin", "observed.json"]
    for digest in result.values():
        assert store.statements(digest)


def test_ingest_without_realization(store, signer, tmp_path):
    world = publish_world(store, signer, tmp_path / "docs")
    run = make_run(tmp_path / "runs", "r1", 2.02, realization=False)
    result = ingest_run(store, signer, "p", run, world["case-a"], world["artifact"], world["adapter"])
    assert "realization" not in result


def test_ingest_checks_reference_kinds(store, signer, tmp_path):
    world = publish_world(store, signer, tmp_path / "docs")
    run = make_run(tmp_path / "runs", "r1", 2.02)
    with pytest.raises(ValueError, match="expected case"):
        ingest_run(store, signer, "p", run, world["artifact"], world["artifact"], world["adapter"])
