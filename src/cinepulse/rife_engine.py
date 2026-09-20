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
        return self.executable.is_file() and self.model.is_dir()


def target_frame_count(duration: float, fps: float, minimum: int = 2) -> int:
    return max(minimum, round(max(0.0, duration) * max(1.0, fps)))


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
