from __future__ import annotations

import sys
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


def build_command(
    paths: RifePaths,
    incoming: Path,
    outgoing: Path,
    frames: int,
    use_cpu: bool,
) -> list[str]:
    """Build the crash-safe CinePulse RIFE wrapper command.

    The wrapper intentionally owns the neural invocation instead of exposing a
    raw ``rife-ncnn-vulkan`` command to Studio.  It generates the native 2x
    frame count first, uses conservative UHD execution when required, validates
    every produced PNG, and only then retimes a residual target such as 17/18
    frames.  Existing callers keep the same API and therefore inherit the
    safety policy without duplicating it in UI/orchestration code.
    """

    if not paths.available:
        raise FileNotFoundError("Executável ou modelo RIFE não encontrado.")
    if frames < 2:
        raise ValueError("RIFE requer ao menos dois quadros de saída.")
    return [
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
