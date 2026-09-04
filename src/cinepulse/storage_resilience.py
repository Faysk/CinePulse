from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .volume_identity import VolumeIdentity, resolve_volume_identity


class StorageBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class SpaceDecision:
    volume: VolumeIdentity
    required_bytes: int
    reserve_bytes: int
    projected_free_bytes: int
    allowed: bool


class StorageGuard:
    def __init__(self, *, reserve_bytes: int = 8 * 1024**3) -> None:
        self.reserve_bytes = int(reserve_bytes)

    def assess(self, path: Path, required_bytes: int, *, reserve_bytes: int | None = None) -> SpaceDecision:
        reserve = self.reserve_bytes if reserve_bytes is None else int(reserve_bytes)
        volume = resolve_volume_identity(path)
        projected = volume.free_bytes - int(required_bytes)
        return SpaceDecision(
            volume=volume,
            required_bytes=int(required_bytes),
            reserve_bytes=reserve,
            projected_free_bytes=projected,
            allowed=projected >= reserve,
        )

    def require(self, path: Path, required_bytes: int, *, reserve_bytes: int | None = None) -> SpaceDecision:
        decision = self.assess(path, required_bytes, reserve_bytes=reserve_bytes)
        if not decision.allowed:
            raise StorageBlocked(
                f"espaço insuficiente no volume {decision.volume.id}: "
                f"free={decision.volume.free_bytes} required={decision.required_bytes} reserve={decision.reserve_bytes}"
            )
        return decision

    def monitor(self, path: Path, *, stop_below_bytes: int | None = None) -> SpaceDecision:
        threshold = self.reserve_bytes if stop_below_bytes is None else int(stop_below_bytes)
        volume = resolve_volume_identity(path)
        decision = SpaceDecision(
            volume=volume,
            required_bytes=0,
            reserve_bytes=threshold,
            projected_free_bytes=volume.free_bytes,
            allowed=volume.free_bytes >= threshold,
        )
        if not decision.allowed:
            raise StorageBlocked(
                f"margem de segurança atingida no volume {volume.id}: {volume.free_bytes} < {threshold}"
            )
        return decision


def should_use_faststart(
    *,
    output_size_bytes: int,
    local_playback: bool,
    drive_type: str,
    threshold_bytes: int = 8 * 1024**3,
) -> bool:
    """Policy for costly MP4 index relocation.

    Local very large deliveries avoid the second full-file rewrite. Web/file
    delivery can still request faststart when the destination is suitable.
    """
    if output_size_bytes >= threshold_bytes and local_playback:
        return False
    if output_size_bytes >= threshold_bytes and drive_type in {"removable", "network"}:
        return False
    return True
