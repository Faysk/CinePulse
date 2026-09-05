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
    realesrgan_pipeline_threads,
)


def test_profiles_scale_with_logical_cpu_envelope() -> None:
    assert profile_cpu_threads(PROFILE_BALANCED, 28) == 17
    assert profile_cpu_threads(PROFILE_DEDICATED, 28) == 26
    assert profile_cpu_threads(PROFILE_OVERNIGHT, 28) == 28
    assert default_cpu_threads(28) == 17


def test_small_machines_remain_valid() -> None:
    assert profile_cpu_threads(PROFILE_BALANCED, 1) == 1
    assert profile_cpu_threads(PROFILE_DEDICATED, 2) == 2
    assert profile_cpu_threads(PROFILE_DEDICATED, 4) == 3
    assert profile_cpu_threads(PROFILE_OVERNIGHT, 4) == 4


def test_manual_thread_requests_never_oversubscribe_hardware() -> None:
    assert clamp_cpu_threads(64, 28) == 28
    assert clamp_cpu_threads(0, 28) == 1
    assert clamp_cpu_threads(-5, 28) == 1
    assert profile_for_threads(17, 28) == PROFILE_BALANCED
    assert profile_for_threads(26, 28) == PROFILE_DEDICATED
    assert profile_for_threads(28, 28) == PROFILE_OVERNIGHT
    assert profile_for_threads(20, 28) == "Manual"


def test_realesrgan_keeps_8gb_gpu_workers_conservative_while_scaling_io() -> None:
    assert realesrgan_pipeline_threads(17, 28, 8192) == "2:2:2"
    assert realesrgan_pipeline_threads(26, 28, 8192) == "3:2:3"
    assert realesrgan_pipeline_threads(28, 28, 8192) == "4:2:4"


def test_realesrgan_can_scale_gpu_workers_on_larger_vram() -> None:
    assert realesrgan_pipeline_threads(28, 28, 12_288) == "4:3:4"
    assert realesrgan_pipeline_threads(28, 28, 24_576) == "4:4:4"


def test_machine_budget_reports_reserved_capacity() -> None:
    budget = machine_budget(PROFILE_DEDICATED, 28, 8192)
    assert budget.cpu_threads == 26
    assert budget.reserved_threads == 2
    assert budget.utilization_percent == 93
    assert budget.realesrgan_pipeline == "3:2:3"
