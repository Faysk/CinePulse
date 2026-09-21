from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from cinepulse.cpu_tuning import CpuTuningStore
from cinepulse.gpu_compositor import GpuCompositorStore
from cinepulse.gpu_encode import ResidentEncodeStore
from cinepulse.gpu_media import GpuMediaTuningStore
from cinepulse.path_transaction import serialized_path_mutation
from cinepulse.realesrgan_tuning import RealEsrganTuningStore
from cinepulse.rife_tuning import RifeTuningStore


class _ProbeStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    @serialized_path_mutation
    def hold(self, entered: threading.Event, release: threading.Event, completed: list[str], label: str) -> None:
        entered.set()
        release.wait(timeout=5)
        completed.append(label)


class EvidenceStoreTransactionTests(unittest.TestCase):
    def test_two_instances_for_same_path_cannot_mutate_concurrently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evidence.json"
            first = _ProbeStore(path)
            second = _ProbeStore(path)
            first_entered = threading.Event()
            second_entered = threading.Event()
            release_first = threading.Event()
            release_second = threading.Event()
            completed: list[str] = []

            one = threading.Thread(
                target=first.hold,
                args=(first_entered, release_first, completed, "first"),
                daemon=True,
            )
            two = threading.Thread(
                target=second.hold,
                args=(second_entered, release_second, completed, "second"),
                daemon=True,
            )
            one.start()
            self.assertTrue(first_entered.wait(timeout=2))
            two.start()
            time.sleep(0.10)
            self.assertFalse(second_entered.is_set(), "second mutation entered the same path concurrently")

            release_first.set()
            self.assertTrue(second_entered.wait(timeout=2))
            release_second.set()
            one.join(timeout=2)
            two.join(timeout=2)
            self.assertEqual(["first", "second"], completed)

    def test_all_policy_store_mutations_are_serialized(self) -> None:
        guarded = (
            GpuCompositorStore.record_benchmark_failure,
            GpuCompositorStore.record_rejection,
            GpuCompositorStore.record,
            GpuCompositorStore.invalidate,
            ResidentEncodeStore.record,
            ResidentEncodeStore.invalidate,
            GpuMediaTuningStore.record,
            GpuMediaTuningStore.invalidate,
            RealEsrganTuningStore.record_samples,
            RealEsrganTuningStore.invalidate,
            RifeTuningStore.record_samples,
            RifeTuningStore.invalidate,
            CpuTuningStore.record_samples,
        )
        for method in guarded:
            with self.subTest(method=method.__qualname__):
                self.assertTrue(
                    hasattr(method, "__wrapped__"),
                    f"{method.__qualname__} is missing serialized_path_mutation",
                )


if __name__ == "__main__":
    unittest.main()
