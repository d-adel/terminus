import json
from dataclasses import dataclass, field
from pathlib import Path

from terminus import measure
from terminus import determine as evaluator_module
from terminus.determine import build
from terminus.digest import digest_of, hex_of
from terminus.export import MissingObject, _prov, closure
from terminus.sign import SignatureInvalid, verify_envelope
from terminus.store import ObjectMismatch, Store


REPRODUCTION = 1.0e-9


def agreement(recomputed: tuple, stored: tuple):
    if recomputed == stored:
        return "identical"
    if recomputed[2] != stored[2]:
        return None
    scale = max(abs(stored[0]), abs(stored[1]))
    if abs(recomputed[0] - stored[0]) <= REPRODUCTION * scale and abs(recomputed[1] - stored[1]) <= REPRODUCTION * abs(stored[1]):
        return "rounding"
    return None


@dataclass
class Report:
    problems: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    determination_matches: bool = False
    measurements_rechecked: int = 0


def _check_keys(keys: dict, trusted, report: Report) -> None:
    for publisher, key in sorted(keys.items()):
        report.notes.append(f"publisher {publisher} signs with key {key['keyid']}")
        if trusted is None:
            continue
        if publisher not in trusted:
            report.problems.append(f"publisher {publisher}: no trusted key was given")
        elif trusted[publisher] != key["keyid"]:
            report.problems.append(f"publisher {publisher}: shipped key {key['keyid']} is not the trusted key {trusted[publisher]}")
    if trusted is None:
        report.notes.append("signatures were checked against the keys shipped in this export; pass trusted keys to check who signed")


def _check_statements(store, digest: str, obj: dict, keys: dict, report: Report) -> None:
    key = keys.get(obj["publisher"])
    if key is None:
        report.problems.append(f"{digest}: no key for publisher {obj['publisher']!r}")
        return
    envelopes = store.statements(digest)
    if not envelopes:
        report.problems.append(f"{digest}: no signed statement")
        return
    for envelope in envelopes:
        try:
            statement = verify_envelope(envelope, key)
        except SignatureInvalid as error:
            report.problems.append(f"{digest}: {error}")
            continue
        subject = statement["subject"][0]["digest"]["sha256"]
        if subject != hex_of(digest) or statement["predicate"].get("kind") != obj["kind"]:
            report.problems.append(f"{digest}: statement does not describe this object")


def _check_closure(store, directory: Path, manifest: dict, report: Report) -> None:
    try:
        objects, blobs = closure(store, manifest["root"])
    except (MissingObject, ObjectMismatch, FileNotFoundError) as error:
        report.problems.append(f"the export is not the complete closure of its root: {error}")
        return
    for digest in sorted(objects - set(manifest["objects"])):
        report.problems.append(f"{digest}: in the closure but not in the manifest")
    for digest in sorted(set(manifest["objects"]) - objects):
        report.problems.append(f"{digest}: in the manifest but not in the closure")
    for digest in sorted(blobs - set(manifest["blobs"])):
        report.problems.append(f"{digest}: blob in the closure but not in the manifest")
    for digest in sorted(blobs):
        try:
            store.read_blob(digest)
        except (ObjectMismatch, FileNotFoundError) as error:
            report.problems.append(f"{digest}: {error}")
    present_objects = {f"sha256:{path.stem}" for path in (directory / "objects").glob("*.json")}
    present_blobs = {f"sha256:{path.name}" for path in (directory / "blobs").iterdir() if not path.name.startswith(".")}
    for digest in sorted((present_objects - objects) | (present_blobs - blobs)):
        report.problems.append(f"{digest}: file is not in the closure of the root")
    prov = directory / "prov.json"
    if not prov.exists() or prov.read_text(encoding="utf-8") != _prov(store, objects):
        report.problems.append("prov.json does not match the exported objects")


def _rerun_measurements(store, objects: dict, report: Report, trusted=None) -> None:
    for digest, obj in sorted(objects.items()):
        if obj["kind"] != "measurement_result":
            continue
        if obj["procedure"].get("source") and (trusted is None or obj["publisher"] not in trusted):
            report.notes.append(f"{digest}: measurement not rechecked: its procedure is code shipped in the export; pass a trusted key for publisher {obj['publisher']} to run it")
            continue
        sources = [d for d in obj["was_derived_from"] if objects.get(d, {}).get("kind") == "observations"]
        if not sources:
            report.notes.append(f"{digest}: measurement not rechecked: no observations in the export")
            continue
        try:
            output, execution = measure.run_procedure(store, sources[0], obj["measurand"], obj["procedure"]["entry"], obj["procedure"].get("source"))
        except measure.ProcedureError as error:
            report.notes.append(f"{digest}: measurement not rechecked: {error}")
            continue
        if execution["case"] != obj["case"] or execution["artifact"] != obj["artifact"]:
            report.notes.append(f"{digest}: measurement not rechecked: its case or artifact does not match its execution, so the determination treats it as inadmissible")
            continue
        recomputed = (float(output["value"]), float(output["uncertainty"]), output["unit"])
        found = agreement(recomputed, (float(obj["value"]), float(obj["uncertainty"]), obj["unit"]))
        if found is None:
            report.problems.append(f"{digest}: rerunning {obj['procedure']['entry']} gives {recomputed}")
        else:
            if found == "rounding":
                report.notes.append(f"{digest}: rerun agrees within {REPRODUCTION:g} relative, not bit for bit; the platform's maths library rounds differently")
            report.measurements_rechecked += 1


def recheck(directory, rerun_measurements: bool = True, trusted=None) -> Report:
    directory = Path(directory)
    store = Store(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    report = Report()
    keys = store.keys()
    _check_keys(keys, trusted, report)
    intact = {}
    for digest in manifest["objects"]:
        try:
            intact[digest] = store.get(digest)
        except (ObjectMismatch, FileNotFoundError) as error:
            report.problems.append(f"{digest}: {error}")
    for digest, obj in intact.items():
        _check_statements(store, digest, obj, keys, report)
    for digest in manifest["blobs"]:
        try:
            store.read_blob(digest)
        except (ObjectMismatch, FileNotFoundError) as error:
            report.problems.append(f"{digest}: {error}")
    root = intact.get(manifest["root"])
    if root is None or root["kind"] != "determination":
        report.problems.append("the export's root is missing or is not a determination")
        return report
    if not report.problems:
        _check_closure(store, directory, manifest, report)
    if report.problems:
        report.notes.append("determination not recomputed: the export failed its integrity checks")
        return report
    claim = store.get(root["claim"])
    _, _, recomputed, _ = build(store, root["publisher"], claim["scheme"], claim["requirement"], claim["artifact"], evaluator=root["evaluator"])
    report.determination_matches = digest_of(recomputed) == digest_of(root)
    running = evaluator_module.EVALUATOR
    if root["evaluator"] != running:
        report.notes.append(f"exported with evaluator {root['evaluator']['name']} {root['evaluator']['version']}, rechecked with {running['name']} {running['version']}")
    if not report.determination_matches:
        report.problems.append(f"the determination does not follow from the exported evidence: recomputed status {recomputed['status']}")
    if rerun_measurements:
        _rerun_measurements(store, intact, report, trusted)
    return report
