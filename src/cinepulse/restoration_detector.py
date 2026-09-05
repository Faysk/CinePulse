"""Preview-only sampled-frame detector for burned-in video overlays.

The detector deliberately depends only on NumPy and FFmpeg. It turns a sparse
set of low-resolution RGB samples into backend-independent ``DetectionEvidence``
for the deterministic selection/reconstruction core in ``restoration_overlay``.
Optional OCR/QR model backends can enrich the semantic signals later without
changing this contract.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from .restoration_overlay import DetectionEvidence, OverlayRegion


@dataclass(frozen=True)
class OverlaySamplingPolicy:
    sample_width: int = 320
    sample_height: int = 180
    sample_interval_seconds: float = 2.0
    max_samples: int = 12
    grid_columns: int = 20
    grid_rows: int = 12
    edge_threshold: float = 18.0
    stable_delta: float = 8.0
    minimum_edge_persistence: float = 0.60
    minimum_cell_score: float = 0.56
    minimum_frames: int = 4

    def __post_init__(self) -> None:
        if self.sample_width <= 0 or self.sample_height <= 0:
            raise ValueError("sample dimensions must be positive")
        if self.sample_interval_seconds <= 0:
            raise ValueError("sample interval must be positive")
        if self.max_samples < 2:
            raise ValueError("max_samples must be at least 2")
        if self.grid_columns <= 0 or self.grid_rows <= 0:
            raise ValueError("grid dimensions must be positive")
        if self.edge_threshold <= 0 or self.stable_delta <= 0:
            raise ValueError("detector thresholds must be positive")
        if not 0.0 <= self.minimum_edge_persistence <= 1.0:
            raise ValueError("minimum_edge_persistence must be normalized to 0..1")
        if not 0.0 <= self.minimum_cell_score <= 1.0:
            raise ValueError("minimum_cell_score must be normalized to 0..1")
        if self.minimum_frames < 2:
            raise ValueError("minimum_frames must be at least 2")


def build_sampling_filter(policy: OverlaySamplingPolicy = OverlaySamplingPolicy()) -> str:
    """Return the bounded FFmpeg filter used by ``decode_rgb_samples``."""

    fps = 1.0 / policy.sample_interval_seconds
    return (
        f"fps={fps:.8f},"
        f"scale={policy.sample_width}:{policy.sample_height}:flags=area,"
        "format=rgb24"
    )


def decode_rgb_samples(
    ffmpeg: str,
    path: Path,
    *,
    policy: OverlaySamplingPolicy = OverlaySamplingPolicy(),
) -> list[np.ndarray]:
    """Decode sparse low-resolution RGB frames using a single FFmpeg process.

    The process is intentionally bounded by ``max_samples`` so detector memory
    and runtime do not grow with source duration. Later orchestration may pass
    scene-aware samples into ``detect_overlay_evidence`` directly.
    """

    command = [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-vf",
        build_sampling_filter(policy),
        "-frames:v",
        str(policy.max_samples),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "pipe:1",
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        message = (result.stderr or b"ffmpeg overlay sampling failed").decode("utf-8", errors="replace").strip()
        raise RuntimeError(message)

    frame_bytes = policy.sample_width * policy.sample_height * 3
    if len(result.stdout) % frame_bytes:
        raise RuntimeError("overlay sample rawvideo ended truncated")

    frames: list[np.ndarray] = []
    for offset in range(0, len(result.stdout), frame_bytes):
        chunk = result.stdout[offset : offset + frame_bytes]
        frames.append(
            np.frombuffer(chunk, dtype=np.uint8)
            .reshape(policy.sample_height, policy.sample_width, 3)
            .copy()
        )
    return frames


def _as_rgb_sequence(frames: Sequence[np.ndarray]) -> np.ndarray:
    if not frames:
        raise ValueError("at least one frame is required")
    arrays = [np.asarray(frame) for frame in frames]
    shape = arrays[0].shape
    if len(shape) != 3 or shape[2] != 3:
        raise ValueError("overlay detector expects RGB frames shaped HxWx3")
    if any(array.shape != shape for array in arrays):
        raise ValueError("overlay detector frames must share dimensions")
    if any(not np.issubdtype(array.dtype, np.number) for array in arrays):
        raise TypeError("overlay detector frames must contain numeric values")
    return np.stack(arrays).astype(np.float32, copy=False)


def _luma(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def _edge_strength(luma: np.ndarray) -> np.ndarray:
    horizontal = np.zeros_like(luma, dtype=np.float32)
    vertical = np.zeros_like(luma, dtype=np.float32)
    horizontal[..., :, 1:] = np.abs(luma[..., :, 1:] - luma[..., :, :-1])
    vertical[..., 1:, :] = np.abs(luma[..., 1:, :] - luma[..., :-1, :])
    return np.maximum(horizontal, vertical)


def _connected_cells(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    rows, columns = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    components: list[list[tuple[int, int]]] = []
    for row in range(rows):
        for column in range(columns):
            if not mask[row, column] or visited[row, column]:
                continue
            stack = [(row, column)]
            visited[row, column] = True
            component: list[tuple[int, int]] = []
            while stack:
                current_row, current_column = stack.pop()
                component.append((current_row, current_column))
                for delta_row, delta_column in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    next_row = current_row + delta_row
                    next_column = current_column + delta_column
                    if not 0 <= next_row < rows or not 0 <= next_column < columns:
                        continue
                    if visited[next_row, next_column] or not mask[next_row, next_column]:
                        continue
                    visited[next_row, next_column] = True
                    stack.append((next_row, next_column))
            components.append(component)
    return components


def _semantic_hints(width: float, height: float, edge_density: float) -> tuple[float, float]:
    aspect = width / max(height, 1e-9)
    text_shape = min(1.0, max(0.0, (aspect - 1.2) / 2.8))
    text_confidence = min(1.0, edge_density * 0.65 + text_shape * 0.35)

    square_likeness = 1.0 - min(1.0, abs(width - height) / max(width, height, 1e-9))
    qr_confidence = min(1.0, edge_density * 0.62 + square_likeness * 0.38)
    if aspect > 1.8 or aspect < 0.55:
        qr_confidence *= 0.45
    return text_confidence, qr_confidence


def detect_overlay_evidence(
    frames: Sequence[np.ndarray],
    *,
    policy: OverlaySamplingPolicy = OverlaySamplingPolicy(),
) -> tuple[DetectionEvidence, ...]:
    """Detect temporally anchored, edge-rich regions from sampled RGB frames.

    A burned-in overlay tends to keep the same high-frequency structure at the
    same coordinates while the underlying source changes. We therefore measure
    per-pixel edge persistence plus distance from the temporal median, aggregate
    those signals over a coarse grid, and merge adjacent suspicious cells.
    """

    rgb = _as_rgb_sequence(frames)
    if rgb.shape[0] < policy.minimum_frames:
        return ()

    luma = _luma(rgb)
    median = np.median(luma, axis=0)
    deviation = np.abs(luma - median)
    stable = deviation <= policy.stable_delta
    temporal_stability_map = np.mean(stable, axis=0)

    edge = _edge_strength(luma) >= policy.edge_threshold
    edge_persistence_map = np.mean(edge, axis=0)
    persistent_edge = edge_persistence_map >= policy.minimum_edge_persistence

    height, width = median.shape
    row_edges = np.linspace(0, height, policy.grid_rows + 1, dtype=int)
    column_edges = np.linspace(0, width, policy.grid_columns + 1, dtype=int)
    cell_score = np.zeros((policy.grid_rows, policy.grid_columns), dtype=np.float32)
    cell_edge = np.zeros_like(cell_score)
    cell_stability = np.zeros_like(cell_score)

    for row in range(policy.grid_rows):
        y1, y2 = row_edges[row], row_edges[row + 1]
        for column in range(policy.grid_columns):
            x1, x2 = column_edges[column], column_edges[column + 1]
            if y2 <= y1 or x2 <= x1:
                continue
            tile_edges = persistent_edge[y1:y2, x1:x2]
            edge_density = float(np.mean(tile_edges))
            edge_persistence = float(np.mean(edge_persistence_map[y1:y2, x1:x2]))
            stability = float(np.mean(temporal_stability_map[y1:y2, x1:x2]))
            # Edge persistence is deliberately dominant. Uniform/static source
            # regions may be stable, but do not become candidates without a
            # repeatable high-frequency structure.
            score = edge_persistence * 0.58 + stability * 0.27 + edge_density * 0.15
            cell_score[row, column] = score
            cell_edge[row, column] = edge_density
            cell_stability[row, column] = stability

    suspicious = cell_score >= policy.minimum_cell_score
    evidence: list[DetectionEvidence] = []
    for component in _connected_cells(suspicious):
        rows = [item[0] for item in component]
        columns = [item[1] for item in component]
        first_row, last_row = min(rows), max(rows)
        first_column, last_column = min(columns), max(columns)
        x1, x2 = column_edges[first_column], column_edges[last_column + 1]
        y1, y2 = row_edges[first_row], row_edges[last_row + 1]

        region_width = (x2 - x1) / width
        region_height = (y2 - y1) / height
        if region_width * region_height > 0.20:
            continue

        indices = tuple(zip(rows, columns, strict=True))
        persistence = float(np.mean([cell_score[row, column] for row, column in indices]))
        edge_density = float(np.mean([cell_edge[row, column] for row, column in indices]))
        stability = float(np.mean([cell_stability[row, column] for row, column in indices]))
        text_confidence, qr_confidence = _semantic_hints(region_width, region_height, edge_density)
        evidence.append(
            DetectionEvidence(
                region=OverlayRegion(
                    x=x1 / width,
                    y=y1 / height,
                    width=region_width,
                    height=region_height,
                ),
                persistence=max(0.0, min(1.0, persistence)),
                edge_density=max(0.0, min(1.0, edge_density)),
                temporal_stability=max(0.0, min(1.0, stability)),
                text_confidence=text_confidence,
                qr_confidence=qr_confidence,
            )
        )

    evidence.sort(key=lambda item: item.score, reverse=True)
    return tuple(evidence)


def inspect_video_for_overlays(
    ffmpeg: str,
    path: Path,
    *,
    policy: OverlaySamplingPolicy = OverlaySamplingPolicy(),
) -> tuple[DetectionEvidence, ...]:
    """Sample a source video and return Preview overlay evidence."""

    return detect_overlay_evidence(decode_rgb_samples(ffmpeg, path, policy=policy), policy=policy)
