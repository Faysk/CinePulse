from __future__ import annotations

import queue
import subprocess
import time
from dataclasses import replace
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


def _drain(app: VideoOptimizerStudio) -> None:
    errors: list[str] = []
    done = False
    while True:
        try:
            event = app._events.get_nowait()
        except queue.Empty:
            break
        done = done or event[0] == "done"
        if event[0] == "error":
            errors.append(event[1])
    if errors or not done:
        raise RuntimeError(errors[-1] if errors else "Render não concluiu.")


def main() -> None:
    ensure_runtime_directories()
    run_root = PATHS.data / "test-runs" / time.strftime("%Y%m%d_%H%M%S_hdr")
    run_root.mkdir(parents=True, exist_ok=True)
    source = run_root / "hdr10_source.mp4"
    preserve_output = run_root / "hdr10_preserved.mp4"
    music_output = run_root / "hdr10_music_preserved.mp4"
    vfx_output = run_root / "hdr10_vfx_sdr.mp4"
    music = run_root / "music.wav"
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-t", "0.8", "-map", "0:v:0", "-map", "1:a:0",
        "-vf", "format=yuv420p10le", "-c:v", "libx265", "-preset", "ultrafast", "-crf", "18",
        "-x265-params", "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc",
        "-color_primaries", "bt2020", "-color_trc", "smpte2084", "-colorspace", "bt2020nc",
        "-color_range", "tv", "-c:a", "aac", "-b:a", "128k", str(source),
    ]
    subprocess.run(command, check=True)
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000", "-t", "0.8",
        "-c:a", "pcm_s24le", str(music),
    ], check=True)
    root = Tk()
    root.withdraw()
    app = VideoOptimizerStudio(root)
    base = RenderSettings(
        mode=MODE_ORIGINAL, video=str(source), audio="", output=str(preserve_output), resolution="720p HD", fps=24,
        aspect=ASPECT_ORIGINAL, enhancement=ENHANCE_NONE, fit_mode=FIT_CONTAIN, use_cpu=True,
        preserve_audio=False, effects=set(), color="#43D6FF", intensity=0.7, occupancy=0.5,
        audio_focus="Todos equilibrados", reaction_smoothing=0.8, reaction_expression=0.8,
        auto_loop=False, dynamic_sections=False, section_dynamics=0.7,
        transition="Corte seco — original", transition_duration=0.5, preview_seconds=1,
        audio_mode="Preservar dinâmica original", interpolation="Quadros repetidos — rápido",
        cpu_threads=4, minimum_free_gb=1, quality_check=False, visual_direction="Personalizada",
        comparison_preview=False,
    )

    # Clean path must preserve genuine HDR10/10-bit metadata.
    app._worker(base, False)
    _drain(app)
    preserved = ColorProfile.from_probe(probe_media(str(preserve_output)))
    if not preserved.hdr or preserved.primaries != "bt2020" or preserved.transfer != "smpte2084" or preserved.bit_depth < 10:
        raise RuntimeError(f"HDR limpo não foi preservado: {preserved}")

    # Music mode forces a studio master.  This is the CP-007 regression case:
    # the intermediate must remain HDR/10-bit instead of collapsing to H.264 8-bit.
    music_settings = replace(base, mode=MODE_MUSIC, audio=str(music), output=str(music_output))
    app._worker(music_settings, False)
    _drain(app)
    music_profile = ColorProfile.from_probe(probe_media(str(music_output)))
    if not music_profile.hdr or music_profile.primaries != "bt2020" or music_profile.transfer != "smpte2084" or music_profile.bit_depth < 10:
        raise RuntimeError(f"HDR não sobreviveu ao master musical 10-bit: {music_profile}")

    # VFX are SDR-only today.  The renderer must perform a real HDR->SDR
    # conversion before VFX and must never relabel the output as HDR.
    vfx_settings = replace(base, output=str(vfx_output), effects={"Pulso cinematográfico"})
    app._worker(vfx_settings, False)
    _drain(app)
    converted = ColorProfile.from_probe(probe_media(str(vfx_output)))
    if converted.hdr or converted.primaries != "bt709" or converted.transfer != "bt709" or converted.bit_depth < 10:
        raise RuntimeError(f"HDR+VFX não virou SDR BT.709 10-bit corretamente: {converted}")

    root.destroy()
    print(f"CINEPULSE_HDR_PRESERVATION_OK {preserved.label}")
    print(f"CINEPULSE_HDR_MASTER_10BIT_OK {music_profile.label}")
    print(f"CINEPULSE_HDR_VFX_TONEMAP_OK {converted.label}")


if __name__ == "__main__":
    main()
