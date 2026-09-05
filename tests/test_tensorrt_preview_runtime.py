from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cinepulse.hardware import HardwareProfile
from cinepulse.tensorrt_preview import TensorRtExternalBackend, TensorRtPreviewStore
from cinepulse.tensorrt_preview_runtime import TensorRtRuntimeRequest, run_tensorrt_preview_or_fallback


class Store(TensorRtPreviewStore):
    def __init__(self, path: Path, approved: bool) -> None:
        super().__init__(path)
        self.value = approved
        self.invalidated = []

    def approved(self, key, backend) -> bool:
        return self.value

    def invalidate(self, key) -> bool:
        self.invalidated.append(key)
        self.value = False
        return True


def request(root: Path, *, approved: bool = True) -> TensorRtRuntimeRequest:
    model = root / "engine.plan"
    model.write_bytes(b"engine")
    source = root / "input"
    source.mkdir()
    return TensorRtRuntimeRequest(
        backend=TensorRtExternalBackend("runner.exe", "1.0", "10.0", "external-license"),
        store=Store(root / "store.json", approved),
        hardware=HardwareProfile("cpu", 16, "RTX Test", 8192, "999.1"),
        model="rife",
        model_path=model,
        input_path=source,
        output_path=root / "output",
        width=1920,
        height=1080,
        precision="fp16",
        ncnn_baseline_fingerprint="ncnn-proof",
        expected_frames=4,
    )


class TensorRtPreviewRuntimeTests(unittest.TestCase):
    def test_absent_evidence_delegates_to_ncnn_without_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            req = request(root, approved=False)
            fallback_output = root / "ncnn"
            with patch("cinepulse.tensorrt_preview_runtime._run_external") as run:
                result = run_tensorrt_preview_or_fallback(req, fallback=lambda: fallback_output)
            self.assertEqual("ncnn", result.backend)
            self.assertFalse(result.tensorrt_attempted)
            self.assertEqual(fallback_output, result.output_path)
            run.assert_not_called()

    def test_approved_evidence_executes_preview_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            req = request(root)
            with patch("cinepulse.tensorrt_preview_runtime._run_external") as run:
                result = run_tensorrt_preview_or_fallback(req, fallback=lambda: root / "ncnn")
            self.assertEqual("tensorrt-preview", result.backend)
            self.assertTrue(result.tensorrt_attempted)
            run.assert_called_once()

    def test_runtime_failure_invalidates_and_falls_back_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            req = request(root)
            calls = []
            def fallback() -> Path:
                calls.append(1)
                return root / "ncnn"
            with patch("cinepulse.tensorrt_preview_runtime._run_external", side_effect=RuntimeError("engine failed")):
                result = run_tensorrt_preview_or_fallback(req, fallback=fallback)
            self.assertEqual("ncnn", result.backend)
            self.assertTrue(result.tensorrt_attempted)
            self.assertIn("engine failed", result.failure or "")
            self.assertEqual(1, len(req.store.invalidated))  # type: ignore[attr-defined]
            self.assertEqual([1], calls)

    def test_cancellation_never_invalidates_or_calls_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            req = request(root)
            fallback_calls = []
            with patch("cinepulse.tensorrt_preview_runtime._run_external", side_effect=InterruptedError("cancelled")):
                with self.assertRaises(InterruptedError):
                    run_tensorrt_preview_or_fallback(req, fallback=lambda: fallback_calls.append(1) or root / "ncnn")
            self.assertEqual([], req.store.invalidated)  # type: ignore[attr-defined]
            self.assertEqual([], fallback_calls)

    def test_key_changes_when_external_model_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            req = request(root)
            before = req.key().token()
            req.model_path.write_bytes(b"new-engine")
            after = req.key().token()
            self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
