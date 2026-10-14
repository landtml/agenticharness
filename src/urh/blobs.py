"""Content-addressed blob store for model inputs/outputs and full tool output."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from typing import Any


class BlobStore:
    def __init__(self, root: str | os.PathLike[str]):
        self.root = os.fspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _path(self, digest: str) -> str:
        return os.path.join(self.root, digest[:2], digest)

    def put_bytes(self, data: bytes) -> str:
        digest = hashlib.sha256(data).hexdigest()
        path = self._path(digest)
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            # unique per writer: threads and processes may store the same blob at once
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=f"{digest[:8]}.", suffix=".tmp")
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        return digest

    def put_json(self, obj: Any) -> str:
        return self.put_bytes(json.dumps(obj, sort_keys=True, default=str).encode())

    def get_bytes(self, digest: str) -> bytes:
        with open(self._path(digest), "rb") as f:
            return f.read()

    def get_json(self, digest: str) -> Any:
        return json.loads(self.get_bytes(digest))
