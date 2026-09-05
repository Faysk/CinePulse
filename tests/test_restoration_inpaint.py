import numpy as np

from cinepulse.restoration_inpaint import (
    TemporalReconstructionPolicy,
    reconstruct_region_temporally,
)
from cinepulse.restoration_overlay import OverlayRegion


def _scene(value=60):
    frame = np.full((40, 60, 3), value, dtype=np.uint8)
    frame[:, :, 1] = value + 5
    frame[12:28, 20:40] = (90, 100, 110)
    return frame


def test_temporal_reconstruction_replaces_overlay_from_compatible_neighbors():
    frames = [_scene() for _ in range(5)]
    frames[2] = frames[2].copy()
    frames[2][12:28, 20:40] = (250, 250, 250)
    region = OverlayRegion(20 / 60, 12 / 40, 20 / 60, 16 / 40, kind="text", confidence=0.9)
    policy = TemporalReconstructionPolicy(radius=2, minimum_donors=2, context_padding=4, feather_pixels=0)

    result = reconstruct_region_temporally(frames, target_index=2, region=region, policy=policy)

    assert result.applied
    assert len(result.donor_indices) == 4
    assert np.array_equal(result.frame[20, 30], np.array([90, 100, 110], dtype=np.uint8))
    assert result.confidence > 0.9


def test_temporal_reconstruction_rejects_neighbor_from_different_scene():
    frames = [_scene() for _ in range(5)]
    frames[0] = _scene(180)
    frames[2] = frames[2].copy()
    frames[2][12:28, 20:40] = 250
    region = OverlayRegion(20 / 60, 12 / 40, 20 / 60, 16 / 40)
    policy = TemporalReconstructionPolicy(
        radius=2,
        minimum_donors=2,
        context_padding=4,
        max_context_mae=20.0,
        feather_pixels=0,
    )

    result = reconstruct_region_temporally(frames, target_index=2, region=region, policy=policy)

    assert result.applied
    assert 0 not in result.donor_indices
    assert set(result.donor_indices) == {1, 3, 4}


def test_temporal_reconstruction_falls_back_without_enough_safe_donors():
    target = _scene()
    target[12:28, 20:40] = 250
    frames = [_scene(180), target, _scene(210)]
    region = OverlayRegion(20 / 60, 12 / 40, 20 / 60, 16 / 40)
    policy = TemporalReconstructionPolicy(
        radius=1,
        minimum_donors=2,
        context_padding=4,
        max_context_mae=10.0,
        feather_pixels=0,
    )

    result = reconstruct_region_temporally(frames, target_index=1, region=region, policy=policy)

    assert not result.applied
    assert result.donor_indices == ()
    assert np.array_equal(result.frame, target)


def test_temporal_reconstruction_preserves_dtype_and_frame_shape():
    frames = [_scene() for _ in range(3)]
    frames[1] = frames[1].copy()
    frames[1][12:28, 20:40] = 250
    region = OverlayRegion(20 / 60, 12 / 40, 20 / 60, 16 / 40)
    policy = TemporalReconstructionPolicy(radius=1, minimum_donors=2, feather_pixels=3)

    result = reconstruct_region_temporally(frames, target_index=1, region=region, policy=policy)

    assert result.applied
    assert result.frame.dtype == np.uint8
    assert result.frame.shape == frames[1].shape
