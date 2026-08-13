from __future__ import annotations

import json
import math
import os
import subprocess
import threading
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Callable

import numpy as np

from .paths import PATHS

SAMPLE_RATE = 48_000
DEFAULT_ANALYSIS_FPS = 120.0
ANALYZER_VERSION = "core-integrity-phase3-envelope-v1"
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


@dataclass(frozen=True)
class EnvelopeSlice:
    energy: np.ndarray
    rms: np.ndarray
    onset: np.ndarray
    fps: float
    start: float
    duration: float
    sections: tuple[tuple[float, float, str], ...] = ()


@dataclass(frozen=True)
class MusicEnvelope:
    energy: np.ndarray
    rms: np.ndarray
    onset: np.ndarray
    fps: float
    duration: float
    source_key: str

    def shaped_slice(
        self,
        *,
        focus: str,
        smoothing: float,
        expression: float,
        target_fps: float,
        start: float,
        duration: float,
        dynamic_sections: bool,
        section_dynamics: float,
    ) -> EnvelopeSlice:
        energy, rms, onset = shape_reactivity(
            self.energy,
            self.rms,
            self.onset,
            focus,
            smoothing,
            expression,
        )
        sections: list[tuple[float, float, str]] = []
        if dynamic_sections:
            modulation, sections = analyze_music_structure(
                energy,
                rms,
                onset,
                section_dynamics,
                fps=self.fps,
            )
            energy = np.clip(energy * modulation[:, None], 0, 1)
            rms = np.clip(rms * modulation, 0, 1)
            onset = np.clip(onset * modulation, 0, 1)

        sliced_energy, sliced_rms, sliced_onset = resample_features(
            energy,
            rms,
            onset,
            source_fps=self.fps,
            target_fps=target_fps,
            start=start,
            duration=duration,
        )
        end = start + duration
        local_sections: list[tuple[float, float, str]] = []
        for section_start, section_end, label in sections:
            if section_end <= start or section_start >= end:
                continue
            local_sections.append(
                (max(0.0, section_start - start), min(duration, section_end - start), label)
            )
        return EnvelopeSlice(
            energy=sliced_energy,
            rms=sliced_rms,
            onset=sliced_onset,
            fps=float(target_fps),
            start=float(start),
            duration=float(duration),
            sections=tuple(local_sections),
        )


def decode_audio(ffmpeg: str, media_path: str, duration: float) -> np.ndarray:
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        media_path,
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
    result = subprocess.run(command, capture_output=True, creationflags=CREATE_NO_WINDOW, check=False)
    if result.returncode:
        details = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(details or "Não foi possível analisar o áudio para os VFX.")
    return np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def analyze_samples(samples: np.ndarray, duration: float, *, fps: float = DEFAULT_ANALYSIS_FPS) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if fps <= 0:
        raise ValueError("Analysis FPS must be positive.")
    frame_count = max(1, math.ceil(duration * fps))
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
        center = int(frame / fps * SAMPLE_RATE)
        start = max(0, center - window_size // 2)
        chunk = samples[start : start + window_size]
        if len(chunk) < window_size:
            chunk = np.pad(chunk, (0, window_size - len(chunk)))
        spectrum = np.abs(np.fft.rfft(chunk * window))
        rms[frame] = float(np.sqrt(np.mean(chunk * chunk)))
        for index, mask in enumerate(masks):
            energy[frame, index] = float(np.mean(spectrum[mask]))

    # Crucially, normalization is performed over the full source duration.
    energy = np.log1p(energy)
    peaks = np.percentile(energy, 96, axis=0)
    peaks[peaks < 1e-6] = 1
    energy = np.clip(energy / peaks, 0, 1)
    rms = np.clip(rms / max(float(np.percentile(rms, 96)), 1e-6), 0, 1)
    raw_bass = energy[:, 0].copy()
    onset = np.maximum(0, raw_bass - np.r_[raw_bass[0], raw_bass[:-1]] * 0.94)
    onset = np.clip(onset / max(float(np.percentile(onset, 97)), 1e-5), 0, 1)
    return energy.astype(np.float32), rms.astype(np.float32), onset.astype(np.float32)


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
    return shaped.astype(np.float32), loudness.astype(np.float32), attacks.astype(np.float32)


def analyze_music_structure(
    energy: np.ndarray,
    rms: np.ndarray,
    onset: np.ndarray,
    strength: float,
    *,
    fps: float = DEFAULT_ANALYSIS_FPS,
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
    block_frames = max(int(round(fps * 6)), 1)
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
    modulation = np.ones(frame_count, dtype=np.float32)
    sections: list[tuple[float, float, str]] = []
    for index, label in enumerate(labels):
        start = index * block_frames
        end = min(frame_count, start + block_frames)
        factor = 1.0 + (base_factors[label] - 1.0) * amount
        modulation[start:end] = factor
        sections.append((start / fps, end / fps, label))
    fade_frames = min(int(round(fps * 2)), max(1, frame_count // 6))
    if fade_frames > 1:
        kernel = np.ones(fade_frames, dtype=np.float32) / fade_frames
        modulation = np.convolve(
            np.pad(modulation, (fade_frames // 2, fade_frames // 2), mode="edge"),
            kernel,
            mode="valid",
        )[:frame_count]
    return modulation.astype(np.float32), sections


def resample_features(
    energy: np.ndarray,
    rms: np.ndarray,
    onset: np.ndarray,
    *,
    source_fps: float,
    target_fps: float,
    start: float,
    duration: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if source_fps <= 0 or target_fps <= 0 or duration <= 0:
        raise ValueError("Envelope resampling requires positive FPS and duration.")
    frame_count = max(1, int(math.ceil(duration * target_fps)))
    target_times = start + np.arange(frame_count, dtype=np.float64) / target_fps
    source_times = np.arange(len(rms), dtype=np.float64) / source_fps
    max_time = source_times[-1] if len(source_times) else 0.0
    target_times = np.clip(target_times, 0.0, max_time)

    out_energy = np.column_stack([
        np.interp(target_times, source_times, energy[:, band]) for band in range(3)
    ]).astype(np.float32)
    out_rms = np.interp(target_times, source_times, rms).astype(np.float32)
    out_onset = np.interp(target_times, source_times, onset).astype(np.float32)
    return out_energy, out_rms, out_onset


def _source_key(media_path: str, duration: float, fps: float) -> str:
    path = Path(media_path).expanduser()
    try:
        stat = path.stat()
        metadata = {
            "path": str(path.resolve()),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "duration": round(float(duration), 6),
            "fps": round(float(fps), 6),
            "version": ANALYZER_VERSION,
        }
    except OSError:
        metadata = {
            "path": str(path),
            "duration": round(float(duration), 6),
            "fps": round(float(fps), 6),
            "version": ANALYZER_VERSION,
        }
    raw = json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(raw.encode("utf-8")).hexdigest()[:24]


_cache_lock = threading.Lock()
_memory_cache: dict[str, MusicEnvelope] = {}


def load_music_envelope(
    ffmpeg: str,
    media_path: str,
    duration: float,
    *,
    analysis_fps: float = DEFAULT_ANALYSIS_FPS,
    cache_dir: Path | None = None,
    log: Callable[[str], None] | None = None,
) -> MusicEnvelope:
    """Return a full-track normalized envelope, using deterministic disk cache.

    Preview and final renders call this function with the *same full source
    duration*.  They can then slice different time windows without changing the
    normalization percentiles, closing CP-013.
    """

    if duration <= 0:
        raise ValueError("Envelope duration must be positive.")
    key = _source_key(media_path, duration, analysis_fps)
    with _cache_lock:
        cached = _memory_cache.get(key)
    if cached is not None:
        if log:
            log(f"Envelope musical: cache RAM {key}.")
        return cached

    directory = cache_dir or (PATHS.cache / "music-envelope")
    cache_path = directory / f"{key}.npz"
    try:
        if cache_path.is_file():
            with np.load(cache_path, allow_pickle=False) as payload:
                envelope = MusicEnvelope(
                    energy=payload["energy"].astype(np.float32),
                    rms=payload["rms"].astype(np.float32),
                    onset=payload["onset"].astype(np.float32),
                    fps=float(payload["fps"]),
                    duration=float(payload["duration"]),
                    source_key=key,
                )
            with _cache_lock:
                _memory_cache[key] = envelope
            if log:
                log(f"Envelope musical: cache SSD {key}.")
            return envelope
    except (OSError, ValueError, KeyError):
        # A stale/corrupt cache is disposable and must never break rendering.
        try:
            cache_path.unlink(missing_ok=True)
        except OSError:
            pass

    if log:
        log(f"Envelope musical: analisando faixa completa a {analysis_fps:g} fps ({duration:.2f}s).")
    samples = decode_audio(ffmpeg, media_path, duration)
    energy, rms, onset = analyze_samples(samples, duration, fps=analysis_fps)
    envelope = MusicEnvelope(
        energy=energy,
        rms=rms,
        onset=onset,
        fps=float(analysis_fps),
        duration=float(duration),
        source_key=key,
    )
    try:
        directory.mkdir(parents=True, exist_ok=True)
        temp = cache_path.with_suffix(".tmp.npz")
        np.savez_compressed(
            temp,
            energy=envelope.energy,
            rms=envelope.rms,
            onset=envelope.onset,
            fps=np.asarray(envelope.fps, dtype=np.float64),
            duration=np.asarray(envelope.duration, dtype=np.float64),
        )
        os.replace(temp, cache_path)
    except OSError:
        pass
    with _cache_lock:
        _memory_cache[key] = envelope
    return envelope


def clear_memory_cache() -> None:
    with _cache_lock:
        _memory_cache.clear()
