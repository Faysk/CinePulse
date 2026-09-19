from __future__ import annotations

import json
from pathlib import Path

from .paths import PATHS


def _normalized_component(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _record_fingerprint(component: str, record: object) -> str:
    if not isinstance(record, dict):
        return ""
    version = str(record.get("version") or "").strip()
    sha256 = str(record.get("sha256") or "").strip().lower()
    if not version or len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256):
        return ""
    return f"{component}:{version}:{sha256}"


def bootstrap_component_fingerprint(
    component: str,
    *,
    root: Path | None = None,
    component_root: Path | None = None,
) -> str:
    """Return the release-locked identity for one bootstrapped component.

    Installed components carry a verified .cinepulse-component.json marker
    written only after archive SHA-256 and required-file checks. Runtime
    callers should pass that component directory so tuning evidence is bound
    to what is actually installed. Source/dev callers may fall back to the
    installer/bootstrap-manifest.json release manifest.
    """
    name = _normalized_component(component)
    if not name:
        return ""

    if component_root is not None:
        marker = Path(component_root) / ".cinepulse-component.json"
        try:
            state = json.loads(marker.read_text(encoding="utf-8-sig"))
        except (OSError, TypeError, ValueError):
            return ""
        if not isinstance(state, dict):
            return ""
        marker_key = _normalized_component(str(state.get("key") or ""))
        if marker_key != name:
            return ""
        return _record_fingerprint(name, state)

    manifest = (Path(root) if root is not None else PATHS.root) / "installer" / "bootstrap-manifest.json"
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8-sig"))
    except (OSError, TypeError, ValueError):
        return ""
    return _record_fingerprint(name, payload.get(name))
