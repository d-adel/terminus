import pytest

from helpers import PROCEDURE, make_run, publish_world
from terminus.ingest import ingest_run
from terminus.measure import ProcedureError, measure


def _observations(store, signer, tmp_path, value=2.02):
    world = publish_world(store, signer, tmp_path / "docs")
    run = make_run(tmp_path / "runs", "r1", value)
    result = ingest_run(store, signer, "p", run, world["case-a"], world["artifact"], world["adapter"])
    return world, result["observations"]


def test_measure_records_result(store, signer, tmp_path):
    world, observations = _observations(store, signer, tmp_path)
    digest = measure(store, signer, "p", observations, world["measurand"], PROCEDURE)
    result = store.get(digest)
    assert result["case"] == world["case-a"]
    assert result["artifact"] == world["artifact"]
    assert abs(result["value"] - 0.01) < 1e-12
    assert result["uncertainty"] == 0.01
    assert result["unit"] == "dimensionless"
    assert result["procedure"] == PROCEDURE
    assert result["was_derived_from"] == [observations]
    assert store.statements(digest)


def test_nan_is_refused_clearly(store, signer, tmp_path):
    world, observations = _observations(store, signer, tmp_path)
    with pytest.raises(ProcedureError, match="not a finite number"):
        measure(store, signer, "p", observations, world["measurand"], {**PROCEDURE, "entry": "fixturepack:returns_nan"})


def test_missing_field_is_refused(store, signer, tmp_path):
    world, observations = _observations(store, signer, tmp_path)
    with pytest.raises(ProcedureError, match="no 'uncertainty'"):
        measure(store, signer, "p", observations, world["measurand"], {**PROCEDURE, "entry": "fixturepack:returns_nothing"})


@pytest.mark.parametrize("entry, message", [
    ("noformat", "is not module:function"),
    ("fixturepack:does_not_exist", "cannot be loaded"),
    ("no_such_module:relative_error", "cannot be loaded"),
])
def test_bad_entries(store, signer, tmp_path, entry, message):
    world, observations = _observations(store, signer, tmp_path)
    with pytest.raises(ProcedureError, match=message):
        measure(store, signer, "p", observations, world["measurand"], {**PROCEDURE, "entry": entry})


def test_malformed_unit_is_refused(store, signer, tmp_path):
    world, observations = _observations(store, signer, tmp_path)
    with pytest.raises(ProcedureError, match="unit"):
        measure(store, signer, "p", observations, world["measurand"], {**PROCEDURE, "entry": "fixturepack:relative_error_bad_unit"})


def source_tar(members) -> bytes:
    import io
    import tarfile

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for name, text in members.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _fixture_source():
    from pathlib import Path

    import fixturepack

    return Path(fixturepack.__file__).read_text(encoding="utf-8")


def _from_source(source, entry="sourcepack:relative_error"):
    return {"repo": "example/pack", "commit": "2" * 40, "entry": entry, "source": source}


def test_procedure_runs_from_source(store, signer, tmp_path):
    import importlib

    world, observations = _observations(store, signer, tmp_path)
    source = store.put_blob(source_tar({"sourcepack.py": _fixture_source()}))
    digest = measure(store, signer, "p", observations, world["measurand"], _from_source(source))
    assert store.get(digest)["value"] == pytest.approx(0.01)
    assert store.get(digest)["procedure"]["source"] == source
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("sourcepack")


def test_failing_procedure_from_source_reports_its_error(store, signer, tmp_path):
    world, observations = _observations(store, signer, tmp_path)
    source = store.put_blob(source_tar({"sourcepack.py": "def broken(files, problem, measurand):\n    raise ValueError('field is not uniaxial')\n"}))
    with pytest.raises(ProcedureError, match="field is not uniaxial"):
        measure(store, signer, "p", observations, world["measurand"], _from_source(source, "sourcepack:broken"))


def test_source_with_escaping_path_is_refused(store, signer, tmp_path):
    world, observations = _observations(store, signer, tmp_path)
    source = store.put_blob(source_tar({"../outside.py": "x = 1\n"}))
    with pytest.raises(ProcedureError, match="cannot be unpacked"):
        measure(store, signer, "p", observations, world["measurand"], _from_source(source))
