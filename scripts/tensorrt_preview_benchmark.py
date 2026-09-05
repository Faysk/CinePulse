from __future__ import annotations

"""Physical H7 benchmark for an externally installed TensorRT Preview runner.

The candidate is compared only against an H2/H3-proven NCNN baseline for the
same GPU, driver, model and source geometry.  TensorRT version comes only from
the external runner protocol.  The script installs/downloads nothing and never
grants a global TensorRT PASS.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

from cinepulse.hardware import detect_hardware
from cinepulse.ncnn_baseline import prove_ncnn_baseline
from cinepulse.rife_safe_runner import validate_png, validate_png_sequence
from cinepulse.tensorrt_preview import (
    TensorRtEvidence,
    TensorRtKey,
    TensorRtPreviewStore,
    build_external_command,
    probe_external_backend,
)


TEMPORAL_DELTA_MAE_FLOOR = 0.75


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CinePulse Preview TensorRT vs proven NCNN benchmark")
    p.add_argument("--runner", required=True)
    p.add_argument("--model", choices=("realesrgan", "rife"), required=True)
    p.add_argument("--model-path", type=Path, required=True)
    p.add_argument("--input", type=Path, required=True, help="Original NCNN input PNG sequence")
    p.add_argument("--baseline", type=Path, required=True, help="Lossless output produced by the proven NCNN policy")
    p.add_argument("--baseline-seconds", type=float, required=True)
    p.add_argument("--ncnn-cache", type=Path, required=True, help="H2/H3 tuning cache that proves the NCNN baseline")
    p.add_argument("--ncnn-model-id", required=True, help="Exact NCNN model id used by H2/H3 tuning")
    p.add_argument("--ncnn-scale", type=int, default=2, help="Real-ESRGAN scale; ignored for RIFE")
    p.add_argument("--gpu-index", type=int, default=0)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--precision", choices=("fp32", "fp16"), default="fp32")
    p.add_argument("--ffmpeg", default="ffmpeg")
    p.add_argument("--timeout", type=float, default=1800.0)
    return p


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
        return hashlib.sha256("\n".join(rows).encode()).hexdigest()[:24]
    raise FileNotFoundError(path)


def metric(ffmpeg: str, baseline: Path, candidate: Path, name: str, timeout: float) -> float:
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostdin", "-framerate", "1", "-i", str(baseline / "%08d.png"),
         "-framerate", "1", "-i", str(candidate / "%08d.png"), "-lavfi", f"[0:v:0][1:v:0]{name}",
         "-an", "-f", "null", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
        timeout=max(1.0, timeout), check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr[-3000:])
    marker = "average:" if name == "psnr" else "All:"
    values = []
    for line in result.stderr.splitlines():
        if marker in line:
            raw = line.split(marker, 1)[1].strip().split()[0]
            try:
                values.append(999.0 if raw.lower() == "inf" else float(raw))
            except ValueError:
                pass
    if not values:
        raise RuntimeError(f"could not parse {name}")
    return values[-1]


def _gray_frame(ffmpeg: str, path: Path) -> np.ndarray:
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-vf", "scale=64:36:flags=area,format=gray", "-frames:v", "1", "-f", "rawvideo", "pipe:1"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
    )
    if result.returncode or len(result.stdout) != 64 * 36:
        raise RuntimeError(f"could not decode temporal sample {path.name}")
    return np.frombuffer(result.stdout, dtype=np.uint8).astype(np.float32).reshape(36, 64)


def temporal_parity(ffmpeg: str, baseline: list[Path], candidate: list[Path]) -> tuple[bool, float | None]:
    if len(baseline) != len(candidate) or len(baseline) < 2:
        return False, None
    pair_count = len(baseline) - 1
    indexes = sorted({
        round(i * (pair_count - 1) / max(1, min(5, pair_count) - 1))
        for i in range(min(5, pair_count))
    })
    errors: list[float] = []
    cache: dict[tuple[str, int], np.ndarray] = {}

    def frame(which: str, frames: list[Path], index: int) -> np.ndarray:
        token = (which, index)
        if token not in cache:
            cache[token] = _gray_frame(ffmpeg, frames[index])
        return cache[token]

    for index in indexes:
        b_delta = frame("b", baseline, index + 1) - frame("b", baseline, index)
        c_delta = frame("c", candidate, index + 1) - frame("c", candidate, index)
        errors.append(float(np.mean(np.abs(b_delta - c_delta))))
    mae = max(errors) if errors else None
    return bool(mae is not None and mae <= TEMPORAL_DELTA_MAE_FLOOR), mae


def black_frame_ok(ffmpeg: str, frames: list[Path]) -> bool:
    selected = [frames[0], frames[len(frames) // 2], frames[-1]] if frames else []
    for frame in dict.fromkeys(selected):
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(frame),
             "-vf", "scale=64:36:flags=area,format=gray", "-frames:v", "1", "-f", "rawvideo", "pipe:1"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
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
        raise SystemExit("external runner did not satisfy cinepulse-tensorrt-preview-v1 with runtime version")

    input_frames = validate_png_sequence(args.input, len(list(args.input.glob("*.png"))))
    baseline_frames = validate_png_sequence(args.baseline, len(list(args.baseline.glob("*.png"))))
    if not input_frames or not baseline_frames:
        raise SystemExit("NCNN input/baseline sequences must be non-empty")
    source_width, source_height = validate_png(input_frames[0])
    width, height = validate_png(baseline_frames[0])
    hardware = detect_hardware()
    if not hardware.gpu:
        raise SystemExit("NVIDIA GPU required; no physical TensorRT evidence recorded")

    baseline_proof = prove_ncnn_baseline(
        model=args.model,
        cache=args.ncnn_cache,
        gpu_name=hardware.gpu,
        vram_mb=int(hardware.vram_mb or 0),
        driver=hardware.driver or "unknown-driver",
        model_id=args.ncnn_model_id,
        source_width=source_width,
        source_height=source_height,
        gpu_index=max(0, int(args.gpu_index)),
        scale=max(1, int(args.ncnn_scale)),
    )
    if baseline_proof is None:
        raise SystemExit(
            "H7 refused: no exact accepted H2/H3 NCNN tuning record matches this GPU/driver/model/source geometry"
        )

    key = TensorRtKey(
        hardware.gpu,
        hardware.driver or "unknown-driver",
        backend.tensorrt_version,
        backend.fingerprint,
        args.model,
        model_fingerprint(args.model_path),
        baseline_proof.fingerprint,
        width,
        height,
        args.precision,
    )
    temporal_mae: float | None = None
    with tempfile.TemporaryDirectory(prefix="cinepulse-h7-") as temporary:
        output = Path(temporary) / "candidate"
        output.mkdir()
        command = build_external_command(
            backend, model=args.model, model_path=args.model_path, input_path=args.input,
            output_path=output, width=width, height=height, precision=args.precision,
        )
        started = time.perf_counter()
        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", timeout=max(1.0, args.timeout), check=False,
        )
        candidate_seconds = max(.000001, time.perf_counter() - started)
        text = result.stdout or ""
        oom = any(t in text.lower() for t in (
            "out of memory", "oom", "failed to allocate", "cuda_error_out_of_memory"
        ))
        integrity = frame_ok = black = temporal_ok = False
        psnr = ssim = 0.0
        if result.returncode == 0:
            try:
                frames = validate_png_sequence(output, len(baseline_frames))
                integrity = True
                frame_ok = len(frames) == len(baseline_frames)
                black = black_frame_ok(ffmpeg, frames)
                psnr = metric(ffmpeg, args.baseline, output, "psnr", args.timeout)
                ssim = metric(ffmpeg, args.baseline, output, "ssim", args.timeout)
                temporal_ok, temporal_mae = temporal_parity(ffmpeg, baseline_frames, frames)
            except (OSError, ValueError, RuntimeError):
                integrity = False
                temporal_ok = False
        evidence = TensorRtEvidence(
            max(0.0, args.baseline_seconds), candidate_seconds, integrity, frame_ok,
            black, temporal_ok, psnr, ssim, None, oom,
        )
        recorded = TensorRtPreviewStore(args.cache).record(key, backend, evidence)

    print(json.dumps({
        "physical_acceptance": "exact-preview-evidence-recorded-not-global-pass" if recorded else "rejected",
        "preview_only": True,
        "stable_fallback": "NCNN Vulkan",
        "hardware": hardware.as_dict(),
        "backend": {
            "version": backend.version,
            "tensorrt_version": backend.tensorrt_version,
            "license_id": backend.license_id,
            "fingerprint": backend.fingerprint,
        },
        "ncnn_baseline": {
            "model_id": args.ncnn_model_id,
            "tuning_key": baseline_proof.tuning_key,
            "fingerprint": baseline_proof.fingerprint,
            "policy": baseline_proof.policy,
        },
        "model": args.model,
        "precision": args.precision,
        "resolution": [width, height],
        "speedup": evidence.speedup,
        "psnr_db": psnr,
        "ssim": ssim,
        "temporal_delta_mae_gray": temporal_mae,
        "temporal_ok": evidence.temporal_ok,
        "accepted": evidence.accepted,
        "cache_key": key.token(),
    }, ensure_ascii=False, indent=2))
    return 0 if recorded else 2


if __name__ == "__main__":
    raise SystemExit(main())
