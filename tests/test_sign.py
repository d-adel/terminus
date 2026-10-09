import base64
import os

import pytest

from terminus.sign import SignatureInvalid, attest, generate_key, load_signer, public_key_dict, verify_envelope

ART = {"kind": "artifact", "publisher": "p", "name": "solver", "repo": "example/solver", "commit": "a" * 40}


def test_key_roundtrip(tmp_path):
    path = generate_key(tmp_path, "alice")
    first = public_key_dict(load_signer(tmp_path, "alice"))
    second = public_key_dict(load_signer(tmp_path, "alice"))
    assert path.exists()
    assert first["keyid"] == second["keyid"]


def test_generate_refuses_overwrite(tmp_path):
    generate_key(tmp_path, "alice")
    with pytest.raises(FileExistsError):
        generate_key(tmp_path, "alice")


def test_attest_and_verify(store, signer):
    digest = store.put(ART)
    attest(store, signer, "p", digest, "artifact")
    [envelope] = store.statements(digest)
    statement = verify_envelope(envelope, store.keys()["p"])
    assert statement["subject"][0]["digest"]["sha256"] == digest.split(":")[1]
    assert statement["predicateType"] == "urn:terminus:predicate:attest:v0"
    assert statement["predicate"] == {"kind": "artifact", "publisher": "p"}


def test_attest_twice_is_idempotent(store, signer):
    digest = store.put(ART)
    attest(store, signer, "p", digest, "artifact")
    attest(store, signer, "p", digest, "artifact")
    assert len(store.statements(digest)) == 1


def test_tampered_payload_fails(store, signer):
    digest = store.put(ART)
    attest(store, signer, "p", digest, "artifact")
    [envelope] = store.statements(digest)
    envelope["payload"] = base64.b64encode(b'{"forged":true}').decode()
    with pytest.raises(SignatureInvalid):
        verify_envelope(envelope, store.keys()["p"])


def test_other_key_fails(store, signer, tmp_path):
    digest = store.put(ART)
    attest(store, signer, "p", digest, "artifact")
    [envelope] = store.statements(digest)
    generate_key(tmp_path / "other", "bob")
    with pytest.raises(SignatureInvalid):
        verify_envelope(envelope, public_key_dict(load_signer(tmp_path / "other", "bob")))


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_private_key_is_readable_only_by_its_owner(tmp_path):
    from terminus.sign import generate_key

    path = generate_key(tmp_path / "keys", "owner")
    assert path.stat().st_mode & 0o077 == 0
    assert (tmp_path / "keys").stat().st_mode & 0o077 == 0
