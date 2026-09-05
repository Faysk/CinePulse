"""Preview-only temporal reconstruction for detected overlay regions.

Burned-in overlays occupy the same screen coordinates in every frame, so raw
neighbor patches are not valid donors: they contain the same text/QR/logo. This
backend instead estimates the hidden patch from the visible boundary around the
region for the target and context-compatible nearby frames, then uses a temporal
median to stabilize that estimate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .restoration_overlay import OverlayRegion


@dataclass(frozen=True)
class TemporalReconstructionPolicy:
    radius: int = 4
    minimum_donors: int = 2
    context_padding: int = 6
    max_context_mae: float = 28.0
    feather_pixels: int = 4

    def __post_init__(self) -> None:
        if self.radius <= 0:
            raise ValueError("radius must be positive")
        if self.minimum_donors <= 0:
            raise ValueError("minimum_donors must be positive")
        if self.context_padding < 1:
            raise ValueError("context_padding must be positive")
        if self.max_context_mae <= 0:
            raise ValueError("max_context_mae must be positive")
        if self.feather_pixels < 0:
            raise ValueError("feather_pixels cannot be negative")


@dataclass(frozen=True)
class ReconstructionResult:
    frame: np.ndarray
    applied: bool
    donor_indices: tuple[int, ...]
    context_mae: tuple[float, ...]

    @property
    def confidence(self) -> float:
        if not self.applied or not self.context_mae:
            return 0.0
        mean_mae = float(np.mean(self.context_mae))
        return max(0.0, min(1.0, 1.0 - mean_mae / 64.0))


def _as_rgb(frame: np.ndarray) -> np.ndarray:
    array = np.asarray(frame)
    if array.ndim != 3 or array.shape[2] != 3:
        raise ValueError("temporal reconstruction expects RGB frames shaped HxWx3")
    if not np.issubdtype(array.dtype, np.number):
        raise TypeError("temporal reconstruction frames must contain numeric values")
    return array


def _context_mask(
    height: int,
    width: int,
    box: tuple[int, int, int, int],
    padding: int,
) -> tuple[slice, slice, np.ndarray]:
    x, y, region_width, region_height = box
    left = max(0, x - padding)
    top = max(0, y - padding)
    right = min(width, x + region_width + padding)
    bottom = min(height, y + region_height + padding)
    mask = np.ones((bottom - top, right - left), dtype=bool)
    inner_left = x - left
    inner_top = y - top
    mask[
        inner_top : inner_top + region_height,
        inner_left : inner_left + region_width,
    ] = False
    return slice(top, bottom), slice(left, right), mask


def _context_mae(
    target: np.ndarray,
    donor: np.ndarray,
    row_slice: slice,
    column_slice: slice,
    context_mask: np.ndarray,
) -> float:
    target_context = target[row_slice, column_slice].astype(np.float32, copy=False)
    donor_context = donor[row_slice, column_slice].astype(np.float32, copy=False)
    if not np.any(context_mask):
        return float("inf")
    difference = np.abs(target_context - donor_context)
    return float(np.mean(difference[context_mask]))


def _feather_mask(height: int, width: int, pixels: int) -> np.ndarray:
    if pixels <= 0:
        return np.ones((height, width), dtype=np.float32)
    y_distance = np.minimum(np.arange(height), np.arange(height)[::-1]).astype(np.float32)
    x_distance = np.minimum(np.arange(width), np.arange(width)[::-1]).astype(np.float32)
    distance = np.minimum(y_distance[:, None], x_distance[None, :])
    return np.clip((distance + 1.0) / (pixels + 1.0), 0.0, 1.0)


def _boundary_guided_patch(frame: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray | None:
    """Estimate a hidden rectangular patch from pixels immediately around it.

    Horizontal and vertical interpolants are averaged when both are available.
    This deliberately favors smooth, conservative reconstruction over invented
    high-frequency detail. Complex regions can later be upgraded by an optional
    neural inpainting backend without changing the Preview orchestration contract.
    """

    x, y, region_width, region_height = box
    frame_height, frame_width, _ = frame.shape
    estimates: list[np.ndarray] = []

    if x > 0 and x + region_width < frame_width:
        left = frame[y : y + region_height, x - 1].astype(np.float32)
        right = frame[y : y + region_height, x + region_width].astype(np.float32)
        weights = ((np.arange(region_width, dtype=np.float32) + 1.0) / (region_width + 1.0))[None, :, None]
        horizontal = left[:, None, :] * (1.0 - weights) + right[:, None, :] * weights
        estimates.append(horizontal)

    if y > 0 and y + region_height < frame_height:
        top = frame[y - 1, x : x + region_width].astype(np.float32)
        bottom = frame[y + region_height, x : x + region_width].astype(np.float32)
        weights = ((np.arange(region_height, dtype=np.float32) + 1.0) / (region_height + 1.0))[:, None, None]
        vertical = top[None, :, :] * (1.0 - weights) + bottom[None, :, :] * weights
        estimates.append(vertical)

    if not estimates:
        return None
    return np.mean(np.stack(estimates), axis=0)


def reconstruct_region_temporally(
    frames: Sequence[np.ndarray],
    *,
    target_index: int,
    region: OverlayRegion,
    policy: TemporalReconstructionPolicy = TemporalReconstructionPolicy(),
) -> ReconstructionResult:
    """Reconstruct one persistent overlay from visible boundary information.

    Neighboring frames are used only when the ring around the overlay resembles
    the target scene. Their *occluded* pixels are never copied directly. Instead
    every accepted frame contributes a boundary-guided estimate and the temporal
    median stabilizes those estimates before feathering them into the target.
    """

    if not frames:
        raise ValueError("at least one frame is required")
    if not 0 <= target_index < len(frames):
        raise IndexError("target_index is outside the frame sequence")

    arrays = [_as_rgb(frame) for frame in frames]
    shape = arrays[0].shape
    if any(frame.shape != shape for frame in arrays):
        raise ValueError("temporal reconstruction frames must share dimensions")

    target = arrays[target_index]
    height, width, _ = target.shape
    box = region.to_pixels(width, height)
    x, y, region_width, region_height = box
    row_slice, column_slice, context_mask = _context_mask(
        height,
        width,
        box,
        policy.context_padding,
    )

    first = max(0, target_index - policy.radius)
    last = min(len(arrays), target_index + policy.radius + 1)
    accepted: list[tuple[int, float, np.ndarray]] = []
    for index in range(first, last):
        if index == target_index:
            continue
        donor = arrays[index]
        mae = _context_mae(target, donor, row_slice, column_slice, context_mask)
        if mae <= policy.max_context_mae:
            estimate = _boundary_guided_patch(donor, box)
            if estimate is not None:
                accepted.append((index, mae, estimate))

    accepted.sort(key=lambda item: item[1])
    if len(accepted) < policy.minimum_donors:
        return ReconstructionResult(
            frame=target.copy(),
            applied=False,
            donor_indices=tuple(item[0] for item in accepted),
            context_mae=tuple(item[1] for item in accepted),
        )

    target_estimate = _boundary_guided_patch(target, box)
    if target_estimate is None:
        return ReconstructionResult(
            frame=target.copy(),
            applied=False,
            donor_indices=tuple(item[0] for item in accepted),
            context_mae=tuple(item[1] for item in accepted),
        )

    estimates = [target_estimate, *[item[2] for item in accepted]]
    replacement = np.median(np.stack(estimates), axis=0)
    original_patch = target[y : y + region_height, x : x + region_width].astype(np.float32, copy=False)
    alpha = _feather_mask(region_height, region_width, policy.feather_pixels)[..., None]
    blended = original_patch * (1.0 - alpha) + replacement * alpha

    output = target.copy()
    if np.issubdtype(output.dtype, np.integer):
        limits = np.iinfo(output.dtype)
        blended = np.clip(np.rint(blended), limits.min, limits.max)
    output[y : y + region_height, x : x + region_width] = blended.astype(output.dtype, copy=False)
    return ReconstructionResult(
        frame=output,
        applied=True,
        donor_indices=tuple(item[0] for item in accepted),
        context_mae=tuple(item[1] for item in accepted),
    )
