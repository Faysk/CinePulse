from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cinepulse.media_stage_adapter import MediaUnitContract, media_validator
from cinepulse.stage_adapter import AtomicStageAdapter, ValidationResult, file_validator
from cinepulse.stage_checkpoint import StageCheckpointStore


class InjectedCrash(RuntimeError):
    pass


class StageAdapterTests(unittest.TestCase):
    def _checkpoint(self, root: Path) -> StageCheckpointStore:
        return StageCheckpointStore(
            root / "checkpoints" / "rife.json",
            job_id="job-1",
            attempt_id="attempt-1",
            stage="rife",
            policy_fingerprint="policy-v1",
        )

    def test_success_commits_only_after_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkpoint = self._checkpoint(root)
            adapter = AtomicStageAdapter(checkpoint)
            final = root / "segment_00001.mkv"
            adapter.execute_unit(
                unit_id="segment-1",
                ordinal=1,
                final=final,
                producer=lambda partial: partial.write_bytes(b"valid"),
                validator=file_validator(expected_bytes=b"valid"),
            )
            self.assertEqual(b"valid", final.read_bytes())
            self.assertEqual(1, checkpoint.committed_count())
            self.assertEqual("committed", checkpoint.committed("segment-1")["state"])

    def test_crash_after_produce_repeats_only_current_unit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkpoint = self._checkpoint(root)
            final = root / "segment_00001.mkv"
            calls = []

            def fault(point, _unit):
                if point == "after_produce" and not calls:
                    calls.append(point)
                    raise InjectedCrash(point)

            adapter = AtomicStageAdapter(checkpoint, fault_hook=fault)
            with self.assertRaises(InjectedCrash):
                adapter.execute_unit(
                    unit_id="segment-1", ordinal=1, final=final,
                    producer=lambda partial: partial.write_bytes(b"valid"),
                    validator=file_validator(expected_bytes=b"valid"),
                )
            self.assertFalse(final.exists())
            self.assertEqual("interrupted", checkpoint.load()["units"]["segment-1"]["state"])
            adapter.execute_unit(
                unit_id="segment-1", ordinal=1, final=final,
                producer=lambda partial: partial.write_bytes(b"valid"),
                validator=file_validator(expected_bytes=b"valid"),
            )
            self.assertEqual(1, checkpoint.committed_count())

    def test_crash_after_promote_reconciles_without_reproducing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkpoint = self._checkpoint(root)
            final = root / "segment_00001.mkv"
            produced = {"count": 0}
            crashed = {"done": False}

            def producer(partial):
                produced["count"] += 1
                partial.write_bytes(b"valid")

            def fault(point, _unit):
                if point == "after_promote" and not crashed["done"]:
                    crashed["done"] = True
                    raise InjectedCrash(point)

            adapter = AtomicStageAdapter(checkpoint, fault_hook=fault)
            with self.assertRaises(InjectedCrash):
                adapter.execute_unit(
                    unit_id="segment-1", ordinal=1, final=final,
                    producer=producer, validator=file_validator(expected_bytes=b"valid"),
                )
            self.assertTrue(final.is_file())
            self.assertEqual("validating", checkpoint.load()["units"]["segment-1"]["state"])
            adapter.execute_unit(
                unit_id="segment-1", ordinal=1, final=final,
                producer=producer, validator=file_validator(expected_bytes=b"valid"),
            )
            self.assertEqual(1, produced["count"])
            self.assertEqual("committed", checkpoint.committed("segment-1")["state"])

    def test_committed_unit_with_missing_artifact_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkpoint = self._checkpoint(root)
            final = root / "segment_00001.mkv"
            adapter = AtomicStageAdapter(checkpoint)
            adapter.execute_unit(
                unit_id="segment-1", ordinal=1, final=final,
                producer=lambda partial: partial.write_bytes(b"valid"),
                validator=file_validator(expected_bytes=b"valid"),
            )
            final.unlink()
            with self.assertRaisesRegex(RuntimeError, "sumiu"):
                adapter.execute_unit(
                    unit_id="segment-1", ordinal=1, final=final,
                    producer=lambda partial: partial.write_bytes(b"new"),
                    validator=file_validator(expected_bytes=b"valid"),
                )

    def test_media_validator_checks_pix_fmt_and_exact_frame_count(self) -> None:
        contract = MediaUnitContract(7680, 4320, 120.0, codec="ffv1", pix_fmt="yuv420p", exact_frames=17)
        probe = {
            "streams": [{
                "codec_type": "video", "width": 7680, "height": 4320,
                "avg_frame_rate": "120/1", "codec_name": "ffv1", "pix_fmt": "yuv420p",
                "nb_read_frames": "17",
            }]
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "segment.mkv"
            path.write_bytes(b"media")
            with patch("cinepulse.media_stage_adapter.probe_media_unit", return_value=probe):
                result = media_validator("ffprobe", contract)(path)
        self.assertIsInstance(result, ValidationResult)
        self.assertTrue(result.passed)
        self.assertEqual(17, result.details["frames"])

    def test_media_validator_rejects_wrong_pix_fmt(self) -> None:
        contract = MediaUnitContract(3840, 2160, 60.0, codec="ffv1", pix_fmt="yuv420p10le", exact_frames=16)
        probe = {
            "streams": [{
                "codec_type": "video", "width": 3840, "height": 2160,
                "avg_frame_rate": "60/1", "codec_name": "ffv1", "pix_fmt": "yuv420p",
                "nb_read_frames": "16",
            }]
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "segment.mkv"
            path.write_bytes(b"media")
            with patch("cinepulse.media_stage_adapter.probe_media_unit", return_value=probe):
                result = media_validator("ffprobe", contract)(path)
        self.assertFalse(result.passed)
        self.assertIn("pix_fmt", result.details["errors"])


if __name__ == "__main__":
    unittest.main()
