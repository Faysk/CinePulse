from __future__ import annotations

import json
from pathlib import Path

from cinepulse.hardware_telemetry import (
    GpuSample,
    HardwareSample,
    HardwareTelemetrySession,
    StageEvent,
    benchmark_summary,
    compare_benchmarks,
    load_telemetry,
    summarize_samples,
)


def sample(t: float, stage: str, gpu: float, cpu: float, vram: float = 4000.0) -> HardwareSample:
    return HardwareSample(
        timestamp=1_700_000_000 + t,
        monotonic=t,
        stage=stage,
        cpu_total_percent=cpu,
        cpu_per_logical_percent=(cpu, cpu / 2),
        ram_total_mb=64_000,
        ram_used_mb=20_000 + t,
        ram_available_mb=44_000 - t,
        ram_percent=31.25,
        disk_read_mbps=100 + t,
        disk_write_mbps=200 + t,
        gpus=(GpuSample(index=0, name="RTX", utilization_percent=gpu, vram_used_mb=vram, vram_free_mb=8000-vram, power_w=90+gpu/10, temperature_c=60+gpu/20),),
    )


def test_summary_keeps_stage_wall_time_and_active_gpu() -> None:
    samples = [sample(1.0, "startup", 5, 10), sample(3.0, "IA", 80, 45), sample(6.0, "IA", 95, 55)]
    events = [StageEvent(timestamp=0.0, monotonic=2.0, stage="IA", detail="Real-ESRGAN")]
    summary = summarize_samples(samples, events, 0.0, 8.0)
    assert summary["active_gpu_index"] == 0
    assert summary["stages"]["startup"]["wall_seconds"] == 2.0
    assert summary["stages"]["IA"]["wall_seconds"] == 6.0
    assert summary["stages"]["IA"]["gpu"]["peak_utilization_percent"] == 95
    assert summary["stages"]["IA"]["cpu"]["peak_percent"] == 55


class FakeCpu:
    def __init__(self) -> None:
        self.value = 10.0

    def sample(self):
        self.value += 1
        return self.value, (self.value, self.value / 2)


class FakeRam:
    def sample(self):
        return 64000.0, 16000.0, 48000.0, 25.0


class FakeDisk:
    def sample(self, now):
        return 123.0, 456.0

    def close(self):
        return None


class FakeGpu:
    def sample(self):
        return (GpuSample(index=0, name="Fake RTX", utilization_percent=75.0, vram_total_mb=8192, vram_used_mb=6144, vram_free_mb=2048),)


def test_session_writes_atomic_render_evidence(tmp_path: Path) -> None:
    destination = tmp_path / "hardware-telemetry.json"
    session = HardwareTelemetrySession(
        destination,
        sample_interval=0.5,
        cpu_sampler=FakeCpu(),
        ram_sampler=FakeRam(),
        disk_sampler=FakeDisk(),
        gpu_sampler=FakeGpu(),
    )
    session.start()
    session.mark_stage("Real-ESRGAN", "teste")
    session._samples.append(session._take_sample())
    payload = session.stop(status="success")
    assert destination.is_file()
    stored = json.loads(destination.read_text(encoding="utf-8"))
    assert stored["schema"] == 1
    assert stored["status"] == "success"
    assert stored["summary"]["active_gpu_index"] == 0
    assert payload["samples"]
    assert not destination.with_suffix(".json.tmp").exists()


def test_benchmark_compare_reports_speedup(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps({"schema": 1, "status": "success", "summary": {"wall_seconds": 100.0, "active_gpu_index": 0, "overall": {}, "stages": {"IA": {"wall_seconds": 60.0}}}}), encoding="utf-8")
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps({"schema": 1, "status": "success", "summary": {"wall_seconds": 50.0, "active_gpu_index": 0, "overall": {}, "stages": {"IA": {"wall_seconds": 20.0}}}}), encoding="utf-8")
    baseline = benchmark_summary(load_telemetry(baseline_path), scenario="1080p30_to_4k60")
    candidate = benchmark_summary(load_telemetry(candidate_path), scenario="1080p30_to_4k60")
    comparison = compare_benchmarks(baseline, candidate)
    assert comparison["speedup"] == 2.0
    assert comparison["improvement_percent"] == 50.0
    assert comparison["stages"]["IA"]["speedup"] == 3.0
