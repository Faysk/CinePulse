from __future__ import annotations

import math
import os
import subprocess
import threading
from collections import deque
from pathlib import Path
from typing import Callable

import numpy as np


EFFECT_FPS = 60
EFFECT_WIDTH = 320
EFFECT_HEIGHT = 180
SAMPLE_RATE = 48000
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class RenderCancelled(Exception):
    pass


def _decode_audio(ffmpeg: str, audio_path: str, duration: float) -> np.ndarray:
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        audio_path,
        "-map",
        "0:a:0",
        "-t",
        f"{duration:.6f}",
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-f",
        "s16le",
        "pipe:1",
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
    if result.returncode:
        details = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(details or "Não foi possível analisar o áudio para criar a aurora.")
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
    for frame in range(1, frame_count):
        energy[frame] = energy[frame - 1] * 0.80 + energy[frame] * 0.20
        rms[frame] = rms[frame - 1] * 0.82 + rms[frame] * 0.18
    onset = np.maximum(0, raw_bass - np.r_[raw_bass[0], raw_bass[:-1]] * 0.94)
    onset = np.clip(onset / max(float(np.percentile(onset, 97)), 1e-5), 0, 1)
    return energy, rms, onset


class AuroraFrameGenerator:
    def __init__(self) -> None:
        self.x = np.linspace(0, 1, EFFECT_WIDTH, dtype=np.float32)
        self.y = np.arange(EFFECT_HEIGHT, dtype=np.float32)[:, None]
        yy, xx = np.mgrid[0:EFFECT_HEIGHT, 0:EFFECT_WIDTH].astype(np.float32)
        self.xx = xx
        self.yy = yy
        center_x, center_y = EFFECT_WIDTH / 2, EFFECT_HEIGHT / 2
        edge_radius = np.sqrt(
            ((xx - center_x) / (EFFECT_WIDTH * 0.60)) ** 2
            + ((yy - center_y) / (EFFECT_HEIGHT * 0.58)) ** 2
        )
        self.edge_mask = np.clip((edge_radius - 0.52) / 0.48, 0, 1) ** 1.6
        self.ribbons = (
            ((50, 126, 255), 0.0, 0.30, 133, 11),
            ((73, 232, 255), 1.7, 0.38, 141, 9),
            ((120, 83, 255), 3.4, 0.24, 149, 12),
            ((255, 186, 76), 4.9, 0.18, 155, 7),
        )

    @staticmethod
    def _composite(
        premultiplied: np.ndarray,
        alpha_total: np.ndarray,
        layer_alpha: np.ndarray,
        color: tuple[int, int, int],
    ) -> tuple[np.ndarray, np.ndarray]:
        layer = np.clip(layer_alpha, 0, 0.82).astype(np.float32)
        remaining = 1.0 - layer
        premultiplied *= remaining[:, :, None]
        premultiplied += layer[:, :, None] * np.asarray(color, dtype=np.float32)
        alpha_total[:] = alpha_total * remaining + layer
        return premultiplied, alpha_total

    def make(self, frame_number: int, bands: np.ndarray, loudness: float, attack: float) -> bytes:
        bass, mids, highs = map(float, bands)
        time = frame_number / EFFECT_FPS
        premultiplied = np.zeros((EFFECT_HEIGHT, EFFECT_WIDTH, 3), dtype=np.float32)
        alpha_total = np.zeros((EFFECT_HEIGHT, EFFECT_WIDTH), dtype=np.float32)

        for color, phase_offset, opacity, base_y, base_thickness in self.ribbons:
            phase = time * (0.65 + 0.38 * mids) + phase_offset
            wave = (
                (5 + 7 * mids) * np.sin(math.tau * (self.x * 1.25 + phase * 0.20))
                + (2.5 + 5 * highs) * np.sin(math.tau * (self.x * 3.1 - phase * 0.13))
                + 2 * np.sin(math.tau * (self.x * 6.3 + phase * 0.08))
            )
            center = base_y + wave
            thickness = base_thickness + 7.5 * bass + 2.5 * loudness
            distance = (self.y - center[None, :]) / thickness
            curtain = np.exp(-(distance * distance) * 1.25)
            vertical_fade = np.clip((self.y - 82) / 48, 0, 1)
            shimmer = 0.84 + 0.16 * np.sin(
                math.tau * (self.x * 8.0 + time * 0.22 + phase_offset)
            )
            layer_alpha = (
                curtain
                * vertical_fade
                * shimmer[None, :]
                * opacity
                * (0.42 + 0.58 * loudness)
            )
            self._composite(premultiplied, alpha_total, layer_alpha, color)

        orb_x, orb_y = 218.5, 123.0
        orb_sigma = 12 + 9 * bass
        orb_distance = ((self.xx - orb_x) ** 2 + (self.yy - orb_y) ** 2) / (2 * orb_sigma * orb_sigma)
        orb_alpha = np.exp(-orb_distance) * ((24 + 112 * bass + 38 * attack) / 255)
        self._composite(premultiplied, alpha_total, orb_alpha, (92, 226, 255))

        flare_y = np.exp(-((self.yy - orb_y) / (4 + 3 * bass)) ** 2)
        flare_x = np.exp(-((self.xx - orb_x) / 92) ** 2)
        flare_alpha = flare_x * flare_y * ((8 + 48 * bass + 38 * attack) / 255)
        self._composite(premultiplied, alpha_total, flare_alpha, (127, 238, 255))

        phoenix_x, phoenix_y = 235.0, 57.5
        gold_sigma = 39 + 12 * mids
        gold_distance = (
            (self.xx - phoenix_x) ** 2 + (self.yy - phoenix_y) ** 2
        ) / (2 * gold_sigma * gold_sigma)
        gold_alpha = np.exp(-gold_distance) * ((4 + 22 * mids) / 255)
        self._composite(premultiplied, alpha_total, gold_alpha, (255, 181, 75))

        flash_alpha = np.full(
            (EFFECT_HEIGHT, EFFECT_WIDTH),
            (2 + 15 * loudness + 28 * attack) / 255,
            dtype=np.float32,
        )
        self._composite(premultiplied, alpha_total, flash_alpha, (204, 243, 255))

        vignette_strength = max(18, 58 - 24 * bass - 13 * attack) / 255
        self._composite(
            premultiplied,
            alpha_total,
            self.edge_mask * vignette_strength,
            (3, 7, 18),
        )

        safe_alpha = np.maximum(alpha_total, 1e-6)
        rgb = np.clip(premultiplied / safe_alpha[:, :, None], 0, 255).astype(np.uint8)
        alpha = np.clip(alpha_total * 255, 0, 255).astype(np.uint8)
        return np.dstack((rgb, alpha)).tobytes()


def render_reactive_intermediate(
    ffmpeg: str,
    master_video: str,
    audio_path: str,
    output_path: str,
    duration: float,
    progress: Callable[[float], None],
    cancelled: Callable[[], bool],
    process_changed: Callable[[subprocess.Popen | None], None],
    output_width: int = 1280,
    output_height: int = 720,
    bitrate: str = "50M",
    maxrate: str = "100M",
    bufsize: str = "200M",
) -> None:
    if cancelled():
        raise RenderCancelled
    samples = _decode_audio(ffmpeg, audio_path, duration)
    if cancelled():
        raise RenderCancelled
    energy, rms, onset = _analyze_audio(samples, duration)
    progress(0.02)

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
        f"{EFFECT_WIDTH}x{EFFECT_HEIGHT}",
        "-r",
        str(EFFECT_FPS),
        "-i",
        "pipe:0",
        "-filter_complex",
        "[0:v]setpts=N/(60*TB)[base];"
        f"[1:v]scale={output_width}:{output_height}:flags=lanczos[effect];"
        "[base][effect]overlay=0:0:format=auto,"
        "eq=contrast=1.035:saturation=1.055,"
        "setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709,"
        "format=yuv420p[vout]",
        "-map",
        "[vout]",
        "-an",
        "-t",
        f"{duration:.6f}",
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
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
        "-color_range",
        "tv",
        "-movflags",
        "+faststart",
        output_path,
    ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,
        creationflags=CREATE_NO_WINDOW,
    )
    process_changed(process)
    recent: deque[str] = deque(maxlen=40)

    def drain_output() -> None:
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if line:
                recent.append(line)

    reader = threading.Thread(target=drain_output, daemon=True)
    reader.start()
    generator = AuroraFrameGenerator()
    frame_count = len(energy)
    try:
        assert process.stdin is not None
        for frame_number in range(frame_count):
            if cancelled():
                process.terminate()
                raise RenderCancelled
            frame = generator.make(frame_number, energy[frame_number], float(rms[frame_number]), float(onset[frame_number]))
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
            details = "\n".join(recent)
            raise RuntimeError(f"Falha ao renderizar a Aurora Cinematográfica.\n\n{details}")
        progress(1.0)
    finally:
        process_changed(None)
