from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from .stage_adapter import AtomicStageAdapter, ValidationResult
from .stage_checkpoint import StageCheckpointStore


@dataclass(frozen=True)
class MediaUnitContract:
    width: int
    height: int
    fps: float
    codec: str | None = None
    pix_fmt: str | None = None
    min_frames: int = 1
    exact_frames: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _ratio(value: object) -> float:
    text = str(value or "0/0")
    if "/" in text:
        left, right = text.split("/", 1)
        try:
            denominator = float(right)
            return float(left) / denominator if denominator else 0.0
        except ValueError:
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def probe_media_unit(ffprobe: str, path: Path) -> dict:
    command = [
        ffprobe,
        "-v",
        "error",
        "-count_frames",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "ffprobe failed").strip())
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("ffprobe retornou estrutura inválida")
    return payload


def media_validator(ffprobe: str, contract: MediaUnitContract):
    def validate(path: Path) -> ValidationResult:
        try:
            info = probe_media_unit(ffprobe, path)
        except Exception as exc:
            return ValidationResult(False, {"error": f"probe:{type(exc).__name__}:{exc}"})
        video = next(
            (item for item in info.get("streams", []) if item.get("codec_type") == "video"),
            {},
        )
        width = int(video.get("width") or 0)
        height = int(video.get("height") or 0)
        fps = _ratio(video.get("avg_frame_rate")) or _ratio(video.get("r_frame_rate"))
        codec = str(video.get("codec_name") or "")
        pix_fmt = str(video.get("pix_fmt") or "")
        frames_raw = video.get("nb_read_frames") or video.get("nb_frames")
        try:
            frames = int(frames_raw)
        except (TypeError, ValueError):
            frames = 0
        details = {
            "width": width,
            "height": height,
            "fps": fps,
            "codec": codec,
            "pix_fmt": pix_fmt,
            "frames": frames,
        }
        errors: list[str] = []
        if (width, height) != (contract.width, contract.height):
            errors.append("size")
        if abs(fps - contract.fps) > 0.02:
            errors.append("fps")
        if contract.codec and codec != contract.codec:
            errors.append("codec")
        if contract.pix_fmt and pix_fmt != contract.pix_fmt:
            errors.append("pix_fmt")
        if frames < contract.min_frames:
            errors.append("frames_min")
        if contract.exact_frames is not None and frames != contract.exact_frames:
            errors.append("frames_exact")
        if errors:
            return ValidationResult(False, {**details, "errors": errors})
        return ValidationResult(True, details)

    return validate


class MediaStageAdapter(AtomicStageAdapter):
    """Media-aware stage adapter used by upscale/RIFE/master/delivery units."""

    def __init__(
        self,
        checkpoint: StageCheckpointStore,
        *,
        ffprobe: str,
        fault_hook=lambda _point, _unit: None,
    ) -> None:
        super().__init__(checkpoint, fault_hook=fault_hook)
        self.ffprobe = ffprobe

    def execute_media_unit(
        self,
        *,
        unit_id: str,
        ordinal: int,
        final: Path,
        producer,
        contract: MediaUnitContract,
        cleanup=None,
    ) -> Path:
        return self.execute_unit(
            unit_id=unit_id,
            ordinal=ordinal,
            final=final,
            producer=producer,
            validator=media_validator(self.ffprobe, contract),
            contract=contract.to_dict(),
            cleanup=cleanup,
        )
