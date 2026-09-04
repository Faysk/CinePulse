from __future__ import annotations

import ctypes
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class VolumeIdentity:
    id: str
    mount: str
    filesystem: str
    drive_type: str
    bus: str
    total_bytes: int
    free_bytes: int

    def to_dict(self) -> dict:
        return asdict(self)


def _nearest_existing(path: Path) -> Path:
    candidate = path.expanduser().resolve(strict=False)
    while not candidate.exists() and candidate.parent != candidate:
        candidate = candidate.parent
    if not candidate.exists():
        raise FileNotFoundError(path)
    return candidate


def _unix_mount(path: Path) -> Path:
    current = _nearest_existing(path)
    while current.parent != current and not os.path.ismount(current):
        current = current.parent
    return current


def _windows_volume(path: Path) -> tuple[str, str, str, str]:
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    existing = str(_nearest_existing(path))
    mount_buffer = ctypes.create_unicode_buffer(260)
    if not kernel32.GetVolumePathNameW(existing, mount_buffer, len(mount_buffer)):
        raise OSError("GetVolumePathNameW falhou")
    mount = mount_buffer.value
    guid_buffer = ctypes.create_unicode_buffer(260)
    guid = mount
    if kernel32.GetVolumeNameForVolumeMountPointW(mount, guid_buffer, len(guid_buffer)):
        guid = guid_buffer.value
    volume_name = ctypes.create_unicode_buffer(261)
    fs_name = ctypes.create_unicode_buffer(261)
    serial = ctypes.c_uint32()
    max_component = ctypes.c_uint32()
    flags = ctypes.c_uint32()
    filesystem = "unknown"
    if kernel32.GetVolumeInformationW(
        mount,
        volume_name,
        len(volume_name),
        ctypes.byref(serial),
        ctypes.byref(max_component),
        ctypes.byref(flags),
        fs_name,
        len(fs_name),
    ):
        filesystem = fs_name.value or "unknown"
    drive_type_code = int(kernel32.GetDriveTypeW(mount))
    labels = {
        0: "unknown",
        1: "no_root",
        2: "removable",
        3: "fixed",
        4: "network",
        5: "cdrom",
        6: "ramdisk",
    }
    drive_type = labels.get(drive_type_code, "unknown")
    bus = "removable" if drive_type == "removable" else "unknown"
    identity = guid or f"serial:{serial.value:08x}"
    return identity, mount, filesystem, f"{drive_type}:{bus}"


def resolve_volume_identity(path: Path) -> VolumeIdentity:
    existing = _nearest_existing(path)
    usage = shutil.disk_usage(existing)
    if os.name == "nt":
        identity, mount, filesystem, drive_bus = _windows_volume(existing)
        drive_type, bus = drive_bus.split(":", 1)
        return VolumeIdentity(identity, mount, filesystem, drive_type, bus, usage.total, usage.free)
    mount = _unix_mount(existing)
    stat = os.stat(mount)
    return VolumeIdentity(
        id=f"dev:{stat.st_dev}",
        mount=str(mount),
        filesystem="unknown",
        drive_type="mounted",
        bus="unknown",
        total_bytes=usage.total,
        free_bytes=usage.free,
    )


def same_volume(left: Path, right: Path) -> bool:
    return resolve_volume_identity(left).id == resolve_volume_identity(right).id
