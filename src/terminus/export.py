import json
from pathlib import Path

from prov.model import ProvDocument

from terminus.digest import hex_of, is_digest
from terminus.store import Store


class MissingObject(LookupError):
    pass


def references(value) -> set:
    if isinstance(value, dict):
        return set().union(*(references(item) for item in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(references(item) for item in value)) if value else set()
    return {value} if is_digest(value) else set()


def closure(store, root: str):
    objects, blobs, stack = set(), set(), [root]
    while stack:
        digest = stack.pop()
        if digest in objects or digest in blobs:
            continue
        if store.has(digest):
            objects.add(digest)
            stack.extend(references(store.get(digest)))
        elif store.has_blob(digest):
            blobs.add(digest)
        else:
            raise MissingObject(f"{digest} is referenced but not in the store")
    for digest, release in store.iter_objects("release"):
        if release["object"] in objects:
            objects.add(digest)
    return objects, blobs


def _prov(store, objects: set) -> str:
    doc = ProvDocument()
    doc.add_namespace("t", "urn:terminus:object:")
    for digest in sorted(objects):
        doc.entity(f"t:{hex_of(digest)}", {"prov:label": store.get(digest)["kind"]})
    for digest in sorted(objects):
        for reference in sorted(references(store.get(digest)) & objects):
            doc.wasDerivedFrom(f"t:{hex_of(digest)}", f"t:{hex_of(reference)}")
    return doc.serialize(format="json")


def export(store, root: str, directory) -> dict:
    objects, blobs = closure(store, root)
    target = Store(directory)
    publishers = set()
    for digest in sorted(objects):
        target.copy_object_from(store, digest)
        publishers.add(store.get(digest)["publisher"])
        for envelope in store.statements(digest):
            target.put_statement(digest, envelope)
    for digest in sorted(blobs):
        target.copy_blob_from(store, digest)
    keys = store.keys()
    for publisher in sorted(publishers & set(keys)):
        target.put_key(publisher, keys[publisher])
    manifest = {
        "root": root,
        "objects": {digest: store.get(digest)["kind"] for digest in sorted(objects)},
        "blobs": {digest: "included" for digest in sorted(blobs)},
    }
    directory = Path(directory)
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    (directory / "prov.json").write_text(_prov(store, objects), encoding="utf-8")
    return manifest
