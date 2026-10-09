import os
import copy
import json
from pathlib import Path

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from google.protobuf import json_format
from in_toto_attestation.v1.resource_descriptor import ResourceDescriptor
from in_toto_attestation.v1.statement import Statement
from securesystemslib.dsse import Envelope
from securesystemslib.signer import CryptoSigner, SSlibKey

from terminus.digest import canonical, hex_of

PAYLOAD_TYPE = "application/vnd.in-toto+json"
PREDICATE_TYPE = "urn:terminus:predicate:attest:v0"


class SignatureInvalid(RuntimeError):
    pass


def generate_key(keys_dir, publisher: str) -> Path:
    keys_dir = Path(keys_dir)
    keys_dir.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        keys_dir.chmod(0o700)
    path = keys_dir / f"{publisher}.pem"
    if path.exists():
        raise FileExistsError(path)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(CryptoSigner.generate_ed25519().private_bytes)
    return path


def load_signer(keys_dir, publisher: str) -> CryptoSigner:
    pem = (Path(keys_dir) / f"{publisher}.pem").read_bytes()
    return CryptoSigner(load_pem_private_key(pem, None))


def public_key_dict(signer: CryptoSigner) -> dict:
    key = signer.public_key
    return {"keyid": key.keyid, **key.to_dict()}


def make_statement(subject_digest: str, kind: str, publisher: str) -> dict:
    subject = ResourceDescriptor(name=kind, digest={"sha256": hex_of(subject_digest)})
    statement = Statement([subject.pb], PREDICATE_TYPE, {"kind": kind, "publisher": publisher})
    statement.validate()
    return json.loads(json_format.MessageToJson(statement.pb))


def sign_statement(signer: CryptoSigner, statement: dict) -> dict:
    envelope = Envelope(payload=canonical(statement), payload_type=PAYLOAD_TYPE, signatures={})
    envelope.sign(signer)
    return envelope.to_dict()


def verify_envelope(envelope: dict, key: dict) -> dict:
    public = SSlibKey.from_dict(key["keyid"], {k: v for k, v in key.items() if k != "keyid"})
    try:
        parsed = Envelope.from_dict(copy.deepcopy(envelope))
        parsed.verify([public], 1)
        return json.loads(parsed.payload)
    except Exception as error:
        raise SignatureInvalid(f"signature check failed: {error}") from error


def attest(store, signer: CryptoSigner, publisher: str, digest: str, kind: str) -> None:
    store.put_key(publisher, public_key_dict(signer))
    store.put_statement(digest, sign_statement(signer, make_statement(digest, kind, publisher)))
