from __future__ import annotations

import math
import os
import subprocess
import threading
from collections import deque
from typing import Callable

import numpy as np


# Legacy constants are kept only for compatibility with code/tests that import
# them.  The final renderer no longer uses them as a fixed canvas.
EFFECT_FPS = 60
EFFECT_WIDTH = 320
EFFECT_HEIGHT = 180
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

from .music_envelope import (
    DEFAULT_ANALYSIS_FPS,
    analyze_music_structure,
    load_music_envelope,
    shape_reactivity,
)
from .vfx_policy import choose_vfx_render_spec


class RenderCancelled(Exception):
    pass


def _hex_color(value: str) -> tuple[int, int, int]:
    clean = value.strip().lstrip("#")
    if len(clean) != 6:
        return 67, 214, 255
    try:
        return tuple(int(clean[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return 67, 214, 255


class StudioFrameGenerator:
    """Resolution-independent NumPy VFX generator.

    Phase 3 keeps the proven effect math but expresses geometry relative to a
    requested canvas and cadence.  320x180/60 is no longer baked into final
    rendering; previews may still request small canvases deliberately.
    """

    def __init__(
        self,
        effects: set[str],
        color: str,
        intensity: float,
        occupancy: float,
        *,
        width: int = EFFECT_WIDTH,
        height: int = EFFECT_HEIGHT,
        fps: float = EFFECT_FPS,
    ) -> None:
        if min(width, height) <= 0 or fps <= 0:
            raise ValueError("VFX canvas dimensions/FPS must be positive.")
        self.effects = effects
        self.width = int(width)
        self.height = int(height)
        self.fps = float(fps)
        self.sx = self.width / EFFECT_WIDTH
        self.sy = self.height / EFFECT_HEIGHT
        self.pixel_scale = max(0.25, math.sqrt(self.sx * self.sy))
        self.color = np.asarray(_hex_color(color), dtype=np.float32)
        self.secondary = np.clip(self.color[[2, 0, 1]] * 1.08 + 18, 0, 255)
        self.warm = np.clip(self.color * np.asarray((1.35, 0.82, 0.55)), 0, 255)
        self.intensity = max(0.05, min(2.0, intensity))
        self.occupancy = max(0.10, min(1.0, occupancy))
        self.x = np.linspace(0, 1, self.width, dtype=np.float32)
        self.y = np.arange(self.height, dtype=np.float32)[:, None]
        yy, xx = np.mgrid[0:self.height, 0:self.width].astype(np.float32)
        self.xx, self.yy = xx, yy
        self.cx, self.cy = self.width / 2, self.height / 2
        radius = np.sqrt(
            ((xx - self.cx) / max(1.0, self.width * 0.594)) ** 2
            + ((yy - self.cy) / max(1.0, self.height * 0.589)) ** 2
        )
        self.edge_mask = np.clip((radius - 0.50) / 0.50, 0, 1) ** 1.6

    @staticmethod
    def _composite(
        premultiplied: np.ndarray,
        alpha_total: np.ndarray,
        layer_alpha: np.ndarray,
        color: np.ndarray,
    ) -> None:
        layer = np.clip(layer_alpha, 0, 0.88).astype(np.float32)
        remaining = 1.0 - layer
        premultiplied *= remaining[:, :, None]
        premultiplied += layer[:, :, None] * color
        alpha_total[:] = alpha_total * remaining + layer

    def _aurora(self, premul, alpha, t, bass, mids, highs, loudness) -> None:
        base_y = self.height * (1.03 - 0.50 * self.occupancy)
        for index, phase_offset in enumerate((0.0, 1.7, 3.4, 4.9)):
            phase = t * (0.65 + 0.38 * mids) + phase_offset
            wave = (
                (5 + 8 * mids) * self.sy * np.sin(math.tau * (self.x * 1.25 + phase * 0.20))
                + (2.5 + 5 * highs) * self.sy * np.sin(math.tau * (self.x * 3.1 - phase * 0.13))
            )
            center = base_y + index * 7 * self.sy - 11 * self.sy + wave
            thickness = max(0.7, (7 + 9 * bass) * self.sy * (0.65 + self.occupancy))
            curtain = np.exp(-(((self.y - center[None, :]) / thickness) ** 2) * 1.15)
            shimmer = 0.82 + 0.18 * np.sin(math.tau * (self.x * 8 + t * 0.22 + phase_offset))
            layer = curtain * shimmer[None, :] * (0.09 + 0.16 * loudness) * self.intensity
            color = self.color if index % 2 == 0 else self.secondary
            self._composite(premul, alpha, layer, color)

    def _spectrum(self, premul, alpha, t, bass, mids, highs, rounded: bool) -> None:
        count = 48
        area = self.height * self.occupancy
        base = self.height - 5 * self.sy
        softness = max(0.55, (1.8 if rounded else 0.8) * self.pixel_scale)
        fringe = max(2.0, 4.0 * self.pixel_scale)
        for index in range(count):
            x0 = index * self.width / count
            x1 = (index + 0.62) * self.width / count
            harmonic = 0.5 + 0.5 * math.sin(index * 0.71 + t * 2.1)
            band = bass * (1 - index / count) + highs * (index / count) + mids * harmonic
            height = max(2 * self.sy, area * (0.08 + 0.82 * min(1, band)))
            dx = np.maximum(np.maximum(x0 - self.xx, self.xx - x1), 0)
            dy = np.maximum(np.maximum(base - height - self.yy, self.yy - base), 0)
            distance = np.sqrt(dx * dx + dy * dy)
            layer = np.exp(-((distance / softness) ** 2)) * (distance < fringe)
            inside = (self.xx >= x0) & (self.xx <= x1) & (self.yy >= base - height) & (self.yy <= base)
            layer = np.maximum(layer * 0.55, inside.astype(np.float32) * 0.38)
            self._composite(premul, alpha, layer * self.intensity, self.color)

    def _liquid(self, premul, alpha, t, bass, mids, highs) -> None:
        center_y = self.height * (1 - self.occupancy * 0.48)
        wave = center_y + (7 + 16 * bass) * self.sy * np.sin(math.tau * (self.x * 1.6 - t * 0.30))
        wave += (3 + 7 * highs) * self.sy * np.sin(math.tau * (self.x * 4.3 + t * 0.19))
        distance = np.abs(self.y - wave[None, :])
        narrow = max(0.7, (2.4 + 5 * mids) * self.sy)
        wide = max(1.5, (10 + 8 * bass) * self.sy)
        layer = np.exp(-((distance / narrow) ** 2)) * (0.28 + 0.42 * bass)
        glow = np.exp(-((distance / wide) ** 2)) * 0.12
        self._composite(premul, alpha, (layer + glow) * self.intensity, self.color)

    def _circle(self, premul, alpha, t, bass, mids, attack) -> None:
        radius = min(self.width, self.height) * (0.16 + 0.28 * self.occupancy) * (1 + 0.12 * bass)
        distance = np.sqrt((self.xx - self.cx) ** 2 + (self.yy - self.cy) ** 2)
        width = max(0.75, (1.3 + 2.8 * bass) * self.pixel_scale)
        ring = np.exp(-(((distance - radius) / width) ** 2))
        runes = 0.5 + 0.5 * np.sin(np.arctan2(self.yy - self.cy, self.xx - self.cx) * 18 + t * 2.5)
        layer = ring * (0.20 + 0.34 * mids + 0.28 * attack) * (0.6 + 0.4 * runes)
        self._composite(premul, alpha, layer * self.intensity, self.secondary)

    def _particles(self, premul, alpha, t, bass, mids, highs) -> None:
        density = min(2.2, max(1.0, self.pixel_scale ** 0.45))
        count = min(180, int((24 + 62 * self.occupancy) * density))
        layer = np.zeros((self.height, self.width), dtype=np.float32)
        for index in range(count):
            px = (
                index * 47.3 * self.sx
                + t * (4 + 10 * highs) * self.sx
                + 14 * self.sx * math.sin(index)
            ) % self.width
            py = self.height - (
                (index * 29.7 * self.sy + t * (8 + 18 * mids) * self.sy)
                % (self.height * self.occupancy + 1)
            )
            sigma = max(0.7, (0.8 + 1.8 * bass + (index % 3) * 0.35) * self.pixel_scale)
            glow = np.exp(-(((self.xx - px) ** 2 + (self.yy - py) ** 2) / (2 * sigma * sigma)))
            layer = np.maximum(layer, glow * (0.15 + 0.38 * highs))
        self._composite(premul, alpha, layer * self.intensity, self.color)

    def _pulse(self, premul, alpha, loudness, attack) -> None:
        flash = np.full(
            (self.height, self.width),
            (0.015 + 0.08 * loudness + 0.16 * attack) * self.intensity,
            dtype=np.float32,
        )
        self._composite(premul, alpha, flash, self.secondary)
        vignette = self.edge_mask * (0.08 + 0.14 * (1 - loudness))
        self._composite(premul, alpha, vignette, np.asarray((3, 7, 18), dtype=np.float32))

    def _energy(self, premul, alpha, t, bass, mids, attack) -> None:
        px = self.cx + math.sin(t * 0.55) * self.width * 0.19 * self.occupancy
        py = self.cy + math.cos(t * 0.41) * self.height * 0.13 * self.occupancy
        sigma = max(2.0, (10 + 26 * self.occupancy + 12 * bass) * self.pixel_scale)
        glow = np.exp(-(((self.xx - px) ** 2 + (self.yy - py) ** 2) / (2 * sigma * sigma)))
        rays = 0.5 + 0.5 * np.cos(np.arctan2(self.yy - py, self.xx - px) * 9 + t * 1.7)
        layer = glow * (0.10 + 0.28 * mids + 0.35 * attack) * (0.72 + 0.28 * rays)
        self._composite(premul, alpha, layer * self.intensity, self.warm)

    def make(self, frame_number: int, bands: np.ndarray, loudness: float, attack: float) -> bytes:
        bass, mids, highs = map(float, bands)
        t = frame_number / self.fps
        premul = np.zeros((self.height, self.width, 3), dtype=np.float32)
        alpha = np.zeros((self.height, self.width), dtype=np.float32)
        if "Aurora" in self.effects:
            self._aurora(premul, alpha, t, bass, mids, highs, loudness)
        if "Espectro" in self.effects:
            self._spectrum(premul, alpha, t, bass, mids, highs, False)
        if "Barras arredondadas" in self.effects:
            self._spectrum(premul, alpha, t, bass, mids, highs, True)
        if "Onda líquida" in self.effects:
            self._liquid(premul, alpha, t, bass, mids, highs)
        if "Círculo mágico" in self.effects:
            self._circle(premul, alpha, t, bass, mids, attack)
        if "Partículas musicais" in self.effects:
            self._particles(premul, alpha, t, bass, mids, highs)
        if "Pulso cinematográfico" in self.effects:
            self._pulse(premul, alpha, loudness, attack)
        if "Energia mágica" in self.effects:
            self._energy(premul, alpha, t, bass, mids, attack)
        safe_alpha = np.maximum(alpha, 1e-6)
        rgb = np.clip(premul / safe_alpha[:, :, None], 0, 255).astype(np.uint8)
        alpha_u8 = np.clip(alpha * 255, 0, 255).astype(np.uint8)
        return np.dstack((rgb, alpha_u8)).tobytes()


def build_vfx_filter_graph(
    output_width: int,
    output_height: int,
    effect_width: int | None = None,
    effect_height: int | None = None,
    *,
    output_pixel_format: str = "yuv420p",
    output_primaries: str = "bt709",
    output_transfer: str = "bt709",
    output_space: str = "bt709",
    output_range: str = "tv",
) -> str:
    """Compose a target-aware effect layer without retiming the base video."""

    effect_width = effect_width or output_width
    effect_height = effect_height or output_height
    scale = "" if (effect_width, effect_height) == (output_width, output_height) else f"scale={output_width}:{output_height}:flags=lanczos,"
    set_range = "full" if output_range in {"pc", "full"} else "limited"
    return (
        f"[0:v]format={output_pixel_format},setpts=PTS-STARTPTS[base];"
        f"[1:v]{scale}setpts=PTS-STARTPTS[effect];"
        "[base][effect]overlay=0:0:format=auto,"
        "eq=contrast=1.025:saturation=1.04,"
        f"format={output_pixel_format},"
        f"setparams=range={set_range}:color_primaries={output_primaries}:color_trc={output_transfer}:colorspace={output_space}[vout]"
    )


def render_vfx_intermediate(
    ffmpeg: str,
    master_video: str,
    audio_source: str,
    output_path: str,
    duration: float,
    effects: set[str],
    color: str,
    intensity: float,
    occupancy: float,
    output_width: int,
    output_height: int,
    output_fps: float,
    bitrate: str,
    maxrate: str,
    bufsize: str,
    use_cpu: bool,
    cpu_threads: int,
    audio_focus: str,
    reaction_smoothing: float,
    reaction_expression: float,
    dynamic_sections: bool,
    section_dynamics: float,
    progress: Callable[[float], None],
    cancelled: Callable[[], bool],
    process_changed: Callable[[subprocess.Popen | None], None],
    log: Callable[[str], None],
    analysis_duration: float | None = None,
    analysis_offset: float = 0.0,
    output_pixel_format: str = "yuv420p",
    output_primaries: str = "bt709",
    output_transfer: str = "bt709",
    output_space: str = "bt709",
    output_range: str = "tv",
    lossless_intermediate: bool = False,
    final_video_args: list[str] | None = None,
    final_audio_source: str | None = None,
    final_audio_filter: str = "",
    final_audio_args: list[str] | None = None,
    final_muxer_args: list[str] | None = None,
) -> None:
    """Render music-reactive VFX using the full-track envelope.

    ``duration`` is the output window. ``analysis_duration`` is the duration of
    the complete source used for percentile normalization.  Preview and final
    therefore share exactly the same base envelope and cache key.
    """

    if cancelled():
        raise RenderCancelled
    analysis_duration = max(float(duration), float(analysis_duration or duration))
    spec = choose_vfx_render_spec(output_width, output_height, output_fps)
    log(f"VFX Phase 3: layer {spec.label}; base {output_width}×{output_height}/{output_fps:g} fps.")
    if not spec.native_spatial:
        log("VFX: saída acima de 4K usa canvas adaptativo 4K para controlar RAM/throughput; composição final usa Lanczos.")
    if not spec.native_temporal:
        log("VFX: saída acima de 120 fps usa amostragem reativa de 120 fps sem retimar a base.")

    envelope = load_music_envelope(
        ffmpeg,
        audio_source,
        analysis_duration,
        analysis_fps=DEFAULT_ANALYSIS_FPS,
        log=log,
    )
    shaped = envelope.shaped_slice(
        focus=audio_focus,
        smoothing=reaction_smoothing,
        expression=reaction_expression,
        target_fps=spec.fps,
        start=max(0.0, analysis_offset),
        duration=duration,
        dynamic_sections=dynamic_sections,
        section_dynamics=section_dynamics,
    )
    for section_start, section_end, label in shaped.sections:
        log(f"Seção musical {section_start:06.1f}s–{section_end:06.1f}s: {label}")
    progress(0.02)

    final_delivery = final_video_args is not None
    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-stream_loop",
        "-1",
        "-i",
        master_video,
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "-s",
        f"{spec.width}x{spec.height}",
        "-r",
        f"{spec.fps:.8f}",
        "-i",
        "pipe:0",
    ]
    if final_delivery and final_audio_source:
        command += ["-i", final_audio_source]
    command += [
        "-filter_complex",
        build_vfx_filter_graph(
            output_width,
            output_height,
            spec.width,
            spec.height,
            output_pixel_format=output_pixel_format,
            output_primaries=output_primaries,
            output_transfer=output_transfer,
            output_space=output_space,
            output_range=output_range,
        ),
        "-map",
        "[vout]",
    ]
    if final_delivery and final_audio_source:
        # Inputs are: 0=loop master, 1=raw VFX pipe, 2=delivery audio.
        command += ["-map", "2:a:0"]
    else:
        command += ["-an"]
    command += ["-t", f"{duration:.6f}", "-r", f"{output_fps:.8f}"]

    if final_delivery:
        command += list(final_video_args or ())
    elif lossless_intermediate:
        command += [
            "-c:v", "ffv1", "-level", "3", "-coder", "1", "-context", "1",
            "-g", "1", "-slicecrc", "1", "-pix_fmt", output_pixel_format,
        ]
    elif use_cpu:
        command += ["-c:v", "libx264", "-preset", "medium", "-crf", "12", "-pix_fmt", output_pixel_format]
    else:
        command += [
            "-c:v",
            "h264_nvenc",
            "-preset",
            "p7",
            "-tune",
            "hq",
            "-rc",
            "vbr",
            "-cq",
            "10",
            "-b:v",
            bitrate,
            "-maxrate",
            maxrate,
            "-bufsize",
            bufsize,
            "-g",
            "30",
            "-bf",
            "2",
            "-pix_fmt",
            output_pixel_format,
        ]
    command += [
        "-color_primaries",
        output_primaries,
        "-color_trc",
        output_transfer,
        "-colorspace",
        output_space,
        "-color_range",
        "pc" if output_range in {"pc", "full"} else "tv",
        "-threads",
        str(max(1, cpu_threads)),
    ]
    if final_delivery:
        if final_audio_source:
            if final_audio_filter:
                command += ["-af", final_audio_filter]
            command += list(final_audio_args or ())
        command += list(final_muxer_args or ())
    elif not lossless_intermediate:
        command += ["-movflags", "+faststart"]
    command += [output_path]
    log("Comando VFX: " + subprocess.list2cmdline(command))
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,
        creationflags=CREATE_NO_WINDOW,
    )
    process_changed(process)
    recent: deque[str] = deque(maxlen=50)

    def drain_output() -> None:
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if line:
                recent.append(line)
                log(line)

    reader = threading.Thread(target=drain_output, daemon=True)
    reader.start()
    generator = StudioFrameGenerator(
        effects,
        color,
        intensity,
        occupancy,
        width=spec.width,
        height=spec.height,
        fps=spec.fps,
    )
    frame_count = len(shaped.energy)
    try:
        assert process.stdin is not None
        for frame_number in range(frame_count):
            if cancelled():
                process.terminate()
                raise RenderCancelled
            frame = generator.make(
                frame_number,
                shaped.energy[frame_number],
                float(shaped.rms[frame_number]),
                float(shaped.onset[frame_number]),
            )
            try:
                process.stdin.write(frame)
            except (BrokenPipeError, OSError):
                break
            if frame_number % max(1, int(round(spec.fps / 5))) == 0:
                progress(0.02 + 0.98 * ((frame_number + 1) / frame_count))
        try:
            process.stdin.close()
        except OSError:
            pass
        return_code = process.wait()
        reader.join(timeout=2)
        if cancelled():
            raise RenderCancelled
        if return_code:
            raise RuntimeError("Falha ao renderizar os VFX.\n\n" + "\n".join(recent))
        progress(1.0)
    finally:
        process_changed(None)
