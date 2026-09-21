from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cinepulse import ai_suite


class AiSuiteTests(unittest.TestCase):
    def test_integrated_modules_have_managed_installer_mapping(self) -> None:
        mappings = {module.key: module.installer_component for module in ai_suite.MODULES}
        self.assertEqual(mappings["realesrgan"], "real-esrgan")
        self.assertEqual(mappings["rife"], "rife")
        self.assertEqual(mappings["demucs"], "demucs")
        self.assertEqual(mappings["vmaf"], "ffmpeg")

    def test_experimental_modules_require_explicit_opt_in(self) -> None:
        experimental = {"basicvsrpp", "clap", "depth", "sam2", "cotracker", "codeformer", "ltx2"}
        marked = {module.key for module in ai_suite.MODULES if module.experimental and module.installer_component}
        self.assertEqual(marked, experimental)

    def test_demucs_inventory_checks_the_same_manifest_used_by_stem_engine(self) -> None:
        module = next(module for module in ai_suite.MODULES if module.key == "demucs")
        required_names = {path.name for path in module.required}
        self.assertIn("htdemucs_ft.yaml", required_names)


    def test_generic_required_file_must_be_real_and_non_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            required = root / "model.bin"
            module = ai_suite.AiModule("x", "X", "test", (required,))
            self.assertFalse(module.installed)

            required.mkdir()
            self.assertFalse(module.installed, "a directory must never satisfy a required file")

            required.rmdir()
            required.write_bytes(b"")
            self.assertFalse(module.installed, "zero-byte model must fail closed")

            required.write_bytes(b"model")
            self.assertTrue(module.installed)

    def test_realesrgan_contract_includes_executable_bin_and_param(self) -> None:
        names = {path.name for path in ai_suite.REAL_ESRGAN_REQUIRED}
        self.assertIn("realesrgan-ncnn-vulkan.exe", names)
        self.assertIn("realesr-animevideov3-x2.bin", names)
        self.assertIn("realesr-animevideov3-x2.param", names)

    def test_integrated_readiness_rejects_one_missing_or_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = tuple(root / name for name in ("engine.exe", "model.bin", "model.param"))
            for path in files:
                path.write_bytes(b"ok")
            with patch.object(ai_suite, "REAL_ESRGAN_REQUIRED", files):
                self.assertTrue(ai_suite.real_esrgan_available())
                files[1].write_bytes(b"")
                self.assertFalse(ai_suite.real_esrgan_available())

    def test_demucs_contract_requires_all_four_weights(self) -> None:
        weight_names = {path.name for path in ai_suite.DEMUCS_REQUIRED if path.suffix == ".th"}
        self.assertEqual(
            weight_names,
            {
                "f7e0c4bc-ba3fe64a.th",
                "d12395a8-e57c48e6.th",
                "92cfc3b6-ef3bcb9c.th",
                "04573f0d-f3cf25b2.th",
            },
        )


if __name__ == "__main__":
    unittest.main()
