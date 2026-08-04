from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import asdict, dataclass


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


@dataclass(frozen=True)
class HardwareProfile:
    cpu: str
    cpu_threads: int
    gpu: str | None
    vram_mb: int | None
    driver: str | None

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def quality_tier(self) -> str:
        if self.vram_mb and self.vram_mb >= 12000:
            return "Máximo"
        if self.vram_mb and self.vram_mb >= 6000:
            return "Recomendado"
        return "Rápido"


def detect_hardware() -> HardwareProfile:
    gpu = driver = None
    vram_mb = None
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode == 0 and result.stdout.strip():
            name, driver_value, memory = [part.strip() for part in result.stdout.splitlines()[0].split(",", 2)]
            gpu, driver, vram_mb = name, driver_value, int(float(memory))
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return HardwareProfile(
        cpu=platform.processor() or "CPU não identificada",
        cpu_threads=os.cpu_count() or 1,
        gpu=gpu,
        vram_mb=vram_mb,
        driver=driver,
    )

