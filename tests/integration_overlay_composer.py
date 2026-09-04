from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from cinepulse.overlay_composer import (
    LayerTransform,
    NormalizedRect,
    OverlayLayer,
    OverlayScene,
    VisualizerSpec,
    make_asset_layer,
)
from cinepulse.overlay_ffmpeg import build_overlay_ffmpeg_plan


def _run(command: list[str], *, timeout: float = 45.0) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(command, capture_output=True, check=False, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return result


def _probe(ffprobe: str, path: Path) -> dict:
    result = _run([
        ffprobe, "-v", "error", "-show_entries",
        "stream=index,codec_type,width,height,avg_frame_rate:format=duration",
        "-of", "json", str(path),
    ])
    return json.loads(result.stdout)


def _decode_rgb(ffmpeg: str, path: Path, *, position: float = 0.5) -> np.ndarray:
    result = _run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", str(position), "-i", str(path),
        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ])
    expected = 640 * 360 * 3
    if len(result.stdout) != expected:
        raise RuntimeError(f"decoded frame has {len(result.stdout)} bytes, expected {expected}")
    return np.frombuffer(result.stdout, dtype=np.uint8).reshape(360, 640, 3)


def _render(ffmpeg: str, output: Path, scene: OverlayScene) -> None:
    plan = build_overlay_ffmpeg_plan(
        scene,
        canvas_width=640,
        canvas_height=360,
        fps=30,
        first_asset_input_index=2,
        base_video_label="0:v",
        audio_label="1:a",
    )
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=0x202030:s=640x360:r=30:d=2",
        "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=2",
        *plan.input_args,
        "-filter_complex", plan.filter_complex,
        "-map", f"[{plan.output_label}]", "-map", "1:a:0",
        "-t", "2", "-c:v", "ffv1", "-level", "3", "-c:a", "pcm_s16le", str(output),
    ]
    _run(command)


def main() -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("FFmpeg/FFprobe are required for overlay integration")

    with tempfile.TemporaryDirectory(prefix="cinepulse_overlay_") as raw:
        root = Path(raw)
        png = root / "character.png"
        gif = root / "character.gif"
        png_output = root / "png-waveform.mkv"
        gif_output = root / "gif-waveform.mkv"

        _run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=0xE0A040:s=96x128:d=0.1",
            "-frames:v", "1", str(png),
        ])
        _run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=s=80x80:r=5:d=1",
            "-vf", "format=rgb8", str(gif),
        ])

        waveform = OverlayLayer(
            id="viz",
            name="Waveform",
            kind="visualizer",
            z_index=20,
            transform=LayerTransform(NormalizedRect(0.38, 0.82, 0.40, 0.10), opacity=0.85, preserve_aspect=False),
            visualizer=VisualizerSpec(style="waveform", color="#F2E5C9", sensitivity=1.2, focus="bass"),
        )
        png_layer = make_asset_layer(
            str(png), layer_id="asset", rect=NormalizedRect(0.73, 0.53, 0.18, 0.35), z_index=10
        )
        _render(ffmpeg, png_output, OverlayScene((png_layer, waveform)))

        gif_layer = make_asset_layer(
            str(gif), layer_id="asset", media_kind="gif", rect=NormalizedRect(0.73, 0.55, 0.18, 0.32), z_index=10
        )
        _render(ffmpeg, gif_output, OverlayScene((gif_layer, waveform)))

        for output in (png_output, gif_output):
            payload = _probe(ffprobe, output)
            streams = payload.get("streams", [])
            video = next(stream for stream in streams if stream.get("codec_type") == "video")
            audio = next(stream for stream in streams if stream.get("codec_type") == "audio")
            if (video.get("width"), video.get("height")) != (640, 360):
                raise RuntimeError(f"wrong output size: {video}")
            if audio.get("codec_type") != "audio":
                raise RuntimeError("audio stream missing")
            duration = float(payload.get("format", {}).get("duration") or 0.0)
            if not 1.90 <= duration <= 2.10:
                raise RuntimeError(f"unexpected duration: {duration}")
            frame = _decode_rgb(ffmpeg, output)
            if float(frame.std()) < 8.0:
                raise RuntimeError("overlay output remained visually flat")

        print("CINEPULSE_OVERLAY_COMPOSER_OK png=pass gif=pass waveform=pass duration=2s size=640x360 audio=pass")


if __name__ == "__main__":
    main()
