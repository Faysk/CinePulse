from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from cinepulse.hardware import detect_hardware
from cinepulse.realesrgan_benchmark import benchmark_and_record, evidence_payload, png_dimensions
from cinepulse.realesrgan_tuning import RealEsrganTuningKey, RealEsrganTuningStore, safe_candidates


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Run integrity-gated physical Real-ESRGAN tuning on a bounded PNG sample.")
    result.add_argument("input_dir", type=Path, help="Directory containing representative input PNG frames.")
    result.add_argument("cache", type=Path, help="Path to realesrgan-tuning.json used by CinePulse runtime.")
    result.add_argument("--executable", type=Path, required=True)
    result.add_argument("--model-dir", type=Path, required=True)
    result.add_argument("--model", default="realesr-animevideov3")
    result.add_argument("--scale", type=int, default=2)
    result.add_argument("--work-dir", type=Path, required=True)
    result.add_argument("--cpu-threads", type=int)
    result.add_argument("--gpu-index", type=int, default=0)
    result.add_argument("--gpu-name")
    result.add_argument("--vram-mb", type=int)
    result.add_argument("--driver")
    result.add_argument("--timeout", type=float, default=900.0)
    result.add_argument("--keep-work", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    inputs = sorted(args.input_dir.glob("*.png"))
    if not inputs:
        raise SystemExit("input_dir contains no PNG frames")
    source_size = png_dimensions(inputs[0])
    if source_size is None:
        raise SystemExit("first PNG does not contain a valid IHDR header")
    if any(png_dimensions(path) != source_size for path in inputs):
        raise SystemExit("all benchmark PNG frames must have identical dimensions")

    hardware = detect_hardware()
    gpu_name = args.gpu_name or hardware.gpu or "unknown-gpu"
    vram_mb = int(args.vram_mb if args.vram_mb is not None else (hardware.vram_mb or 0))
    driver = args.driver or hardware.driver or "unknown-driver"
    cpu_threads = max(1, int(args.cpu_threads or hardware.cpu_threads or 1))
    scale = max(1, int(args.scale))

    candidates = safe_candidates(
        vram_mb=vram_mb,
        cpu_threads=cpu_threads,
        gpu_index=max(0, int(args.gpu_index)),
        width=source_size[0],
        height=source_size[1],
    )
    key = RealEsrganTuningKey(
        gpu_name,
        vram_mb,
        driver,
        args.model,
        source_size[0],
        source_size[1],
        scale,
    )
    store = RealEsrganTuningStore(args.cache)
    try:
        winner, samples = benchmark_and_record(
            store,
            key,
            candidates,
            executable=args.executable,
            model_dir=args.model_dir,
            input_dir=args.input_dir,
            work_dir=args.work_dir,
            model=args.model,
            scale=scale,
            expected_size=source_size,
            timeout_seconds=args.timeout,
        )
        print(json.dumps(evidence_payload(key, winner, samples), ensure_ascii=False, indent=2))
        return 0 if winner is not None else 2
    finally:
        if not args.keep_work:
            shutil.rmtree(args.work_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
