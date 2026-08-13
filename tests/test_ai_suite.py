from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
