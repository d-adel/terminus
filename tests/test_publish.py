import pytest

from helpers import MEASURAND, publish_world, scheme_doc, write_doc
from terminus.publish import ResolveError, publish, resolve_ref


def test_publish_resolves_refs_and_releases(store, signer, tmp_path):
    world = publish_world(store, signer, tmp_path)
    requirement = store.get(world["scheme"])["requirements"][0]
    assert requirement["measurand"] == world["measurand"]
    assert requirement["cases"] == [world["case-a"], world["case-b"]]
    assert resolve_ref(store, "ref:p/reference@1") == world["scheme"]


def test_unknown_reference_fails(store, signer, tmp_path):
    with pytest.raises(ResolveError, match="nothing released"):
        publish(store, signer, "p", write_doc(tmp_path, "scheme", scheme_doc(["missing"])))


def test_malformed_reference_fails(store):
    with pytest.raises(ResolveError, match="bad reference"):
        resolve_ref(store, "ref:no-version")


def test_same_name_and_version_with_different_content_is_refused(store, signer, tmp_path):
    publish(store, signer, "p", write_doc(tmp_path, "m", MEASURAND))
    changed = {**MEASURAND, "definition": "changed"}
    with pytest.raises(ValueError, match="already released"):
        publish(store, signer, "p", write_doc(tmp_path, "m2", changed))
    assert not any(obj.get("definition") == "changed" for _, obj in store.iter_objects("measurand"))


def test_republishing_identical_content_is_fine(store, signer, tmp_path):
    first = publish(store, signer, "p", write_doc(tmp_path, "m", MEASURAND))
    second = publish(store, signer, "p", write_doc(tmp_path, "m", MEASURAND))
    assert first == second


def test_publisher_mismatch_is_refused(store, signer, tmp_path):
    with pytest.raises(ValueError, match="publisher"):
        publish(store, signer, "q", write_doc(tmp_path, "m", MEASURAND))


def test_every_published_object_is_attested(store, signer, tmp_path):
    world = publish_world(store, signer, tmp_path)
    for digest in world.values():
        assert store.statements(digest)


def test_release_documents_cannot_be_published(store, signer, tmp_path):
    world = publish_world(store, signer, tmp_path / "docs")
    forged = {"kind": "release", "publisher": "p", "name": "case-a", "version": "1", "object": world["case-b"], "object_kind": "case"}
    with pytest.raises(ValueError, match="release"):
        publish(store, signer, "p", write_doc(tmp_path, "release", forged))
    assert resolve_ref(store, "ref:p/case-a@1") == world["case-a"]


def test_ambiguous_release_is_refused(store, signer, tmp_path):
    world = publish_world(store, signer, tmp_path / "docs")
    store.put({"kind": "release", "publisher": "p", "name": "case-a", "version": "1", "object": world["case-b"], "object_kind": "case"})
    with pytest.raises(ResolveError, match="ambiguous"):
        resolve_ref(store, "ref:p/case-a@1")


def test_unparseable_measurand_unit_is_refused(store, signer, tmp_path):
    with pytest.raises(ValueError, match="unit"):
        publish(store, signer, "p", write_doc(tmp_path, "m", {**MEASURAND, "unit": "1/0"}))


def _composite(claims, extra_requirement=True):
    scheme = scheme_doc(["case-a", "case-b"])
    if extra_requirement:
        scheme["requirements"].append({**scheme["requirements"][0], "id": "strict", "predicate": {"operator": "le", "limit": 0.001}})
    scheme["claims"] = claims
    scheme["inference_patterns"] = ["all_cases_conform", "all_of"]
    return scheme


def _publish_cases(store, signer, tmp_path):
    from helpers import case_doc

    publish(store, signer, "p", write_doc(tmp_path, "measurand", MEASURAND))
    for name, expected in (("case-a", 2.0), ("case-b", 4.0)):
        publish(store, signer, "p", write_doc(tmp_path, name, case_doc(name, expected)))


def test_composite_scheme_publishes(store, signer, tmp_path):
    _publish_cases(store, signer, tmp_path)
    digest = publish(store, signer, "p", write_doc(tmp_path, "scheme", _composite([{"id": "root", "all_of": ["accuracy", "strict"]}])))["object"]
    assert store.get(digest)["claims"] == [{"id": "root", "all_of": ["accuracy", "strict"]}]


@pytest.mark.parametrize("claims, message", [
    ([{"id": "root", "all_of": ["accuracy", "missing"]}], "unknown ids: missing"),
    ([{"id": "accuracy", "all_of": ["strict"]}], "not unique: accuracy"),
    ([{"id": "a", "all_of": ["b"]}, {"id": "b", "all_of": ["a"]}], "cycle"),
    ([{"id": "root", "all_of": []}], "lists no children"),
])
def test_bad_composite_scheme_is_refused(store, signer, tmp_path, claims, message):
    _publish_cases(store, signer, tmp_path)
    with pytest.raises(ValueError, match=message):
        publish(store, signer, "p", write_doc(tmp_path, "scheme", _composite(claims)))
