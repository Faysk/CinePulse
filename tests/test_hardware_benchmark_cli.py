from __future__ import annotations

from scripts.hardware_benchmark import _realesrgan_key, parser


def test_record_realesrgan_requires_runtime_exact_host_and_component_identity() -> None:
    args = parser().parse_args([
        "record-realesrgan",
        "cache.json",
        "--gpu-name", "RTX Test",
        "--vram-mb", "8192",
        "--driver", "999.1",
        "--width", "1920",
        "--height", "1080",
        "--scale", "2",
        "--cpu-threads", "6",
        "--logical-threads", "28",
        "--cpu-name", "CPU Test",
        "--gpu-index", "1",
        "--component-fingerprint", "real_esrgan:v1:" + "a" * 64,
        "--sample", "256:2:2:2:10:true:false:6:6",
    ])
    key = _realesrgan_key(args)
    assert key.cpu_threads == 6
    assert key.logical_threads == 28
    assert key.cpu_name == "CPU Test"
    assert key.gpu_index == 1
    assert key.component_fingerprint.endswith("a" * 64)
    assert "host6of28" in key.token()
    assert "gpu1" in key.token()


def test_realesrgan_candidates_receive_logical_machine_envelope() -> None:
    args = parser().parse_args([
        "realesrgan-candidates",
        "--vram-mb", "8192",
        "--cpu-threads", "6",
        "--logical-threads", "28",
        "--width", "1920",
        "--height", "1080",
    ])
    assert args.cpu_threads == 6
    assert args.logical_threads == 28


def test_cpu_benchmark_cli_accepts_overnight_mode() -> None:
    args = parser().parse_args([
        "cpu-candidates",
        "--stage", "encode",
        "--logical", "28",
        "--physical", "20",
        "--mode", "overnight",
    ])
    assert args.mode == "overnight"
