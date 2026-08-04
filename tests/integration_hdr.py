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
    MODE_ORIGINAL,
    RenderSettings,
    VideoOptimizerStudio,
)


def main() -> None:
    ensure_runtime_directories()
    run_root = PATHS.data / "test-runs" / time.strftime("%Y%m%d_%H%M%S_hdr")
    run_root.mkdir(parents=True, exist_ok=True)
    source = run_root / "hdr10_source.mp4"
    output = run_root / "hdr10_output.mp4"
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24", "-t", "0.8",
        "-vf", "format=yuv420p10le", "-c:v", "libx265", "-preset", "ultrafast", "-crf", "18",
        "-x265-params", "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc",
        "-color_primaries", "bt2020", "-color_trc", "smpte2084", "-colorspace", "bt2020nc",
        "-color_range", "tv", str(source),
    ]
    subprocess.run(command, check=True)
    root = Tk()
    root.withdraw()
    app = VideoOptimizerStudio(root)
    settings = RenderSettings(
        mode=MODE_ORIGINAL, video=str(source), audio="", output=str(output), resolution="720p HD", fps=24,
        aspect=ASPECT_ORIGINAL, enhancement=ENHANCE_NONE, fit_mode=FIT_CONTAIN, use_cpu=True,
        preserve_audio=False, effects=set(), color="#43D6FF", intensity=0.7, occupancy=0.5,
        audio_focus="Todos equilibrados", reaction_smoothing=0.8, reaction_expression=0.8,
        auto_loop=False, dynamic_sections=False, section_dynamics=0.7,
        transition="Corte seco — original", transition_duration=0.5, preview_seconds=1,
        audio_mode="Preservar dinâmica original", interpolation="Quadros repetidos — rápido",
        cpu_threads=4, minimum_free_gb=1, quality_check=False, visual_direction="Personalizada",
        comparison_preview=False,
    )
    app._worker(settings, False)
    errors = []
    done = False
    while True:
        try:
            event = app._events.get_nowait()
        except queue.Empty:
            break
        done = done or event[0] == "done"
        if event[0] == "error":
            errors.append(event[1])
    root.destroy()
    if errors or not done:
        raise RuntimeError(errors[-1] if errors else "Render HDR não concluiu.")
    profile = ColorProfile.from_probe(probe_media(str(output)))
    if not profile.hdr or profile.primaries != "bt2020" or profile.transfer != "smpte2084":
        raise RuntimeError(f"Metadados HDR não foram preservados: {profile}")
    print(f"CINEPULSE_HDR_PRESERVATION_OK {profile.label}")


if __name__ == "__main__":
    main()
