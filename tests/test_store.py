import pytest

from terminus.store import ObjectMismatch, Store
from terminus.validate import InvalidObject

ART = {"kind": "artifact", "publisher": "p", "name": "solver", "repo": "example/solver", "commit": "a" * 40}


def test_put_get_roundtrip(store):
    digest = store.put(ART)
    assert store.get(digest) == ART
    assert store.has(digest)


def test_put_is_idempotent_across_key_order(store):
    assert store.put(ART) == store.put(dict(reversed(list(ART.items()))))


def test_put_rejects_invalid(store):
    with pytest.raises(InvalidObject):
        store.put({"kind": "artifact"})


def test_tampered_object_is_detected(store):
    digest = store.put(ART)
    path = store.object_path(digest)
    path.write_bytes(path.read_bytes().replace(b"solver", b"sorvel"))
    with pytest.raises(ObjectMismatch):
        store.get(digest)


def test_blobs(store):
    digest = store.put_blob(b"hello")
    assert store.has_blob(digest)
    assert store.read_blob(digest) == b"hello"


def test_missing_blob(store):
    with pytest.raises(FileNotFoundError):
        store.blob_path("sha256:" + "0" * 64)


def test_find_by_kind_and_field(store):
    digest = store.put(ART)
    store.put({**ART, "name": "other"})
    assert [d for d, _ in store.find("artifact", name="solver")] == [digest]


def test_statements_are_kept_per_subject(store):
    digest = store.put(ART)
    store.put_statement(digest, {"payload": "a"})
    store.put_statement(digest, {"payload": "b"})
    assert sorted(e["payload"] for e in store.statements(digest)) == ["a", "b"]


def test_keys_are_write_once(store):
    store.put_key("p", {"keyid": "1"})
    store.put_key("p", {"keyid": "1"})
    with pytest.raises(ObjectMismatch):
        store.put_key("p", {"keyid": "2"})
    assert store.keys() == {"p": {"keyid": "1"}}


def test_copy_between_stores(store, tmp_path):
    digest = store.put(ART)
    blob = store.put_blob(b"data")
    other = Store(tmp_path / "other")
    other.copy_object_from(store, digest)
    other.copy_blob_from(store, blob)
    assert other.get(digest) == ART
    assert other.read_blob(blob) == b"data"
