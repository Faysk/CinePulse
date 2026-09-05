from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cinepulse.ncnn_baseline import prove_ncnn_baseline
from cinepulse.realesrgan_tuning import (
    RealEsrganPolicy,
    RealEsrganSample,
    RealEsrganTuningKey,
    RealEsrganTuningStore,
)
from cinepulse.rife_tuning import RifePolicy, RifeSample, RifeTuningKey, RifeTuningStore


class NcnnBaselineProofTests(unittest.TestCase):
    def test_realesrgan_requires_exact_hardware_driver_geometry_and_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "realesrgan.json"
            key = RealEsrganTuningKey("RTX Test", 8192, "999.1", "realesr-animevideov3", 1280, 720, 2)
            policy = RealEsrganPolicy(320, 3, 2, 3, 0)
            sample = RealEsrganSample(policy, 4.0, True, output_frames=8, expected_frames=8)
            self.assertEqual(policy, RealEsrganTuningStore(cache).record_samples(key, (sample,)))

            proof = prove_ncnn_baseline(
                model="realesrgan", cache=cache, gpu_name="RTX Test", vram_mb=8192,
                driver="999.1", model_id="realesr-animevideov3", source_width=1280,
                source_height=720, gpu_index=0, scale=2,
            )
            self.assertIsNotNone(proof)
            assert proof is not None
            self.assertEqual("realesrgan", proof.model)
            self.assertTrue(proof.fingerprint)

            self.assertIsNone(prove_ncnn_baseline(
                model="realesrgan", cache=cache, gpu_name="RTX Test", vram_mb=8192,
                driver="999.2", model_id="realesr-animevideov3", source_width=1280,
                source_height=720, gpu_index=0, scale=2,
            ))

    def test_rife_requires_exact_accepted_baseline_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "rife.json"
            key = RifeTuningKey("RTX Test", 8192, "999.1", "rife-v4.6", 1920, 1080)
            fallback = RifePolicy("2:2:2", 0)
            sample = RifeSample(
                fallback, 5.0, True, output_frames=16, expected_frames=16,
                black_frame_ok=True, quality_ok=True, quality_psnr_db=80.0,
            )
            self.assertEqual(fallback, RifeTuningStore(cache).record_samples(key, (sample,), fallback=fallback))

            proof = prove_ncnn_baseline(
                model="rife", cache=cache, gpu_name="RTX Test", vram_mb=8192,
                driver="999.1", model_id="rife-v4.6", source_width=1920,
                source_height=1080, gpu_index=0,
            )
            self.assertIsNotNone(proof)
            assert proof is not None
            first = proof.fingerprint

            store = RifeTuningStore(cache)
            self.assertTrue(store.invalidate(key))
            self.assertIsNone(prove_ncnn_baseline(
                model="rife", cache=cache, gpu_name="RTX Test", vram_mb=8192,
                driver="999.1", model_id="rife-v4.6", source_width=1920,
                source_height=1080, gpu_index=0,
            ))
            self.assertTrue(first)


if __name__ == "__main__":
    unittest.main()
