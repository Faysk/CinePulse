from __future__ import annotations

import queue
import shutil
import subprocess
import tempfile
from pathlib import Path
from tkinter import Tk

from cinepulse.studio import (
    ASPECT_LANDSCAPE,
    ENHANCE_NONE,
    FIT_COVER,
    MODE_MUSIC,
    RenderSettings,
    VideoOptimizerStudio,
)

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True)


def main() -> None:
    root_dir = Path(tempfile.mkdtemp(prefix="cinepulse_storage_"))
    scratch = root_dir / "scratch"
    video = root_dir / "source.mp4"
    music = root_dir / "music.wav"
    output = root_dir / "output.mp4"
    run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24",
        "-t", "0.8", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video),
    ])
    run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "sine=frequency=660:sample_rate=48000:duration=2.4",
        "-c:a", "pcm_s24le", str(music),
    ])
    cfg = RenderSettings(
        mode=MODE_MUSIC, video=str(video), audio=str(music), output=str(output),
        resolution="720p HD", fps=24, aspect=ASPECT_LANDSCAPE,
        enhancement=ENHANCE_NONE, fit_mode=FIT_COVER, use_cpu=True,
        preserve_audio=True, effects=set(), color="#43D6FF", intensity=0.75,
        occupancy=0.55, audio_focus="Graves e batidas", reaction_smoothing=0.82,
        reaction_expression=0.78, auto_loop=False, dynamic_sections=False,
        section_dynamics=0.75, transition="Corte seco — original", transition_duration=0.5,
        preview_seconds=1, audio_mode="Preservar dinâmica original",
        interpolation="Quadros repetidos — rápido", cpu_threads=2, minimum_free_gb=0.1,
        quality_check=False, visual_direction="Cinematográfica", comparison_preview=False,
        scratch_dir=str(scratch), cache_quota_gb=5.0,
    )

    tk = Tk(); tk.withdraw()
    app = VideoOptimizerStudio(tk)
    try:
        report = app._preflight_report(cfg, False)
        if Path(report["scratch_dir"]).resolve() != scratch.resolve():
            raise RuntimeError("Preflight não utilizou o scratch configurado.")
        if "storage_estimate" not in report or "scratch_probe" not in report:
            raise RuntimeError("Contrato de armazenamento ausente do preflight.")
        estimate = report["storage_estimate"]
        if not (0.70 <= float(estimate["clip_duration_seconds"]) <= 1.0):
            raise RuntimeError(f"Preflight perdeu a duração real do clipe: {estimate['clip_duration_seconds']}")
        if not (2.2 <= float(estimate["project_duration_seconds"]) <= 2.6):
            raise RuntimeError(f"Preflight perdeu a duração da música: {estimate['project_duration_seconds']}")
        master = next((stage for stage in estimate["stages"] if stage["key"] == "master"), None)
        if master is None or float(master["duration_seconds"]) > 1.0:
            raise RuntimeError(f"Master do loop foi estimado com a duração do projeto: {master}")
        app._cancelled = False
        app._worker(cfg, preview=False)
        events = []
        while True:
            try:
                events.append(app._events.get_nowait())
            except queue.Empty:
                break
        errors = [event[1] for event in events if event[0] == "error"]
        if errors:
            raise RuntimeError(errors[-1])
        if not any(event[0] == "done" for event in events):
            raise RuntimeError("Worker terminou sem evento done.")
        logs = [event[1] for event in events if event[0] == "log"]
        if not any(str(scratch.resolve()) in line and "STORAGE Phase 6" in line for line in logs):
            raise RuntimeError("Log não registrou o scratch real do job.")
        leftovers = list(scratch.glob("job_*"))
        if leftovers:
            raise RuntimeError(f"Jobs scratch não foram limpos: {leftovers}")
        if not output.is_file():
            raise RuntimeError("Saída final ausente.")
        print(
            "CINEPULSE_STORAGE_ENGINE_OK "
            f"scratch={scratch} peak={report['temp_gb']:.3f}GB "
            f"cache={report['cache_current_gb']:.3f}/{report['cache_quota_gb']:.1f}GB"
        )
    finally:
        tk.destroy()
        shutil.rmtree(root_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
