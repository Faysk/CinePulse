from __future__ import annotations

import hashlib
import json
from pathlib import Path


FOCUS_STEMS = {
    "Graves": ("bass",),
    "Graves e batidas": ("bass", "drums"),
    "Médios": ("vocals", "other"),
    "Agudos": ("other",),
    "Batidas e ataques": ("drums",),
}


def stems_for_focus(focus: str) -> tuple[str, ...]:
    return FOCUS_STEMS.get(focus, ())


def stem_cache_key(audio: Path) -> str:
    stat = audio.stat()
    payload = {"path": str(audio.resolve()), "size": stat.st_size, "mtime": stat.st_mtime_ns, "model": "htdemucs_ft"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]


def build_demucs_command(python: Path, model_repo: Path, output: Path, audio: Path, use_cpu: bool) -> list[str]:
    if not python.is_file() or not (model_repo / "htdemucs_ft.yaml").is_file():
        raise FileNotFoundError("Ambiente ou modelo local do Demucs não encontrado.")
    return [
        str(python), "-m", "demucs", "-n", "htdemucs_ft", "--repo", str(model_repo),
        "--device", "cpu" if use_cpu else "cuda", "--shifts", "1", "--overlap", "0.25",
        "--int24", "-j", "1", "-o", str(output), str(audio),
    ]

