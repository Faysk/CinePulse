from __future__ import annotations

"""Cancellable, atomic CPU-reference export for the Preview Overlay Composer.

The export path intentionally prioritizes correctness and recovery over speed.
It decodes the base video to an explicit BT.709 RGBA reference, composites every
frame through the same deterministic NumPy renderer used by Preview, writes a
lossless RGB FFV1 visual master, then muxes the chosen soundtrack atomically.
GPU acceleration may replace this path only after H6 physical parity evidence.
"""

from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping

import numpy as np

from .audio_mastering import bounded_audio_input_args
from .composer_audio import VisualizerAudioEnvelope
from .composer_audio_binding import composer_audio_features, load_bound_visualizer_envelopes
from .composer_base_probe import ComposerBaseProfile
from .composer_decode_stream import ComposerMediaDecoderPool
from .composer_media import ComposerMediaInfo, playback_position, probe_composer_media, validate_layer_media
from .composer_preflight import validate_composer_resources
from .composer_runtime import ComposerFrameInputs, render_composer_frame
from .overlay_composer import OverlayComposerState
from .process_control import popen_group_kwargs, terminate_process_tree
from .safe_output import AtomicOutput
from .verification import VerifyExpectation, quick_verify


@dataclass(frozen=True)
class ComposerExportRequest:
    source: Path
    output: Path
    profile: ComposerBaseProfile
    state: OverlayComposerState
    ffmpeg: str
    ffprobe: str
    audio_sources: Mapping[str, str | Path]
    output_audio: str | Path | None = None


@dataclass(frozen=True)
class ComposerExportResult:
    output: Path
    frames: int


def _range_token(value: str) -> str:
    return "pc" if str(value).strip().lower() in {"pc", "jpeg", "full"} else "tv"


def _base_decode_command(request: ComposerExportRequest, frames: int) -> list[str]:
    p = request.profile
    if p.still_image:
        # Keep a still background alive for the exact project duration.  The
        # image is cover-fitted to the selected output canvas; no temporary
        # video needs to be created by the user.
        vf = (
            f"scale=w={p.width}:h={p.height}:force_original_aspect_ratio=increase,"
            f"crop={p.width}:{p.height},format=rgba"
        )
        return [
            str(request.ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error",
            "-loop", "1", "-framerate", f"{p.fps:.12g}", "-i", str(request.source),
            "-map", "0:v:0", "-an", "-sn", "-vf", vf,
            "-frames:v", str(frames), "-pix_fmt", "rgba", "-f", "rawvideo", "pipe:1",
        ]

    range_in = _range_token(p.color_range)
    vf = (
        f"scale=w=iw:h=ih:in_color_matrix=bt709:out_color_matrix=bt709:"
        f"in_range={range_in}:out_range=pc,format=rgba"
    )
    return [
        str(request.ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error",
        "-i", str(request.source), "-map", "0:v:0", "-an", "-sn",
        "-vf", vf, "-fps_mode", "passthrough", "-frames:v", str(frames),
        "-pix_fmt", "rgba", "-f", "rawvideo", "pipe:1",
    ]


def _video_encode_command(request: ComposerExportRequest, target: Path) -> list[str]:
    p = request.profile
    return [
        str(request.ffmpeg), "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s:v", f"{p.width}x{p.height}",
        "-r", f"{p.fps:.12g}", "-i", "pipe:0", "-an",
        "-c:v", "ffv1", "-level", "3", "-pix_fmt", "gbrap",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "pc",
        str(target),
    ]


def composer_frame_count(request: ComposerExportRequest) -> int:
    return max(1, int(round(float(request.profile.duration) * float(request.profile.fps))))


def composer_has_audio_stream(ffprobe: str, path: str | Path) -> bool:
    try:
        result = subprocess.run(
            [
                str(ffprobe), "-v", "error", "-select_streams", "a:0",
                "-show_entries", "stream=index", "-of", "csv=p=0", str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and bool((result.stdout or "").strip())


def verify_composer_product(
    request: ComposerExportRequest,
    path: Path,
    *,
    expect_audio: bool,
) -> None:
    p = request.profile
    verification = quick_verify(
        str(request.ffprobe),
        path,
        VerifyExpectation(
            width=p.width,
            height=p.height,
            fps=p.fps,
            duration=p.duration,
            expect_audio=expect_audio,
            video_codec="ffv1",
            frame_tolerance=0,
            duration_tolerance=0.12,
            sync_tolerance=0.12,
        ),
    )
    if verification.frame_count is None:
        raise RuntimeError("composer verification failed: FFprobe did not report exact frame count")
    if verification.frame_count != composer_frame_count(request):
        raise RuntimeError(
            "composer verification failed: "
            f"{verification.frame_count}/{composer_frame_count(request)} frames"
        )
    if not verification.passed:
        detail = "; ".join(issue.message for issue in verification.errors)
        raise RuntimeError("composer verification failed: " + (detail or "unknown integrity error"))


def _mux_command(request: ComposerExportRequest, visual: Path, target: Path) -> list[str]:
    audio = request.output_audio or request.source
    return [
        str(request.ffmpeg), "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
        "-i", str(visual),
        *bounded_audio_input_args(str(audio), request.profile.duration),
        "-map", "0:v:0", "-map", "1:a:0?",
        "-c:v", "copy", "-c:a", "copy",
        "-frames:v", str(composer_frame_count(request)),
        str(target),
    ]


def _read_exact(stream, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = int(size)
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _resolve_audio_envelopes(
    request: ComposerExportRequest,
    envelopes: Mapping[str, VisualizerAudioEnvelope] | None,
    logger: Callable[[str], None],
) -> dict[str, VisualizerAudioEnvelope]:
    """Mirror Preview audio analysis when export did not receive precomputed envelopes."""
    if envelopes is not None:
        return dict(envelopes)
    sources = dict(request.audio_sources)
    if "master" not in sources:
        sources["master"] = request.output_audio or request.source
    return load_bound_visualizer_envelopes(
        request.state,
        ffmpeg=str(request.ffmpeg),
        sources=sources,
        duration=request.profile.duration,
        log=logger,
    )


def _run_cancellable_command(
    command: list[str],
    *,
    cancelled: Callable[[], bool],
    logger: Callable[[str], None],
    stderr_path: Path,
    cancel_message: str,
) -> None:
    """Run one FFmpeg stage without making cancellation wait for subprocess.run()."""
    with stderr_path.open("wb") as stderr_handle:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=stderr_handle,
            **popen_group_kwargs(),
        )
        try:
            while process.poll() is None:
                if cancelled():
                    terminate_process_tree(process, logger)
                    raise InterruptedError(cancel_message)
                time.sleep(0.05)
            code = int(process.returncode or 0)
        finally:
            if process.poll() is None:
                terminate_process_tree(process, logger)
    if code:
        try:
            details = stderr_path.read_text(encoding="utf-8", errors="replace")[-4000:].strip()
        except OSError:
            details = ""
        raise RuntimeError(details or f"composer process exited with {code}")


def _validate_media(request: ComposerExportRequest) -> dict[str, ComposerMediaInfo]:
    infos: dict[str, ComposerMediaInfo] = {}
    for item in request.state.ordered():
        if item.media is None:
            continue
        info = probe_composer_media(request.ffprobe, item.media.source)
        problems = validate_layer_media(item.media, info)
        if problems:
            raise ValueError(f"composer media {item.id}: " + "; ".join(problems))
        infos[item.id] = info
    return infos


def export_composer_reference(
    request: ComposerExportRequest,
    *,
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[int, int], None] | None = None,
    log: Callable[[str], None] | None = None,
    envelopes: Mapping[str, VisualizerAudioEnvelope] | None = None,
) -> ComposerExportResult:
    """Render one Preview Composer project through the lossless CPU reference."""
    cancel = cancelled or (lambda: False)
    logger = log or (lambda _message: None)
    source = Path(request.source)
    output = Path(request.output)
    if not source.is_file():
        raise FileNotFoundError(f"composer source not found: {source}")
    if source.resolve(strict=False) == output.resolve(strict=False):
        raise ValueError("composer output cannot overwrite source")
    if not request.profile.reference_supported:
        raise ValueError("composer CPU reference currently supports only SDR BT.709 8-bit sources")
    ordered = request.state.ordered()
    if not ordered:
        raise ValueError("composer project has no layers or visualizers")
    infos = _validate_media(request)
    frames = max(1, round(request.profile.duration * request.profile.fps))
    frame_bytes = request.profile.width * request.profile.height * 4
    output.parent.mkdir(parents=True, exist_ok=True)
    validate_composer_resources(request.profile, output.parent)

    decoder_layers = {
        item.id: (item.media, infos[item.id])
        for item in ordered
        if item.media is not None
    }
    bound_envelopes = _resolve_audio_envelopes(request, envelopes, logger)

    with tempfile.TemporaryDirectory(prefix="cinepulse-composer-", dir=output.parent) as temporary:
        temp_root = Path(temporary)
        visual = temp_root / "composer-reference.mkv"
        base = subprocess.Popen(
            _base_decode_command(request, frames),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **popen_group_kwargs(),
        )
        encoder = subprocess.Popen(
            _video_encode_command(request, visual),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            **popen_group_kwargs(),
        )
        logger("Composer Preview: iniciando referência CPU RGBA/FFV1 lossless.")
        decoders = ComposerMediaDecoderPool(request.ffmpeg, decoder_layers, log=logger)
        try:
            assert base.stdout is not None
            assert encoder.stdin is not None
            for frame_index in range(frames):
                if cancel():
                    raise InterruptedError("composer export cancelled")
                payload = _read_exact(base.stdout, frame_bytes)
                if len(payload) != frame_bytes:
                    raise RuntimeError(
                        f"composer base decode ended at frame {frame_index}/{frames}; "
                        f"got {len(payload)} of {frame_bytes} bytes"
                    )
                base_frame = np.frombuffer(payload, dtype=np.uint8).reshape(
                    request.profile.height, request.profile.width, 4
                ).copy()
                project_time = frame_index / request.profile.fps
                media_frames: dict[str, np.ndarray] = {}
                for item in ordered:
                    if item.media is None:
                        continue
                    info = infos[item.id]
                    position = playback_position(item.media, info, project_time=project_time)
                    decoded = decoders.frame(item.id, position)
                    if decoded is not None:
                        media_frames[item.id] = decoded
                features = composer_audio_features(
                    request.state,
                    bound_envelopes,
                    project_time=project_time,
                )
                composed = render_composer_frame(
                    base_frame,
                    request.state,
                    ComposerFrameInputs(
                        project_time=project_time,
                        media_rgba=media_frames,
                        audio=features,
                    ),
                )
                try:
                    encoder.stdin.write(composed.tobytes())
                except (BrokenPipeError, OSError) as exc:
                    raise RuntimeError("composer reference encoder pipe closed early") from exc
                if progress:
                    progress(frame_index + 1, frames)
            encoder.stdin.close()
            base_code = base.wait(timeout=30)
            encoder_code = encoder.wait(timeout=30)
            if base_code:
                details = (base.stderr.read() if base.stderr else b"").decode("utf-8", errors="replace")
                raise RuntimeError(details.strip() or f"composer base decoder exited with {base_code}")
            if encoder_code:
                details = (encoder.stderr.read() if encoder.stderr else b"").decode("utf-8", errors="replace")
                raise RuntimeError(details.strip() or f"composer reference encoder exited with {encoder_code}")
            if cancel():
                raise InterruptedError("composer export cancelled")
            if not visual.is_file() or visual.stat().st_size <= 0:
                raise RuntimeError("composer reference visual master was not produced")
            verify_composer_product(request, visual, expect_audio=False)

            atomic = AtomicOutput.for_path(output)
            atomic.prepare()
            try:
                _run_cancellable_command(
                    _mux_command(request, visual, atomic.partial),
                    cancelled=cancel,
                    logger=logger,
                    stderr_path=temp_root / "composer-mux.stderr.log",
                    cancel_message="composer export cancelled",
                )
                if cancel():
                    raise InterruptedError("composer export cancelled")
                audio_source = request.output_audio or request.source
                verify_composer_product(
                    request,
                    atomic.partial,
                    expect_audio=composer_has_audio_stream(request.ffprobe, audio_source),
                )
                atomic.commit()
            finally:
                atomic.discard()
        finally:
            decoders.close()
            for process in (base, encoder):
                if process.poll() is None:
                    terminate_process_tree(process, logger)
            # Popen does not close user-visible pipe objects just because the
            # child exited. Close every stream explicitly so repeated Preview
            # exports/cancellations cannot accumulate Windows handles or leak
            # ResourceWarning noise into the release gate.
            for stream in (base.stdout, base.stderr, encoder.stdin, encoder.stderr):
                if stream is None:
                    continue
                try:
                    if not stream.closed:
                        stream.close()
                except OSError:
                    pass
    return ComposerExportResult(output, frames)
