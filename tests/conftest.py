import pytest

from terminus.sign import generate_key, load_signer
from terminus.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "store")


@pytest.fixture
def signer(tmp_path):
    generate_key(tmp_path / "keys", "p")
    return load_signer(tmp_path / "keys", "p")
