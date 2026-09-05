from __future__ import annotations

"""Physical H7 benchmark for an externally installed TensorRT Preview runner.

The caller supplies a lossless PNG sequence produced by the already-proven NCNN
baseline plus its measured wall time. This script runs the external TensorRT
protocol, compares its output against that exact sequence, and records one
hardware/model/resolution/precision key only when all safety and quality gates
pass. It installs or downloads nothing.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from cinepulse.rife_safe_runner import validate_png_sequence
from cinepulse.tensorrt_preview import (
    TensorRtEvidence,
    TensorRtKey,
    TensorRtPreviewStore,
    build_external_command,
    probe_external_backend,
)
from cinepulse.hardware import detect_hardware


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="CinePulse Preview TensorRT vs proven NCNN benchmark")
    result.add_argument("--runner", required=True)
    result.add_argument("--model", choices=("realesrgan", "rife"), required=True)
    result.add_argument("--model-path", type=Path, required=True)
    result.add_argument("--input", type=Path, required=True)
    result.add_argument("--baseline", type=Path, required=True, help="Approved NCNN lossless PNG sequence")
    result.add_argument("--baseline-seconds", type=float, required=True)
    result.add_argument("--cache", type=Path, required=True)
    result.add_argument("--tensorrt-version", required=True)
    result.add_argument("--precision", choices=("fp32", "fp16"), default="fp32")
    result.add_argument("--ffmpeg", default="ffmpeg")
    result.add_argument("--timeout", type=float, default=1800.0)
    return result


def model_fingerprint(path: Path) -> str:
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()[:24]
    if path.is_dir():
        rows = []
        for item in sorted(path.rglob("*")):
            if item.is_file():
                stat = item.stat()
                rows.append(f"{item.relative_to(path)}:{stat.st_size}:{stat.st_mtime_ns}")
        return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()[:24]
    raise FileNotFoundError(path)


def metric(ffmpeg: str, baseline: Path, candidate: Path, name: str, timeout: float) -> float:
    command = [
        ffmpeg, "-hide_banner", "-nostdin",
        "-framerate", "1", "-i", str(baseline / "%08d.png"),
        "-framerate", "1", "-i", str(candidate / "%08d.png"),
        "-lavfi", f"[0:v:0][1:v:0]{name}", "-an", "-f", "null", "-",
    ]
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(1.0, timeout),
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr[-3000:])
    text = result.stderr
    marker = "average:" if name == "psnr" else "All:"
    values = []
    for line in text.splitlines():
        if marker not in line:
            continue
        tail = line.split(marker, 1)[1].strip().split()[0]
        try:
            values.append(999.0 if tail.lower() == "inf" else float(tail))
        except ValueError:
            pass
    if not values:
        raise RuntimeError(f"could not parse {name}")
    return values[-1]


def black_frame_ok(ffmpeg: str, frames: list[Path]) -> bool:
    selected = [frames[0], frames[len(frames) // 2], frames[-1]] if frames else []
    for frame in dict.fromkeys(selected):
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(frame),
             "-vf", "scale=64:36:flags=area,format=gray", "-frames:v", "1", "-f", "rawvideo", "pipe:1"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        if result.returncode or len(result.stdout) != 64 * 36 or max(result.stdout, default=0) <= 1:
            return False
    return True


def main() -> int:
    args = parser().parse_args()
    ffmpeg = shutil.which(args.ffmpeg) or (str(args.ffmpeg) if Path(args.ffmpeg).is_file() else "")
    if not ffmpeg:
        raise SystemExit("FFmpeg required for quality gates")
    backend = probe_external_backend(args.runner)
    if backend is None:
        raise SystemExit("external runner did not satisfy cinepulse-tensorrt-preview-v1")
    baseline_frames = validate_png_sequence(args.baseline, len(list(args.baseline.glob("*.png"))))
    if not baseline_frames:
        raise SystemExit("approved NCNN baseline sequence is empty")
    width, height = __import__("cinepulse.rife_safe_runner", fromlist=["validate_png"]).validate_png(baseline_frames[0])
    hardware = detect_hardware()
    if not hardware.gpu:
        raise SystemExit("NVIDIA GPU required; no physical TensorRT evidence recorded")
    fingerprint = model_fingerprint(args.model_path)
    key = TensorRtKey(
        gpu_name=hardware.gpu,
        driver=hardware.driver or "unknown-driver",
        tensorrt_version=args.tensorrt_version,
        backend_fingerprint=backend.fingerprint,
        model=args.model,
        model_fingerprint=fingerprint,
        width=width,
        height=height,
        precision=args.precision,
    )

    with tempfile.TemporaryDirectory(prefix="cinepulse-h7-") as temporary:
        output = Path(temporary) / "candidate"
        output.mkdir()
        command = build_external_command(
            backend,
            model=args.model,
            model_path=args.model_path,
            input_path=args.input,
            output_path=output,
            width=width,
            height=height,
            precision=args.precision,
        )
        started = time.perf_counter()
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(1.0, args.timeout),
            check=False,
        )
        candidate_seconds = max(0.000001, time.perf_counter() - started)
        text = result.stdout or ""
        oom = any(token in text.lower() for token in (
            "out of memory", "oom", "failed to allocate", "cuda_error_out_of_memory"
        ))
        integrity_ok = False
        frame_count_ok = False
        black_ok = False
        psnr = 0.0
        ssim = 0.0
        if result.returncode == 0:
            try:
                candidate_frames = validate_png_sequence(output, len(baseline_frames))
                integrity_ok = True
                frame_count_ok = len(candidate_frames) == len(baseline_frames)
                black_ok = black_frame_ok(ffmpeg, candidate_frames)
                psnr = metric(ffmpeg, args.baseline, output, "psnr", args.timeout)
                ssim = metric(ffmpeg, args.baseline, output, "ssim", args.timeout)
            except (OSError, ValueError, RuntimeError):
                integrity_ok = False
        evidence = TensorRtEvidence(
            baseline_seconds=max(0.0, args.baseline_seconds),
            candidate_seconds=candidate_seconds,
            integrity_ok=integrity_ok,
            frame_count_ok=frame_count_ok,
            black_frame_ok=black_ok,
            temporal_ok=frame_count_ok and integrity_ok,
            psnr_db=psnr,
            ssim=ssim,
            vmaf_delta=None,
            oom=oom,
        )
        recorded = TensorRtPreviewStore(args.cache).record(key, backend, evidence)

    print(json.dumps({
        "physical_acceptance": "exact-preview-evidence-recorded-not-global-pass" if recorded else "rejected",
        "preview_only": True,
        "stable_fallback": "NCNN Vulkan",
        "hardware": hardware.as_dict(),
        "backend": {"version": backend.version, "license_id": backend.license_id, "fingerprint": backend.fingerprint},
        "model": args.model,
        "precision": args.precision,
        "resolution": [width, height],
        "baseline_seconds": evidence.baseline_seconds,
        "candidate_seconds": evidence.candidate_seconds,
        "speedup": evidence.speedup,
        "psnr_db": evidence.psnr_db,
        "ssim": evidence.ssim,
        "integrity_ok": evidence.integrity_ok,
        "frame_count_ok": evidence.frame_count_ok,
        "black_frame_ok": evidence.black_frame_ok,
        "temporal_ok": evidence.temporal_ok,
        "oom": evidence.oom,
        "accepted": evidence.accepted,
        "cache_key": key.token(),
    }, ensure_ascii=False, indent=2))
    return 0 if recorded else 2


if __name__ == "__main__":
    raise SystemExit(main())
