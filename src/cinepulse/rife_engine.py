from __future__ import annotations

import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


SAFE_RUNNER_MODULE = "cinepulse.rife_safe_runner"


@dataclass(frozen=True)
class RifePaths:
    executable: Path
    model: Path

    @property
    def available(self) -> bool:
        required = (
            self.executable,
            self.model / "flownet.bin",
            self.model / "flownet.param",
        )
        try:
            return all(path.is_file() and path.stat().st_size > 0 for path in required)
        except OSError:
            return False


def target_frame_count(duration: float, fps: float, minimum: int = 2) -> int:
    return max(minimum, round(max(0.0, duration) * max(1.0, fps)))


def distributed_chunk_target_count(
    *,
    source_after: int,
    total_source: int,
    produced_target: int,
    total_target: int,
    minimum: int = 2,
) -> int:
    """Allocate this chunk from the cumulative source-to-target frame contract.

    Independent per-chunk rounding drifts on rates such as 60000/1001 to 120.
    Rounding the cumulative target position instead distributes the residual
    across chunks and guarantees that the final chunk reaches total_target.
    """

    total_source = max(1, int(total_source))
    total_target = max(0, int(total_target))
    produced_target = max(0, int(produced_target))
    source_after = max(0, min(total_source, int(source_after)))
    remaining = max(0, total_target - produced_target)
    if remaining <= 0:
        return 0
    target_after = total_target if source_after >= total_source else round(
        source_after / total_source * total_target
    )
    desired = max(0, target_after - produced_target)
    if desired < int(minimum):
        raise ValueError(
            f"RIFE chunk target would be {desired} frame(s), below minimum {minimum}"
        )
    return min(remaining, desired)

def timed_concat_manifest(
    segments: Iterable[Path],
    frame_counts: Iterable[int],
    fps: float,
) -> str:
    """Build an FFmpeg concat manifest from exact frame-count durations."""

    segment_list = tuple(Path(item) for item in segments)
    count_list = tuple(int(value) for value in frame_counts)
    if len(segment_list) != len(count_list):
        raise ValueError("segments and frame_counts must have the same length")
    if float(fps) <= 0:
        raise ValueError("fps must be positive")
    lines: list[str] = []
    for segment, frame_count in zip(segment_list, count_list, strict=True):
        if frame_count <= 0:
            raise ValueError(f"{segment.name}: frame count must be positive")
        escaped = str(segment.resolve()).replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
        lines.append(f"duration {frame_count / float(fps):.12f}")
    return "\n".join(lines) + "\n"

def applied_jobs_from_log(lines: Iterable[str]) -> str:
    """Return the last successful RIFE jobs policy reported by the safe runner."""
    for line in reversed(tuple(lines)):
        if not str(line).startswith("CINEPULSE_RIFE_SAFE APPLIED "):
            continue
        for token in str(line).split():
            if not token.startswith("jobs="):
                continue
            jobs = token.partition("=")[2].strip()
            parts = jobs.split(":")
            try:
                values = tuple(int(value) for value in parts)
            except ValueError:
                return ""
            if len(values) == 3 and all(1 <= value <= 8 for value in values):
                return jobs
            return ""
    return ""


def build_command(
    paths: RifePaths,
    incoming: Path,
    outgoing: Path,
    frames: int,
    use_cpu: bool,
    *,
    component_fingerprint: str = "",
    jobs_override: str = "",
    gpu_index: int | None = None,
) -> list[str]:
    """Build the crash-safe CinePulse RIFE wrapper command.

    The wrapper intentionally owns the neural invocation instead of exposing a
    raw ``rife-ncnn-vulkan`` command to Studio. It generates the native 2x
    frame count first, starts from the full-utilization policy, validates every
    produced PNG, and only then retimes a residual target such as 17/18 frames.
    ``jobs_override`` carries a lower-pressure policy already proven necessary
    by an earlier chunk in the same render; it never raises concurrency.
    """

    if not paths.available:
        raise FileNotFoundError("Executável ou modelo RIFE não encontrado.")
    if frames < 2:
        raise ValueError("RIFE requer ao menos dois quadros de saída.")
    command = [
        sys.executable,
        "-m",
        SAFE_RUNNER_MODULE,
        "--rife",
        str(paths.executable),
        "--model",
        str(paths.model),
        "--input",
        str(incoming),
        "--output",
        str(outgoing),
        "--frames",
        str(frames),
        "--device",
        "cpu" if use_cpu else "gpu",
    ]
    if component_fingerprint:
        command += ["--component-fingerprint", str(component_fingerprint)]
    if jobs_override and not use_cpu:
        command += ["--jobs-override", str(jobs_override)]
    if gpu_index is not None and not use_cpu:
        command += ["--gpu-index", str(max(0, int(gpu_index)))]
    return command
