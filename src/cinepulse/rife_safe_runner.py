from __future__ import annotations

import argparse
import os
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .hardware import detect_hardware
from .paths import PATHS
from .rife_tuning import RifePolicy, RifeTuningKey, RifeTuningStore, fallback_policy


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB`\x82"
OOM_TOKENS = (
    "out of memory",
    "oom",
    "failed to allocate",
    "vk_error_out_of_device_memory",
    "device memory allocation failed",
)


@dataclass(frozen=True)
class RifeExecutionPolicy:
    uhd: bool
    jobs: str
    native_target: int
    requested_target: int
    gpu_index: int = 0
    measured: bool = False


def _png_dimensions(path: Path) -> tuple[int, int]:
    try:
        with path.open("rb") as handle:
            if handle.read(8) != PNG_SIGNATURE:
                raise ValueError(f"assinatura PNG inválida em {path.name}")
            length = struct.unpack(">I", handle.read(4))[0]
            chunk = handle.read(4)
            if chunk != b"IHDR" or length < 8:
                raise ValueError(f"IHDR ausente ou inválido em {path.name}")
            width, height = struct.unpack(">II", handle.read(8))
    except (OSError, struct.error) as exc:
        raise ValueError(f"não foi possível ler {path.name}: {exc}") from exc
    if width <= 0 or height <= 0:
        raise ValueError(f"dimensões PNG inválidas em {path.name}")
    return width, height


def validate_png(path: Path) -> tuple[int, int]:
    width, height = _png_dimensions(path)
    try:
        if path.stat().st_size < 33:
            raise ValueError(f"PNG pequeno demais em {path.name}")
        with path.open("rb") as handle:
            handle.seek(-12, os.SEEK_END)
            if handle.read(12) != PNG_IEND:
                raise ValueError(f"PNG truncado em {path.name}")
    except OSError as exc:
        raise ValueError(f"não foi possível validar {path.name}: {exc}") from exc
    return width, height


def validate_png_sequence(directory: Path, expected: int) -> list[Path]:
    frames = sorted(directory.glob("*.png"))
    if len(frames) != expected:
        raise ValueError(f"sequência produziu {len(frames)}/{expected} PNGs")
    dimensions: tuple[int, int] | None = None
    for frame in frames:
        current = validate_png(frame)
        if dimensions is None:
            dimensions = current
        elif current != dimensions:
            raise ValueError(
                f"dimensões inconsistentes em {frame.name}: {current[0]}x{current[1]} != {dimensions[0]}x{dimensions[1]}"
            )
    return frames


def execution_policy(
    input_frames: int,
    width: int,
    height: int,
    requested_target: int,
    device: str,
    *,
    jobs_override: str = "",
    gpu_index: int = 0,
    measured: bool = False,
) -> RifeExecutionPolicy:
    if input_frames < 2:
        raise ValueError("RIFE requer ao menos dois quadros de entrada")
    if requested_target < 2:
        raise ValueError("RIFE requer ao menos dois quadros de saída")
    native_target = input_frames * 2
    uhd = max(width, height) >= 3840 or width * height >= 3840 * 2160
    if device == "cpu":
        jobs = "1:2:2"
        selected_gpu = -1
    else:
        fallback = fallback_policy(uhd=uhd, gpu_index=max(0, int(gpu_index)))
        jobs = jobs_override or fallback.jobs
        RifePolicy(jobs, max(0, int(gpu_index)))
        selected_gpu = max(0, int(gpu_index))
    return RifeExecutionPolicy(
        uhd=uhd,
        jobs=jobs,
        native_target=native_target,
        requested_target=requested_target,
        gpu_index=selected_gpu,
        measured=bool(measured and device != "cpu"),
    )


def _find_ffmpeg(rife_executable: Path, override: str = "") -> str:
    if override:
        candidate = Path(override)
        if candidate.is_file():
            return str(candidate)
        resolved = shutil.which(override)
        if resolved:
            return resolved
        raise FileNotFoundError(f"FFmpeg informado não foi encontrado: {override}")
    resolved = shutil.which("ffmpeg")
    if resolved:
        return resolved
    for parent in rife_executable.resolve().parents:
        for relative in (
            Path("ffmpeg") / "bin" / "ffmpeg.exe",
            Path("ffmpeg") / "bin" / "ffmpeg",
            Path("components") / "ffmpeg" / "bin" / "ffmpeg.exe",
            Path("components") / "ffmpeg" / "bin" / "ffmpeg",
        ):
            candidate = parent / relative
            if candidate.is_file():
                return str(candidate)
    raise FileNotFoundError("FFmpeg não foi encontrado para o retime seguro do RIFE")


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    print("CINEPULSE_RIFE_SAFE RUN " + subprocess.list2cmdline(command), flush=True)
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.stdout:
        print(result.stdout.rstrip(), flush=True)
    if result.returncode:
        raise RuntimeError((result.stdout or "") + f"\nprocesso terminou com código {result.returncode}")


def _move_native_frames(native_dir: Path, output_dir: Path, expected: int) -> None:
    frames = validate_png_sequence(native_dir, expected)
    for index, frame in enumerate(frames, start=1):
        os.replace(frame, output_dir / f"{index:08d}.png")
    validate_png_sequence(output_dir, expected)


def _hardware_tuning_policy(width: int, height: int, model: Path) -> tuple[RifePolicy | None, RifeTuningKey | None, RifeTuningStore | None]:
    hardware = detect_hardware()
    if not hardware.gpu:
        return None, None, None
    key = RifeTuningKey(
        hardware.gpu,
        int(hardware.vram_mb or 0),
        hardware.driver or "unknown-driver",
        model.name or "rife-v4.6",
        width,
        height,
    )
    store = RifeTuningStore(PATHS.cache / "hardware" / "rife-tuning.json")
    policy = store.lookup(key, gpu_index=0)
    return policy, key, store


def _native_command(
    *,
    rife_executable: Path,
    model: Path,
    incoming: Path,
    native_dir: Path,
    policy: RifeExecutionPolicy,
) -> list[str]:
    command = [
        str(rife_executable),
        "-i",
        str(incoming),
        "-o",
        str(native_dir),
        "-n",
        str(policy.native_target),
        "-m",
        str(model),
    ]
    command += ["-g", str(policy.gpu_index)]
    command += ["-j", policy.jobs]
    if policy.uhd:
        command.append("-u")
    command += ["-f", "%08d.png"]
    return command


def _run_native_with_rollback(
    *,
    rife_executable: Path,
    model: Path,
    incoming: Path,
    native_dir: Path,
    policy: RifeExecutionPolicy,
    fallback: RifeExecutionPolicy,
    tuning_key: RifeTuningKey | None,
    tuning_store: RifeTuningStore | None,
) -> RifeExecutionPolicy:
    attempted_fallback = policy.jobs == fallback.jobs and policy.gpu_index == fallback.gpu_index
    current = policy
    while True:
        shutil.rmtree(native_dir, ignore_errors=True)
        native_dir.mkdir(parents=False)
        print(
            "CINEPULSE_RIFE_SAFE POLICY "
            f"native={current.native_target} requested={current.requested_target} "
            f"uhd={current.uhd} jobs={current.jobs} gpu={current.gpu_index} measured={current.measured}",
            flush=True,
        )
        try:
            _run(
                _native_command(
                    rife_executable=rife_executable,
                    model=model,
                    incoming=incoming,
                    native_dir=native_dir,
                    policy=current,
                ),
                cwd=rife_executable.parent,
            )
            validate_png_sequence(native_dir, current.native_target)
            return current
        except Exception as exc:
            if current.measured and tuning_key is not None and tuning_store is not None:
                tuning_store.invalidate(tuning_key)
                print(
                    "CINEPULSE_RIFE_SAFE TUNING_INVALIDATED "
                    f"jobs={current.jobs} reason={type(exc).__name__}",
                    flush=True,
                )
            if attempted_fallback or (current.jobs == fallback.jobs and current.gpu_index == fallback.gpu_index):
                raise
            text = str(exc).lower()
            oom = any(token in text for token in OOM_TOKENS)
            print(
                "CINEPULSE_RIFE_SAFE ROLLBACK "
                f"reason={'oom' if oom else 'instability/integrity'} "
                f"from={current.jobs} to={fallback.jobs}",
                flush=True,
            )
            current = fallback
            attempted_fallback = True


def run_safe_rife(
    *,
    rife_executable: Path,
    model: Path,
    incoming: Path,
    outgoing: Path,
    requested_target: int,
    device: str,
    ffmpeg: str = "",
) -> RifeExecutionPolicy:
    input_frames = validate_png_sequence(incoming, len(list(incoming.glob("*.png"))))
    if len(input_frames) < 2:
        raise ValueError("RIFE recebeu menos de dois PNGs válidos")
    width, height = validate_png(input_frames[0])
    uhd = max(width, height) >= 3840 or width * height >= 3840 * 2160
    tuned: RifePolicy | None = None
    tuning_key: RifeTuningKey | None = None
    tuning_store: RifeTuningStore | None = None
    if device == "gpu":
        tuned, tuning_key, tuning_store = _hardware_tuning_policy(width, height, model)
    fallback_spec = fallback_policy(uhd=uhd, gpu_index=0)
    fallback = execution_policy(
        len(input_frames), width, height, requested_target, device,
        jobs_override=fallback_spec.jobs if device == "gpu" else "",
        gpu_index=fallback_spec.gpu_index,
        measured=False,
    )
    policy = execution_policy(
        len(input_frames), width, height, requested_target, device,
        jobs_override=tuned.jobs if tuned is not None else fallback.jobs,
        gpu_index=tuned.gpu_index if tuned is not None else fallback.gpu_index,
        measured=tuned is not None,
    )
    outgoing.mkdir(parents=True, exist_ok=True)
    if any(outgoing.iterdir()):
        raise ValueError(f"diretório de saída RIFE não está vazio: {outgoing}")
    native_dir = outgoing.with_name(f".{outgoing.name}.native-{os.getpid()}")
    shutil.rmtree(native_dir, ignore_errors=True)
    native_dir.mkdir(parents=False)
    try:
        applied = _run_native_with_rollback(
            rife_executable=rife_executable,
            model=model,
            incoming=incoming,
            native_dir=native_dir,
            policy=policy,
            fallback=fallback,
            tuning_key=tuning_key,
            tuning_store=tuning_store,
        )
        native_frames = validate_png_sequence(native_dir, applied.native_target)
        if requested_target == applied.native_target:
            _move_native_frames(native_dir, outgoing, requested_target)
            return applied

        ffmpeg_executable = _find_ffmpeg(rife_executable, ffmpeg)
        first_number = int(native_frames[0].stem)
        input_rate = max(1, applied.native_target - 1)
        output_rate = max(1, requested_target - 1)
        retime = [
            ffmpeg_executable,
            "-y",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-framerate",
            str(input_rate),
            "-start_number",
            str(first_number),
            "-i",
            str(native_dir / "%08d.png"),
            "-vf",
            f"framerate=fps={output_rate}:interp_start=0:interp_end=255:scene=100",
            "-frames:v",
            str(requested_target),
            "-start_number",
            "1",
            str(outgoing / "%08d.png"),
        ]
        _run(retime)
        validate_png_sequence(outgoing, requested_target)
        print(
            f"CINEPULSE_RIFE_SAFE RETIME native={applied.native_target} requested={requested_target} mode=uniform-blend",
            flush=True,
        )
        return applied
    finally:
        shutil.rmtree(native_dir, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CinePulse crash-safe RIFE invocation")
    parser.add_argument("--rife", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--frames", required=True, type=int)
    parser.add_argument("--device", choices=("gpu", "cpu"), default="gpu")
    parser.add_argument("--ffmpeg", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run_safe_rife(
            rife_executable=Path(args.rife),
            model=Path(args.model),
            incoming=Path(args.input),
            outgoing=Path(args.output),
            requested_target=args.frames,
            device=args.device,
            ffmpeg=args.ffmpeg,
        )
        return 0
    except Exception as exc:
        print(f"CINEPULSE_RIFE_SAFE ERROR {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
