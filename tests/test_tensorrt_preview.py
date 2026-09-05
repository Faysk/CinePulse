from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cinepulse.tensorrt_preview import (
    TensorRtEvidence,
    TensorRtExternalBackend,
    TensorRtKey,
    TensorRtPreviewStore,
    build_external_command,
)


def backend() -> TensorRtExternalBackend:
    return TensorRtExternalBackend("runner.exe", "1.4.0", "11.2", "Apache-2.0", True)


def key(value: TensorRtExternalBackend | None = None) -> TensorRtKey:
    value = value or backend()
    return TensorRtKey(
        gpu_name="RTX Test",
        driver="999.1",
        tensorrt_version=value.tensorrt_version,
        backend_fingerprint=value.fingerprint,
        model="rife",
        model_fingerprint="model123",
        width=3840,
        height=2160,
        precision="fp16",
    )


class TensorRtPreviewTests(unittest.TestCase):
    def test_backend_is_never_promoted_to_stable_distribution(self) -> None:
        self.assertFalse(backend().stable_distribution_allowed)

    def test_slow_or_quality_regressed_candidate_is_rejected(self) -> None:
        slow = TensorRtEvidence(10, 9.5, True, True, True, True, 80, 1.0)
        changed = TensorRtEvidence(10, 5, True, True, True, True, 40, 0.99)
        self.assertFalse(slow.accepted)
        self.assertFalse(changed.accepted)

    def test_temporal_and_black_frame_gates_are_mandatory(self) -> None:
        temporal_bad = TensorRtEvidence(10, 5, True, True, True, False, 80, 1.0)
        black_bad = TensorRtEvidence(10, 5, True, True, False, True, 80, 1.0)
        self.assertFalse(temporal_bad.accepted)
        self.assertFalse(black_bad.accepted)

    def test_exact_backend_fingerprint_and_hardware_key_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = TensorRtPreviewStore(Path(temporary) / "trt.json")
            good = TensorRtEvidence(10, 5, True, True, True, True, 80, 1.0, vmaf_delta=0.0)
            self.assertTrue(store.record(key(), backend(), good))
            self.assertTrue(store.approved(key(), backend()))
            other = TensorRtExternalBackend("other.exe", "1.4.0", "11.2", "Apache-2.0", True)
            self.assertFalse(store.approved(key(), other))

    def test_runtime_version_mismatch_invalidates_permission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = TensorRtPreviewStore(Path(temporary) / "trt.json")
            value = backend()
            good = TensorRtEvidence(10, 5, True, True, True, True, 80, 1.0)
            self.assertTrue(store.record(key(value), value, good))
            upgraded = TensorRtExternalBackend("runner.exe", "1.4.0", "11.3", "Apache-2.0", True)
            self.assertFalse(store.approved(key(value), upgraded))

    def test_external_command_contains_no_installer_or_global_changes(self) -> None:
        command = build_external_command(
            backend(),
            model="rife",
            model_path=Path("model.onnx"),
            input_path=Path("in"),
            output_path=Path("out"),
            width=1920,
            height=1080,
            precision="fp32",
        )
        self.assertEqual("runner.exe", command[0])
        self.assertIn("--cinepulse-run", command)
        self.assertNotIn("pip", command)
        self.assertNotIn("install", command)


if __name__ == "__main__":
    unittest.main()
