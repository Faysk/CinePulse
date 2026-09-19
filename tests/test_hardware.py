from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from cinepulse.hardware import HardwareProfile, detect_hardware


def test_hardware_profile_keeps_backward_compatible_default_gpu_index() -> None:
    profile = HardwareProfile("CPU", 8, "RTX", 8192, "999.1")
    assert profile.gpu_index == 0


def test_detect_hardware_selects_nvidia_adapter_with_largest_vram() -> None:
    result = SimpleNamespace(
        returncode=0,
        stdout=(
            "0, RTX 4070, 999.1, 8192\n"
            "1, RTX 3090, 999.1, 24576\n"
        ),
    )
    with (
        patch("cinepulse.hardware.subprocess.run", return_value=result),
        patch("cinepulse.hardware.platform.processor", return_value="CPU"),
        patch("cinepulse.hardware.os.cpu_count", return_value=28),
    ):
        profile = detect_hardware()
    assert profile.gpu == "RTX 3090"
    assert profile.vram_mb == 24576
    assert profile.gpu_index == 1
    assert profile.cpu_threads == 28


def test_detect_hardware_honors_explicit_adapter_index() -> None:
    result = SimpleNamespace(
        returncode=0,
        stdout=(
            "0, RTX 4070, 999.1, 8192\n"
            "1, RTX 3090, 999.1, 24576\n"
        ),
    )
    with patch("cinepulse.hardware.subprocess.run", return_value=result):
        profile = detect_hardware(0)
    assert profile.gpu == "RTX 4070"
    assert profile.vram_mb == 8192
    assert profile.gpu_index == 0


def test_detect_hardware_fails_closed_for_missing_explicit_adapter() -> None:
    result = SimpleNamespace(
        returncode=0,
        stdout="0, RTX 4070, 999.1, 8192\n",
    )
    with patch("cinepulse.hardware.subprocess.run", return_value=result):
        profile = detect_hardware(7)
    assert profile.gpu is None
    assert profile.vram_mb is None
    assert profile.gpu_index == 7


def test_detect_hardware_prefers_lower_index_when_vram_ties() -> None:
    result = SimpleNamespace(
        returncode=0,
        stdout=(
            "2, RTX B, 999.1, 16384\n"
            "0, RTX A, 999.1, 16384\n"
        ),
    )
    with patch("cinepulse.hardware.subprocess.run", return_value=result):
        profile = detect_hardware()
    assert profile.gpu == "RTX A"
    assert profile.gpu_index == 0
