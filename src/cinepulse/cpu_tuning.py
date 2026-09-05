from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .resource_scheduler import CpuTopology, MachineMode, StageKind, choose_proven_thread_count


@dataclass(frozen=True)
class CpuTuningKey:
    stage: StageKind
    logical_cpus: int
    physical_cores: int
    mode: MachineMode
    gpu_active: bool = False

    def token(self) -> str:
        return ":".join(
            (
                self.stage,
                str(max(1, int(self.logical_cpus))),
                str(max(1, int(self.physical_cores))),
                self.mode,
                "gpu" if self.gpu_active else "cpu",
            )
        )

    @classmethod
    def from_topology(
        cls,
        stage: StageKind,
        topology: CpuTopology,
        *,
        mode: MachineMode,
        gpu_active: bool = False,
    ) -> "CpuTuningKey":
        return cls(
            stage=stage,
            logical_cpus=max(1, topology.logical_cpus),
            physical_cores=max(1, topology.physical_cores),
            mode=mode,
            gpu_active=bool(gpu_active),
        )


@dataclass(frozen=True)
class CpuTuningSample:
    threads: int
    wall_seconds: float
    integrity_ok: bool

    def as_tuple(self) -> tuple[int, float, bool]:
        return (int(self.threads), float(self.wall_seconds), bool(self.integrity_ok))


class CpuTuningStore:
    """Small fail-closed cache for physically benchmarked CPU policies.

    The cache never invents a winner. A record is written only when at least one
    candidate completed with its integrity gate intact. Runtime lookup requires an
    exact topology/stage/mode/GPU-feed match and still respects the current user's
    CPU ceiling.
    """

    VERSION = 1

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _load(self) -> dict[str, object]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {"version": self.VERSION, "records": {}}
        if not isinstance(payload, dict) or payload.get("version") != self.VERSION:
            return {"version": self.VERSION, "records": {}}
        records = payload.get("records")
        if not isinstance(records, dict):
            return {"version": self.VERSION, "records": {}}
        return payload

    def lookup(self, key: CpuTuningKey, *, max_threads: int) -> int | None:
        payload = self._load()
        records = payload.get("records", {})
        if not isinstance(records, dict):
            return None
        record = records.get(key.token())
        if not isinstance(record, dict) or not record.get("integrity_ok"):
            return None
        try:
            threads = int(record["threads"])
        except (KeyError, TypeError, ValueError):
            return None
        ceiling = max(1, min(int(max_threads), max(1, int(key.logical_cpus))))
        if not 1 <= threads <= ceiling:
            return None
        return threads

    def record_samples(
        self,
        key: CpuTuningKey,
        samples: Iterable[CpuTuningSample],
        *,
        fallback_threads: int,
    ) -> int | None:
        materialized = tuple(samples)
        valid = [sample for sample in materialized if sample.threads > 0 and sample.wall_seconds > 0 and sample.integrity_ok]
        if not valid:
            return None
        chosen = choose_proven_thread_count(
            (sample.as_tuple() for sample in materialized),
            fallback_threads=fallback_threads,
        )
        winner = min(
            (sample for sample in valid if sample.threads == chosen),
            key=lambda sample: sample.wall_seconds,
        )
        payload = self._load()
        records = payload.setdefault("records", {})
        if not isinstance(records, dict):
            records = {}
            payload["records"] = records
        records[key.token()] = {
            "key": asdict(key),
            "threads": int(chosen),
            "wall_seconds": float(winner.wall_seconds),
            "integrity_ok": True,
            "sample_count": len(materialized),
            "verified_sample_count": len(valid),
            "samples": [asdict(sample) for sample in materialized],
            "updated_unix": time.time(),
        }
        payload["version"] = self.VERSION
        self._atomic_write(payload)
        return int(chosen)

    def _atomic_write(self, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.path)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
