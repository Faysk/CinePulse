from pathlib import Path

import numpy as np

from cinepulse.restoration_detector import (
    OverlaySamplingPolicy,
    build_sampling_filter,
    decode_rgb_samples,
    detect_overlay_evidence,
)


def _synthetic_overlay_frames(*, frames=8, width=80, height=48):
    sequence = []
    for index in range(frames):
        # The source changes strongly over time but remains spatially smooth.
        value = 25 + index * 24
        frame = np.full((height, width, 3), value, dtype=np.uint8)
        frame[:, :, 1] = np.uint8(min(255, value + 10))

        # Static, edge-rich subtitle-like overlay anchored near the top-left.
        for y in range(8, 16):
            for x in range(8, 40):
                pixel = 245 if (x // 2 + y // 2) % 2 else 8
                frame[y, x] = pixel
        sequence.append(frame)
    return sequence


def test_sampling_filter_is_sparse_scaled_rgb():
    policy = OverlaySamplingPolicy(sample_width=160, sample_height=90, sample_interval_seconds=2.5)
    assert build_sampling_filter(policy) == "fps=0.40000000,scale=160:90:flags=area,format=rgb24"


def test_detector_finds_static_edge_rich_overlay_in_moving_source():
    policy = OverlaySamplingPolicy(
        sample_width=80,
        sample_height=48,
        grid_columns=10,
        grid_rows=6,
        edge_threshold=18.0,
        stable_delta=8.0,
        minimum_cell_score=0.50,
        minimum_frames=4,
    )
    evidence = detect_overlay_evidence(_synthetic_overlay_frames(), policy=policy)
    assert evidence
    strongest = evidence[0]
    assert strongest.region.x <= 0.2
    assert strongest.region.y <= 0.34
    assert strongest.region.area <= 0.20
    assert strongest.temporal_stability > 0.8
    assert strongest.edge_density > 0.20
    assert strongest.text_confidence >= strongest.qr_confidence


def test_detector_does_not_promote_uniform_static_region_without_edges():
    frames = [np.full((48, 80, 3), 120, dtype=np.uint8) for _ in range(6)]
    policy = OverlaySamplingPolicy(sample_width=80, sample_height=48, grid_columns=10, grid_rows=6)
    assert detect_overlay_evidence(frames, policy=policy) == ()


def test_detector_returns_empty_when_temporal_sample_is_too_short():
    frames = _synthetic_overlay_frames(frames=3)
    policy = OverlaySamplingPolicy(sample_width=80, sample_height=48, minimum_frames=4)
    assert detect_overlay_evidence(frames, policy=policy) == ()


def test_decode_rgb_samples_rejects_truncated_rawvideo(monkeypatch):
    class Result:
        returncode = 0
        stdout = b"not-a-complete-frame"
        stderr = b""

    monkeypatch.setattr("cinepulse.restoration_detector.subprocess.run", lambda *args, **kwargs: Result())
    policy = OverlaySamplingPolicy(sample_width=8, sample_height=8, max_samples=2)
    try:
        decode_rgb_samples("ffmpeg", Path("source.mp4"), policy=policy)
    except RuntimeError as exc:
        assert "truncated" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
