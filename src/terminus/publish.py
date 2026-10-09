import json
from pathlib import Path

import yaml

from terminus.digest import digest_of
from terminus.gather import unit_problem
from terminus.sign import attest
from terminus.validate import validate

REF_PREFIX = "ref:"


class ResolveError(LookupError):
    pass


def load_document(path) -> dict:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text) if path.suffix in (".yaml", ".yml") else json.loads(text)


def find_release(store, publisher: str, name: str, version: str):
    found = store.find("release", publisher=publisher, name=name, version=version)
    objects = sorted({release["object"] for _, release in found})
    if len(objects) > 1:
        raise ResolveError(f"{publisher}/{name}@{version} is ambiguous: released as {', '.join(objects)}")
    return found[0][1] if found else None


def resolve_ref(store, ref: str) -> str:
    body = ref[len(REF_PREFIX):] if ref.startswith(REF_PREFIX) else ref
    owner, _, version = body.rpartition("@")
    publisher, _, name = owner.partition("/")
    if not (publisher and name and version):
        raise ResolveError(f"bad reference {ref!r}; expected ref:publisher/name@version")
    release = find_release(store, publisher, name, version)
    if release is None:
        raise ResolveError(f"nothing released as {publisher}/{name}@{version}")
    return release["object"]


def resolve_refs(store, value):
    if isinstance(value, dict):
        return {key: resolve_refs(store, item) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_refs(store, item) for item in value]
    if isinstance(value, str) and value.startswith(REF_PREFIX):
        return resolve_ref(store, value)
    return value


def scheme_problem(doc: dict):
    claims = doc.get("claims", [])
    ids = [r["id"] for r in doc["requirements"]] + [c["id"] for c in claims]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        return f"ids are not unique: {', '.join(duplicates)}"
    known = set(ids)
    children = {c["id"]: c["all_of"] for c in claims}
    for claim in claims:
        if not claim["all_of"]:
            return f"claim {claim['id']} lists no children"
        unknown = sorted(set(claim["all_of"]) - known)
        if unknown:
            return f"claim {claim['id']} names unknown ids: {', '.join(unknown)}"

    def cycle_from(node, path):
        if node in path:
            return " -> ".join([*path, node])
        for child in children.get(node, []):
            found = cycle_from(child, [*path, node])
            if found:
                return found
        return None

    for claim in claims:
        found = cycle_from(claim["id"], [])
        if found:
            return f"claims form a cycle: {found}"
    return None


def publish(store, signer, publisher: str, path) -> dict:
    doc = resolve_refs(store, load_document(path))
    if not isinstance(doc, dict) or doc.get("publisher") != publisher:
        raise ValueError(f"{path}: the document's publisher must be {publisher!r}")
    if doc.get("kind") == "release":
        raise ValueError(f"{path}: releases are created by publishing the object itself, not published directly")
    validate(doc)
    if doc["kind"] == "measurand":
        problem = unit_problem(doc["unit"])
        if problem:
            raise ValueError(f"{path}: {problem}")
    if doc["kind"] == "scheme":
        problem = scheme_problem(doc)
        if problem:
            raise ValueError(f"{path}: {problem}")
    digest = digest_of(doc)
    named = "name" in doc and "version" in doc
    if named:
        existing = find_release(store, publisher, doc["name"], doc["version"])
        if existing is not None and existing["object"] != digest:
            raise ValueError(f"{publisher}/{doc['name']}@{doc['version']} is already released as {existing['object']}")
    store.put(doc)
    attest(store, signer, publisher, digest, doc["kind"])
    result = {"object": digest}
    if named:
        release = {
            "kind": "release", "publisher": publisher, "name": doc["name"], "version": doc["version"],
            "object": digest, "object_kind": doc["kind"],
        }
        result["release"] = store.put(release)
        attest(store, signer, publisher, result["release"], "release")
    return result
