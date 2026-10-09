from helpers import make_run, publish_world, qualify
from terminus.determine import determine
from terminus.ingest import ingest_run
from terminus.store import Store

GOOD = {"case-a": {"value": 2.02}, "case-b": {"value": 4.04}}


def _world(store, signer, tmp_path, observed, entry=None, **scheme_options):
    world = publish_world(store, signer, tmp_path / "docs", **scheme_options)
    qualify(store, signer, tmp_path / "runs", world, observed, entry=entry)
    return world


def _determine(store, signer, world, requirement="accuracy"):
    return store.get(determine(store, signer, "p", world["scheme"], requirement, world["artifact"]))


def _reason(store, determination, case):
    return next(r["finding"] for r in determination["reasons"] if r["case"] == case)


def test_supported(store, signer, tmp_path):
    world = _world(store, signer, tmp_path, GOOD)
    determination = _determine(store, signer, world)
    assert determination["status"] == "SUPPORTED"
    assert determination["established_scope"] == [world["case-a"], world["case-b"]]
    [argument] = [store.get(a) for a in determination["arguments"]]
    assert argument["role"] == "supports"
    assert argument["pattern"] == "all_cases_conform"
    assert len(argument["premises"]) == 2


def test_failed_records_the_counterexample(store, signer, tmp_path):
    world = _world(store, signer, tmp_path, {"case-a": {"value": 2.02}, "case-b": {"value": 4.4}})
    determination = _determine(store, signer, world)
    assert determination["status"] == "FAILED"
    [argument] = [store.get(a) for a in determination["arguments"]]
    assert argument["role"] == "refutes"
    assert argument["witness"] == world["case-b"]


def test_unsupported_realization_is_inadmissible(store, signer, tmp_path):
    unsupported = {"physical": "exact", "material": "unsupported", "observation": "exact"}
    world = _world(store, signer, tmp_path, {"case-a": {"value": 2.02}, "case-b": {"value": 4.04, "facets": unsupported}})
    determination = _determine(store, signer, world)
    assert determination["status"] == "NOT_ESTABLISHED"
    assert _reason(store, determination, world["case-b"]) == "inadmissible: realization material is unsupported"


def test_approximate_realization_needs_the_scheme(signer, tmp_path):
    approximate = {"physical": "approximate", "material": "exact", "observation": "exact"}
    observed = {"case-a": {"value": 2.02}, "case-b": {"value": 4.04, "facets": approximate}}
    strict = Store(tmp_path / "strict")
    world = _world(strict, signer, tmp_path / "s", observed)
    assert _determine(strict, signer, world)["status"] == "NOT_ESTABLISHED"
    lenient = Store(tmp_path / "lenient")
    world = _world(lenient, signer, tmp_path / "l", observed, accept_approximate=True)
    assert _determine(lenient, signer, world)["status"] == "SUPPORTED"


def test_failed_execution_is_inadmissible(store, signer, tmp_path):
    world = _world(store, signer, tmp_path, {"case-a": {"value": 2.02}, "case-b": {"value": 4.04, "outcome": "failed"}})
    determination = _determine(store, signer, world)
    assert _reason(store, determination, world["case-b"]) == "inadmissible: execution outcome failed"


def test_first_party_adapter_refused_when_the_scheme_requires_independence(store, signer, tmp_path):
    world = _world(store, signer, tmp_path, GOOD, first_party=False)
    determination = _determine(store, signer, world)
    assert determination["status"] == "NOT_ESTABLISHED"
    assert _reason(store, determination, world["case-a"]) == "inadmissible: first-party adapter not accepted by the scheme"


def test_calibration_data_cannot_validate(store, signer, tmp_path):
    world = _world(store, signer, tmp_path, {"case-a": {"value": 2.02}})
    data = store.put_blob(b"tensile test 1")
    store.put({"kind": "calibration", "publisher": "p", "target_artifact": world["artifact"], "data": [data], "parameters": {"E": 1.0}})
    run = make_run(tmp_path / "runs", "contaminated", 4.04)
    observations = ingest_run(store, signer, "p", run, world["case-b"], world["artifact"], world["adapter"])["observations"]
    [(_, clean)] = store.find("measurement_result", case=world["case-a"])
    contaminated = {**clean, "case": world["case-b"], "was_derived_from": [observations], "reference_data": [data]}
    store.put(contaminated)
    determination = _determine(store, signer, world)
    assert determination["status"] == "NOT_ESTABLISHED"
    assert _reason(store, determination, world["case-b"]) == f"inadmissible: reference data {data} was used in calibration"


def test_compatible_units_are_converted(store, signer, tmp_path):
    world = _world(store, signer, tmp_path, GOOD, entry="fixturepack:relative_error_percent")
    assert _determine(store, signer, world)["status"] == "SUPPORTED"


def test_incompatible_units_are_inadmissible(store, signer, tmp_path):
    world = _world(store, signer, tmp_path, GOOD, entry="fixturepack:relative_error_metres")
    determination = _determine(store, signer, world)
    assert determination["status"] == "NOT_ESTABLISHED"
    assert _reason(store, determination, world["case-a"]) == "inadmissible: unit 'm' cannot be converted to 'dimensionless'"


def test_unknown_requirement_is_out_of_scope(store, signer, tmp_path):
    world = _world(store, signer, tmp_path, GOOD)
    determination = _determine(store, signer, world, requirement="speed")
    assert determination["status"] == "OUT_OF_SCOPE"
    assert determination["notes"] == ["scheme has no requirement 'speed'"]


def test_pending_argument_is_noted_but_not_counted(store, signer, tmp_path):
    world = _world(store, signer, tmp_path, {"case-a": {"value": 2.02}})
    claim = store.put({"kind": "claim", "publisher": "p", "scheme": world["scheme"], "requirement": "accuracy", "artifact": world["artifact"]})
    pending = store.put({
        "kind": "argument", "publisher": "q", "claim": claim, "role": "supports", "pattern": "monotonic_extremum",
        "premises": [], "author": "q", "admissibility": "pending_review",
    })
    determination = _determine(store, signer, world)
    assert determination["status"] == "NOT_ESTABLISHED"
    assert "1 argument(s) pending review, not evaluated" in determination["notes"]
    assert pending in determination["used"]


def test_determination_is_deterministic_and_records_realizations(store, signer, tmp_path):
    world = _world(store, signer, tmp_path, GOOD)
    first = determine(store, signer, "p", world["scheme"], "accuracy", world["artifact"])
    second = determine(store, signer, "p", world["scheme"], "accuracy", world["artifact"])
    assert first == second
    realizations = {d for d, _ in store.iter_objects("realization")}
    assert realizations <= set(store.get(first)["used"])


def test_mislabelled_measurement_is_inadmissible(store, signer, tmp_path):
    world = _world(store, signer, tmp_path, {"case-a": {"value": 2.02}})
    run = make_run(tmp_path / "runs", "real-b", 4.4)
    ingest_run(store, signer, "p", run, world["case-b"], world["artifact"], world["adapter"])
    [(_, real)] = store.find("measurement_result", case=world["case-a"])
    store.put({**real, "case": world["case-b"]})
    determination = _determine(store, signer, world)
    assert determination["status"] == "NOT_ESTABLISHED"
    assert _reason(store, determination, world["case-b"]) == "inadmissible: measurement case does not match its execution"


def test_conflicting_realizations_are_inadmissible(store, signer, tmp_path):
    from helpers import PROCEDURE
    from terminus.measure import measure

    world = _world(store, signer, tmp_path, {"case-a": {"value": 2.02}})
    unsupported = {"physical": "exact", "material": "unsupported", "observation": "exact"}
    run = make_run(tmp_path / "runs", "b", 4.04, facets=unsupported)
    first = ingest_run(store, signer, "p", run, world["case-b"], world["artifact"], world["adapter"])
    measure(store, signer, "p", first["observations"], world["measurand"], PROCEDURE)
    exact = '{"facets": {"physical": "exact", "material": "exact", "observation": "exact"}}'
    (run / "out" / "realization.json").write_text(exact, encoding="utf-8")
    ingest_run(store, signer, "p", run, world["case-b"], world["artifact"], world["adapter"])
    determination = _determine(store, signer, world)
    assert determination["status"] == "NOT_ESTABLISHED"
    assert _reason(store, determination, world["case-b"]) == "inadmissible: conflicting realization records"


def test_unparseable_stored_unit_is_inadmissible_not_a_crash(store, signer, tmp_path):
    world = _world(store, signer, tmp_path, GOOD)
    [(_, real)] = store.find("measurement_result", case=world["case-b"])
    store.put({**real, "unit": "m**", "value": 0.02})
    determination = _determine(store, signer, world)
    assert determination["status"] == "SUPPORTED"


def _composite_world(store, signer, tmp_path, observed, second_limit, patterns=("all_cases_conform", "all_of")):
    from helpers import ADAPTER, ARTIFACT, MEASURAND, case_doc, scheme_doc, write_doc
    from terminus.publish import publish

    docs = tmp_path / "docs"
    world = {"measurand": publish(store, signer, "p", write_doc(docs, "measurand", MEASURAND))["object"]}
    for name, expected in (("case-a", 2.0), ("case-b", 4.0)):
        world[name] = publish(store, signer, "p", write_doc(docs, name, case_doc(name, expected)))["object"]
    scheme = scheme_doc(["case-a", "case-b"], patterns=patterns)
    scheme["requirements"].append({**scheme["requirements"][0], "id": "second", "predicate": {"operator": "le", "limit": second_limit}})
    scheme["claims"] = [{"id": "root", "all_of": ["accuracy", "second"]}]
    world["scheme"] = publish(store, signer, "p", write_doc(docs, "scheme", scheme))["object"]
    world["artifact"] = publish(store, signer, "p", write_doc(docs, "artifact", ARTIFACT))["object"]
    world["adapter"] = publish(store, signer, "p", write_doc(docs, "adapter", ADAPTER))["object"]
    qualify(store, signer, tmp_path / "runs", world, observed)
    return world


def test_all_of_supported_when_every_child_is(store, signer, tmp_path):
    world = _composite_world(store, signer, tmp_path, GOOD, second_limit=0.1)
    root = _determine(store, signer, world, requirement="root")
    assert root["status"] == "SUPPORTED"
    assert root["established_scope"] == sorted([world["case-a"], world["case-b"]])
    [argument] = [store.get(a) for a in root["arguments"]]
    assert argument["pattern"] == "all_of"
    assert [store.get(p)["status"] for p in argument["premises"]] == ["SUPPORTED", "SUPPORTED"]
    assert [r["finding"] for r in root["reasons"]] == ["SUPPORTED", "SUPPORTED"]
    for premise in argument["premises"]:
        assert store.statements(premise)


def test_all_of_failed_when_one_child_fails(store, signer, tmp_path):
    world = _composite_world(store, signer, tmp_path, {"case-a": {"value": 2.02}, "case-b": {"value": 4.4}}, second_limit=0.5)
    root = _determine(store, signer, world, requirement="root")
    assert root["status"] == "FAILED"
    assert root["established_scope"] == []
    [argument] = [store.get(a) for a in root["arguments"]]
    assert argument["role"] == "refutes"
    assert store.get(argument["witness"])["status"] == "FAILED"


def test_all_of_not_established_when_one_child_is_inconclusive(store, signer, tmp_path):
    world = _composite_world(store, signer, tmp_path, GOOD, second_limit=0.001)
    root = _determine(store, signer, world, requirement="root")
    assert root["status"] == "NOT_ESTABLISHED"
    assert root["arguments"] == []


def test_all_of_needs_the_pattern(store, signer, tmp_path):
    world = _composite_world(store, signer, tmp_path, GOOD, second_limit=0.1, patterns=("all_cases_conform",))
    root = _determine(store, signer, world, requirement="root")
    assert root["status"] == "NOT_ESTABLISHED"
    assert any("all_of" in note for note in root["notes"])
