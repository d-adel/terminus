import hashlib
import re

import rfc8785

DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def canonical(obj: dict) -> bytes:
    return rfc8785.dumps(obj)


def digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def digest_of(obj: dict) -> str:
    return digest_bytes(canonical(obj))


def is_digest(value) -> bool:
    return isinstance(value, str) and DIGEST_PATTERN.match(value) is not None


def hex_of(digest: str) -> str:
    if not is_digest(digest):
        raise ValueError(f"not a digest: {digest!r}")
    return digest.split(":", 1)[1]
