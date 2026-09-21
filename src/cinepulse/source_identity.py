from __future__ import annotations

import hashlib
from pathlib import Path


FULL_HASH_LIMIT_BYTES = 32 * 1024 * 1024
SAMPLE_BYTES = 256 * 1024


def file_content_identity(path: Path) -> dict[str, object]:
    """Return a bounded content-aware identity for cache keys.

    Small files are hashed completely. Large media hashes five deterministic
    windows plus stable filesystem metadata so cache lookup stays bounded while
    replacements that preserve path/size/mtime do not silently reuse old work.
    """
    source = Path(path).expanduser()
    stat = source.stat()
    size = int(stat.st_size)
    digest = hashlib.sha256()
    mode = "full-sha256-v1"
    with source.open("rb") as stream:
        if size <= FULL_HASH_LIMIT_BYTES:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        else:
            mode = "sampled-sha256-v1"
            maximum = max(0, size - SAMPLE_BYTES)
            offsets = sorted({
                0,
                max(0, size // 4 - SAMPLE_BYTES // 2),
                max(0, size // 2 - SAMPLE_BYTES // 2),
                max(0, (size * 3) // 4 - SAMPLE_BYTES // 2),
                maximum,
            })
            for offset in offsets:
                stream.seek(offset)
                block = stream.read(min(SAMPLE_BYTES, max(0, size - offset)))
                digest.update(int(offset).to_bytes(8, "little", signed=False))
                digest.update(len(block).to_bytes(8, "little", signed=False))
                digest.update(block)
    return {
        "path": str(source.resolve()),
        "size": size,
        "mtime_ns": int(stat.st_mtime_ns),
        "ctime_ns": int(getattr(stat, "st_ctime_ns", 0)),
        "inode": int(getattr(stat, "st_ino", 0)),
        "content_mode": mode,
        "content_sha256": digest.hexdigest(),
    }
