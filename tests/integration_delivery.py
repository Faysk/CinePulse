from __future__ import annotations

import json
import queue
import shutil
import subprocess
import tempfile
from pathlib import Path
from tkinter import Tk

from cinepulse.delivery import PROFILE_ARCHIVE, PROFILE_AUTO, PROFILE_MASTER, PROFILE_WEB
from cinepulse.loop_engine import probe_media
from cinepulse.studio import (
    ASPECT_LANDSCAPE, ENHANCE_NONE, FIT_COVER, MODE_MUSIC, RenderSettings, VideoOptimizerStudio,
)

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def fixture(root: Path) -> tuple[Path, Path]:
    video = root / "source.mp4"
    music = root / "music.wav"
    run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24", "-t", "0.8", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)])
    run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=0.8", "-c:a", "pcm_s24le", str(music)])
    return video, music


def settings(video: Path, music: Path, output: Path, profile: str) -> RenderSettings:
    return RenderSettings(
        mode=MODE_MUSIC, video=str(video), audio=str(music), output=str(output), resolution="720p HD", fps=24,
        aspect=ASPECT_LANDSCAPE, enhancement=ENHANCE_NONE, fit_mode=FIT_COVER, use_cpu=True,
        preserve_audio=True, effects=set(), color="#43D6FF", intensity=0.75, occupancy=0.55,
        audio_focus="Graves e batidas", reaction_smoothing=0.82, reaction_expression=0.78,
        auto_loop=False, dynamic_sections=False, section_dynamics=0.75, transition="Corte seco — original",
        transition_duration=0.5, preview_seconds=1, audio_mode="Preservar dinâmica original",
        interpolation="Quadros repetidos — rápido", cpu_threads=2, minimum_free_gb=0.1,
        quality_check=False, visual_direction="Cinematográfica", comparison_preview=False,
        delivery_profile=profile,
    )


def main() -> None:
    root_dir = Path(tempfile.mkdtemp(prefix="cinepulse_delivery_"))
    video, music = fixture(root_dir)
    root = Tk(); root.withdraw()
    app = VideoOptimizerStudio(root)
    cases = [
        ("mp4", PROFILE_AUTO, "hevc", "aac"),
        ("mov", PROFILE_MASTER, "prores", "pcm_s24le"),
        ("mkv", PROFILE_ARCHIVE, "hevc", "flac"),
        ("webm", PROFILE_WEB, "vp9", "opus"),
    ]
    report = {}
    try:
        for suffix, profile, video_codec, audio_codec in cases:
            out = root_dir / f"delivery.{suffix}"
            cfg = settings(video, music, out, profile)
            app._cancelled = False
            app._worker(cfg, preview=False)
            events=[]
            while True:
                try: events.append(app._events.get_nowait())
                except queue.Empty: break
            errors=[event[1] for event in events if event[0] == "error"]
            if errors: raise RuntimeError(f"{suffix}: {errors[-1]}")
            info = probe_media(str(out))
            streams=info.get("streams", [])
            v=next(stream for stream in streams if stream.get("codec_type")=="video")
            a=next(stream for stream in streams if stream.get("codec_type")=="audio")
            if v.get("codec_name") != video_codec or a.get("codec_name") != audio_codec:
                raise RuntimeError(f"{suffix}: codecs inesperados {v.get('codec_name')}/{a.get('codec_name')}")
            report[suffix]={"video":v.get("codec_name"),"audio":a.get("codec_name"),"bytes":out.stat().st_size}
            print(f"CINEPULSE_DELIVERY_{suffix.upper()}_OK {video_codec}/{audio_codec}")
    finally:
        root.destroy()
    print("CINEPULSE_DELIVERY_MATRIX_OK " + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
