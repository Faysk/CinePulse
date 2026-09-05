from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from cinepulse.hardware import detect_hardware
from cinepulse.rife_benchmark import benchmark_and_record
from cinepulse.rife_safe_runner import validate_png
from cinepulse.rife_tuning import RifeTuningKey, RifeTuningStore, safe_candidates


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Benchmark physical RIFE concurrency without weakening CinePulse safety gates.")
    result.add_argument("--input", type=Path, required=True, help="Directory containing a short representative PNG sequence.")
    result.add_argument("--rife", type=Path, required=True)
    result.add_argument("--model", type=Path, required=True)
    result.add_argument("--cache", type=Path, required=True)
    result.add_argument("--work", type=Path, required=True)
    result.add_argument("--ffmpeg", default="ffmpeg")
    result.add_argument("--gpu-index", type=int, default=0)
    result.add_argument("--timeout", type=float, default=900.0)
    return result


def main() -> int:
    args = parser().parse_args()
    frames = sorted(args.input.glob("*.png"))
    if len(frames) < 2:
        raise SystemExit("RIFE benchmark requires at least two PNG input frames")
    width, height = validate_png(frames[0])
    uhd = max(width, height) >= 3840 or width * height >= 3840 * 2160
    hardware = detect_hardware()
    if not hardware.gpu:
        raise SystemExit("No NVIDIA GPU was detected; physical RIFE GPU tuning was not recorded")
    ffmpeg = shutil.which(args.ffmpeg) or (str(args.ffmpeg) if Path(args.ffmpeg).is_file() else "")
    if not ffmpeg:
        raise SystemExit("FFmpeg is required for the RIFE black-frame integrity gate")
    candidates = safe_candidates(
        uhd=uhd,
        vram_mb=hardware.vram_mb,
        gpu_index=max(0, args.gpu_index),
    )
    key = RifeTuningKey(
        hardware.gpu,
        int(hardware.vram_mb or 0),
        hardware.driver or "unknown-driver",
        args.model.name or "rife-v4.6",
        width,
        height,
    )
    store = RifeTuningStore(args.cache)
    winner, samples = benchmark_and_record(
        store,
        key,
        candidates,
        executable=args.rife,
        model=args.model,
        incoming=args.input,
        work_dir=args.work,
        uhd=uhd,
        ffmpeg=ffmpeg,
        timeout_seconds=args.timeout,
    )
    payload = {
        "hardware": hardware.as_dict(),
        "resolution": [width, height],
        "uhd": uhd,
        "key": key.token(),
        "winner": {"jobs": winner.jobs, "gpu_index": winner.gpu_index} if winner else None,
        "physical_acceptance": "evidence-recorded-not-global-pass" if winner else "rejected",
        "samples": [
            {
                "jobs": sample.policy.jobs,
                "gpu_index": sample.policy.gpu_index,
                "wall_seconds": sample.wall_seconds,
                "integrity_ok": sample.integrity_ok,
                "black_frame_ok": sample.black_frame_ok,
                "oom": sample.oom,
                "output_frames": sample.output_frames,
                "expected_frames": sample.expected_frames,
                "accepted": sample.accepted,
            }
            for sample in samples
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if winner else 2


if __name__ == "__main__":
    raise SystemExit(main())
