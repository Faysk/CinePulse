from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .source_identity import file_content_identity


FOCUS_STEMS = {
    "Graves": ("bass",),
    "Graves e batidas": ("bass", "drums"),
    "Médios": ("vocals", "other"),
    "Agudos": ("other",),
    "Batidas e ataques": ("drums",),
}


def stems_for_focus(focus: str) -> tuple[str, ...]:
    return FOCUS_STEMS.get(focus, ())


def demucs_model_identity(model_repo: Path | None, state_file: Path | None = None) -> str:
    payload: dict[str, object] = {"model": "htdemucs_ft"}
    if state_file is not None:
        try:
            state = json.loads(Path(state_file).read_text(encoding="utf-8-sig"))
        except (OSError, TypeError, ValueError):
            state = None
        if isinstance(state, dict):
            payload["runtime"] = {
                key: state.get(key)
                for key in (
                    "schema", "python", "demucs", "torch", "soundfile",
                    "cuda_runtime", "torch_index", "weights_fingerprint",
                )
            }
    if model_repo is not None:
        root = Path(model_repo)
        tracked = (
            "htdemucs_ft.yaml",
            "f7e0c4bc-ba3fe64a.th",
            "d12395a8-e57c48e6.th",
            "92cfc3b6-ef3bcb9c.th",
            "04573f0d-f3cf25b2.th",
        )
        files: dict[str, object] = {}
        for name in tracked:
            path = root / name
            try:
                stat = path.stat()
                files[name] = {"size": stat.st_size, "mtime": stat.st_mtime_ns}
            except OSError:
                files[name] = None
        payload["files"] = files
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def stem_cache_key(
    audio: Path,
    *,
    model_repo: Path | None = None,
    state_file: Path | None = None,
) -> str:
    payload = {
        "source": file_content_identity(audio),
        "model_identity": demucs_model_identity(model_repo, state_file),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]


def build_demucs_command(python: Path, model_repo: Path, output: Path, audio: Path, use_cpu: bool) -> list[str]:
    if not python.is_file() or not (model_repo / "htdemucs_ft.yaml").is_file():
        raise FileNotFoundError("Ambiente ou modelo local do Demucs não encontrado.")
    return [
        str(python), "-m", "demucs", "-n", "htdemucs_ft", "--repo", str(model_repo),
        "--device", "cpu" if use_cpu else "cuda", "--shifts", "1", "--overlap", "0.25",
        "--int24", "-j", "1", "-o", str(output), str(audio),
    ]

