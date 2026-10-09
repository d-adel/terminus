import base64
import json

from helpers import publish_world, qualify
from terminus import measure as measure_module
from terminus.determine import determine
from terminus.digest import hex_of
from terminus.export import export
from terminus.measure import ProcedureError
from terminus.recheck import recheck

GOOD = {"case-a": {"value": 2.02}, "case-b": {"value": 4.04}}


def _exported(store, signer, tmp_path, observed=GOOD):
    world = publish_world(store, signer, tmp_path / "docs")
    qualify(store, signer, tmp_path / "runs", world, observed)
    digest = determine(store, signer, "p", world["scheme"], "accuracy", world["artifact"])
    manifest = export(store, digest, tmp_path / "export")
    return digest, manifest


def test_export_contains_the_closure(store, signer, tmp_path):
    digest, manifest = _exported(store, signer, tmp_path)
    assert manifest["root"] == digest
    kinds = set(manifest["objects"].values())
    assert {"determination", "claim", "argument", "scheme", "measurand", "case", "measurement_result",
            "observations", "execution", "realization", "artifact", "adapter", "release"} <= kinds
    assert set(manifest["blobs"].values()) == {"included"}
    assert (tmp_path / "export" / "prov.json").exists()
    assert json.loads((tmp_path / "export" / "manifest.json").read_text(encoding="utf-8")) == manifest


def test_recheck_of_a_clean_export(store, signer, tmp_path):
    _exported(store, signer, tmp_path)
    report = recheck(tmp_path / "export")
    assert report.problems == []
    assert report.determination_matches
    assert report.measurements_rechecked == 2
    assert any(note.startswith("publisher p signs with key") for note in report.notes)


def test_recheck_of_a_failed_determination_still_matches(store, signer, tmp_path):
    _exported(store, signer, tmp_path, {"case-a": {"value": 2.02}, "case-b": {"value": 4.4}})
    report = recheck(tmp_path / "export")
    assert report.problems == []
    assert report.determination_matches


def test_recheck_detects_an_edited_object(store, signer, tmp_path):
    _, manifest = _exported(store, signer, tmp_path)
    measurement = next(d for d, kind in manifest["objects"].items() if kind == "measurement_result")
    path = tmp_path / "export" / "objects" / f"{hex_of(measurement)}.json"
    obj = json.loads(path.read_bytes())
    obj["value"] = 0.0
    path.write_text(json.dumps(obj), encoding="utf-8")
    report = recheck(tmp_path / "export")
    assert any("does not match its digest" in problem for problem in report.problems)
    assert not report.determination_matches


def test_recheck_detects_a_forged_statement(store, signer, tmp_path):
    _, manifest = _exported(store, signer, tmp_path)
    case = next(d for d, kind in manifest["objects"].items() if kind == "case")
    [path] = (tmp_path / "export" / "statements").glob(f"{hex_of(case)}.*.dsse.json")
    envelope = json.loads(path.read_bytes())
    envelope["payload"] = base64.b64encode(b'{"forged":true}').decode()
    path.write_text(json.dumps(envelope), encoding="utf-8")
    report = recheck(tmp_path / "export")
    assert any("signature check failed" in problem for problem in report.problems)


def test_recheck_notes_a_procedure_it_cannot_load(store, signer, tmp_path, monkeypatch):
    _exported(store, signer, tmp_path)

    def unavailable(entry):
        raise ProcedureError(f"procedure entry {entry!r} cannot be loaded: not installed")

    monkeypatch.setattr(measure_module, "load_entry", unavailable)
    report = recheck(tmp_path / "export")
    assert report.problems == []
    assert report.determination_matches
    assert report.measurements_rechecked == 0
    assert sum("measurement not rechecked" in note for note in report.notes) == 2


def _manifest(tmp_path):
    return json.loads((tmp_path / "export" / "manifest.json").read_text(encoding="utf-8"))


def _write_manifest(tmp_path, manifest):
    (tmp_path / "export" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _run_record(manifest, tmp_path):
    execution = next(d for d, kind in manifest["objects"].items() if kind == "execution")
    path = tmp_path / "export" / "objects" / f"{hex_of(execution)}.json"
    return json.loads(path.read_bytes())["run_record"]


def test_recheck_detects_a_removed_blob(store, signer, tmp_path):
    _, manifest = _exported(store, signer, tmp_path)
    blob = _run_record(manifest, tmp_path)
    (tmp_path / "export" / "blobs" / hex_of(blob)).unlink()
    del manifest["blobs"][blob]
    _write_manifest(tmp_path, manifest)
    report = recheck(tmp_path / "export", rerun_measurements=False)
    assert report.problems


def test_recheck_detects_a_forged_blob_dropped_from_the_manifest(store, signer, tmp_path):
    _, manifest = _exported(store, signer, tmp_path)
    blob = _run_record(manifest, tmp_path)
    (tmp_path / "export" / "blobs" / hex_of(blob)).write_text('{"outcome":"failed","run":"forged"}', encoding="utf-8")
    del manifest["blobs"][blob]
    _write_manifest(tmp_path, manifest)
    report = recheck(tmp_path / "export", rerun_measurements=False)
    assert report.problems


def test_recheck_detects_a_forged_prov_file(store, signer, tmp_path):
    _exported(store, signer, tmp_path)
    (tmp_path / "export" / "prov.json").write_text('{"forged": true}', encoding="utf-8")
    report = recheck(tmp_path / "export", rerun_measurements=False)
    assert any("prov.json" in problem for problem in report.problems)


def test_recheck_detects_a_stray_object(store, signer, tmp_path):
    from terminus.store import Store

    _exported(store, signer, tmp_path)
    Store(tmp_path / "export").put({"kind": "artifact", "publisher": "p", "name": "stray", "repo": "x/y", "commit": "9" * 40})
    report = recheck(tmp_path / "export", rerun_measurements=False)
    assert any("not in the closure" in problem for problem in report.problems)


def test_recheck_tolerates_a_newer_evaluator_version(store, signer, tmp_path, monkeypatch):
    from terminus import determine as determine_module

    _exported(store, signer, tmp_path)
    monkeypatch.setattr(determine_module, "EVALUATOR", {"name": "terminus", "version": "9.9.9"})
    report = recheck(tmp_path / "export", rerun_measurements=False)
    assert report.problems == []
    assert report.determination_matches
    assert any("9.9.9" in note for note in report.notes)


def test_recheck_checks_trusted_keys(store, signer, tmp_path):
    _exported(store, signer, tmp_path)
    keyid = json.loads((tmp_path / "export" / "keys" / "p.json").read_bytes())["keyid"]
    assert recheck(tmp_path / "export", rerun_measurements=False, trusted={"p": keyid}).problems == []
    report = recheck(tmp_path / "export", rerun_measurements=False, trusted={"p": "0" * 64})
    assert any("not the trusted key" in problem for problem in report.problems)
    untrusted = recheck(tmp_path / "export", rerun_measurements=False)
    assert any("keys shipped in this export" in note for note in untrusted.notes)


def test_recheck_notes_a_mislabelled_measurement(store, signer, tmp_path):
    from helpers import make_run
    from terminus.ingest import ingest_run

    world = publish_world(store, signer, tmp_path / "docs")
    qualify(store, signer, tmp_path / "runs", world, {"case-a": {"value": 2.02}})
    ingest_run(store, signer, "p", make_run(tmp_path / "runs", "real-b", 4.4), world["case-b"], world["artifact"], world["adapter"])
    from terminus.sign import attest

    [(_, real)] = store.find("measurement_result", case=world["case-a"])
    attest(store, signer, "p", store.put({**real, "case": world["case-b"]}), "measurement_result")
    digest = determine(store, signer, "p", world["scheme"], "accuracy", world["artifact"])
    export(store, digest, tmp_path / "export")
    report = recheck(tmp_path / "export")
    assert report.determination_matches
    assert any("does not match its execution" in note for note in report.notes)


def test_recheck_of_a_composite_root(store, signer, tmp_path):
    from test_determine import GOOD as GOOD_VALUES, _composite_world

    world = _composite_world(store, signer, tmp_path, GOOD_VALUES, second_limit=0.1)
    digest = determine(store, signer, "p", world["scheme"], "root", world["artifact"])
    export(store, digest, tmp_path / "export")
    report = recheck(tmp_path / "export")
    assert report.problems == []
    assert report.determination_matches
    assert report.measurements_rechecked == 2


def test_recheck_reruns_a_procedure_from_the_bundled_source(store, signer, tmp_path):
    from helpers import make_run
    from terminus.ingest import ingest_run
    from terminus.measure import measure
    from test_measure import _fixture_source, source_tar

    world = publish_world(store, signer, tmp_path / "docs")
    source = store.put_blob(source_tar({"bundledpack.py": _fixture_source()}))
    procedure = {"repo": "example/pack", "commit": "2" * 40, "entry": "bundledpack:relative_error", "source": source}
    for case, value in (("case-a", 2.02), ("case-b", 4.04)):
        run = make_run(tmp_path / "runs", case, value)
        observations = ingest_run(store, signer, "p", run, world[case], world["artifact"], world["adapter"])["observations"]
        measure(store, signer, "p", observations, world["measurand"], procedure)
    digest = determine(store, signer, "p", world["scheme"], "accuracy", world["artifact"])
    export(store, digest, tmp_path / "export")
    keyid = json.loads((tmp_path / "export" / "keys" / "p.json").read_bytes())["keyid"]
    report = recheck(tmp_path / "export", trusted={"p": keyid})
    assert report.problems == []
    assert report.measurements_rechecked == 2
    untrusted = recheck(tmp_path / "export")
    assert untrusted.problems == []
    assert untrusted.measurements_rechecked == 0
    assert sum("code shipped in the export" in note for note in untrusted.notes) == 2


def test_rerun_agreement_allows_only_platform_rounding():
    from terminus.recheck import agreement

    stored = (0.002579771024981004, 4.3653171218195265e-05, "dimensionless")
    assert agreement(stored, stored) == "identical"
    assert agreement((0.002579771024981387, 4.365317121819525e-05, "dimensionless"), stored) == "rounding"
    assert agreement((0.0025798, 4.3653171218195265e-05, "dimensionless"), stored) is None
    assert agreement((0.002579771024981004, 4.3653171218195265e-05, "m"), stored) is None
