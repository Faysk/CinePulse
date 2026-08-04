from __future__ import annotations

import unittest

from cinepulse.quality_metrics import parse_vmaf_report


class QualityMetricsTests(unittest.TestCase):
    def test_parses_mean_vmaf(self) -> None:
        self.assertEqual(96.25, parse_vmaf_report({"pooled_metrics": {"vmaf": {"mean": 96.25}}}))

    def test_rejects_incomplete_report(self) -> None:
        with self.assertRaises(ValueError):
            parse_vmaf_report({})

