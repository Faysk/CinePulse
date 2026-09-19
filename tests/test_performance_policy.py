from __future__ import annotations

from cinepulse.performance_policy import (
    PROFILE_BALANCED,
    PROFILE_DEDICATED,
    PROFILE_OVERNIGHT,
    clamp_cpu_threads,
    default_cpu_threads,
    machine_budget,
    profile_cpu_threads,
    profile_for_threads,
    realesrgan_live_process_cap,
    realesrgan_pipeline_threads,
)


def test_all_profiles_use_complete_cpu_envelope() -> None:
    assert profile_cpu_threads(PROFILE_BALANCED, 28) == 28
    assert profile_cpu_threads(PROFILE_DEDICATED, 28) == 28
    assert profile_cpu_threads(PROFILE_OVERNIGHT, 28) == 28
    assert default_cpu_threads(28) == 28


def test_small_machines_still_use_every_logical_cpu() -> None:
    assert profile_cpu_threads(PROFILE_BALANCED, 1) == 1
    assert profile_cpu_threads(PROFILE_DEDICATED, 2) == 2
    assert profile_cpu_threads(PROFILE_DEDICATED, 4) == 4
    assert profile_cpu_threads(PROFILE_OVERNIGHT, 4) == 4


def test_manual_thread_requests_still_cannot_exceed_hardware() -> None:
    assert clamp_cpu_threads(64, 28) == 28
    assert clamp_cpu_threads(0, 28) == 1
    assert clamp_cpu_threads(-5, 28) == 1
    assert profile_for_threads(28, 28) == PROFILE_OVERNIGHT
    assert profile_for_threads(20, 28) == "Manual"


def test_realesrgan_8gb_starts_with_three_gpu_workers() -> None:
    assert realesrgan_pipeline_threads(6, 28, 8192) == "4:3:4"
    assert realesrgan_pipeline_threads(28, 28, 8192) == "4:3:4"


def test_realesrgan_live_vram_and_geometry_do_not_throttle() -> None:
    assert realesrgan_live_process_cap(
        8192, vram_free_mb=100, width=7680, height=4320
    ) == 3
    assert realesrgan_pipeline_threads(
        28, 28, 24_576, vram_free_mb=100, width=7680, height=4320
    ) == "4:4:4"


def test_realesrgan_scales_by_static_adapter_size_only() -> None:
    assert realesrgan_live_process_cap(4096, vram_free_mb=None) == 2
    assert realesrgan_live_process_cap(8192, vram_free_mb=None) == 3
    assert realesrgan_live_process_cap(12_288, vram_free_mb=None) == 3
    assert realesrgan_live_process_cap(24_576, vram_free_mb=None) == 4


def test_machine_budget_reserves_no_cpu_capacity() -> None:
    budget = machine_budget(PROFILE_DEDICATED, 28, 8192)
    assert budget.cpu_threads == 28
    assert budget.reserved_threads == 0
    assert budget.utilization_percent == 100
    assert budget.realesrgan_pipeline == "4:3:4"
