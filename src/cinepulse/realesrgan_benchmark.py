from __future__ import annotations

import shutil
import struct
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .realesrgan_tuning import RealEsrganPolicy, RealEsrganSample, RealEsrganTuningKey, RealEsrganTuningStore


OOM_TOKENS = (
    "out of memory",
    "oom",
    "failed to allocate",
    "vk_error_out_of_device_memory",
    "device memory allocation failed",
)


def png_dimensions(path: Path) -> tuple[int, int] | None:
    """Read PNG IHDR dimensions without adding an image-library dependency."""
    try:
        with Path(path).open("rb") as handle:
            header = handle.read(24)
    except OSError:
        return None
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", header[16:24])
    if width < 1 or height < 1:
        return None
    return int(width), int(height)


def looks_like_oom(text: str) -> bool:
    value = str(text or "").lower()
    return any(token in value for token in OOM_TOKENS)


def _clean_output(directory: Path) -> None:
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True, exist_ok=True)


def run_candidate(
    executable: Path,
    model_dir: Path,
    input_dir: Path,
    output_dir: Path,
    *,
    policy: RealEsrganPolicy,
    model: str,
    scale: int,
    expected_frames: int,
    expected_size: tuple[int, int] | None,
    cwd: Path | None = None,
    timeout_seconds: float = 900.0,
) -> RealEsrganSample:
    """Run one physical candidate and return integrity-gated evidence."""
    _clean_output(output_dir)
    command = [
        str(executable),
        "-i", str(input_dir),
        "-o", str(output_dir),
        "-m", str(model_dir),
        "-n", model,
        "-s", str(max(1, int(scale))),
        "-f", "png",
    ] + policy.command_args()
    started = time.perf_counter()
    output_text = ""
    code = -1
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd or executable.parent),
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

    outputs = sorted(output_dir.glob("*.png"))
    output_frames = len(outputs)
    size_ok = True
    if expected_size is not None and outputs:
        expected_output_size = (
            max(1, int(expected_size[0])) * max(1, int(scale)),
            max(1, int(expected_size[1])) * max(1, int(scale)),
        )
        size_ok = all(png_dimensions(path) == expected_output_size for path in outputs)
    integrity_ok = (
        code == 0
        and output_frames == max(0, int(expected_frames))
        and output_frames > 0
        and size_ok
    )
    return RealEsrganSample(
        policy=policy,
        wall_seconds=elapsed,
        integrity_ok=integrity_ok,
        oom=looks_like_oom(output_text),
        output_frames=output_frames,
        expected_frames=max(0, int(expected_frames)),
    )


def benchmark_and_record(
    store: RealEsrganTuningStore,
    key: RealEsrganTuningKey,
    candidates: Iterable[RealEsrganPolicy],
    *,
    executable: Path,
    model_dir: Path,
    input_dir: Path,
    work_dir: Path,
    model: str,
    scale: int,
    expected_size: tuple[int, int] | None,
    timeout_seconds: float = 900.0,
) -> tuple[RealEsrganPolicy | None, tuple[RealEsrganSample, ...]]:
    frames = len(list(Path(input_dir).glob("*.png")))
    if frames < 1:
        raise ValueError("benchmark input directory contains no PNG frames")
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    samples: list[RealEsrganSample] = []
    materialized = tuple(candidates)
    if not materialized:
        raise ValueError("no Real-ESRGAN candidates supplied")
    for index, policy in enumerate(materialized, start=1):
        output_dir = work_dir / f"candidate_{index:02d}"
        sample = run_candidate(
            executable,
            model_dir,
            input_dir,
            output_dir,
            policy=policy,
            model=model,
            scale=scale,
            expected_frames=frames,
            expected_size=expected_size,
            timeout_seconds=timeout_seconds,
        )
        samples.append(sample)

    # Candidate zero is the known/current runtime baseline. If that baseline
    # cannot complete the exact same sample with integrity, the benchmark run
    # itself is not trustworthy enough to promote a different policy.
    if not samples[0].accepted:
        return None, tuple(samples)

    winner = store.record_samples(key, samples, fallback=materialized[0])
    return winner, tuple(samples)


def evidence_payload(
    key: RealEsrganTuningKey,
    winner: RealEsrganPolicy | None,
    samples: Iterable[RealEsrganSample],
) -> dict[str, object]:
    values = tuple(samples)
    return {
        "key": key.token(),
        "winner": asdict(winner) if winner is not None else None,
        "physical_acceptance": "evidence-recorded-not-global-pass" if winner is not None else "rejected",
        "samples": [
            {
                "policy": asdict(sample.policy),
                "wall_seconds": sample.wall_seconds,
                "integrity_ok": sample.integrity_ok,
                "oom": sample.oom,
                "output_frames": sample.output_frames,
                "expected_frames": sample.expected_frames,
                "accepted": sample.accepted,
            }
            for sample in values
        ],
    }
