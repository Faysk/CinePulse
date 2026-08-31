from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .frame_quality import FrameQualityPolicy, analyze_timeline, inspect_video_frames
from .media_stage_adapter import MediaUnitContract, media_validator
from .stage_adapter import ValidationResult


def probe_frame_pts(ffprobe: str, path: Path) -> list[float]:
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "frame=best_effort_timestamp_time",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "ffprobe pts failed").strip())
    payload = json.loads(result.stdout)
    values: list[float] = []
    for frame in payload.get("frames", []) if isinstance(payload, dict) else []:
        try:
            values.append(float(frame.get("best_effort_timestamp_time")))
        except (TypeError, ValueError):
            continue
    return values


def media_quality_validator(
    *,
    ffprobe: str,
    ffmpeg: str,
    contract: MediaUnitContract,
    policy: FrameQualityPolicy = FrameQualityPolicy(),
    inspect_frames: bool = True,
    inspect_timeline: bool = True,
):
    structural = media_validator(ffprobe, contract)

    def validate(path: Path) -> ValidationResult:
        base = structural(path)
        if not base.passed:
            return base
        details = dict(base.details)
        errors: list[str] = []
        if inspect_frames:
            try:
                report = inspect_video_frames(ffmpeg, path, policy=policy)
            except Exception as exc:
                return ValidationResult(False, {**details, "quality_error": f"{type(exc).__name__}: {exc}"})
            details["frame_quality"] = report.to_dict()
            if report.black_frames:
                errors.append("black_frames")
            if report.freeze_intervals:
                errors.append("unexpected_freeze")
        if inspect_timeline:
            try:
                pts = probe_frame_pts(ffprobe, path)
                timeline = analyze_timeline(pts, contract.fps, policy)
            except Exception as exc:
                return ValidationResult(False, {**details, "timeline_error": f"{type(exc).__name__}: {exc}"})
            details["timeline_issues"] = [issue.__dict__ for issue in timeline]
            if timeline:
                errors.append("timeline")
        if errors:
            details["quality_errors"] = errors
            return ValidationResult(False, details)
        return ValidationResult(True, details)

    return validate
