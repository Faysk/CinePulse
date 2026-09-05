from __future__ import annotations

"""High-detail audio analysis for Preview music visualizers.

The legacy music envelope intentionally keeps only three broad frequency bands,
which is ideal for effect reactivity but not enough to draw a real 32/64/128-bar
spectrum.  The Overlay Composer therefore owns a separate, cached analysis
contract: log-spaced spectral bands for spectrum/circular views plus a compact
signed waveform stream for waveform rendering.

Analysis is chunk-vectorized to keep memory bounded on long tracks.  Final
renderers may sample/interpolate this deterministic envelope at any output FPS;
there is no reason to recompute FFTs at 120 fps or 12K output resolution.
"""

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import threading
from typing import Callable, Literal

import numpy as np

from .music_envelope import SAMPLE_RATE, decode_audio
from .paths import PATHS


ANALYZER_VERSION = "preview-composer-audio-v1"
DEFAULT_ANALYSIS_FPS = 30.0
DEFAULT_BANDS = 64
DEFAULT_WAVEFORM_RATE = 960.0
MIN_FREQUENCY = 35.0
MAX_FREQUENCY = 16_000.0

VisualizerSignalKind = Literal["waveform", "spectrum", "circular"]


@dataclass(frozen=True)
class ComposerAudioFrame:
    rms: float
    onset: float
    band_energy: float
    values: tuple[float, ...]


@dataclass(frozen=True)
class VisualizerAudioEnvelope:
    spectrum: np.ndarray
    rms: np.ndarray
    onset: np.ndarray
    frequencies: np.ndarray
    waveform: np.ndarray
    fps: float
    waveform_rate: float
    duration: float
    source_key: str

    def __post_init__(self) -> None:
        if self.spectrum.ndim != 2 or self.spectrum.shape[0] < 1 or self.spectrum.shape[1] < 8:
            raise ValueError("visualizer spectrum must be frames x >=8 bands")
        if self.rms.shape != (self.spectrum.shape[0],) or self.onset.shape != self.rms.shape:
            raise ValueError("visualizer scalar envelopes must match spectrum frames")
        if self.frequencies.shape != (self.spectrum.shape[1],):
            raise ValueError("visualizer frequency centers must match spectrum bands")
        if self.waveform.ndim != 1 or len(self.waveform) < 1:
            raise ValueError("visualizer waveform must be a non-empty vector")
        if self.fps <= 0 or self.waveform_rate <= 0 or self.duration <= 0:
            raise ValueError("visualizer timing values must be positive")

    @property
    def bands(self) -> int:
        return int(self.spectrum.shape[1])

    @property
    def frame_count(self) -> int:
        return int(self.spectrum.shape[0])


def _clamp_time(value: float, duration: float) -> float:
    return max(0.0, min(max(0.0, float(duration) - 1e-9), float(value)))


def _resample_values(values: np.ndarray, count: int) -> np.ndarray:
    target = max(2, int(count))
    source = np.asarray(values, dtype=np.float32).reshape(-1)
    if len(source) == target:
        return np.clip(source, 0.0, 1.0).astype(np.float32, copy=True)
    if len(source) == 1:
        return np.full(target, np.clip(source[0], 0.0, 1.0), dtype=np.float32)
    source_x = np.linspace(0.0, 1.0, len(source), dtype=np.float64)
    target_x = np.linspace(0.0, 1.0, target, dtype=np.float64)
    return np.clip(np.interp(target_x, source_x, source), 0.0, 1.0).astype(np.float32)


def _smoothed_spectrum(envelope: VisualizerAudioEnvelope, frame: int, smoothing: float) -> np.ndarray:
    """Causal bounded smoothing suitable for both random preview and final render."""
    memory = max(0.0, min(0.94, float(smoothing) * 0.94))
    if memory <= 1e-6 or frame <= 0:
        return envelope.spectrum[frame].astype(np.float32, copy=True)
    # Stop when the oldest contribution is below ~0.1%, capped for corrupted
    # settings.  This makes random seeks deterministic without scanning a track.
    depth = min(frame + 1, 48)
    weights = np.asarray([memory ** age for age in range(depth)], dtype=np.float64)
    rows = envelope.spectrum[frame - np.arange(depth)]
    result = np.average(rows, axis=0, weights=weights)
    return np.clip(result, 0.0, 1.0).astype(np.float32)


def _waveform_window(envelope: VisualizerAudioEnvelope, time_seconds: float, count: int) -> np.ndarray:
    """Return a centered signed waveform slice mapped to geometry-friendly 0..1."""
    target = max(8, int(count))
    center = int(round(_clamp_time(time_seconds, envelope.duration) * envelope.waveform_rate))
    # Roughly 100 ms gives a readable oscilloscope-like shape while retaining
    # transients.  Interpolation makes the requested point count independent of
    # the cached waveform rate.
    source_count = max(target, int(round(envelope.waveform_rate * 0.10)))
    half = source_count // 2
    indexes = np.arange(center - half, center - half + source_count, dtype=np.int64)
    indexes = np.clip(indexes, 0, len(envelope.waveform) - 1)
    signed = envelope.waveform[indexes].astype(np.float32)
    source_x = np.linspace(0.0, 1.0, len(signed), dtype=np.float64)
    target_x = np.linspace(0.0, 1.0, target, dtype=np.float64)
    values = np.interp(target_x, source_x, signed)
    return np.clip(0.5 + values * 0.5, 0.0, 1.0).astype(np.float32)


def frame_audio(
    envelope: VisualizerAudioEnvelope,
    *,
    time_seconds: float,
    kind: VisualizerSignalKind,
    bars: int = DEFAULT_BANDS,
    smoothing: float = 0.65,
) -> ComposerAudioFrame:
    """Sample one deterministic visualizer frame from a cached full-track analysis."""
    time_value = _clamp_time(time_seconds, envelope.duration)
    frame = min(envelope.frame_count - 1, max(0, int(math.floor(time_value * envelope.fps))))
    if kind == "waveform":
        values = _waveform_window(envelope, time_value, bars)
    elif kind in {"spectrum", "circular"}:
        values = _resample_values(_smoothed_spectrum(envelope, frame, smoothing), bars)
    else:
        raise ValueError(f"unsupported visualizer audio kind: {kind}")
    spectrum = envelope.spectrum[frame]
    return ComposerAudioFrame(
        rms=float(np.clip(envelope.rms[frame], 0.0, 1.0)),
        onset=float(np.clip(envelope.onset[frame], 0.0, 1.0)),
        band_energy=float(np.clip(np.mean(spectrum), 0.0, 1.0)),
        values=tuple(float(value) for value in values),
    )


def _band_layout(bands: int, window_size: int) -> tuple[np.ndarray, tuple[tuple[int, int], ...]]:
    if bands < 8 or bands > 512:
        raise ValueError("visualizer analysis bands must be within 8..512")
    frequencies = np.fft.rfftfreq(window_size, 1.0 / SAMPLE_RATE)
    nyquist = float(frequencies[-1])
    high = min(MAX_FREQUENCY, nyquist * 0.98)
    low = min(MIN_FREQUENCY, high * 0.5)
    edges = np.geomspace(max(1.0, low), max(low + 1.0, high), bands + 1)
    ranges: list[tuple[int, int]] = []
    centers = np.empty(bands, dtype=np.float32)
    for index in range(bands):
        start = int(np.searchsorted(frequencies, edges[index], side="left"))
        end = int(np.searchsorted(frequencies, edges[index + 1], side="left"))
        start = min(max(1, start), len(frequencies) - 1)
        end = min(max(start + 1, end), len(frequencies))
        ranges.append((start, end))
        centers[index] = float(math.sqrt(max(edges[index], 1.0) * max(edges[index + 1], 1.0)))
    return centers, tuple(ranges)


def _compact_waveform(samples: np.ndarray, duration: float, waveform_rate: float) -> np.ndarray:
    if waveform_rate < 120 or waveform_rate > 6000:
        raise ValueError("waveform cache rate must be within 120..6000 Hz")
    count = max(1, int(math.ceil(duration * waveform_rate)))
    if len(samples) <= 1:
        return np.zeros(count, dtype=np.float32)
    source_x = np.arange(len(samples), dtype=np.float64)
    target_x = np.arange(count, dtype=np.float64) * SAMPLE_RATE / waveform_rate
    target_x = np.clip(target_x, 0.0, len(samples) - 1.0)
    result = np.interp(target_x, source_x, samples).astype(np.float32)
    peak = max(float(np.percentile(np.abs(result), 99.5)), 1e-5)
    return np.clip(result / peak, -1.0, 1.0).astype(np.float32)


def analyze_visualizer_samples(
    samples: np.ndarray,
    duration: float,
    *,
    fps: float = DEFAULT_ANALYSIS_FPS,
    bands: int = DEFAULT_BANDS,
    waveform_rate: float = DEFAULT_WAVEFORM_RATE,
    chunk_frames: int = 384,
    source_key: str = "memory",
) -> VisualizerAudioEnvelope:
    """Analyze mono float audio with bounded chunk-vectorized FFT work."""
    if duration <= 0 or fps <= 0:
        raise ValueError("visualizer audio duration/fps must be positive")
    mono = np.asarray(samples, dtype=np.float32).reshape(-1)
    if len(mono) < 1:
        mono = np.zeros(1, dtype=np.float32)
    frame_count = max(1, int(math.ceil(duration * fps)))
    window_size = 4096
    half = window_size // 2
    window = np.hanning(window_size).astype(np.float32)
    centers_hz, ranges = _band_layout(int(bands), window_size)
    spectral = np.zeros((frame_count, int(bands)), dtype=np.float32)
    rms = np.zeros(frame_count, dtype=np.float32)

    # half-window zero pads both ends.  A frame centered on original sample C
    # starts at padded index C, so no negative gather indexes are required.
    padded = np.pad(mono, (half, half + 2), mode="constant")
    sample_centers = np.floor(np.arange(frame_count, dtype=np.float64) * SAMPLE_RATE / fps).astype(np.int64)
    sample_centers = np.clip(sample_centers, 0, max(0, len(mono) - 1))
    offsets = np.arange(window_size, dtype=np.int64)
    step = max(16, min(2048, int(chunk_frames)))

    for first in range(0, frame_count, step):
        last = min(frame_count, first + step)
        starts = sample_centers[first:last]
        indexes = starts[:, None] + offsets[None, :]
        frames = padded[indexes]
        rms[first:last] = np.sqrt(np.mean(frames * frames, axis=1)).astype(np.float32)
        magnitudes = np.abs(np.fft.rfft(frames * window[None, :], axis=1))
        for band, (start, end) in enumerate(ranges):
            spectral[first:last, band] = np.mean(magnitudes[:, start:end], axis=1).astype(np.float32)

    spectral = np.log1p(spectral).astype(np.float32)
    peaks = np.percentile(spectral, 97.0, axis=0).astype(np.float32)
    peaks[peaks < 1e-6] = 1.0
    normalized = np.clip(spectral / peaks[None, :], 0.0, 1.0).astype(np.float32)

    rms_peak = max(float(np.percentile(rms, 97.0)), 1e-6)
    rms = np.clip(rms / rms_peak, 0.0, 1.0).astype(np.float32)

    # Positive spectral flux catches transients across the full visualizer range
    # instead of tying onset detection exclusively to bass.
    previous = np.vstack((normalized[0:1], normalized[:-1]))
    flux = np.mean(np.maximum(0.0, normalized - previous), axis=1)
    loudness_delta = np.maximum(0.0, rms - np.r_[rms[0], rms[:-1]])
    onset = flux * 0.78 + loudness_delta * 0.35
    onset_peak = max(float(np.percentile(onset, 98.0)), 1e-6)
    onset = np.clip(onset / onset_peak, 0.0, 1.0).astype(np.float32)

    waveform = _compact_waveform(mono, duration, float(waveform_rate))
    return VisualizerAudioEnvelope(
        spectrum=normalized,
        rms=rms,
        onset=onset,
        frequencies=centers_hz,
        waveform=waveform,
        fps=float(fps),
        waveform_rate=float(waveform_rate),
        duration=float(duration),
        source_key=str(source_key),
    )


def _source_key(media_path: str, duration: float, fps: float, bands: int, waveform_rate: float) -> str:
    path = Path(media_path).expanduser()
    metadata: dict[str, object] = {
        "path": str(path),
        "duration": round(float(duration), 6),
        "fps": round(float(fps), 6),
        "bands": int(bands),
        "waveform_rate": round(float(waveform_rate), 3),
        "version": ANALYZER_VERSION,
    }
    try:
        stat = path.stat()
        metadata.update(path=str(path.resolve()), size=stat.st_size, mtime_ns=stat.st_mtime_ns)
    except OSError:
        pass
    raw = json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(raw.encode("utf-8")).hexdigest()[:24]


_cache_lock = threading.Lock()
_memory_cache: dict[str, VisualizerAudioEnvelope] = {}


def load_visualizer_envelope(
    ffmpeg: str,
    media_path: str,
    duration: float,
    *,
    analysis_fps: float = DEFAULT_ANALYSIS_FPS,
    bands: int = DEFAULT_BANDS,
    waveform_rate: float = DEFAULT_WAVEFORM_RATE,
    cache_dir: Path | None = None,
    log: Callable[[str], None] | None = None,
) -> VisualizerAudioEnvelope:
    """Load or build one full-track high-detail visualizer envelope."""
    if duration <= 0:
        raise ValueError("visualizer envelope duration must be positive")
    key = _source_key(media_path, duration, analysis_fps, bands, waveform_rate)
    with _cache_lock:
        cached = _memory_cache.get(key)
    if cached is not None:
        if log:
            log(f"Visualizer: cache RAM {key}.")
        return cached

    directory = cache_dir or (PATHS.cache / "composer-audio")
    cache_path = directory / f"{key}.npz"
    try:
        if cache_path.is_file():
            with np.load(cache_path, allow_pickle=False) as payload:
                envelope = VisualizerAudioEnvelope(
                    spectrum=payload["spectrum"].astype(np.float32),
                    rms=payload["rms"].astype(np.float32),
                    onset=payload["onset"].astype(np.float32),
                    frequencies=payload["frequencies"].astype(np.float32),
                    waveform=payload["waveform"].astype(np.float32),
                    fps=float(payload["fps"]),
                    waveform_rate=float(payload["waveform_rate"]),
                    duration=float(payload["duration"]),
                    source_key=key,
                )
            with _cache_lock:
                _memory_cache[key] = envelope
            if log:
                log(f"Visualizer: cache SSD {key}.")
            return envelope
    except (OSError, ValueError, KeyError):
        try:
            cache_path.unlink(missing_ok=True)
        except OSError:
            pass

    if log:
        log(f"Visualizer: analisando {bands} bandas a {analysis_fps:g} fps ({duration:.2f}s).")
    samples = decode_audio(ffmpeg, media_path, duration)
    envelope = analyze_visualizer_samples(
        samples,
        duration,
        fps=analysis_fps,
        bands=bands,
        waveform_rate=waveform_rate,
        source_key=key,
    )
    try:
        directory.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(".tmp.npz")
        np.savez_compressed(
            temporary,
            spectrum=envelope.spectrum.astype(np.float16),
            rms=envelope.rms.astype(np.float16),
            onset=envelope.onset.astype(np.float16),
            frequencies=envelope.frequencies,
            waveform=envelope.waveform.astype(np.float16),
            fps=np.asarray(envelope.fps, dtype=np.float64),
            waveform_rate=np.asarray(envelope.waveform_rate, dtype=np.float64),
            duration=np.asarray(envelope.duration, dtype=np.float64),
        )
        os.replace(temporary, cache_path)
    except OSError:
        pass
    with _cache_lock:
        _memory_cache[key] = envelope
    return envelope


def clear_visualizer_memory_cache() -> None:
    with _cache_lock:
        _memory_cache.clear()
