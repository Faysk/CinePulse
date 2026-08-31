from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cinepulse.staging import ResumableStager, StagingError
from cinepulse.storage_resilience import StorageBlocked, StorageGuard, should_use_faststart
from cinepulse.volume_identity import VolumeIdentity, resolve_volume_identity, same_volume


class AllowGuard:
    def require(self, *_args, **_kwargs):
        return None

    def monitor(self, *_args, **_kwargs):
        return None


class StorageResilienceTests(unittest.TestCase):
    def test_volume_identity_is_stable_for_same_temp_volume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "a"
            right = root / "b"
            left.mkdir()
            right.mkdir()
            self.assertEqual(resolve_volume_identity(left).id, resolve_volume_identity(right).id)
            self.assertTrue(same_volume(left, right))

    def test_guard_blocks_when_required_plus_reserve_exceeds_free(self) -> None:
        identity = VolumeIdentity("vol", "/", "x", "fixed", "unknown", 1000, 100)
        guard = StorageGuard(reserve_bytes=20)
        with patch("cinepulse.storage_resilience.resolve_volume_identity", return_value=identity):
            with self.assertRaises(StorageBlocked):
                guard.require(Path("."), 90)
            decision = guard.require(Path("."), 70)
        self.assertTrue(decision.allowed)
        self.assertEqual(30, decision.projected_free_bytes)

    def test_faststart_policy_avoids_second_large_local_or_removable_pass(self) -> None:
        large = 9 * 1024**3
        self.assertFalse(should_use_faststart(output_size_bytes=large, local_playback=True, drive_type="fixed"))
        self.assertFalse(should_use_faststart(output_size_bytes=large, local_playback=False, drive_type="removable"))
        self.assertTrue(should_use_faststart(output_size_bytes=1024**3, local_playback=True, drive_type="fixed"))

    def test_staging_resumes_after_interruption_and_preserves_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "master.mkv"
            destination = root / "ssd" / "master.mkv"
            source.write_bytes(bytes(range(100)))
            stager = ResumableStager(guard=AllowGuard(), chunk_size=16)
            with self.assertRaisesRegex(StagingError, "fault injection"):
                stager.copy(source, destination, fault_after_bytes=32)
            partial = destination.parent / f".{destination.name}.staging.partial"
            self.assertTrue(partial.is_file())
            self.assertGreaterEqual(partial.stat().st_size, 32)
            result = stager.copy(source, destination, verify_checksum=True)
            self.assertEqual(destination, result)
            self.assertEqual(source.read_bytes(), destination.read_bytes())
            self.assertTrue(source.is_file())
            self.assertFalse(partial.exists())

    def test_staging_rejects_changed_source_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "master.mkv"
            destination = root / "stage" / "master.mkv"
            source.write_bytes(b"a" * 100)
            stager = ResumableStager(guard=AllowGuard(), chunk_size=16)
            with self.assertRaises(StagingError):
                stager.copy(source, destination, fault_after_bytes=16)
            source.write_bytes(b"b" * 101)
            with self.assertRaisesRegex(StagingError, "outra origem/contrato"):
                stager.copy(source, destination)

    def test_validator_runs_before_staged_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "master.mkv"
            destination = root / "stage" / "master.mkv"
            source.write_bytes(b"media")
            stager = ResumableStager(guard=AllowGuard(), chunk_size=2)

            def reject(_path: Path) -> None:
                raise RuntimeError("invalid media")

            with self.assertRaisesRegex(RuntimeError, "invalid media"):
                stager.copy(source, destination, validator=reject)
            self.assertFalse(destination.exists())
            self.assertTrue((destination.parent / f".{destination.name}.staging.partial").exists())


if __name__ == "__main__":
    unittest.main()
