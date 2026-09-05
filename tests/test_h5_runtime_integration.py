from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

from cinepulse.hardware_telemetry import GpuSample, HardwareSample, HardwareTelemetrySession
from cinepulse.studio import VideoOptimizerStudio


class H5RuntimeIntegrationTests(unittest.TestCase):
    def test_neural_entry_points_keep_runtime_guard_opt_in(self) -> None:
        ai = inspect.signature(VideoOptimizerStudio._enhance_clip_ai)
        rife = inspect.signature(VideoOptimizerStudio._interpolate_rife)
        self.assertIsNone(ai.parameters["runtime_guard"].default)
        self.assertIsNone(rife.parameters["runtime_guard"].default)

    def test_neural_loops_only_downshift_h4_permissions(self) -> None:
        ai = inspect.getsource(VideoOptimizerStudio._enhance_clip_ai)
        rife = inspect.getsource(VideoOptimizerStudio._interpolate_rife)
        self.assertIn("overlap_extract = overlap_extract and decision.allow_extract_overlap", ai)
        self.assertIn("overlap_pack = overlap_pack and decision.allow_pack_overlap", ai)
        self.assertIn("decision.limit_chunk_frames(chunk_frames)", ai)
        self.assertIn("overlap_extract = overlap_extract and decision.allow_extract_overlap", rife)
        self.assertIn("decision.limit_chunk_frames(chunk_frames, minimum=2)", rife)

    def test_pressure_cancels_future_prefetch_before_smaller_chunk_is_planned(self) -> None:
        ai = inspect.getsource(VideoOptimizerStudio._enhance_clip_ai)
        pressure = ai.index("if decision.level > 0 and prefetch is not None")
        cancel = ai.index("task.cancel()", pressure)
        cleanup = ai.index("safe_rmtree(prefetched_dir)", cancel)
        resize = ai.index("active_chunk_frames = decision.limit_chunk_frames(chunk_frames)", cleanup)
        self.assertLess(pressure, cancel)
        self.assertLess(cancel, cleanup)
        self.assertLess(cleanup, resize)

    def test_telemetry_exposes_latest_observational_sample_without_stopping(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            session = HardwareTelemetrySession(Path(temp) / "telemetry.json")
            payload = HardwareSample(
                timestamp=1.0,
                monotonic=1.0,
                stage="IA 2/3",
                cpu_total_percent=10.0,
                cpu_per_logical_percent=(),
                ram_total_mb=1000.0,
                ram_used_mb=500.0,
                ram_available_mb=500.0,
                ram_percent=50.0,
                disk_read_mbps=None,
                disk_write_mbps=None,
                gpus=(GpuSample(index=0, name="GPU", temperature_c=70.0),),
            )
            with session._lock:
                session._samples.append(payload)
            self.assertIs(session.latest_sample(), payload)


if __name__ == "__main__":
    unittest.main()
