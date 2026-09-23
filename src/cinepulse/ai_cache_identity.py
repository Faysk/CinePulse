from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .component_identity import bootstrap_component_fingerprint
from .source_identity import file_content_identity


def realesrgan_cache_key(
    source: str | Path,
    *,
    start_time: float,
    duration: float,
    source_fps: float,
    source_width: int,
    source_height: int,
    executable: Path,
    model_bin: Path,
    model_param: Path,
    component_fingerprint: str | None = None,
) -> str:
    """Return the single Real-ESRGAN cache identity shared by render and recovery."""
    source_path = Path(source)
    executable = Path(executable)
    model_bin = Path(model_bin)
    model_param = Path(model_param)
    if component_fingerprint is None:
        component_fingerprint = bootstrap_component_fingerprint(
            "real_esrgan",
            component_root=executable.parent,
            critical_files=(executable, model_bin, model_param),
        )
    identity = {
        "source": file_content_identity(source_path),
        "start": round(float(start_time), 5),
        "duration": round(float(duration), 5),
        "fps": round(float(source_fps), 5),
        "width": int(source_width),
        "height": int(source_height),
        "component": component_fingerprint or "unverified-component",
        "scale": 2,
    }
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]
