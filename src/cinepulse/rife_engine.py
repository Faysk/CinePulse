from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
    if not paths.available:
        raise FileNotFoundError("Executável ou modelo RIFE não encontrado.")
    if frames < 2:
        raise ValueError("RIFE requer ao menos dois quadros de saída.")
    return [
        str(paths.executable),
        "-i", str(incoming),
        "-o", str(outgoing),
        "-n", str(frames),
        "-m", str(paths.model),
        "-g", "-1" if use_cpu else "0",
        "-j", "1:2:2" if use_cpu else "2:2:2",
        "-f", "%08d.png",
    ]

