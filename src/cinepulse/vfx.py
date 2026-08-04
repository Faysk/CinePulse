from __future__ import annotations

import math
import os
import subprocess
import threading
from collections import deque
from typing import Callable

import numpy as np


EFFECT_FPS = 60
EFFECT_WIDTH = 320
EFFECT_HEIGHT = 180
SAMPLE_RATE = 48000
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class RenderCancelled(Exception):
    pass


def _decode_audio(ffmpeg: str, media_path: str, duration: float) -> np.ndarray:
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", media_path,
        "-map", "0:a:0", "-t", f"{duration:.6f}", "-vn", "-ac", "1",
        "-ar", str(SAMPLE_RATE), "-f", "s16le", "pipe:1",
    ]
    result = subprocess.run(
        command, capture_output=True, creationflags=CREATE_NO_WINDOW, check=False
    )
    if result.returncode:
        details = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(details or "Não foi possível analisar o áudio para os VFX.")
    return np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def _analyze_audio(samples: np.ndarray, duration: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    frame_count = max(1, math.ceil(duration * EFFECT_FPS))
    window_size = 2048
    window = np.hanning(window_size).astype(np.float32)
    frequencies = np.fft.rfftfreq(window_size, 1 / SAMPLE_RATE)
    masks = (
        (frequencies >= 45) & (frequencies < 180),
        (frequencies >= 180) & (frequencies < 2200),
        (frequencies >= 2200) & (frequencies < 14000),
    )
    energy = np.zeros((frame_count, 3), dtype=np.float32)
    rms = np.zeros(frame_count, dtype=np.float32)
    for frame in range(frame_count):
        center = int(frame / EFFECT_FPS * SAMPLE_RATE)
        start = max(0, center - window_size // 2)
        chunk = samples[start : start + window_size]
        if len(chunk) < window_size:
            chunk = np.pad(chunk, (0, window_size - len(chunk)))
        spectrum = np.abs(np.fft.rfft(chunk * window))
        rms[frame] = float(np.sqrt(np.mean(chunk * chunk)))
        for index, mask in enumerate(masks):
            energy[frame, index] = float(np.mean(spectrum[mask]))
    energy = np.log1p(energy)
    peaks = np.percentile(energy, 96, axis=0)
    peaks[peaks < 1e-6] = 1
    energy = np.clip(energy / peaks, 0, 1)
    rms = np.clip(rms / max(float(np.percentile(rms, 96)), 1e-6), 0, 1)
    raw_bass = energy[:, 0].copy()
    onset = np.maximum(0, raw_bass - np.r_[raw_bass[0], raw_bass[:-1]] * 0.94)
    onset = np.clip(onset / max(float(np.percentile(onset, 97)), 1e-5), 0, 1)
    return energy, rms, onset


def shape_reactivity(
    energy: np.ndarray,
    rms: np.ndarray,
    onset: np.ndarray,
    focus: str,
    smoothing: float,
    expression: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    shaped = energy.copy()
    loudness = rms.copy()
    attacks = onset.copy()
    bass, mids, highs = shaped[:, 0].copy(), shaped[:, 1].copy(), shaped[:, 2].copy()
    if focus == "Graves":
        shaped = np.column_stack((bass, bass * 0.62, bass * 0.34))
        loudness = bass
        attacks *= 0.85
    elif focus == "Graves e batidas":
        pulse = np.clip(bass * 0.78 + attacks * 0.48, 0, 1)
        shaped = np.column_stack((pulse, bass * 0.55, attacks * 0.72))
        loudness = pulse
    elif focus == "Médios":
        shaped = np.column_stack((mids * 0.42, mids, mids * 0.58))
        loudness = mids
        attacks *= 0.55
    elif focus == "Agudos":
        shaped = np.column_stack((highs * 0.28, highs * 0.60, highs))
        loudness = highs
        attacks *= 0.45
    elif focus == "Batidas e ataques":
        shaped = np.column_stack((attacks, attacks * 0.82, attacks * 0.64))
        loudness = attacks.copy()

    gain = max(0.25, min(2.0, expression))
    shaped = np.clip(shaped * gain, 0, 1)
    loudness = np.clip(loudness * gain, 0, 1)
    attacks = np.clip(attacks * gain, 0, 1)
    memory = max(0.0, min(0.965, smoothing * 0.965))
    if memory > 0:
        for frame in range(1, len(shaped)):
            shaped[frame] = shaped[frame - 1] * memory + shaped[frame] * (1 - memory)
            loudness[frame] = loudness[frame - 1] * memory + loudness[frame] * (1 - memory)
            attacks[frame] = attacks[frame - 1] * memory + attacks[frame] * (1 - memory)
    return shaped, loudness, attacks


def analyze_music_structure(
    energy: np.ndarray,
    rms: np.ndarray,
    onset: np.ndarray,
    strength: float,
) -> tuple[np.ndarray, list[tuple[float, float, str]]]:
    frame_count = len(rms)
    if frame_count == 0:
        return np.ones(0, dtype=np.float32), []
    feature = np.clip(
        energy[:, 0] * 0.42 + energy[:, 1] * 0.32 + energy[:, 2] * 0.12
        + rms * 0.10 + onset * 0.18,
        0,
        1.5,
    )
    block_frames = max(EFFECT_FPS * 6, 1)
    block_scores = np.asarray(
        [float(np.mean(feature[start : start + block_frames])) for start in range(0, frame_count, block_frames)],
        dtype=np.float32,
    )
    if float(np.ptp(block_scores)) < 0.035:
        labels = ["Normal"] * len(block_scores)
    else:
        low = float(np.percentile(block_scores, 34))
        high = float(np.percentile(block_scores, 72))
        labels = ["Calmo" if score <= low else "Refrão/clímax" if score >= high else "Normal" for score in block_scores]
    base_factors = {"Calmo": 0.72, "Normal": 0.94, "Refrão/clímax": 1.16}
    amount = max(0.0, min(1.0, strength))
    envelope = np.ones(frame_count, dtype=np.float32)
    sections: list[tuple[float, float, str]] = []
    for index, label in enumerate(labels):
        start = index * block_frames
        end = min(frame_count, start + block_frames)
        factor = 1.0 + (base_factors[label] - 1.0) * amount
        envelope[start:end] = factor
        sections.append((start / EFFECT_FPS, end / EFFECT_FPS, label))
    fade_frames = min(EFFECT_FPS * 2, max(1, frame_count // 6))
    if fade_frames > 1:
        kernel = np.ones(fade_frames, dtype=np.float32) / fade_frames
        envelope = np.convolve(np.pad(envelope, (fade_frames // 2, fade_frames // 2), mode="edge"), kernel, mode="valid")[:frame_count]
    return envelope.astype(np.float32), sections


def _hex_color(value: str) -> tuple[int, int, int]:
    clean = value.strip().lstrip("#")
    if len(clean) != 6:
        return 67, 214, 255
    try:
        return tuple(int(clean[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return 67, 214, 255


class StudioFrameGenerator:
    def __init__(self, effects: set[str], color: str, intensity: float, occupancy: float) -> None:
        self.effects = effects
        self.color = np.asarray(_hex_color(color), dtype=np.float32)
        self.secondary = np.clip(self.color[[2, 0, 1]] * 1.08 + 18, 0, 255)
        self.warm = np.clip(self.color * np.asarray((1.35, 0.82, 0.55)), 0, 255)
        self.intensity = max(0.05, min(2.0, intensity))
        self.occupancy = max(0.10, min(1.0, occupancy))
        self.x = np.linspace(0, 1, EFFECT_WIDTH, dtype=np.float32)
        self.y = np.arange(EFFECT_HEIGHT, dtype=np.float32)[:, None]
        yy, xx = np.mgrid[0:EFFECT_HEIGHT, 0:EFFECT_WIDTH].astype(np.float32)
        self.xx, self.yy = xx, yy
        self.cx, self.cy = EFFECT_WIDTH / 2, EFFECT_HEIGHT / 2
        radius = np.sqrt(((xx - self.cx) / 190) ** 2 + ((yy - self.cy) / 106) ** 2)
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
        base_y = EFFECT_HEIGHT * (1.03 - 0.50 * self.occupancy)
        for index, phase_offset in enumerate((0.0, 1.7, 3.4, 4.9)):
            phase = t * (0.65 + 0.38 * mids) + phase_offset
            wave = (
                (5 + 8 * mids) * np.sin(math.tau * (self.x * 1.25 + phase * 0.20))
                + (2.5 + 5 * highs) * np.sin(math.tau * (self.x * 3.1 - phase * 0.13))
            )
            center = base_y + index * 7 - 11 + wave
            thickness = (7 + 9 * bass) * (0.65 + self.occupancy)
            curtain = np.exp(-(((self.y - center[None, :]) / thickness) ** 2) * 1.15)
            shimmer = 0.82 + 0.18 * np.sin(math.tau * (self.x * 8 + t * 0.22 + phase_offset))
            layer = curtain * shimmer[None, :] * (0.09 + 0.16 * loudness) * self.intensity
            color = self.color if index % 2 == 0 else self.secondary
            self._composite(premul, alpha, layer, color)

    def _spectrum(self, premul, alpha, t, bass, mids, highs, rounded: bool) -> None:
        count = 48
        area = EFFECT_HEIGHT * self.occupancy
        base = EFFECT_HEIGHT - 5
        for index in range(count):
            x0 = index * EFFECT_WIDTH / count
            x1 = (index + 0.62) * EFFECT_WIDTH / count
            harmonic = 0.5 + 0.5 * math.sin(index * 0.71 + t * 2.1)
            band = bass * (1 - index / count) + highs * (index / count) + mids * harmonic
            height = max(2, area * (0.08 + 0.82 * min(1, band)))
            dx = np.maximum(np.maximum(x0 - self.xx, self.xx - x1), 0)
            dy = np.maximum(np.maximum(base - height - self.yy, self.yy - base), 0)
            distance = np.sqrt(dx * dx + dy * dy)
            softness = 1.8 if rounded else 0.8
            layer = np.exp(-((distance / softness) ** 2)) * (distance < 4)
            inside = (self.xx >= x0) & (self.xx <= x1) & (self.yy >= base - height) & (self.yy <= base)
            layer = np.maximum(layer * 0.55, inside.astype(np.float32) * 0.38)
            self._composite(premul, alpha, layer * self.intensity, self.color)

    def _liquid(self, premul, alpha, t, bass, mids, highs) -> None:
        center_y = EFFECT_HEIGHT * (1 - self.occupancy * 0.48)
        wave = center_y + (7 + 16 * bass) * np.sin(math.tau * (self.x * 1.6 - t * 0.30))
        wave += (3 + 7 * highs) * np.sin(math.tau * (self.x * 4.3 + t * 0.19))
        distance = np.abs(self.y - wave[None, :])
        layer = np.exp(-((distance / (2.4 + 5 * mids)) ** 2)) * (0.28 + 0.42 * bass)
        glow = np.exp(-((distance / (10 + 8 * bass)) ** 2)) * 0.12
        self._composite(premul, alpha, (layer + glow) * self.intensity, self.color)

    def _circle(self, premul, alpha, t, bass, mids, attack) -> None:
        radius = min(EFFECT_WIDTH, EFFECT_HEIGHT) * (0.16 + 0.28 * self.occupancy) * (1 + 0.12 * bass)
        distance = np.sqrt((self.xx - self.cx) ** 2 + (self.yy - self.cy) ** 2)
        ring = np.exp(-(((distance - radius) / (1.3 + 2.8 * bass)) ** 2))
        runes = 0.5 + 0.5 * np.sin(np.arctan2(self.yy - self.cy, self.xx - self.cx) * 18 + t * 2.5)
        layer = ring * (0.20 + 0.34 * mids + 0.28 * attack) * (0.6 + 0.4 * runes)
        self._composite(premul, alpha, layer * self.intensity, self.secondary)

    def _particles(self, premul, alpha, t, bass, mids, highs) -> None:
        count = int(24 + 62 * self.occupancy)
        layer = np.zeros((EFFECT_HEIGHT, EFFECT_WIDTH), dtype=np.float32)
        for index in range(count):
            px = (index * 47.3 + t * (4 + 10 * highs) + 14 * math.sin(index)) % EFFECT_WIDTH
            py = EFFECT_HEIGHT - ((index * 29.7 + t * (8 + 18 * mids)) % (EFFECT_HEIGHT * self.occupancy + 1))
            sigma = 0.8 + 1.8 * bass + (index % 3) * 0.35
            glow = np.exp(-(((self.xx - px) ** 2 + (self.yy - py) ** 2) / (2 * sigma * sigma)))
            layer = np.maximum(layer, glow * (0.15 + 0.38 * highs))
        self._composite(premul, alpha, layer * self.intensity, self.color)

    def _pulse(self, premul, alpha, loudness, attack) -> None:
        flash = np.full((EFFECT_HEIGHT, EFFECT_WIDTH), (0.015 + 0.08 * loudness + 0.16 * attack) * self.intensity)
        self._composite(premul, alpha, flash, self.secondary)
        vignette = self.edge_mask * (0.08 + 0.14 * (1 - loudness))
        self._composite(premul, alpha, vignette, np.asarray((3, 7, 18), dtype=np.float32))

    def _energy(self, premul, alpha, t, bass, mids, attack) -> None:
        px = self.cx + math.sin(t * 0.55) * EFFECT_WIDTH * 0.19 * self.occupancy
        py = self.cy + math.cos(t * 0.41) * EFFECT_HEIGHT * 0.13 * self.occupancy
        sigma = 10 + 26 * self.occupancy + 12 * bass
        glow = np.exp(-(((self.xx - px) ** 2 + (self.yy - py) ** 2) / (2 * sigma * sigma)))
        rays = 0.5 + 0.5 * np.cos(np.arctan2(self.yy - py, self.xx - px) * 9 + t * 1.7)
        layer = glow * (0.10 + 0.28 * mids + 0.35 * attack) * (0.72 + 0.28 * rays)
        self._composite(premul, alpha, layer * self.intensity, self.warm)

    def make(self, frame_number: int, bands: np.ndarray, loudness: float, attack: float) -> bytes:
        bass, mids, highs = map(float, bands)
        t = frame_number / EFFECT_FPS
        premul = np.zeros((EFFECT_HEIGHT, EFFECT_WIDTH, 3), dtype=np.float32)
        alpha = np.zeros((EFFECT_HEIGHT, EFFECT_WIDTH), dtype=np.float32)
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
) -> None:
    if cancelled():
        raise RenderCancelled
    log("Analisando frequências, volume e ataques do áudio para os VFX.")
    samples = _decode_audio(ffmpeg, audio_source, duration)
    energy, rms, onset = _analyze_audio(samples, duration)
    energy, rms, onset = shape_reactivity(
        energy,
        rms,
        onset,
        audio_focus,
        reaction_smoothing,
        reaction_expression,
    )
    if dynamic_sections:
        envelope, sections = analyze_music_structure(energy, rms, onset, section_dynamics)
        energy = np.clip(energy * envelope[:, None], 0, 1)
        rms = np.clip(rms * envelope, 0, 1)
        onset = np.clip(onset * envelope, 0, 1)
        for start, end, label in sections:
            log(f"Seção musical {start:06.1f}s–{end:06.1f}s: {label}")
    progress(0.02)
    command = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-stream_loop", "-1",
        "-i", master_video, "-f", "rawvideo", "-pix_fmt", "rgba",
        "-s", f"{EFFECT_WIDTH}x{EFFECT_HEIGHT}", "-r", str(EFFECT_FPS), "-i", "pipe:0",
        "-filter_complex",
        "[0:v]setpts=N/(60*TB)[base];"
        f"[1:v]scale={output_width}:{output_height}:flags=lanczos[effect];"
        "[base][effect]overlay=0:0:format=auto,"
        "eq=contrast=1.025:saturation=1.04,"
        "setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709,"
        "format=yuv420p[vout]",
        "-map", "[vout]", "-an", "-t", f"{duration:.6f}",
    ]
    if use_cpu:
        command += ["-c:v", "libx264", "-preset", "medium", "-crf", "12", "-pix_fmt", "yuv420p"]
    else:
        command += [
            "-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq", "-rc", "vbr",
            "-cq", "10", "-b:v", bitrate, "-maxrate", maxrate, "-bufsize", bufsize,
            "-g", "30", "-bf", "2",
        ]
    command += [
        "-color_primaries", "bt709", "-color_trc", "bt709",
        "-colorspace", "bt709", "-color_range", "tv", "-threads", str(max(1, cpu_threads)),
        "-movflags", "+faststart", output_path,
    ]
    log("Comando VFX: " + subprocess.list2cmdline(command))
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=False, creationflags=CREATE_NO_WINDOW,
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
    generator = StudioFrameGenerator(effects, color, intensity, occupancy)
    frame_count = len(energy)
    try:
        assert process.stdin is not None
        for frame_number in range(frame_count):
            if cancelled():
                process.terminate()
                raise RenderCancelled
            frame = generator.make(
                frame_number, energy[frame_number], float(rms[frame_number]), float(onset[frame_number])
            )
            try:
                process.stdin.write(frame)
            except (BrokenPipeError, OSError):
                break
            if frame_number % 12 == 0:
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
