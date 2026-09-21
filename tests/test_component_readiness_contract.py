from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

from cinepulse import ai_suite
from cinepulse.studio import VideoOptimizerStudio


class ComponentReadinessContractTests(unittest.TestCase):
    def test_quality_helpers_delegate_to_central_component_contract(self) -> None:
        studio = VideoOptimizerStudio.__new__(VideoOptimizerStudio)
        with patch("cinepulse.studio.ai_suite.real_esrgan_available", return_value=False) as real:
            self.assertFalse(studio._quality_real_esrgan_available())
        real.assert_called_once_with()
        with patch("cinepulse.studio.ai_suite.rife_available", return_value=False) as rife:
            self.assertFalse(studio._quality_rife_available())
        rife.assert_called_once_with()

    def test_studio_does_not_use_executable_only_readiness_checks(self) -> None:
        source = inspect.getsource(VideoOptimizerStudio)
        self.assertNotIn("REAL_ESRGAN.is_file()", source)
        self.assertNotIn("RIFE_EXE.is_file()", source)
        self.assertIn("ai_suite.real_esrgan_available()", source)
        self.assertIn("ai_suite.rife_available()", source)
        self.assertIn("ai_suite.demucs_available()", source)

    def test_integrated_inventory_uses_readiness_detectors(self) -> None:
        modules = {module.key: module for module in ai_suite.MODULES}
        self.assertIs(modules["realesrgan"].detector, ai_suite.real_esrgan_available)
        self.assertIs(modules["rife"].detector, ai_suite.rife_available)
        self.assertIs(modules["demucs"].detector, ai_suite.demucs_available)


if __name__ == "__main__":
    unittest.main()
