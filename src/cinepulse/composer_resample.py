from __future__ import annotations

"""Quality-first deterministic RGBA transforms for the Preview CPU reference."""

import math
import numpy as np


def resize_bilinear_rgba(source: np.ndarray, width: int, height: int) -> np.ndarray:
    value = np.asarray(source)
    if value.ndim != 3 or value.shape[2] != 4 or value.dtype != np.uint8:
        raise ValueError("bilinear resize requires uint8 HxWxRGBA")
    width = int(width)
    height = int(height)
    if width <= 0 or height <= 0:
        raise ValueError("bilinear resize dimensions must be positive")
    src_h, src_w = value.shape[:2]
    if (src_w, src_h) == (width, height):
        return value.copy()

    # Pixel-center mapping. Premultiply RGB before interpolation so transparent
    # colored pixels cannot bleed halos into visible edges.
    x = (np.arange(width, dtype=np.float64) + 0.5) * src_w / width - 0.5
    y = (np.arange(height, dtype=np.float64) + 0.5) * src_h / height - 0.5
    x = np.clip(x, 0.0, max(0.0, src_w - 1.0))
    y = np.clip(y, 0.0, max(0.0, src_h - 1.0))
    x0 = np.floor(x).astype(np.int64); x1 = np.minimum(x0 + 1, src_w - 1)
    y0 = np.floor(y).astype(np.int64); y1 = np.minimum(y0 + 1, src_h - 1)
    wx = (x - x0)[None, :, None]
    wy = (y - y0)[:, None, None]

    src = value.astype(np.float64) / 255.0
    alpha = src[..., 3:4]
    premul = np.concatenate((src[..., :3] * alpha, alpha), axis=2)
    top = premul[y0[:, None], x0[None, :]] * (1.0 - wx) + premul[y0[:, None], x1[None, :]] * wx
    bottom = premul[y1[:, None], x0[None, :]] * (1.0 - wx) + premul[y1[:, None], x1[None, :]] * wx
    out = top * (1.0 - wy) + bottom * wy
    out_a = out[..., 3:4]
    rgb = np.divide(out[..., :3], np.maximum(out_a, 1e-12), out=np.zeros_like(out[..., :3]), where=out_a > 1e-12)
    straight = np.concatenate((rgb, out_a), axis=2)
    return np.clip(np.rint(straight * 255.0), 0, 255).astype(np.uint8)


def rotate_bilinear_rgba(source: np.ndarray, degrees: float) -> np.ndarray:
    value = np.asarray(source)
    if value.ndim != 3 or value.shape[2] != 4 or value.dtype != np.uint8:
        raise ValueError("bilinear rotation requires uint8 HxWxRGBA")
    angle = float(degrees) % 360.0
    if abs(angle) < 1e-9:
        return value.copy()
    quarter = round(angle / 90.0)
    if abs(angle - quarter * 90.0) < 1e-9:
        return np.rot90(value, k=(-quarter) % 4).copy()

    height, width = value.shape[:2]
    yy, xx = np.indices((height, width), dtype=np.float64)
    cx = (width - 1) * 0.5
    cy = (height - 1) * 0.5
    radians = math.radians(-angle)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    dx = xx - cx
    dy = yy - cy
    sx = cx + dx * cosine - dy * sine
    sy = cy + dx * sine + dy * cosine

    valid = (sx >= 0.0) & (sx <= width - 1.0) & (sy >= 0.0) & (sy <= height - 1.0)
    sx_clip = np.clip(sx, 0.0, max(0.0, width - 1.0))
    sy_clip = np.clip(sy, 0.0, max(0.0, height - 1.0))
    x0 = np.floor(sx_clip).astype(np.int64); x1 = np.minimum(x0 + 1, width - 1)
    y0 = np.floor(sy_clip).astype(np.int64); y1 = np.minimum(y0 + 1, height - 1)
    wx = (sx_clip - x0)[..., None]
    wy = (sy_clip - y0)[..., None]

    src = value.astype(np.float64) / 255.0
    alpha = src[..., 3:4]
    premul = np.concatenate((src[..., :3] * alpha, alpha), axis=2)
    top = premul[y0, x0] * (1.0 - wx) + premul[y0, x1] * wx
    bottom = premul[y1, x0] * (1.0 - wx) + premul[y1, x1] * wx
    out = top * (1.0 - wy) + bottom * wy
    out[~valid] = 0.0
    out_a = out[..., 3:4]
    rgb = np.divide(out[..., :3], np.maximum(out_a, 1e-12), out=np.zeros_like(out[..., :3]), where=out_a > 1e-12)
    straight = np.concatenate((rgb, out_a), axis=2)
    return np.clip(np.rint(straight * 255.0), 0, 255).astype(np.uint8)
