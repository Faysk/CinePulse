from __future__ import annotations

import argparse
import json
import queue
import shutil
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from tkinter import Tk

import numpy as np

from cinepulse.loop_engine import first_video_fps, first_video_size, has_audio, media_duration, probe_media
from cinepulse.paths import PATHS, ensure_runtime_directories
from cinepulse.audio_mastering import analyze_loudness
from cinepulse.studio import (
    ASPECT_LANDSCAPE,
    ASPECT_ORIGINAL,
    ENHANCE_AI,
    ENHANCE_NONE,
    FIT_CONTAIN,
    FIT_COVER,
    MODE_MUSIC,
    MODE_ORIGINAL,
    RIFE_OPTION,
    RenderSettings,
    VideoOptimizerStudio,
)


FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


def run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError("\n".join([subprocess.list2cmdline(command), result.stdout, result.stderr]))


def create_fixtures(root: Path) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    video = root / "source_with_440hz_audio.mp4"
    music = root / "music_880hz.wav"
    run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-t", "1.2", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", str(video),
    ])
    run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=2.4",
        "-c:a", "pcm_s24le", str(music),
    ])
    return video, music


def dominant_frequency(path: Path) -> float:
    result = subprocess.run([
        FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(path), "-vn", "-ac", "1",
        "-ar", "48000", "-t", "1", "-f", "f32le", "pipe:1",
    ], capture_output=True, check=True)
    samples = np.frombuffer(result.stdout, dtype=np.float32)
    spectrum = np.abs(np.fft.rfft(samples * np.hanning(samples.size)))
    frequencies = np.fft.rfftfreq(samples.size, 1 / 48000)
    return float(frequencies[int(np.argmax(spectrum))])


def settings_for(kind: str, video: Path, music: Path, output: Path) -> RenderSettings:
    common = dict(
        video=str(video), output=str(output), resolution="720p HD", fps=30,
        aspect=ASPECT_LANDSCAPE, enhancement=ENHANCE_NONE, fit_mode=FIT_COVER,
        use_cpu=True, preserve_audio=True, effects=set(), color="#43D6FF", intensity=0.75,
        occupancy=0.55, audio_focus="Graves e batidas", reaction_smoothing=0.82,
        reaction_expression=0.78, auto_loop=False, dynamic_sections=True, section_dynamics=0.75,
        transition="Corte seco — original", transition_duration=0.5, preview_seconds=2,
        audio_mode="Preservar dinâmica original", interpolation="Quadros repetidos — rápido",
        cpu_threads=4, minimum_free_gb=1.0, quality_check=False,
        visual_direction="Cinematográfica", comparison_preview=False,
    )
    if kind in {"basic", "audio"}:
        if kind == "audio":
            common["audio_mode"] = "Normalizar para YouTube — -14 LUFS"
        return RenderSettings(mode=MODE_MUSIC, audio=str(music), **common)
    if kind in {"vfx", "stems"}:
        common.update(effects={"Aurora", "Pulso cinematográfico"}, use_stems=kind == "stems")
        return RenderSettings(mode=MODE_MUSIC, audio=str(music), **common)
    if kind == "rife":
        common.update(
            mode=MODE_ORIGINAL, audio="", fps=48, aspect=ASPECT_ORIGINAL,
            fit_mode=FIT_CONTAIN, interpolation=RIFE_OPTION, use_cpu=False,
        )
        return RenderSettings(**common)
    if kind == "ai":
        common.update(
            mode=MODE_ORIGINAL, audio="", fps=24, aspect=ASPECT_ORIGINAL,
            fit_mode=FIT_CONTAIN, enhancement=ENHANCE_AI, use_cpu=False,
        )
        return RenderSettings(**common)
    raise ValueError(kind)


def execute(app: VideoOptimizerStudio, settings: RenderSettings) -> dict:
    started = time.monotonic()
    app._cancelled = False
    app._worker(settings, preview=False)
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
        raise RuntimeError("O worker terminou sem evento de conclusão.")
    output = Path(settings.output)
    info = probe_media(str(output))
    return {
        "seconds": round(time.monotonic() - started, 3),
        "output": str(output),
        "bytes": output.stat().st_size,
        "duration": media_duration(info),
        "size": first_video_size(info),
        "fps": first_video_fps(info),
        "audio": has_audio(info),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("basic", "audio", "vfx", "stems", "rife", "ai", "all"), default="all")
    args = parser.parse_args()
    ensure_runtime_directories()
    run_root = PATHS.data / "test-runs" / time.strftime("%Y%m%d_%H%M%S")
    fixture_root = run_root / "fixtures"
    output_root = run_root / "outputs"
    output_root.mkdir(parents=True, exist_ok=True)
    video, music = create_fixtures(fixture_root)
    root = Tk()
    root.withdraw()
    app = VideoOptimizerStudio(root)
    kinds = ("basic", "audio", "vfx", "stems", "rife", "ai") if args.mode == "all" else (args.mode,)
    report = {"created_at": time.strftime("%Y-%m-%d %H:%M:%S"), "runs": {}}
    try:
        for kind in kinds:
            settings = settings_for(kind, video, music, output_root / f"{kind}.mp4")
            result = execute(app, settings)
            if kind in {"basic", "audio", "vfx", "stems"}:
                frequency = dominant_frequency(Path(settings.output))
                result["dominant_audio_hz"] = round(frequency, 2)
                if abs(frequency - 880) > 8:
                    raise RuntimeError(f"{kind}: áudio final não corresponde à música de 880 Hz: {frequency:.2f}")
            if kind == "audio":
                loudness = analyze_loudness(FFMPEG, str(settings.output), result["duration"], "Normalizar para YouTube — -14 LUFS")
                result["integrated_lufs"] = loudness["input_i"]
                result["true_peak_db"] = loudness["input_tp"]
                if abs(loudness["input_i"] - (-14.0)) > 1.0 or loudness["input_tp"] > -0.8:
                    raise RuntimeError(f"Normalização fora da meta: {loudness}")
            report["runs"][kind] = result
            print(f"CINEPULSE_SMOKE_{kind.upper()}_OK {json.dumps(result, ensure_ascii=False)}")
    finally:
        root.destroy()
    report_path = run_root / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"CINEPULSE_INTEGRATION_REPORT {report_path}")


if __name__ == "__main__":
    main()
