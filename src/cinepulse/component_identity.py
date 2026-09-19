from __future__ import annotations

import json
from pathlib import Path

from .paths import PATHS


def bootstrap_component_fingerprint(
    component: str,
    *,
    root: Path | None = None,
) -> str:
    """Return the release-locked identity for one bootstrapped component.

    The bootstrap manifest already pins the archive with SHA-256. Using the
    manifest identity in hardware-tuning keys makes physical evidence stale as
    soon as a future release changes the component payload, even if executable
    or model directory names stay the same.
    """
    name = str(component or "").strip()
    if not name:
        return ""
    manifest = (Path(root) if root is not None else PATHS.root) / "installer" / "bootstrap-manifest.json"
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8-sig"))
    except (OSError, TypeError, ValueError):
        return ""
    record = payload.get(name)
    if not isinstance(record, dict):
        return ""
    version = str(record.get("version") or "").strip()
    sha256 = str(record.get("sha256") or "").strip().lower()
    if not version or len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256):
        return ""
    return f"{name}:{version}:{sha256}"
