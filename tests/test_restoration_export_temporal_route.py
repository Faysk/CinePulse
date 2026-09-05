from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cinepulse.restoration_export import export_preview_restoration
from cinepulse.restoration_overlay import OverlayRegion
from cinepulse.restoration_preview import PreviewRestorationPlan
from cinepulse.restoration_temporal_export import TemporalStreamReport


OVERLAY_PLAN = PreviewRestorationPlan(
    evidence=(),
    regions=(OverlayRegion(0.1, 0.1, 0.2, 0.2, kind="text", confidence=0.9),),
    overlay_filter="delogo=x=10:y=10:w=20:h=20",
    color_filter="",
)


class TemporalRoutingTests(unittest.TestCase):
    def test_overlay_export_refuses_silent_spatial_fallback_without_ffprobe(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.mp4"
            output = root / "output.mp4"
            source.write_bytes(b"source")
            with patch("cinepulse.restoration_export.ensure_preview_scratch_capacity", return_value=0):
                with self.assertRaises(ValueError):
                    export_preview_restoration("ffmpeg", source, output, OVERLAY_PLAN)

    def test_overlay_export_routes_to_temporal_backend_and_promotes_atomically(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.mp4"
            output = root / "output.mp4"
            source.write_bytes(b"source")

            def fake_temporal(_ffmpeg, _ffprobe, _source, temporary, _plan, **_kwargs):
                temporary.write_bytes(b"temporal-video")
                return TemporalStreamReport(frames_written=12, applied_regions=10, fallback_regions=2)

            with patch("cinepulse.restoration_export.ensure_preview_scratch_capacity", return_value=0), patch(
                "cinepulse.restoration_export.stream_temporal_preview", side_effect=fake_temporal
            ) as temporal:
                result = export_preview_restoration(
                    "ffmpeg",
                    source,
                    output,
                    OVERLAY_PLAN,
                    ffprobe="ffprobe",
                )

            temporal.assert_called_once()
            self.assertTrue(result.used_temporal_reconstruction)
            self.assertEqual(result.temporal_frames, 12)
            self.assertEqual(result.temporal_regions_applied, 10)
            self.assertEqual(result.temporal_regions_fallback, 2)
            self.assertEqual(output.read_bytes(), b"temporal-video")
            self.assertEqual(list(root.glob(".*cinepulse-preview*")), [])


if __name__ == "__main__":
    unittest.main()
