from __future__ import annotations

"""Bounded resource preflight for Preview Composer reference exports.

The CPU reference intentionally materializes a lossless FFV1 visual master and
then atomically muxes a second file beside it.  High-resolution music projects
can therefore consume substantial RAM and scratch space even when the final
delivery is compact.  This module fails early on clearly insufficient local
resources instead of discovering the problem after hours of work.
"""

import ctypes
from dataclasses import dataclass
import os
from pathlib import Path
import platform
import shutil

from .composer_base_probe import ComposerBaseProfile


MIB = 1024 ** 2
GIB = 1024 ** 3
_DISK_RESERVE_BYTES = 1024 * MIB
_RAM_RESERVE_BYTES = 512 * MIB


@dataclass(frozen=True)
class ComposerResourceEstimate:
    frame_bytes: int
    estimated_peak_ram_bytes: int
    estimated_visual_master_bytes: int
    required_free_disk_bytes: int
    available_ram_bytes: int | None
    free_disk_bytes: int


def _available_ram_bytes() -> int | None:
    if os.name == "nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(status)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullAvailPhys)
        except (AttributeError, OSError):
            return None
        return None

    if platform.system() == "Linux":
        try:
            for line in Path("/proc/meminfo").read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.startswith("MemAvailable:"):
                    continue
                fields = line.split()
                if len(fields) >= 2:
                    return int(float(fields[1]) * 1024.0)
        except (OSError, ValueError):
            return None
    return None


def estimate_composer_resources(
    profile: ComposerBaseProfile,
    output_directory: Path,
) -> ComposerResourceEstimate:
    width = max(1, int(profile.width))
    height = max(1, int(profile.height))
    fps = max(1.0, float(profile.fps))
    duration = max(0.001, float(profile.duration))
    frame_bytes = width * height * 4

    # The frame loop can transiently hold decoded input, a copied RGBA base,
    # the composed canvas and the bytes handed to FFmpeg.  Keep additional
    # allocator/UI headroom rather than treating those four buffers as a target.
    peak_ram = frame_bytes * 4 + 256 * MIB

    # FFV1 is intra-frame and content dependent.  This is deliberately a
    # planning floor, not a claimed codec bitrate: still-image projects usually
    # compress better than moving video, while both must coexist with the mux
    # partial before AtomicOutput promotion.
    bytes_per_pixel_frame = 0.50 if profile.still_image else 1.00
    visual_master = int(width * height * fps * duration * bytes_per_pixel_frame)
    required_disk = int(visual_master * 2.25) + _DISK_RESERVE_BYTES

    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    free_disk = int(shutil.disk_usage(directory).free)
    return ComposerResourceEstimate(
        frame_bytes=frame_bytes,
        estimated_peak_ram_bytes=peak_ram,
        estimated_visual_master_bytes=visual_master,
        required_free_disk_bytes=required_disk,
        available_ram_bytes=_available_ram_bytes(),
        free_disk_bytes=free_disk,
    )


def validate_composer_resources(
    profile: ComposerBaseProfile,
    output_directory: Path,
) -> ComposerResourceEstimate:
    estimate = estimate_composer_resources(profile, output_directory)
    if estimate.free_disk_bytes < estimate.required_free_disk_bytes:
        required = estimate.required_free_disk_bytes / GIB
        free = estimate.free_disk_bytes / GIB
        raise RuntimeError(
            f"Composer precisa de ~{required:.1f} GiB livres para o master lossless + mux atômico; "
            f"há {free:.1f} GiB disponíveis no destino."
        )

    available = estimate.available_ram_bytes
    if available is not None:
        required_ram = int(estimate.estimated_peak_ram_bytes * 1.25) + _RAM_RESERVE_BYTES
        if available < required_ram:
            required = required_ram / GIB
            free = available / GIB
            raise RuntimeError(
                f"Composer precisa de ~{required:.1f} GiB de RAM disponível para este canvas; "
                f"há {free:.1f} GiB disponíveis."
            )
    return estimate
