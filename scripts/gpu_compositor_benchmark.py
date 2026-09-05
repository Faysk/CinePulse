from __future__ import annotations

"""Physical H6 overlay_cuda parity benchmark against the real Composer reference.

Permission is granted only for one exact GPU/driver/FFmpeg/base/layer contract.
The baseline is ``export_composer_reference`` (NumPy RGBA), not FFmpeg's own CPU
overlay filter. This matters: proving CUDA against a different implementation
would not prove that replacing CinePulse's actual reference preserves pixels.
"""

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from cinepulse.composer_export import ComposerBaseProfile, ComposerExportRequest, export_composer_reference
from cinepulse.gpu_compositor import (
    COMPOSITOR_REFERENCE_ID,
    GpuCompositorEvidence,
    GpuCompositorKey,
    GpuCompositorStore,
    OverlayLayer,
    build_cuda_overlay_filter,
    cuda_layer_eligible,
    detect_gpu_compositor_capabilities,
)
from cinepulse.hardware import detect_hardware
from cinepulse.media_profile import ColorProfile
from cinepulse.overlay_composer import ComposerItem, OverlayComposerState

PSNR_RE = re.compile(r"average:([0-9]+(?:\.[0-9]+)?|inf)", re.IGNORECASE)
SSIM_RE = re.compile(r"All:([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)


def run(command: list[str], timeout: float, *, capture: bool = False) -> tuple[float, str]:
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
        raise RuntimeError("FFmpeg failed:\n" + "\n".join(text.splitlines()[-30:]))
    return elapsed, text


def probe(ffprobe: str, path: Path) -> dict:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-count_frames", "-of", "json", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    return json.loads(result.stdout)


def video_stream(payload: dict) -> dict:
    return next((item for item in payload.get("streams", []) if item.get("codec_type") == "video"), {})


def audio_stream(payload: dict) -> dict:
    return next((item for item in payload.get("streams", []) if item.get("codec_type") == "audio"), {})


def frames(stream: dict) -> int | None:
    for key in ("nb_read_frames", "nb_frames"):
        value = stream.get(key)
        if value not in (None, "N/A", ""):
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return None


def duration(payload: dict) -> float | None:
    try:
        return float(payload.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        return None


def signature(stream: dict) -> tuple[object, ...]:
    return tuple(stream.get(name) for name in (
        "width", "height", "pix_fmt", "color_range", "color_space", "color_transfer", "color_primaries"
    ))


def metric(ffmpeg: str, baseline: Path, candidate: Path, name: str, timeout: float) -> float:
    _elapsed, text = run(
        [ffmpeg, "-hide_banner", "-nostdin", "-i", str(baseline), "-i", str(candidate),
         "-lavfi", f"[0:v:0][1:v:0]{name}", "-an", "-f", "null", "-"],
        timeout,
        capture=True,
    )
    match = PSNR_RE.search(text) if name == "psnr" else SSIM_RE.search(text)
    if not match:
        raise RuntimeError(f"could not parse {name}")
    raw = match.group(1).lower()
    return 999.0 if raw == "inf" else float(raw)


def layer_input_args(layer: OverlayLayer) -> list[str]:
    args: list[str] = []
    if layer.loop and layer.kind in {"gif", "apng", "webp", "video-alpha"}:
        args += ["-stream_loop", "-1"]
    return args + ["-i", layer.source]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Physical CinePulse H6 CUDA compositor benchmark")
    result.add_argument("--base", type=Path, required=True)
    result.add_argument("--layer", type=Path, required=True)
    result.add_argument("--kind", choices=("png", "gif", "apng", "webp", "video-alpha"), required=True)
    result.add_argument("--cache", type=Path, required=True)
    result.add_argument("--ffmpeg", default="ffmpeg")
    result.add_argument("--ffprobe", default="ffprobe")
    result.add_argument("--duration", type=float, default=5.0)
    result.add_argument("--x", type=float, default=0.5)
    result.add_argument("--y", type=float, default=0.5)
    result.add_argument("--opacity", type=float, default=1.0)
    result.add_argument("--timeout", type=float, default=900.0)
    return result


def main() -> int:
    args = parser().parse_args()
    ffmpeg = shutil.which(args.ffmpeg) or (str(args.ffmpeg) if Path(args.ffmpeg).is_file() else "")
    ffprobe = shutil.which(args.ffprobe) or (str(args.ffprobe) if Path(args.ffprobe).is_file() else "")
    if not ffmpeg or not ffprobe:
        raise SystemExit("FFmpeg/FFprobe required")

    base_probe = probe(ffprobe, args.base)
    base_video = video_stream(base_probe)
    if not base_video:
        raise SystemExit("base video stream required")
    profile = ColorProfile.from_probe({"streams": [base_video]})
    if profile.hdr or profile.pixel_format != "yuv420p":
        raise SystemExit("initial H6 physical envelope is SDR yuv420p only")
    if any(value in {"", "unknown", "unspecified", "reserved"} for value in (
        profile.primaries, profile.transfer, profile.space, profile.range
    )):
        raise SystemExit("known color metadata required")

    width = int(base_video.get("width") or 0)
    height = int(base_video.get("height") or 0)
    fps_text = str(base_video.get("avg_frame_rate") or "0/1")
    try:
        num, den = (float(value) for value in fps_text.split("/", 1))
        fps = num / den if den else 0.0
    except (TypeError, ValueError, ZeroDivisionError):
        fps = 0.0
    source_duration = duration(base_probe) or 0.0
    benchmark_duration = min(max(0.1, float(args.duration)), source_duration) if source_duration > 0 else 0.0
    if width <= 0 or height <= 0 or fps <= 0 or benchmark_duration <= 0:
        raise SystemExit("valid base geometry/fps/duration required")

    layer = OverlayLayer(str(args.layer), args.kind, x=args.x, y=args.y, opacity=args.opacity)
    caps = detect_gpu_compositor_capabilities(ffmpeg)
    if not cuda_layer_eligible(layer, caps):
        raise SystemExit("layer is outside the initial proven CUDA envelope")
    hardware = detect_hardware()
    if not hardware.gpu:
        raise SystemExit("NVIDIA GPU required; no H6 physical evidence recorded")

    key = GpuCompositorKey(
        gpu_name=hardware.gpu,
        driver=hardware.driver or "unknown-driver",
        ffmpeg_fingerprint=caps.fingerprint,
        width=width,
        height=height,
        fps_milli=round(fps * 1000),
        pixel_format=profile.pixel_format,
        primaries=profile.primaries,
        transfer=profile.transfer,
        space=profile.space,
        color_range=profile.range,
        layer_contract=layer.contract_token(),
    )

    with tempfile.TemporaryDirectory(prefix="cinepulse-h6-") as temporary:
        root = Path(temporary)
        baseline = root / "baseline.mkv"
        candidate = root / "candidate.mkv"

        state = OverlayComposerState([ComposerItem("physical-h6-layer", media=layer)])
        request = ComposerExportRequest(
            source=args.base,
            output=baseline,
            profile=ComposerBaseProfile(
                width=width,
                height=height,
                fps=fps,
                duration=benchmark_duration,
                pixel_format=profile.pixel_format,
                primaries=profile.primaries,
                transfer=profile.transfer,
                matrix=profile.space,
                color_range=profile.range,
            ),
            state=state,
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            # The compositor benchmark is visual-only. Production audio is muxed
            # after visual composition by the same reference path, so H6 never
            # gets permission to alter or re-time audio.
            audio_sources={},
        )
        started = time.perf_counter()
        export_composer_reference(request)
        baseline_seconds = max(0.000001, time.perf_counter() - started)

        cuda_graph = build_cuda_overlay_filter(
            layer,
            canvas_width=width,
            canvas_height=height,
            layer_width=0,
            layer_height=0,
        ) + ";[vout]format=rgba[vfinal]"
        candidate_cmd = [ffmpeg, "-y", "-hide_banner", "-nostdin", "-i", str(args.base)] + layer_input_args(layer) + [
            "-filter_complex", cuda_graph,
            "-map", "[vfinal]", "-an",
            "-t", f"{benchmark_duration:.6f}",
            "-c:v", "ffv1", "-level", "3", "-pix_fmt", "gbrap",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "gbr", "-color_range", "pc",
            str(candidate),
        ]
        candidate_seconds, _ = run(candidate_cmd, args.timeout)

        baseline_probe = probe(ffprobe, baseline)
        candidate_probe = probe(ffprobe, candidate)
        bv, cv = video_stream(baseline_probe), video_stream(candidate_probe)
        frame_count_ok = frames(bv) is not None and frames(bv) == frames(cv)
        metadata_ok = signature(bv) == signature(cv)
        duration_base, duration_candidate = duration(baseline_probe), duration(candidate_probe)
        # Both benchmark outputs intentionally contain no audio; the production
        # mux stage is unchanged and therefore outside the optimized boundary.
        audio_sync_ok = (
            duration_base is not None and duration_candidate is not None
            and abs(duration_base - duration_candidate) <= 0.020
            and not audio_stream(baseline_probe) and not audio_stream(candidate_probe)
        )
        psnr = metric(ffmpeg, baseline, candidate, "psnr", args.timeout)
        ssim = metric(ffmpeg, baseline, candidate, "ssim", args.timeout)
        evidence = GpuCompositorEvidence(
            baseline_seconds=baseline_seconds,
            candidate_seconds=candidate_seconds,
            psnr_db=psnr,
            ssim=ssim,
            frame_count_ok=frame_count_ok,
            metadata_ok=metadata_ok,
            alpha_contract_ok=psnr >= 80.0 and ssim >= 0.999999,
            audio_sync_ok=audio_sync_ok,
            reference_id=COMPOSITOR_REFERENCE_ID,
        )
        recorded = GpuCompositorStore(args.cache).record(key, evidence)

    print(json.dumps({
        "physical_acceptance": "exact-evidence-recorded-not-global-pass" if recorded else "rejected",
        "reference_id": COMPOSITOR_REFERENCE_ID,
        "hardware": hardware.as_dict(),
        "ffmpeg_fingerprint": caps.fingerprint,
        "base": {"width": width, "height": height, "fps": fps, "profile": profile.label},
        "layer_contract": layer.contract_token(),
        "baseline_seconds": evidence.baseline_seconds,
        "candidate_seconds": evidence.candidate_seconds,
        "speedup": evidence.speedup,
        "psnr_db": evidence.psnr_db,
        "ssim": evidence.ssim,
        "frame_count_ok": evidence.frame_count_ok,
        "metadata_ok": evidence.metadata_ok,
        "audio_sync_ok": evidence.audio_sync_ok,
        "accepted": evidence.accepted,
        "cache_key": key.token(),
    }, indent=2, ensure_ascii=False))
    return 0 if recorded else 2


if __name__ == "__main__":
    raise SystemExit(main())
