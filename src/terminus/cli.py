import argparse
import json
import os
import sys
from pathlib import Path

import yaml

from terminus.determine import determine
from terminus.diff import diff
from terminus.export import export
from terminus.ingest import ingest_run
from terminus.measure import measure
from terminus.publish import publish, resolve_ref
from terminus.recheck import recheck
from terminus.run import run as run_claim
from terminus.show import render, to_gsn
from terminus.sign import generate_key, load_signer
from terminus.store import Store


def _publisher(args) -> str:
    if not args.publisher:
        raise SystemExit("terminus: set --publisher or TERMINUS_PUBLISHER")
    return args.publisher


def _store(args) -> Store:
    return Store(args.store)


def _signer(args):
    return load_signer(args.keys, _publisher(args))


def _ref(store, value: str) -> str:
    return resolve_ref(store, value) if value.startswith("ref:") else value


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


def cmd_keygen(args) -> int:
    _print({"key": str(generate_key(args.keys, _publisher(args)))})
    return 0


def cmd_publish(args) -> int:
    _print(publish(_store(args), _signer(args), _publisher(args), args.file))
    return 0


def cmd_ingest(args) -> int:
    store = _store(args)
    _print(ingest_run(store, _signer(args), _publisher(args), args.run_dir,
                      _ref(store, args.case), _ref(store, args.artifact), _ref(store, args.adapter)))
    return 0


def cmd_measure(args) -> int:
    store = _store(args)
    procedure = {"repo": args.procedure_repo, "commit": args.procedure_commit, "entry": args.entry}
    _print({"measurement": measure(store, _signer(args), _publisher(args), _ref(store, args.observations), _ref(store, args.measurand), procedure)})
    return 0


def cmd_evaluate(args) -> int:
    store = _store(args)
    digest = determine(store, _signer(args), _publisher(args), _ref(store, args.scheme), args.requirement, _ref(store, args.artifact))
    _print({"determination": digest, "status": store.get(digest)["status"]})
    return 0


def cmd_show(args) -> int:
    store = _store(args)
    print(render(store, args.determination))
    if args.gsn:
        Path(args.gsn).write_text(yaml.safe_dump(to_gsn(store, args.determination), sort_keys=False, allow_unicode=True), encoding="utf-8")
    return 0


def cmd_diff(args) -> int:
    for line in diff(_store(args), args.a, args.b) or ["no changes"]:
        print(line)
    return 0


def cmd_export(args) -> int:
    manifest = export(_store(args), args.determination, args.directory)
    _print({"root": manifest["root"], "objects": len(manifest["objects"]), "blobs": len(manifest["blobs"])})
    return 0


def cmd_recheck(args) -> int:
    trusted = None
    if args.trust:
        trusted = {}
        for item in args.trust:
            publisher, _, keyid = item.partition("=")
            if not publisher or not keyid:
                raise SystemExit(f"terminus: --trust expects PUBLISHER=KEYID, got {item!r}")
            trusted[publisher] = keyid
    report = recheck(args.directory, rerun_measurements=not args.no_measurements, trusted=trusted)
    for problem in report.problems:
        print(f"problem: {problem}")
    for note in report.notes:
        print(f"note: {note}")
    passed = not report.problems and report.determination_matches
    print("OK" if passed else "FAILED")
    return 0 if passed else 1


def cmd_run(args) -> int:
    store = _store(args)
    lab_cli = os.environ.get("TERMINUS_LAB_CLI")
    if not lab_cli:
        raise SystemExit("terminus: set TERMINUS_LAB_CLI to the lab command-line script")
    digest = run_claim(store, _signer(args), _publisher(args), args.scheme, args.claim, args.artifact, args.adapter,
                       args.pack, args.pack_repo, args.pack_commit, args.on, lab_cli=lab_cli,
                       results=os.environ.get("TERMINUS_LAB_RESULTS", "/srv/lab/results"), timeout=args.timeout,
                       memory=args.memory)
    _print({"determination": digest, "status": store.get(digest)["status"]})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="terminus")
    parser.add_argument("--store", default=os.environ.get("TERMINUS_STORE", "terminus-store"))
    parser.add_argument("--keys", default=os.environ.get("TERMINUS_KEYS", str(Path.home() / ".terminus" / "keys")))
    parser.add_argument("--publisher", default=os.environ.get("TERMINUS_PUBLISHER"))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("keygen").set_defaults(func=cmd_keygen)

    p = sub.add_parser("publish")
    p.add_argument("file")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("ingest")
    p.add_argument("run_dir")
    p.add_argument("--case", required=True)
    p.add_argument("--artifact", required=True)
    p.add_argument("--adapter", required=True)
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("measure")
    p.add_argument("observations")
    p.add_argument("--measurand", required=True)
    p.add_argument("--entry", required=True)
    p.add_argument("--procedure-repo", required=True)
    p.add_argument("--procedure-commit", required=True)
    p.set_defaults(func=cmd_measure)

    p = sub.add_parser("evaluate")
    p.add_argument("--scheme", required=True)
    p.add_argument("--requirement", required=True)
    p.add_argument("--artifact", required=True)
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("show")
    p.add_argument("determination")
    p.add_argument("--gsn")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("diff")
    p.add_argument("a")
    p.add_argument("b")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("export")
    p.add_argument("determination")
    p.add_argument("directory")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("run")
    for flag in ("--scheme", "--claim", "--artifact", "--adapter", "--pack", "--pack-repo", "--pack-commit"):
        p.add_argument(flag, required=True)
    p.add_argument("--on", required=True)
    p.add_argument("--timeout", type=float, default=1800.0)
    p.add_argument("--memory", type=int, help="MB for each case's lab task; the lab default otherwise")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("recheck")
    p.add_argument("directory")
    p.add_argument("--no-measurements", action="store_true")
    p.add_argument("--trust", action="append", metavar="PUBLISHER=KEYID")
    p.set_defaults(func=cmd_recheck)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
