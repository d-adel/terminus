import json

from helpers import ADAPTER, ARTIFACT, MEASURAND, case_doc, make_run, scheme_doc, write_doc
from terminus.cli import main


def test_end_to_end(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TERMINUS_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("TERMINUS_KEYS", str(tmp_path / "keys"))
    monkeypatch.setenv("TERMINUS_PUBLISHER", "p")

    def run(*args):
        capsys.readouterr()
        code = main(list(args))
        return code, capsys.readouterr().out

    assert run("keygen")[0] == 0
    docs = tmp_path / "docs"
    for name, doc in [
        ("measurand", MEASURAND),
        ("case-a", case_doc("case-a", 2.0)),
        ("case-b", case_doc("case-b", 4.0)),
        ("scheme", scheme_doc(["case-a", "case-b"])),
        ("adapter", ADAPTER),
    ]:
        assert run("publish", str(write_doc(docs, name, doc)))[0] == 0
    code, out = run("publish", str(write_doc(docs, "artifact", ARTIFACT)))
    artifact = json.loads(out)["object"]

    for case, value in (("case-a", 2.02), ("case-b", 4.04)):
        run_dir = make_run(tmp_path / "runs", case, value)
        code, out = run("ingest", str(run_dir), "--case", f"ref:p/{case}@1", "--artifact", artifact, "--adapter", "ref:p/solver-adapter@1")
        assert code == 0
        observations = json.loads(out)["observations"]
        code, _ = run("measure", observations, "--measurand", "ref:p/relative-error@1", "--entry", "fixturepack:relative_error",
                      "--procedure-repo", "example/pack", "--procedure-commit", "2" * 40)
        assert code == 0

    code, out = run("evaluate", "--scheme", "ref:p/reference@1", "--requirement", "accuracy", "--artifact", artifact)
    result = json.loads(out)
    assert result["status"] == "SUPPORTED"

    code, out = run("show", result["determination"], "--gsn", str(tmp_path / "tree.yaml"))
    assert out.startswith("SUPPORTED")
    assert (tmp_path / "tree.yaml").exists()

    code, out = run("diff", result["determination"], result["determination"])
    assert out.strip() == "no changes"

    assert run("export", result["determination"], str(tmp_path / "export"))[0] == 0
    code, out = run("recheck", str(tmp_path / "export"))
    assert code == 0
    assert out.strip().endswith("OK")

    keyid = json.loads((tmp_path / "export" / "keys" / "p.json").read_bytes())["keyid"]
    code, out = run("recheck", str(tmp_path / "export"), "--trust", f"p={keyid}")
    assert code == 0
    code, out = run("recheck", str(tmp_path / "export"), "--trust", "p=" + "0" * 64)
    assert code == 1
    assert "not the trusted key" in out


def test_recheck_fails_on_a_tampered_export(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TERMINUS_STORE", str(tmp_path / "store"))
    (tmp_path / "export" / "objects").mkdir(parents=True)
    (tmp_path / "export" / "manifest.json").write_text(json.dumps({"root": "sha256:" + "0" * 64, "objects": {}, "blobs": {}}), encoding="utf-8")
    code = main(["recheck", str(tmp_path / "export")])
    assert code == 1
    assert capsys.readouterr().out.strip().endswith("FAILED")


def test_writing_commands_need_a_publisher(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("TERMINUS_PUBLISHER", raising=False)
    monkeypatch.setenv("TERMINUS_KEYS", str(tmp_path / "keys"))
    try:
        main(["keygen"])
    except SystemExit as error:
        assert "publisher" in str(error)
    else:
        raise AssertionError("keygen without a publisher must exit")
