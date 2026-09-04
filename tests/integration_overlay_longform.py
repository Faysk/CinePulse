from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from cinepulse.overlay_composer import (
    LayerTransform,
    NormalizedRect,
    OverlayLayer,
    OverlayScene,
    VisualizerSpec,
    make_asset_layer,
)
from cinepulse.overlay_ffmpeg import build_overlay_ffmpeg_plan


SOAK_SECONDS = 30


def _run(command: list[str], *, timeout: float = 90.0) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(command, capture_output=True, check=False, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return result


def main() -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for longform overlay soak")

    with tempfile.TemporaryDirectory(prefix="cinepulse_overlay_longform_") as raw:
        root = Path(raw)
        png = root / "character.png"
        gif = root / "character.gif"

        _run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=0xD29A54:s=48x64:d=0.1",
            "-frames:v", "1", str(png),
        ])
        _run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=s=40x40:r=4:d=1",
            "-vf", "format=rgb8", str(gif),
        ])
        baseline_files = {path.name for path in root.iterdir()}

        png_layer = make_asset_layer(
            str(png),
            layer_id="png",
            rect=NormalizedRect(0.72, 0.42, 0.20, 0.42),
            z_index=10,
        )
        gif_layer = make_asset_layer(
            str(gif),
            layer_id="gif",
            media_kind="gif",
            rect=NormalizedRect(0.08, 0.14, 0.14, 0.24),
            z_index=15,
        )
        waveform = OverlayLayer(
            id="wave",
            name="Wave",
            kind="visualizer",
            z_index=20,
            transform=LayerTransform(
                NormalizedRect(0.32, 0.80, 0.58, 0.08),
                opacity=0.85,
                preserve_aspect=False,
            ),
            visualizer=VisualizerSpec(
                style="waveform",
                color="#F2E5C9",
                thickness=0.65,
                focus="bass",
            ),
        )
        bars = OverlayLayer(
            id="bars",
            name="Bars",
            kind="visualizer",
            z_index=25,
            transform=LayerTransform(
                NormalizedRect(0.12, 0.72, 0.28, 0.16),
                opacity=0.78,
                preserve_aspect=False,
            ),
            visualizer=VisualizerSpec(
                style="bars",
                bars=18,
                mirror=True,
                color="#FFAA44",
                secondary_color="#44AAFF",
                focus="beats",
            ),
        )
        scene = OverlayScene((png_layer, gif_layer, waveform, bars))
        plan = build_overlay_ffmpeg_plan(
            scene,
            canvas_width=320,
            canvas_height=180,
            fps=30,
            first_asset_input_index=2,
            base_video_label="0:v",
            audio_label="1:a",
        )

        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "lavfi", "-i", f"color=c=0x202030:s=320x180:r=30:d={SOAK_SECONDS}",
            "-f", "lavfi", "-i", f"sine=frequency=220:sample_rate=48000:duration={SOAK_SECONDS}",
            *plan.input_args,
            "-filter_complex", plan.filter_complex,
            "-map", f"[{plan.output_label}]",
            "-t", str(SOAK_SECONDS),
            "-f", "null", "-",
        ]
        _run(command, timeout=120.0)

        after_files = {path.name for path in root.iterdir()}
        unexpected = sorted(after_files - baseline_files)
        if unexpected:
            raise RuntimeError(f"longform graph materialized unexpected files: {unexpected}")

        print(
            "CINEPULSE_OVERLAY_LONGFORM_OK "
            f"seconds={SOAK_SECONDS} size=320x180 png=pass gif_loop=pass visualizers=2 temp_expansion=none"
        )


if __name__ == "__main__":
    main()
