from __future__ import annotations

import queue
import subprocess
import time
from pathlib import Path
from tkinter import Tk

from cinepulse.loop_engine import probe_media
from cinepulse.media_profile import ColorProfile
from cinepulse.paths import PATHS, ensure_runtime_directories
from cinepulse.studio import (
    ASPECT_ORIGINAL,
    ENHANCE_NONE,
    FIT_CONTAIN,
    MODE_MUSIC,
    MODE_ORIGINAL,
    RenderSettings,
    VideoOptimizerStudio,
)


def execute(app: VideoOptimizerStudio, settings: RenderSettings) -> ColorProfile:
    app._worker(settings, False)
    done = False
    errors: list[str] = []
    while True:
        try:
            event = app._events.get_nowait()
        except queue.Empty:
            break
        done = done or event[0] == "done"
        if event[0] == "error":
            errors.append(event[1])
    if errors or not done:
        raise RuntimeError(errors[-1] if errors else "Render não concluiu")
    return ColorProfile.from_probe(probe_media(settings.output))


def settings(video: Path, output: Path, *, mode: str, audio: Path | None = None) -> RenderSettings:
    return RenderSettings(
        mode=mode, video=str(video), audio=str(audio or ""), output=str(output), resolution="720p HD", fps=24,
        aspect=ASPECT_ORIGINAL, enhancement=ENHANCE_NONE, fit_mode=FIT_CONTAIN, use_cpu=True,
        preserve_audio=False, effects=set(), color="#43D6FF", intensity=0.7, occupancy=0.5,
        audio_focus="Todos equilibrados", reaction_smoothing=0.8, reaction_expression=0.8,
        auto_loop=False, dynamic_sections=False, section_dynamics=0.7,
        transition="Corte seco — original", transition_duration=0.5, preview_seconds=1,
        audio_mode="Preservar dinâmica original", interpolation="Quadros repetidos — rápido",
        cpu_threads=4, minimum_free_gb=1, quality_check=False, visual_direction="Personalizada",
        comparison_preview=False,
    )


def main() -> None:
    ensure_runtime_directories()
    root_dir = PATHS.data / "test-runs" / time.strftime("%Y%m%d_%H%M%S_color")
    root_dir.mkdir(parents=True, exist_ok=True)
    video = root_dir / "sdr10.mp4"
    full = root_dir / "sdr10_full.mp4"
    music = root_dir / "music.wav"
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24",
        "-t", "0.8", "-vf", "format=yuv420p10le", "-c:v", "libx265", "-preset", "ultrafast", "-crf", "18",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv", str(video),
    ], check=True)
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24",
        "-t", "0.8", "-vf", "format=yuv420p10le", "-c:v", "libx265", "-preset", "ultrafast", "-crf", "18",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "pc", str(full),
    ], check=True)
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000",
        "-t", "0.8", "-c:a", "pcm_s24le", str(music),
    ], check=True)

    tk = Tk(); tk.withdraw(); app = VideoOptimizerStudio(tk)
    try:
        master_profile = execute(app, settings(video, root_dir / "sdr10_music.mp4", mode=MODE_MUSIC, audio=music))
        if master_profile.bit_depth < 10 or master_profile.hdr or master_profile.primaries != "bt709":
            raise RuntimeError(f"SDR10 não sobreviveu ao master: {master_profile}")
        full_profile = execute(app, settings(full, root_dir / "sdr10_full_out.mp4", mode=MODE_ORIGINAL))
        if full_profile.bit_depth < 10 or full_profile.range != "pc":
            raise RuntimeError(f"Range full/10-bit não foi preservado: {full_profile}")
    finally:
        tk.destroy()
    print(f"CINEPULSE_SDR10_MASTER_OK {master_profile.label}")
    print(f"CINEPULSE_FULL_RANGE_OK {full_profile.label} range={full_profile.range}")


if __name__ == "__main__":
    main()
