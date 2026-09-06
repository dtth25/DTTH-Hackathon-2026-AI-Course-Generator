"""Content-addressed, scope-isolated cache for explicit embedding vectors."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import struct
import tempfile


_MAGIC = b"HGEMB01\0"
_HEADER = struct.Struct("!8sI")


def embedding_key(
    text: str,
    model: str,
    dimensions: int,
    normalization_version: str,
) -> str:
    """Hash the complete provider input and every vector identity field."""
    payload = json.dumps(
        [model, dimensions, normalization_version, text],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class EmbeddingCache:
    """Store validated float64 vectors below a hashed, untrusted scope name."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def path_for(self, cache_scope: str, key: str) -> Path:
        scope_hash = hashlib.sha256(cache_scope.encode("utf-8")).hexdigest()
        return self.root / scope_hash / f"{key}.bin"

    def get(self, cache_scope: str, key: str, dimensions: int) -> list[float] | None:
        path = self.path_for(cache_scope, key)
        try:
            raw = path.read_bytes()
            if len(raw) < _HEADER.size:
                return None
            magic, stored_dimensions = _HEADER.unpack_from(raw)
            if magic != _MAGIC or stored_dimensions != dimensions:
                return None
            expected_size = _HEADER.size + dimensions * 8
            if len(raw) != expected_size:
                return None
            vector = list(struct.unpack(f"!{dimensions}d", raw[_HEADER.size :]))
            if not all(math.isfinite(value) for value in vector):
                return None
            return vector
        except (OSError, ValueError, struct.error):
            return None

    def put(self, cache_scope: str, key: str, vector: list[float], dimensions: int) -> None:
        if len(vector) != dimensions or not all(math.isfinite(value) for value in vector):
            raise ValueError("Embedding cache accepts only finite vectors of the requested dimension")
        path = self.path_for(cache_scope, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _HEADER.pack(_MAGIC, dimensions) + struct.pack(f"!{dimensions}d", *vector)
        temporary_name: str | None = None
        try:
            # Keep the temporary basename short for Windows' legacy MAX_PATH boundary.
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".tmp-", delete=False) as handle:
                temporary_name = handle.name
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        finally:
            if temporary_name:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass
