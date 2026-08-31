from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np


@dataclass(frozen=True)
class FrameQualityPolicy:
    black_mean_max: float = 2.0
    black_std_max: float = 1.5
    freeze_mae_max: float = 0.45
    freeze_min_pairs: int = 3
    motion_context_min: float = 2.5
    timeline_tolerance_ratio: float = 0.20


@dataclass(frozen=True)
class FreezeInterval:
    start_frame: int
    end_frame: int
    pairs: int
    context_before: float | None
    context_after: float | None


@dataclass(frozen=True)
class TimelineIssue:
    kind: str
    index: int
    previous_pts: float
    current_pts: float
    delta: float


@dataclass(frozen=True)
class FrameQualityReport:
    frames: int
    black_frames: tuple[int, ...]
    freeze_intervals: tuple[FreezeInterval, ...]
    mean_luma: float
    mean_pair_mae: float

    @property
    def passed(self) -> bool:
        return not self.black_frames and not self.freeze_intervals

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["passed"] = self.passed
        return payload


def _as_luma(frame: np.ndarray) -> np.ndarray:
    array = np.asarray(frame)
    if array.ndim != 2:
        raise ValueError("frame de qualidade deve ser luma 2D")
    if not np.issubdtype(array.dtype, np.number):
        raise TypeError("frame de qualidade deve conter valores numéricos")
    return array.astype(np.float32, copy=False)


def frame_stats(frame: np.ndarray) -> tuple[float, float]:
    luma = _as_luma(frame)
    return float(np.mean(luma)), float(np.std(luma))


def pair_mae(left: np.ndarray, right: np.ndarray) -> float:
    a = _as_luma(left)
    b = _as_luma(right)
    if a.shape != b.shape:
        raise ValueError("frames possuem dimensões diferentes")
    return float(np.mean(np.abs(a - b)))


def analyze_luma_sequence(
    frames: Sequence[np.ndarray],
    policy: FrameQualityPolicy = FrameQualityPolicy(),
) -> FrameQualityReport:
    if not frames:
        return FrameQualityReport(0, (), (), 0.0, 0.0)
    normalized = [_as_luma(frame) for frame in frames]
    means: list[float] = []
    black: list[int] = []
    for index, frame in enumerate(normalized):
        mean, std = frame_stats(frame)
        means.append(mean)
        if mean <= policy.black_mean_max and std <= policy.black_std_max:
            black.append(index)
    diffs = [pair_mae(normalized[index], normalized[index + 1]) for index in range(len(normalized) - 1)]
    freezes: list[FreezeInterval] = []
    cursor = 0
    while cursor < len(diffs):
        if diffs[cursor] > policy.freeze_mae_max:
            cursor += 1
            continue
        start = cursor
        while cursor < len(diffs) and diffs[cursor] <= policy.freeze_mae_max:
            cursor += 1
        end = cursor - 1
        pairs = end - start + 1
        if pairs < policy.freeze_min_pairs:
            continue
        before = diffs[start - 1] if start > 0 else None
        after = diffs[cursor] if cursor < len(diffs) else None
        # A genuinely static shot is not a defect by itself. Flag a freeze only
        # when the low-motion run is bounded by evidence of real motion on at
        # least one side. This catches inserted frozen spans without punishing
        # titles, still photos or intentionally locked shots.
        context_motion = max(value for value in (before, after) if value is not None) if (before is not None or after is not None) else 0.0
        if context_motion >= policy.motion_context_min:
            freezes.append(
                FreezeInterval(
                    start_frame=start,
                    end_frame=end + 1,
                    pairs=pairs,
                    context_before=before,
                    context_after=after,
                )
            )
    return FrameQualityReport(
        frames=len(normalized),
        black_frames=tuple(black),
        freeze_intervals=tuple(freezes),
        mean_luma=float(np.mean(means)),
        mean_pair_mae=float(np.mean(diffs)) if diffs else 0.0,
    )


def analyze_timeline(
    pts_times: Iterable[float],
    fps: float,
    policy: FrameQualityPolicy = FrameQualityPolicy(),
) -> tuple[TimelineIssue, ...]:
    values = [float(value) for value in pts_times]
    if fps <= 0:
        raise ValueError("fps deve ser positivo")
    expected = 1.0 / fps
    tolerance = expected * policy.timeline_tolerance_ratio
    issues: list[TimelineIssue] = []
    for index in range(1, len(values)):
        previous = values[index - 1]
        current = values[index]
        delta = current - previous
        if delta <= tolerance:
            issues.append(TimelineIssue("duplicate_or_reverse", index, previous, current, delta))
        elif delta > expected + tolerance:
            issues.append(TimelineIssue("gap", index, previous, current, delta))
    return tuple(issues)


def decode_luma_frames(
    ffmpeg: str,
    path: Path,
    *,
    sample_width: int = 64,
    sample_height: int = 36,
    max_frames: int = 0,
) -> list[np.ndarray]:
    if sample_width <= 0 or sample_height <= 0:
        raise ValueError("sample dimensions devem ser positivas")
    command = [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-vf",
        f"scale={sample_width}:{sample_height}:flags=area,format=gray",
    ]
    if max_frames > 0:
        command += ["-frames:v", str(max_frames)]
    command += ["-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError((result.stderr or b"ffmpeg decode failed").decode("utf-8", errors="replace").strip())
    frame_bytes = sample_width * sample_height
    if frame_bytes <= 0 or len(result.stdout) % frame_bytes:
        raise RuntimeError("rawvideo de qualidade terminou truncado")
    frames: list[np.ndarray] = []
    for offset in range(0, len(result.stdout), frame_bytes):
        chunk = result.stdout[offset : offset + frame_bytes]
        frames.append(np.frombuffer(chunk, dtype=np.uint8).reshape(sample_height, sample_width).copy())
    return frames


def inspect_video_frames(
    ffmpeg: str,
    path: Path,
    *,
    policy: FrameQualityPolicy = FrameQualityPolicy(),
    max_frames: int = 0,
) -> FrameQualityReport:
    return analyze_luma_sequence(
        decode_luma_frames(ffmpeg, path, max_frames=max_frames),
        policy,
    )
