from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cinepulse.hardware_telemetry import (
    GpuSample,
    HardwareSample,
    HardwareTelemetrySession,
    NvidiaSmiSampler,
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
        gpus=(GpuSample(
            index=0, name="RTX", utilization_percent=gpu,
            encoder_utilization_percent=gpu / 2, decoder_utilization_percent=gpu / 4,
            vram_used_mb=vram, vram_free_mb=8000-vram,
            power_w=90+gpu/10, temperature_c=60+gpu/20,
        ),),
    )


def test_summary_keeps_stage_wall_time_and_active_gpu() -> None:
    samples = [sample(1.0, "startup", 5, 10), sample(3.0, "IA", 80, 45), sample(6.0, "IA", 95, 55)]
    events = [StageEvent(timestamp=0.0, monotonic=2.0, stage="IA", detail="Real-ESRGAN")]
    summary = summarize_samples(samples, events, 0.0, 8.0)
    assert summary["active_gpu_index"] == 0
    assert summary["stages"]["startup"]["wall_seconds"] == 2.0
    assert summary["stages"]["IA"]["wall_seconds"] == 6.0
    assert summary["stages"]["IA"]["gpu"]["peak_utilization_percent"] == 95
    assert summary["stages"]["IA"]["gpu"]["peak_encoder_utilization_percent"] == 47.5
    assert summary["stages"]["IA"]["gpu"]["peak_decoder_utilization_percent"] == 23.75
    assert summary["stages"]["IA"]["cpu"]["peak_percent"] == 55


def test_nvidia_sampler_reads_video_engine_utilization() -> None:
    row = "0, RTX Test, 999.1, 91, 62, 8192, 7000, 1192, 150, 200, 67, 2400, 10000, P2, 73, 58\n"
    result = SimpleNamespace(returncode=0, stdout=row)
    with patch("cinepulse.hardware_telemetry.subprocess.run", return_value=result) as run:
        samples = NvidiaSmiSampler("nvidia-smi").sample()
    assert len(samples) == 1
    assert samples[0].encoder_utilization_percent == 73
    assert samples[0].decoder_utilization_percent == 58
    assert run.call_count == 1


def test_nvidia_sampler_falls_back_when_video_engine_fields_are_unsupported() -> None:
    failed = SimpleNamespace(
        returncode=1,
        stdout="",
        stderr="Field 'utilization.encoder' is not a valid field to query.",
    )
    base = SimpleNamespace(
        returncode=0,
        stdout="0, RTX Legacy, 555.1, 80, 40, 8192, 4096, 4096, 120, 180, 65, 2200, 9000, P2\n",
    )
    sampler = NvidiaSmiSampler("nvidia-smi")
    with patch(
        "cinepulse.hardware_telemetry.subprocess.run",
        side_effect=(failed, base, base),
    ) as run:
        first = sampler.sample()
        second = sampler.sample()
    assert len(first) == 1
    assert len(second) == 1
    assert first[0].utilization_percent == 80
    assert first[0].encoder_utilization_percent is None
    assert first[0].decoder_utilization_percent is None
    assert second[0].utilization_percent == 80
    # First sample probes ENGINE_QUERY then falls back; later samples remember
    # the unsupported fields and go straight to BASE_QUERY.
    assert run.call_count == 3


def test_transient_extended_query_failure_is_retried_next_sample() -> None:
    transient = SimpleNamespace(returncode=1, stdout="", stderr="GPU is temporarily unavailable")
    base = SimpleNamespace(
        returncode=0,
        stdout="0, RTX Test, 999.1, 40, 20, 8192, 2048, 6144, 80, 180, 60, 2100, 9000, P2\n",
        stderr="",
    )
    extended = SimpleNamespace(
        returncode=0,
        stdout="0, RTX Test, 999.1, 60, 30, 8192, 3000, 5192, 100, 180, 63, 2200, 9500, P2, 44, 22\n",
        stderr="",
    )
    sampler = NvidiaSmiSampler("nvidia-smi")
    with patch(
        "cinepulse.hardware_telemetry.subprocess.run",
        side_effect=(transient, base, extended),
    ) as run:
        first = sampler.sample()
        second = sampler.sample()
    assert first[0].encoder_utilization_percent is None
    assert second[0].encoder_utilization_percent == 44
    assert second[0].decoder_utilization_percent == 22
    assert run.call_count == 3


def test_active_gpu_selection_counts_nvenc_nvdec_activity() -> None:
    payload = HardwareSample(
        timestamp=1.0,
        monotonic=1.0,
        stage="Encode",
        cpu_total_percent=10.0,
        cpu_per_logical_percent=(),
        ram_total_mb=64000.0,
        ram_used_mb=10000.0,
        ram_available_mb=54000.0,
        ram_percent=16.0,
        disk_read_mbps=10.0,
        disk_write_mbps=20.0,
        gpus=(
            GpuSample(index=0, name="GPU0", utilization_percent=25.0, encoder_utilization_percent=2.0),
            GpuSample(index=1, name="GPU1", utilization_percent=5.0, encoder_utilization_percent=90.0),
        ),
    )
    summary = summarize_samples([payload], [], 0.0, 1.0)
    assert summary["active_gpu_index"] == 1
    assert summary["overall"]["gpu"]["peak_encoder_utilization_percent"] == 90.0


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
    with patch("cinepulse.hardware_telemetry.os.fsync", wraps=os.fsync) as fsync:
        payload = session.stop(status="success")
    assert fsync.call_count >= 1
    assert destination.is_file()
    stored = json.loads(destination.read_text(encoding="utf-8"))
    assert stored["schema"] == 1
    assert stored["status"] == "success"
    assert stored["summary"]["active_gpu_index"] == 0
    assert payload["samples"]
    assert not destination.with_suffix(".json.tmp").exists()
    assert list(tmp_path.glob("hardware-telemetry.json.tmp-*")) == []


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
