from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "src" / "cinepulse" / "studio.py"


class H5GpuMediaRuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = STUDIO.read_text(encoding="utf-8")
        start = cls.text.index("        # H5: CUDA decode is evidence-gated")
        end = cls.text.index("        try:\n            while processed < total_frames:", start)
        cls.block = cls.text[start:end]

    def test_runtime_requires_exact_evidence_lookup(self) -> None:
        self.assertIn("GpuMediaTuningStore(PATHS.cache / \"hardware\" / \"gpu-media-tuning.json\")", self.block)
        self.assertIn("select_gpu_media_policy(", self.block)
        self.assertIn("ffmpeg_fingerprint=gpu_caps.fingerprint", self.block)
        self.assertIn("driver=self._hardware.driver", self.block)
        self.assertIn("operation=\"decode\"", self.block)

    def test_cuda_decode_requires_live_vram_headroom_without_deleting_evidence(self) -> None:
        self.assertIn("gpu_media_vram_floor_mb(gpu_media_key)", self.block)
        self.assertIn("decode_free_mb = vram_free_mb(gpu_media_policy.gpu_index)", self.block)
        self.assertIn("evidência exata preservada", self.block)
        self.assertIn("gpu_media_policy = None", self.block)

    def test_cuda_frames_are_downloaded_without_gpu_color_conversion(self) -> None:
        self.assertIn("policy.input_args()", self.block)
        self.assertIn("hwdownload,format={gpu_media_profile.pixel_format},fps=", self.block)
        self.assertNotIn("colorspace_cuda", self.block)
        self.assertNotIn("tonemap_cuda", self.block)

    def test_production_failure_invalidates_exact_evidence(self) -> None:
        self.assertIn("invalidate_gpu_media_policy(gpu_media_store, gpu_media_key)", self.block)
        self.assertIn("gpu_media_policy = None", self.block)
        self.assertIn("será repetido uma vez pela CPU", self.block)

    def test_foreground_failure_retries_cpu_after_clearing_partial_frames(self) -> None:
        self.assertIn("safe_rmtree(destination)", self.block)
        self.assertIn("policy=None", self.block)
        self.assertIn("retry = extraction_command", self.block)

    def test_short_cuda_extraction_retries_cpu_and_never_skips_requested_frames(self) -> None:
        full_start = self.text.index(
            "        try:\n            while processed < total_frames:",
            self.text.index("        # H5: CUDA decode is evidence-gated"),
        )
        full_end = self.text.index("        finally:", full_start)
        runtime = self.text[full_start:full_end]
        self.assertIn("CUDA/CUVID frame-count integrity mismatch", runtime)
        self.assertIn("run_extraction(", runtime)
        self.assertIn("total_frames = processed + frames", runtime)
        self.assertIn("processed += count", runtime)
        self.assertIn("render interrompido para evitar lacuna temporal", runtime)

    def test_prefetch_respects_runtime_downshifted_chunk_size(self) -> None:
        full_start = self.text.index(
            "        try:\n            while processed < total_frames:",
            self.text.index("        # H5: CUDA decode is evidence-gated"),
        )
        full_end = self.text.index("        finally:", full_start)
        runtime = self.text[full_start:full_end]
        self.assertIn("next_count = min(active_chunk_frames, total_frames - next_processed)", runtime)
        self.assertNotIn("next_count = min(chunk_frames, total_frames - next_processed)", runtime)

    def test_prefetch_failure_cannot_leave_cuda_policy_active(self) -> None:
        # The H4 background prefetch wait catches a GPU runtime failure,
        # invalidates the policy, clears the partial chunk and runs the same
        # bounded extraction synchronously through the CPU path.
        full_start = self.text.index("        try:\n            while processed < total_frames:", self.text.index("        # H5: CUDA decode is evidence-gated"))
        full_end = self.text.index("        finally:", full_start)
        runtime = self.text[full_start:full_end]
        self.assertIn("except RuntimeError as exc:", runtime)
        self.assertIn("invalidate_gpu_extract(exc)", runtime)
        self.assertIn("run_extraction(", runtime)


if __name__ == "__main__":
    unittest.main()
