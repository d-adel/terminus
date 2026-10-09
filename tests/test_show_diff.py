from helpers import ARTIFACT, publish_world, qualify, write_doc
from terminus.determine import determine
from terminus.diff import diff
from terminus.publish import publish
from terminus.show import render, to_gsn


def _determined(store, signer, tmp_path, observed):
    world = publish_world(store, signer, tmp_path / "docs")
    qualify(store, signer, tmp_path / "runs", world, observed)
    return world, determine(store, signer, "p", world["scheme"], "accuracy", world["artifact"])


def test_render(store, signer, tmp_path):
    _, digest = _determined(store, signer, tmp_path, {"case-a": {"value": 2.02}, "case-b": {"value": 4.04}})
    text = render(store, digest)
    assert text.startswith("SUPPORTED")
    assert "  case-a@1: conforming" in text
    assert "established 2 of 2 cases" in text
    assert text.endswith(digest)


def test_gsn_for_a_supported_claim(store, signer, tmp_path):
    _, digest = _determined(store, signer, tmp_path, {"case-a": {"value": 2.02}, "case-b": {"value": 4.04}})
    doc = to_gsn(store, digest)
    assert doc["G1"]["supportedBy"] == ["S1"]
    assert sorted(doc["S1"]["supportedBy"]) == ["Sn1_1", "Sn1_2"]
    assert "SUPPORTED" in doc["G1"]["text"]


def test_gsn_for_a_failed_claim(store, signer, tmp_path):
    _, digest = _determined(store, signer, tmp_path, {"case-a": {"value": 2.02}, "case-b": {"value": 4.4}})
    doc = to_gsn(store, digest)
    counters = [key for key in doc if key.startswith("CSn")]
    assert len(counters) == 1
    assert doc[counters[0]]["challenges"] == "G1"
    assert doc["G1"]["undeveloped"] is True


def test_diff_reports_a_regression(store, signer, tmp_path):
    world, before = _determined(store, signer, tmp_path, {"case-a": {"value": 2.02}, "case-b": {"value": 4.04}})
    newer = publish(store, signer, "p", write_doc(tmp_path / "docs", "artifact-2", {**ARTIFACT, "commit": "3" * 40}))["object"]
    qualify(store, signer, tmp_path / "runs", world, {"case-a": {"value": 2.02}, "case-b": {"value": 4.4}}, artifact=newer)
    after = determine(store, signer, "p", world["scheme"], "accuracy", newer)
    changes = diff(store, before, after)
    assert "status SUPPORTED -> FAILED" in changes
    assert "case-b@1: conforming -> nonconforming" in changes
    assert "new counterexample: case-b@1" in changes
    assert any(line.startswith("case-b@1: measured") for line in changes)
    assert diff(store, before, before) == []


def test_show_renders_a_composite_root(store, signer, tmp_path):
    from test_determine import GOOD as GOOD_VALUES, _composite_world
    from terminus.determine import determine
    from terminus.show import render, to_gsn

    world = _composite_world(store, signer, tmp_path, GOOD_VALUES, second_limit=0.1)
    digest = determine(store, signer, "p", world["scheme"], "root", world["artifact"])
    text = render(store, digest)
    assert "requirement root" in text
    assert "  accuracy: SUPPORTED" in text
    assert "  second: SUPPORTED" in text
    gsn = to_gsn(store, digest)
    assert gsn["G1"]["supportedBy"] == ["S1"]
    assert gsn["S1"]["supportedBy"] == ["C1_G1", "C2_G1"]


def test_diff_of_composite_roots_descends_into_children(store, signer, tmp_path):
    from helpers import ARTIFACT, qualify, write_doc
    from terminus.determine import determine
    from terminus.diff import diff
    from terminus.publish import publish
    from test_determine import GOOD as GOOD_VALUES, _composite_world

    world = _composite_world(store, signer, tmp_path, GOOD_VALUES, second_limit=0.5)
    other = publish(store, signer, "p", write_doc(tmp_path / "docs", "artifact-b", {**ARTIFACT, "name": "solver-b", "commit": "3" * 40}))["object"]
    qualify(store, signer, tmp_path / "runs-b", world, {"case-a": {"value": 2.02}, "case-b": {"value": 4.4}}, artifact=other)
    good = determine(store, signer, "p", world["scheme"], "root", world["artifact"])
    bad = determine(store, signer, "p", world["scheme"], "root", other)
    assert store.get(bad)["status"] == "FAILED"
    changes = diff(store, good, bad)
    assert "status SUPPORTED -> FAILED" in changes
    assert "accuracy: SUPPORTED -> FAILED" in changes
    assert sum(c.startswith("case-b@1: measured") for c in changes) == 1
    assert "new counterexample: case-b@1" in changes
