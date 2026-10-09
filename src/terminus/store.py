import json
import os
import tempfile
from pathlib import Path

from terminus.digest import canonical, digest_bytes, digest_of, hex_of
from terminus.validate import validate


class ObjectMismatch(RuntimeError):
    pass


class Store:
    def __init__(self, root):
        self.root = Path(root)
        for sub in ("objects", "blobs", "statements", "keys"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    def object_path(self, digest: str) -> Path:
        return self.root / "objects" / f"{hex_of(digest)}.json"

    def _blob_file(self, digest: str) -> Path:
        return self.root / "blobs" / hex_of(digest)

    def _write_once(self, path: Path, data: bytes) -> None:
        if path.exists():
            if path.read_bytes() != data:
                raise ObjectMismatch(f"{path.name} already exists with different content")
            return
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)

    def put(self, obj: dict) -> str:
        validate(obj)
        data = canonical(obj)
        digest = digest_bytes(data)
        self._write_once(self.object_path(digest), data)
        return digest

    def get(self, digest: str) -> dict:
        path = self.object_path(digest)
        data = path.read_bytes()
        if digest_bytes(data) != digest:
            raise ObjectMismatch(f"{path.name} does not match its digest")
        return json.loads(data)

    def has(self, digest: str) -> bool:
        return self.object_path(digest).exists()

    def put_blob(self, data: bytes) -> str:
        digest = digest_bytes(data)
        self._write_once(self._blob_file(digest), data)
        return digest

    def has_blob(self, digest: str) -> bool:
        return self._blob_file(digest).exists()

    def blob_path(self, digest: str) -> Path:
        path = self._blob_file(digest)
        if not path.exists():
            raise FileNotFoundError(f"no blob {digest}")
        return path

    def read_blob(self, digest: str) -> bytes:
        data = self.blob_path(digest).read_bytes()
        if digest_bytes(data) != digest:
            raise ObjectMismatch(f"blob {digest} does not match its digest")
        return data

    def put_statement(self, subject: str, envelope: dict) -> None:
        name = f"{hex_of(subject)}.{hex_of(digest_of(envelope))[:16]}.dsse.json"
        self._write_once(self.root / "statements" / name, canonical(envelope))

    def statements(self, subject: str) -> list:
        pattern = f"{hex_of(subject)}.*.dsse.json"
        return [json.loads(path.read_bytes()) for path in sorted((self.root / "statements").glob(pattern))]

    def put_key(self, publisher: str, key: dict) -> None:
        self._write_once(self.root / "keys" / f"{publisher}.json", canonical(key))

    def keys(self) -> dict:
        return {path.stem: json.loads(path.read_bytes()) for path in sorted((self.root / "keys").glob("*.json"))}

    def iter_objects(self, kind=None):
        for path in sorted((self.root / "objects").glob("*.json")):
            obj = json.loads(path.read_bytes())
            if kind is None or obj.get("kind") == kind:
                yield f"sha256:{path.stem}", obj

    def find(self, kind, **fields) -> list:
        return [(d, o) for d, o in self.iter_objects(kind) if all(o.get(k) == v for k, v in fields.items())]

    def copy_object_from(self, other, digest: str) -> None:
        self._write_once(self.object_path(digest), other.object_path(digest).read_bytes())

    def copy_blob_from(self, other, digest: str) -> None:
        self._write_once(self._blob_file(digest), other.blob_path(digest).read_bytes())
