"""Crash-safe repair of RIFE segments containing deterministic black frames."""

from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import shutil
import sys
from typing import Callable

from .matroska_quality import MatroskaSegmentQuality, inspect_matroska_segment
from .rife_recovery import (
    RecoveryContract,
    RecoveryError,
    RecoveryLogger,
    _run_logged,
    _safe_rmtree_child,
    _validate_video,
    _write_state,
    contiguous_segments,
    generate_rife_frames_safe,
    load_contract,
    source_chunk_counts,
)


def _quarantine_incomplete_repair(
    contract: RecoveryContract,
    index: int,
    log: Callable[[str], None],
) -> None:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidates = [
        contract.chunk_root / f"repair_{index:05d}_in",
        contract.chunk_root / f"repair_{index:05d}_out",
        contract.chunk_root / f"repair_{index:05d}_out_resampled",
        contract.chunk_root / f"segment_{index:05d}.repair.partial.mkv",
    ]
    for path in candidates:
        if not path.exists():
            continue
        target = contract.job_dir / f"interrupted_{path.name}_{stamp}"
        os.replace(path, target)
        log(f"REPAIR_QUARANTINE {path} -> {target}")


def audit_segments(
    segments: list[Path],
    log: Callable[[str], None],
) -> tuple[list[tuple[Path, MatroskaSegmentQuality]], int]:
    affected: list[tuple[Path, MatroskaSegmentQuality]] = []
    total_frames = 0
    total_black = 0
    for number, segment in enumerate(segments, start=1):
        quality = inspect_matroska_segment(segment)
        if quality.packet_count <= 0:
            raise RecoveryError(f"{segment.name}: nenhum pacote de video encontrado")
        total_frames += quality.packet_count
        total_black += quality.solid_black_frames
        if quality.solid_black_frames:
            affected.append((segment, quality))
        if number % 100 == 0 or number == len(segments):
            log(
                f"BLACK_AUDIT {number}/{len(segments)} affected={len(affected)} "
                f"black_frames={total_black}"
            )
    log(
        f"BLACK_AUDIT_COMPLETE segments={len(segments)} frames={total_frames} "
        f"affected={len(affected)} black_frames={total_black}"
    )
    return affected, total_frames


def _repair_one(
    contract: RecoveryContract,
    segment: Path,
    quality: MatroskaSegmentQuality,
    source_counts: list[int],
    log: Callable[[str], None],
    *,
    timeout_minutes: float,
) -> None:
    index = int(segment.stem.split("_")[-1])
    source_frames = source_counts[index - 1]
    source_start = sum(source_counts[: index - 1])
    source_fps = contract.source_fps
    incoming = contract.chunk_root / f"repair_{index:05d}_in"
    outgoing = contract.chunk_root / f"repair_{index:05d}_out"
    partial = contract.chunk_root / f"segment_{index:05d}.repair.partial.mkv"
    _quarantine_incomplete_repair(contract, index, log)
    incoming.mkdir(parents=False, exist_ok=False)
    outgoing.mkdir(parents=False, exist_ok=False)
    stop_file = contract.job_dir / "STOP_RECOVERY"

    log(
        f"REPAIR_START segment={index} black={quality.solid_black_frames}/{quality.packet_count} "
        f"source={source_start + 1}-{source_start + source_frames} mode=8k-uhd"
    )
    extract = [
        str(contract.ffmpeg), "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
        "-ss", f"{source_start / source_fps:.6f}", "-i", str(contract.cache),
        "-map", "0:v:0", "-an", "-vf", f"fps={source_fps:.8f}",
        "-frames:v", str(source_frames), "-start_number", "0",
        "-progress", "pipe:1", "-nostats", str(incoming / "%08d.png"),
    ]
    _run_logged(
        extract,
        label=f"repair-extract-{index:05d}",
        log=log,
        timeout_seconds=timeout_minutes * 60,
        progress_probe=lambda: len(list(incoming.glob("*.png"))),
        stop_file=stop_file,
    )
    extracted = len(list(incoming.glob("*.png")))
    if extracted != source_frames:
        raise RecoveryError(f"Reparo {index}: extraiu {extracted}/{source_frames} quadros")

    frames, frame_directory = generate_rife_frames_safe(
        contract,
        incoming,
        outgoing,
        source_frames=source_frames,
        target_frames=quality.packet_count,
        label=f"repair-rife-{index:05d}",
        log=log,
        timeout_minutes=timeout_minutes,
        stop_file=stop_file,
    )
    first_number = int(frames[0].stem)
    merge = [
        str(contract.ffmpeg), "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
        "-framerate", f"{contract.target_fps:.8f}", "-start_number", str(first_number),
        "-i", str(frame_directory / "%08d.png"), "-map", "0:v:0", "-an",
        "-frames:v", str(len(frames)), "-c:v", "ffv1", "-level", "3",
        "-coder", "1", "-context", "1", "-g", "1", "-slicecrc", "1",
        "-pix_fmt", "yuv420p", "-threads", str(contract.cpu_threads),
        "-progress", "pipe:1", "-nostats", str(partial),
    ]
    _run_logged(
        merge,
        label=f"repair-segment-{index:05d}",
        log=log,
        timeout_seconds=timeout_minutes * 60,
        stop_file=stop_file,
    )
    _validate_video(
        ffprobe=contract.ffprobe,
        path=partial,
        width=contract.target_width,
        height=contract.target_height,
        fps=contract.target_fps,
        codec="ffv1",
    )
    repaired_quality = inspect_matroska_segment(partial)
    if repaired_quality.packet_count != quality.packet_count:
        raise RecoveryError(
            f"Reparo {index}: segmento tem {repaired_quality.packet_count}/{quality.packet_count} pacotes"
        )
    if repaired_quality.solid_black_frames:
        raise RecoveryError(
            f"Reparo {index}: modo UHD ainda produziu {repaired_quality.solid_black_frames} quadros pretos"
        )

    backup_dir = contract.job_dir / "black-frame-quarantine"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / segment.name
    if not backup.exists():
        try:
            os.link(segment, backup)
        except OSError:
            shutil.copy2(segment, backup)
    os.replace(partial, segment)
    _safe_rmtree_child(contract.chunk_root, incoming)
    if frame_directory != outgoing:
        _safe_rmtree_child(contract.chunk_root, frame_directory)
    _safe_rmtree_child(contract.chunk_root, outgoing)
    log(
        f"REPAIR_COMMIT segment={index} old_black={quality.solid_black_frames} "
        f"frames={repaired_quality.packet_count} backup={backup}"
    )


def repair_black_segments(
    contract: RecoveryContract,
    log: Callable[[str], None],
    *,
    timeout_minutes: float,
) -> int:
    stop_file = contract.job_dir / "STOP_RECOVERY"
    if stop_file.exists():
        raise KeyboardInterrupt(f"Stop file detected: {stop_file}")
    segments = contiguous_segments(contract.chunk_root)
    source_counts = source_chunk_counts(contract.total_source_frames, contract.chunk_frames)
    if len(segments) > len(source_counts):
        raise RecoveryError("Ha mais segmentos que lotes previstos")
    affected, completed_target = audit_segments(segments, log)
    completed_source = sum(source_counts[: len(segments)])
    backup_dir = contract.job_dir / "black-frame-quarantine"
    previously_repaired = len(list(backup_dir.glob("segment_*.mkv"))) if backup_dir.is_dir() else 0
    repair_total = previously_repaired + len(affected)
    _write_state(
        contract,
        phase="repair",
        completed_segments=len(segments),
        completed_source_frames=completed_source,
        completed_target_frames=completed_target,
        extra={
            "remaining_chunks": len(source_counts) - len(segments),
            "repair_total": repair_total,
            "repair_completed": previously_repaired,
            "repair_remaining": len(affected),
        },
    )
    for position, (segment, quality) in enumerate(affected, start=1):
        if stop_file.exists():
            raise KeyboardInterrupt(f"Stop file detected: {stop_file}")
        _repair_one(
            contract,
            segment,
            quality,
            source_counts,
            log,
            timeout_minutes=timeout_minutes,
        )
        _write_state(
            contract,
            phase="repair",
            completed_segments=len(segments),
            completed_source_frames=completed_source,
            completed_target_frames=completed_target,
            extra={
                "remaining_chunks": len(source_counts) - len(segments),
                "repair_total": repair_total,
                "repair_completed": previously_repaired + position,
                "repair_remaining": len(affected) - position,
            },
        )
    _write_state(
        contract,
        phase="rife",
        completed_segments=len(segments),
        completed_source_frames=completed_source,
        completed_target_frames=completed_target,
        extra={
            "remaining_chunks": len(source_counts) - len(segments),
            "quality_repair": "complete",
            "repaired_segments": repair_total,
        },
    )
    log(f"BLACK_REPAIR_COMPLETE repaired_segments={repair_total}")
    return repair_total


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repara segmentos RIFE 8K com quadros pretos")
    parser.add_argument("--app-root", required=True)
    parser.add_argument("--history-dir", required=True)
    parser.add_argument("--chunk-root", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--source")
    parser.add_argument("--output")
    parser.add_argument("--timeout-minutes", type=float, default=20.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    contract = load_contract(args)
    logger = RecoveryLogger(contract.log_path)
    try:
        logger(f"BLACK_REPAIR_START job={contract.job_id}")
        repair_black_segments(contract, logger, timeout_minutes=args.timeout_minutes)
        return 0
    except KeyboardInterrupt:
        logger("BLACK_REPAIR_STOPPED graceful interruption; repaired segments remain committed")
        return 130
    except Exception as exc:
        logger(f"BLACK_REPAIR_FAILED {type(exc).__name__}: {exc}")
        return 1
    finally:
        logger.close()


if __name__ == "__main__":
    raise SystemExit(main())
