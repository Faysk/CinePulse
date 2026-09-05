from __future__ import annotations

import shutil
import subprocess
import time
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
        # Only reject near-zero machine-black output. Real dark footage normally
        # retains codec/image noise or non-zero structure and remains accepted.
        if max(values, default=0) <= 1:
            return False
    return True


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
    """Benchmark a bounded RIFE candidate set and persist only proven evidence.

    The first policy is the conservative baseline by contract.  If that baseline
    cannot pass the same integrity gates on the real machine, Phase 3 stops there
    instead of trying more aggressive concurrency against an already unstable
    hardware/software state.
    """
    materialized = tuple(candidates)
    if not materialized:
        raise ValueError("no RIFE candidates supplied")
    work_dir.mkdir(parents=True, exist_ok=True)
    samples: list[RifeSample] = []

    baseline = run_candidate(
        executable=executable,
        model=model,
        incoming=incoming,
        outgoing=work_dir / "candidate_01",
        policy=materialized[0],
        uhd=uhd,
        ffmpeg=ffmpeg,
        timeout_seconds=timeout_seconds,
    )
    samples.append(baseline)
    if not baseline.accepted:
        return None, tuple(samples)

    for index, policy in enumerate(materialized[1:], start=2):
        samples.append(
            run_candidate(
                executable=executable,
                model=model,
                incoming=incoming,
                outgoing=work_dir / f"candidate_{index:02d}",
                policy=policy,
                uhd=uhd,
                ffmpeg=ffmpeg,
                timeout_seconds=timeout_seconds,
            )
        )
    winner = store.record_samples(key, samples, fallback=materialized[0])
    return winner, tuple(samples)
