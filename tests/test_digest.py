import pytest

from terminus.digest import canonical, digest_bytes, digest_of, hex_of, is_digest


def test_key_order_does_not_change_digest():
    assert digest_of({"b": 1, "a": [1, 2]}) == digest_of({"a": [1, 2], "b": 1})


def test_canonical_form_is_rfc8785():
    assert canonical({"b": 1, "a": 3.0}) == b'{"a":3,"b":1}'


def test_digest_format():
    digest = digest_bytes(b"x")
    assert is_digest(digest)
    assert digest == "sha256:2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"


def test_hex_of_rejects_non_digest():
    with pytest.raises(ValueError):
        hex_of("sha256:xyz")


def test_nan_is_rejected():
    with pytest.raises(ValueError):
        digest_of({"v": float("nan")})
