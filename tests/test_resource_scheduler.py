from __future__ import annotations

import unittest

from cinepulse.resource_scheduler import CpuTopology, candidate_thread_counts, choose_proven_thread_count, schedule_cpu_threads


class ResourceSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.topology = CpuTopology(logical_cpus=20, physical_cores=14, source="test")

    def test_cpu_heavy_stage_exceeds_legacy_eight_thread_cap(self) -> None:
        plan = schedule_cpu_threads("encode", topology=self.topology, mode="balanced")
        self.assertGreater(plan.threads, 8)
        self.assertLess(plan.threads, 20)

    def test_dedicated_mode_uses_more_headroom(self) -> None:
        balanced = schedule_cpu_threads("encode", topology=self.topology, mode="balanced")
        dedicated = schedule_cpu_threads("encode", topology=self.topology, mode="dedicated")
        self.assertGreater(dedicated.threads, balanced.threads)
        self.assertLess(dedicated.threads, 20)

    def test_gpu_neural_stage_keeps_host_threads_modest(self) -> None:
        plan = schedule_cpu_threads("neural_gpu", topology=self.topology, mode="dedicated", gpu_active=True)
        self.assertLessEqual(plan.threads, 6)

    def test_thermal_constraint_downshifts(self) -> None:
        normal = schedule_cpu_threads("encode", topology=self.topology, mode="dedicated")
        constrained = schedule_cpu_threads("encode", topology=self.topology, mode="dedicated", thermal_constrained=True)
        self.assertLess(constrained.threads, normal.threads)

    def test_candidate_set_is_bounded(self) -> None:
        values = candidate_thread_counts("encode", topology=self.topology, mode="balanced")
        self.assertEqual(values, tuple(sorted(set(values))))
        self.assertTrue(all(1 <= value <= 20 for value in values))

    def test_benchmark_choice_requires_integrity(self) -> None:
        chosen = choose_proven_thread_count([(8, 20.0, True), (16, 10.0, False), (12, 15.0, True)], fallback_threads=8)
        self.assertEqual(chosen, 12)


if __name__ == "__main__":
    unittest.main()
