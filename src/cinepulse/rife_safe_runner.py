from __future__ import annotations

import argparse
import os
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB`\x82"


@dataclass(frozen=True)
class RifeExecutionPolicy:
    uhd: bool
    jobs: str
    native_target: int
    requested_target: int


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


def execution_policy(input_frames: int, width: int, height: int, requested_target: int, device: str) -> RifeExecutionPolicy:
    if input_frames < 2:
        raise ValueError("RIFE requer ao menos dois quadros de entrada")
    if requested_target < 2:
        raise ValueError("RIFE requer ao menos dois quadros de saída")
    native_target = input_frames * 2
    uhd = max(width, height) >= 3840 or width * height >= 3840 * 2160
    if device == "cpu":
        jobs = "1:2:2"
    elif uhd:
        jobs = "1:1:1"
    else:
        jobs = "2:2:2"
    return RifeExecutionPolicy(
        uhd=uhd,
        jobs=jobs,
        native_target=native_target,
        requested_target=requested_target,
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
    result = subprocess.run(command, cwd=str(cwd) if cwd else None, check=False)
    if result.returncode:
        raise RuntimeError(f"processo terminou com código {result.returncode}")


def _move_native_frames(native_dir: Path, output_dir: Path, expected: int) -> None:
    frames = validate_png_sequence(native_dir, expected)
    for index, frame in enumerate(frames, start=1):
        os.replace(frame, output_dir / f"{index:08d}.png")
    validate_png_sequence(output_dir, expected)


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
    policy = execution_policy(len(input_frames), width, height, requested_target, device)
    outgoing.mkdir(parents=True, exist_ok=True)
    if any(outgoing.iterdir()):
        raise ValueError(f"diretório de saída RIFE não está vazio: {outgoing}")
    native_dir = outgoing.with_name(f".{outgoing.name}.native-{os.getpid()}")
    if native_dir.exists():
        shutil.rmtree(native_dir, ignore_errors=True)
    native_dir.mkdir(parents=False)
    try:
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
        if device == "cpu":
            command += ["-g", "-1"]
        command += ["-j", policy.jobs]
        if policy.uhd:
            command.append("-u")
        command += ["-f", "%08d.png"]
        print(
            "CINEPULSE_RIFE_SAFE POLICY "
            f"input={len(input_frames)} native={policy.native_target} requested={requested_target} "
            f"uhd={policy.uhd} jobs={policy.jobs} device={device}",
            flush=True,
        )
        _run(command, cwd=rife_executable.parent)
        native_frames = validate_png_sequence(native_dir, policy.native_target)
        if requested_target == policy.native_target:
            _move_native_frames(native_dir, outgoing, requested_target)
            return policy

        ffmpeg_executable = _find_ffmpeg(rife_executable, ffmpeg)
        first_number = int(native_frames[0].stem)
        input_rate = max(1, policy.native_target - 1)
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
            f"CINEPULSE_RIFE_SAFE RETIME native={policy.native_target} requested={requested_target} mode=uniform-blend",
            flush=True,
        )
        return policy
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
