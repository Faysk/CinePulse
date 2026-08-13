from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cinepulse.preflight import StoragePlan, quality_warnings, validate_output_path


class PreflightTests(unittest.TestCase):
    def test_shared_volume_counts_output_and_temporary_once(self) -> None:
        plan = StoragePlan(4, 3, 10, 10, True, 2)
        self.assertEqual(plan.blocking_reasons, ())
        blocked = StoragePlan(4, 3, 8, 8, True, 2)
        self.assertTrue(blocked.blocking_reasons)

    def test_separate_volumes_are_checked_independently(self) -> None:
        plan = StoragePlan(4, 3, 5, 20, False, 2)
        self.assertIn("disco de saída", plan.blocking_reasons[0])

    def test_cache_growth_is_counted_when_cache_shares_scratch(self) -> None:
        plan = StoragePlan(1, 2, 100, 6, False, 2, cache_growth_gb=3, cache_free_gb=6, cache_on_temporary=True)
        self.assertTrue(any("disco temporário" in reason for reason in plan.blocking_reasons))

    def test_output_may_not_overwrite_an_input(self) -> None:
        source = Path("song.mp4")
        self.assertTrue(validate_output_path(source, (source,)))
        self.assertFalse(validate_output_path(Path("result.mkv"), (source,)))
        self.assertTrue(validate_output_path(Path("result.txt"), (source,)))

    def test_extreme_quality_has_honest_warnings(self) -> None:
        warnings = quality_warnings(1280, 720, 24, 11520, 6480, 480, 8192, True, True)
        self.assertGreaterEqual(len(warnings), 4)


if __name__ == "__main__":
    unittest.main()
