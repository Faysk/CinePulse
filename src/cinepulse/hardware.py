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
    gpu_index: int = 0

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def quality_tier(self) -> str:
        if self.vram_mb and self.vram_mb >= 12000:
            return "Máximo"
        if self.vram_mb and self.vram_mb >= 6000:
            return "Recomendado"
        return "Rápido"


def detect_hardware(gpu_index: int | None = None) -> HardwareProfile:
    gpu = driver = None
    vram_mb = None
    gpu_index = 0
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,driver_version,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode == 0 and result.stdout.strip():
            adapters: list[tuple[int, str, str, int]] = []
            for raw in result.stdout.splitlines():
                parts = [part.strip() for part in raw.split(",", 3)]
                if len(parts) != 4:
                    continue
                try:
                    index = max(0, int(parts[0]))
                    memory = max(0, int(float(parts[3])))
                except ValueError:
                    continue
                adapters.append((index, parts[1], parts[2], memory))
            if adapters:
                if gpu_index is None:
                    # Prefer the adapter with the largest physical VRAM envelope.
                    # Live headroom gates still decide per-operation admission.
                    selected_adapter = max(
                        adapters,
                        key=lambda item: (item[3], -item[0]),
                    )
                else:
                    requested_index = max(0, int(gpu_index))
                    selected_adapter = next(
                        (item for item in adapters if item[0] == requested_index),
                        None,
                    )
                    if selected_adapter is None:
                        return HardwareProfile(
                            cpu=platform.processor() or "CPU não identificada",
                            cpu_threads=os.cpu_count() or 1,
                            gpu=None,
                            vram_mb=None,
                            driver=None,
                            gpu_index=requested_index,
                        )
                selected_index, gpu, driver, vram_mb = selected_adapter
                gpu_index = selected_index
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return HardwareProfile(
        cpu=platform.processor() or "CPU não identificada",
        cpu_threads=os.cpu_count() or 1,
        gpu=gpu,
        vram_mb=vram_mb,
        driver=driver,
        gpu_index=gpu_index,
    )

