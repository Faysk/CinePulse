from __future__ import annotations

"""Physical H5 NVDEC/CUDA equivalence benchmark.

This script never grants a generic GPU PASS. It records one exact media policy
only when the candidate beats all structural, color-metadata, timing and
quality gates against the authoritative CPU baseline.
"""

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from cinepulse.gpu_media import (
    GpuMediaEvidence,
    GpuMediaKey,
    GpuMediaPolicy,
    GpuMediaTuningStore,
    detect_gpu_media_capabilities,
    safe_candidate_policies,
)
from cinepulse.hardware import detect_hardware
from cinepulse.media_profile import ColorProfile


PSNR_RE = re.compile(r"average:([0-9]+(?:\.[0-9]+)?|inf)", re.IGNORECASE)
SSIM_RE = re.compile(r"All:([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)


def _run(command: list[str], *, timeout: float, capture: bool = False) -> tuple[float, str]:
    started = time.perf_counter()
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(1.0, timeout),
        check=False,
    )
    elapsed = max(0.000001, time.perf_counter() - started)
    text = (result.stdout or "") + "\n" + (result.stderr or "")
    if result.returncode:
        tail = "\n".join(text.splitlines()[-30:])
        raise RuntimeError(f"FFmpeg exited {result.returncode}:\n{tail}")
    return elapsed, text


def _probe(ffprobe: str, path: Path) -> dict:
    result = subprocess.run(
        [
            ffprobe,
            "-v", "error",
            "-show_streams",
            "-show_format",
            "-count_frames",
            "-of", "json",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"ffprobe failed for {path}: {result.stderr[-2000:]}")
    return json.loads(result.stdout)


def _video(probe: dict) -> dict:
    return next((stream for stream in probe.get("streams", []) if stream.get("codec_type") == "video"), {})


def _audio(probe: dict) -> dict:
    return next((stream for stream in probe.get("streams", []) if stream.get("codec_type") == "audio"), {})


def _number(value: object) -> float | None:
    try:
        return float(value) if value is not None and str(value) not in {"", "N/A"} else None
    except (TypeError, ValueError):
        return None


def _frames(stream: dict) -> int | None:
    for key in ("nb_read_frames", "nb_frames"):
        try:
            value = stream.get(key)
            if value not in (None, "N/A", ""):
                return int(value)
        except (TypeError, ValueError):
            pass
    return None


def _duration(probe: dict) -> float | None:
    value = _number(probe.get("format", {}).get("duration"))
    if value is not None:
        return value
    values = [_number(stream.get("duration")) for stream in probe.get("streams", [])]
    valid = [value for value in values if value is not None]
    return max(valid) if valid else None


def _profile(video: dict) -> ColorProfile:
    return ColorProfile.from_probe({"streams": [video]})


def _metadata_signature(video: dict) -> tuple[object, ...]:
    return tuple(
        video.get(name)
        for name in (
            "width",
            "height",
            "pix_fmt",
            "color_range",
            "color_space",
            "color_transfer",
            "color_primaries",
        )
    )


def _metric(ffmpeg: str, baseline: Path, candidate: Path, filter_name: str, timeout: float) -> float:
    _elapsed, text = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostdin",
            "-i", str(baseline),
            "-i", str(candidate),
            "-lavfi", f"[0:v:0][1:v:0]{filter_name}",
            "-an",
            "-f", "null",
            "-",
        ],
        timeout=timeout,
        capture=True,
    )
    match = PSNR_RE.search(text) if filter_name == "psnr" else SSIM_RE.search(text)
    if not match:
        raise RuntimeError(f"could not parse {filter_name} result")
    raw = match.group(1).lower()
    return 999.0 if raw == "inf" else float(raw)


def _color_args(profile: ColorProfile) -> list[str]:
    range_arg = "pc" if profile.range in {"pc", "full"} else "tv"
    return [
        "-color_primaries", profile.primaries,
        "-color_trc", profile.transfer,
        "-colorspace", profile.space,
        "-color_range", range_arg,
    ]


def _build_baseline(
    ffmpeg: str,
    source: Path,
    output: Path,
    *,
    profile: ColorProfile,
    width: int,
    height: int,
    scale: bool,
) -> list[str]:
    command = [ffmpeg, "-y", "-hide_banner", "-nostdin", "-i", str(source), "-map", "0:v:0", "-map", "0:a?"]
    if scale:
        # zscale remains the quality reference. No tone-map or gamut conversion
        # is allowed in this benchmark envelope.
        command += ["-vf", f"zscale=w={width}:h={height}:dither=error_diffusion,format={profile.pixel_format}"]
    else:
        command += ["-vf", f"format={profile.pixel_format}"]
    command += ["-c:v", "ffv1", "-level", "3", "-c:a", "copy"] + _color_args(profile) + [str(output)]
    return command


def _build_candidate(
    ffmpeg: str,
    source: Path,
    output: Path,
    *,
    policy: GpuMediaPolicy,
    profile: ColorProfile,
    width: int,
    height: int,
) -> list[str]:
    command = [ffmpeg, "-y", "-hide_banner", "-nostdin"] + policy.input_args() + ["-i", str(source), "-map", "0:v:0", "-map", "0:a?"]
    filters: list[str] = []
    if policy.scaler:
        filters.append(policy.scale_filter(width, height))
    # H5 phase-A benchmarks resident decode/scale, then downloads once to the
    # same lossless reference format. A fully resident NVENC delivery candidate
    # is a separate evidence key and is not silently inferred from this result.
    filters.append(f"hwdownload,format={profile.pixel_format}")
    command += ["-vf", ",".join(filters), "-c:v", "ffv1", "-level", "3", "-c:a", "copy"]
    command += _color_args(profile) + [str(output)]
    return command


def _integrity(
    source_probe: dict,
    baseline_probe: dict,
    candidate_probe: dict,
) -> tuple[bool, bool, bool, bool]:
    baseline_video = _video(baseline_probe)
    candidate_video = _video(candidate_probe)
    metadata_ok = _metadata_signature(baseline_video) == _metadata_signature(candidate_video)
    baseline_frames = _frames(baseline_video)
    candidate_frames = _frames(candidate_video)
    frame_count_ok = baseline_frames is not None and baseline_frames == candidate_frames
    duration_base = _duration(baseline_probe)
    duration_candidate = _duration(candidate_probe)
    duration_ok = (
        duration_base is not None
        and duration_candidate is not None
        and abs(duration_base - duration_candidate) <= 0.020
    )
    source_has_audio = bool(_audio(source_probe))
    baseline_has_audio = bool(_audio(baseline_probe))
    candidate_has_audio = bool(_audio(candidate_probe))
    audio_sync_ok = duration_ok and (
        (not source_has_audio and not baseline_has_audio and not candidate_has_audio)
        or (source_has_audio and baseline_has_audio and candidate_has_audio)
    )
    integrity_ok = bool(candidate_video) and candidate_probe.get("format", {}).get("size") not in (None, "0", 0)
    return integrity_ok, metadata_ok, frame_count_ok, audio_sync_ok


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Physical NVDEC/CUDA equivalence benchmark for CinePulse H5")
    result.add_argument("--input", type=Path, required=True)
    result.add_argument("--cache", type=Path, required=True)
    result.add_argument("--ffmpeg", default="ffmpeg")
    result.add_argument("--ffprobe", default="ffprobe")
    result.add_argument("--gpu-index", type=int, default=0)
    result.add_argument("--scale-width", type=int, default=0)
    result.add_argument("--scale-height", type=int, default=0)
    result.add_argument("--timeout", type=float, default=900.0)
    return result


def main() -> int:
    args = parser().parse_args()
    ffmpeg = shutil.which(args.ffmpeg) or (str(args.ffmpeg) if Path(args.ffmpeg).is_file() else "")
    ffprobe = shutil.which(args.ffprobe) or (str(args.ffprobe) if Path(args.ffprobe).is_file() else "")
    if not ffmpeg or not ffprobe:
        raise SystemExit("FFmpeg and FFprobe are required")
    source_probe = _probe(ffprobe, args.input)
    source_video = _video(source_probe)
    if not source_video:
        raise SystemExit("No video stream found")
    profile = _profile(source_video)
    codec = str(source_video.get("codec_name") or "unknown")
    source_w = int(source_video.get("width") or 0)
    source_h = int(source_video.get("height") or 0)
    do_scale = args.scale_width > 0 and args.scale_height > 0 and (args.scale_width, args.scale_height) != (source_w, source_h)
    width = args.scale_width if do_scale else source_w
    height = args.scale_height if do_scale else source_h

    hardware = detect_hardware()
    if not hardware.gpu:
        raise SystemExit("No NVIDIA GPU detected; no physical H5 evidence recorded")
    capabilities = detect_gpu_media_capabilities(ffmpeg)
    candidates = safe_candidate_policies(
        capabilities,
        codec=codec,
        profile=profile,
        gpu_index=max(0, args.gpu_index),
        allow_scale=do_scale,
    )
    if not candidates:
        raise SystemExit("No safe CUDA media candidate for this exact source/color contract")
    # Prefer the scale candidate when scaling is requested, otherwise decode.
    policy = next((item for item in reversed(candidates) if bool(item.scaler) == do_scale), candidates[0])
    operation = policy.operation
    key = GpuMediaKey.from_profile(
        gpu_name=hardware.gpu,
        driver=hardware.driver or "unknown-driver",
        ffmpeg_fingerprint=capabilities.fingerprint,
        codec=codec,
        width=source_w,
        height=source_h,
        profile=profile,
        operation=operation,
    )

    with tempfile.TemporaryDirectory(prefix="cinepulse-h5-") as temporary:
        root = Path(temporary)
        baseline = root / "baseline.mkv"
        candidate = root / "candidate.mkv"
        baseline_seconds, _ = _run(
            _build_baseline(ffmpeg, args.input, baseline, profile=profile, width=width, height=height, scale=do_scale),
            timeout=args.timeout,
        )
        candidate_seconds, _ = _run(
            _build_candidate(ffmpeg, args.input, candidate, policy=policy, profile=profile, width=width, height=height),
            timeout=args.timeout,
        )
        baseline_probe = _probe(ffprobe, baseline)
        candidate_probe = _probe(ffprobe, candidate)
        integrity_ok, metadata_ok, frame_count_ok, audio_sync_ok = _integrity(
            source_probe, baseline_probe, candidate_probe
        )
        psnr = _metric(ffmpeg, baseline, candidate, "psnr", args.timeout)
        ssim = _metric(ffmpeg, baseline, candidate, "ssim", args.timeout)
        evidence = GpuMediaEvidence(
            policy=policy,
            baseline_seconds=baseline_seconds,
            candidate_seconds=candidate_seconds,
            psnr_db=psnr,
            ssim=ssim,
            integrity_ok=integrity_ok,
            metadata_ok=metadata_ok,
            frame_count_ok=frame_count_ok,
            audio_sync_ok=audio_sync_ok,
        )
        recorded = GpuMediaTuningStore(args.cache).record(key, evidence)

    payload = {
        "physical_acceptance": "exact-evidence-recorded-not-global-pass" if recorded else "rejected",
        "hardware": hardware.as_dict(),
        "ffmpeg_fingerprint": capabilities.fingerprint,
        "source": {
            "codec": codec,
            "width": source_w,
            "height": source_h,
            "profile": profile.label,
        },
        "target": {"width": width, "height": height},
        "operation": operation,
        "policy": {"decoder": policy.decoder, "scaler": policy.scaler, "gpu_index": policy.gpu_index},
        "baseline_seconds": evidence.baseline_seconds,
        "candidate_seconds": evidence.candidate_seconds,
        "speedup": evidence.speedup,
        "psnr_db": evidence.psnr_db,
        "ssim": evidence.ssim,
        "integrity_ok": evidence.integrity_ok,
        "metadata_ok": evidence.metadata_ok,
        "frame_count_ok": evidence.frame_count_ok,
        "audio_sync_ok": evidence.audio_sync_ok,
        "accepted": evidence.accepted,
        "cache_key": key.token(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if recorded else 2


if __name__ == "__main__":
    raise SystemExit(main())
