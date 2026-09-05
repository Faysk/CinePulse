from __future__ import annotations

import math
import shutil
import subprocess
import time
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from .rife_safe_runner import validate_png, validate_png_sequence
from .rife_tuning import RifePolicy, RifeSample, RifeTuningKey, RifeTuningStore


OOM_TOKENS = (
    "out of memory",
    "oom",
    "failed to allocate",
    "vk_error_out_of_device_memory",
    "device memory allocation failed",
)
QUALITY_PSNR_FLOOR_DB = 55.0
QUALITY_SAMPLE_WIDTH = 320
QUALITY_SAMPLE_HEIGHT = 180


def looks_like_oom(text: str) -> bool:
    value = str(text or "").lower()
    return any(token in value for token in OOM_TOKENS)


def _clean(directory: Path) -> None:
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True, exist_ok=True)


def _black_frame_ok(ffmpeg: str, frames: list[Path]) -> bool:
    """Reject obviously empty neural outputs without classifying intentional dark scenes."""
    if not frames:
        return False
    selected = [frames[0], frames[len(frames) // 2], frames[-1]]
    for frame in dict.fromkeys(selected):
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(frame),
            "-vf",
            "scale=64:36:flags=area,format=gray",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "pipe:1",
        ]
        result = subprocess.run(command, capture_output=True, check=False)
        if result.returncode or len(result.stdout) != 64 * 36:
            return False
        values = result.stdout
        if max(values, default=0) <= 1:
            return False
    return True


def _decode_quality_sample(ffmpeg: str, path: Path) -> bytes | None:
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-vf",
        f"scale={QUALITY_SAMPLE_WIDTH}:{QUALITY_SAMPLE_HEIGHT}:flags=lanczos,format=gray",
        "-frames:v",
        "1",
        "-f",
        "rawvideo",
        "pipe:1",
    ]
    result = subprocess.run(command, capture_output=True, check=False)
    expected = QUALITY_SAMPLE_WIDTH * QUALITY_SAMPLE_HEIGHT
    if result.returncode or len(result.stdout) != expected:
        return None
    return result.stdout


def sampled_psnr(ffmpeg: str, reference_dir: Path, candidate_dir: Path) -> float | None:
    """Measure sampled visual parity; concurrency tuning should be effectively identical."""
    references = sorted(reference_dir.glob("*.png"))
    candidates = sorted(candidate_dir.glob("*.png"))
    if not references or len(references) != len(candidates):
        return None
    positions = sorted(set((0, len(references) // 2, len(references) - 1)))
    squared_error = 0
    sample_values = 0
    for index in positions:
        left = _decode_quality_sample(ffmpeg, references[index])
        right = _decode_quality_sample(ffmpeg, candidates[index])
        if left is None or right is None or len(left) != len(right):
            return None
        squared_error += sum((a - b) * (a - b) for a, b in zip(left, right))
        sample_values += len(left)
    if sample_values <= 0:
        return None
    mse = squared_error / sample_values
    if mse <= 0:
        return 120.0
    return 10.0 * math.log10((255.0 * 255.0) / mse)


def run_candidate(
    *,
    executable: Path,
    model: Path,
    incoming: Path,
    outgoing: Path,
    policy: RifePolicy,
    uhd: bool,
    ffmpeg: str,
    timeout_seconds: float = 900.0,
) -> RifeSample:
    _clean(outgoing)
    inputs = validate_png_sequence(incoming, len(list(incoming.glob("*.png"))))
    if len(inputs) < 2:
        raise ValueError("RIFE benchmark requires at least two input PNGs")
    source_size = validate_png(inputs[0])
    native_target = len(inputs) * 2
    command = [
        str(executable),
        "-i", str(incoming),
        "-o", str(outgoing),
        "-n", str(native_target),
        "-m", str(model),
        "-g", str(policy.gpu_index),
        "-j", policy.jobs,
    ]
    if uhd:
        command.append("-u")
    command += ["-f", "%08d.png"]
    started = time.perf_counter()
    output_text = ""
    code = -1
    try:
        result = subprocess.run(
            command,
            cwd=str(executable.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(1.0, float(timeout_seconds)),
            check=False,
        )
        code = int(result.returncode)
        output_text = result.stdout or ""
    except subprocess.TimeoutExpired as exc:
        output_text = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        output_text += "\nbenchmark timeout"
    except OSError as exc:
        output_text = str(exc)
    elapsed = max(0.000001, time.perf_counter() - started)

    outputs = sorted(outgoing.glob("*.png"))
    integrity_ok = False
    black_ok = False
    if code == 0 and len(outputs) == native_target:
        try:
            validated = validate_png_sequence(outgoing, native_target)
            integrity_ok = all(validate_png(frame) == source_size for frame in validated)
            black_ok = integrity_ok and _black_frame_ok(ffmpeg, validated)
        except ValueError:
            integrity_ok = False
            black_ok = False
    return RifeSample(
        policy=policy,
        wall_seconds=elapsed,
        integrity_ok=integrity_ok,
        oom=looks_like_oom(output_text),
        output_frames=len(outputs),
        expected_frames=native_target,
        black_frame_ok=black_ok,
    )


def benchmark_and_record(
    store: RifeTuningStore,
    key: RifeTuningKey,
    candidates: Iterable[RifePolicy],
    *,
    executable: Path,
    model: Path,
    incoming: Path,
    work_dir: Path,
    uhd: bool,
    ffmpeg: str,
    timeout_seconds: float = 900.0,
) -> tuple[RifePolicy | None, tuple[RifeSample, ...]]:
    """Benchmark candidates; baseline integrity and visual parity outrank speed."""
    materialized = tuple(candidates)
    if not materialized:
        raise ValueError("no RIFE candidates supplied")
    work_dir.mkdir(parents=True, exist_ok=True)
    samples: list[RifeSample] = []
    baseline_dir = work_dir / "candidate_01"
    baseline = run_candidate(
        executable=executable,
        model=model,
        incoming=incoming,
        outgoing=baseline_dir,
        policy=materialized[0],
        uhd=uhd,
        ffmpeg=ffmpeg,
        timeout_seconds=timeout_seconds,
    )
    samples.append(baseline)
    if not baseline.accepted:
        return None, tuple(samples)

    for index, policy in enumerate(materialized[1:], start=2):
        candidate_dir = work_dir / f"candidate_{index:02d}"
        sample = run_candidate(
            executable=executable,
            model=model,
            incoming=incoming,
            outgoing=candidate_dir,
            policy=policy,
            uhd=uhd,
            ffmpeg=ffmpeg,
            timeout_seconds=timeout_seconds,
        )
        if sample.accepted:
            psnr = sampled_psnr(ffmpeg, baseline_dir, candidate_dir)
            quality_ok = psnr is not None and psnr >= QUALITY_PSNR_FLOOR_DB
            sample = replace(sample, quality_ok=quality_ok, quality_psnr_db=psnr)
        samples.append(sample)
    winner = store.record_samples(key, samples, fallback=materialized[0])
    return winner, tuple(samples)
