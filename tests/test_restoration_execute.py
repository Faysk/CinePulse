from __future__ import annotations

import numpy as np

from cinepulse.restoration_execute import apply_temporal_reconstruction, build_preview_ffmpeg_command
from cinepulse.restoration_overlay import OverlayRegion
from cinepulse.restoration_preview import PreviewRestorationPlan


def _plan(region: OverlayRegion | None = None) -> PreviewRestorationPlan:
    regions = (region,) if region is not None else ()
    return PreviewRestorationPlan(
        evidence=(),
        regions=regions,
        overlay_filter="delogo=x=1:y=1:w=2:h=2" if region is not None else "",
        color_filter="eq=contrast=1.05" if region is None else "",
    )


def test_ffmpeg_command_uses_preview_filter_and_optional_audio_mapping(tmp_path) -> None:
    command = build_preview_ffmpeg_command(
        "ffmpeg",
        tmp_path / "input.mp4",
        tmp_path / "output.mp4",
        _plan(),
    )

    assert command[0] == "ffmpeg"
    assert "-vf" in command
    assert "eq=contrast=1.05" in command
    assert "0:a?" in command
    assert command[-1].endswith("output.mp4")


def test_ffmpeg_command_rejects_invalid_crf(tmp_path) -> None:
    try:
        build_preview_ffmpeg_command("ffmpeg", tmp_path / "in.mp4", tmp_path / "out.mp4", _plan(), crf=99)
    except ValueError:
        return
    raise AssertionError("invalid CRF should be rejected")


def test_temporal_execution_reconstructs_compatible_overlay() -> None:
    frames = []
    for index in range(5):
        frame = np.full((12, 12, 3), 40 + index, dtype=np.uint8)
        frame[4:8, 4:8] = 220
        frames.append(frame)
    # Donors expose the hidden source while the target contains the overlay.
    frames[1][4:8, 4:8] = 50
    frames[3][4:8, 4:8] = 52
    region = OverlayRegion(x=4 / 12, y=4 / 12, width=4 / 12, height=4 / 12)

    report = apply_temporal_reconstruction(frames, _plan(region))

    assert report.attempted_regions == 5
    assert report.applied_regions >= 1
    assert report.used_temporal_reconstruction
    assert 0.0 < report.mean_confidence <= 1.0


def test_temporal_execution_preserves_shape_and_reports_fallback() -> None:
    frames = [np.zeros((8, 8, 3), dtype=np.uint8) for _ in range(2)]
    region = OverlayRegion(x=0.25, y=0.25, width=0.25, height=0.25)

    report = apply_temporal_reconstruction(frames, _plan(region))

    assert report.applied_regions == 0
    assert report.fallback_regions == report.attempted_regions
    assert all(frame.shape == (8, 8, 3) for frame in report.frames)
