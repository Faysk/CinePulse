from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, order=True)
class RifePolicy:
    jobs: str
    gpu_index: int = 0

    def __post_init__(self) -> None:
        parts = self.jobs.split(":")
        if len(parts) != 3:
            raise ValueError("RIFE jobs must be LOAD:PROC:SAVE")
        values = tuple(int(value) for value in parts)
        if any(value < 1 or value > 8 for value in values):
            raise ValueError("RIFE job values must be between 1 and 8")
        if int(self.gpu_index) < 0:
            raise ValueError("RIFE GPU index must be >= 0")

    @property
    def pressure(self) -> tuple[int, int, int]:
        load, process, save = (int(value) for value in self.jobs.split(":"))
        return process, load + process + save, max(load, process, save)


@dataclass(frozen=True)
class RifeTuningKey:
    gpu_name: str
    vram_mb: int
    driver: str
    model: str
    width: int
    height: int

    def token(self) -> str:
        return "|".join(
            (
                " ".join(str(self.gpu_name).split()).lower() or "unknown-gpu",
                str(max(0, int(self.vram_mb))),
                str(self.driver).strip().lower() or "unknown-driver",
                str(self.model).strip().lower() or "unknown-model",
                f"{max(1, int(self.width))}x{max(1, int(self.height))}",
            )
        )


@dataclass(frozen=True)
class RifeSample:
    policy: RifePolicy
    wall_seconds: float
    integrity_ok: bool
    oom: bool = False
    output_frames: int | None = None
    expected_frames: int | None = None
    black_frame_ok: bool = True

    @property
    def accepted(self) -> bool:
        if self.oom or not self.integrity_ok or not self.black_frame_ok or self.wall_seconds <= 0:
            return False
        if self.expected_frames is not None and self.output_frames != self.expected_frames:
            return False
        return True


def fallback_policy(*, uhd: bool, gpu_index: int = 0) -> RifePolicy:
    return RifePolicy("1:1:1" if uhd else "2:2:2", max(0, int(gpu_index)))


def safe_candidates(*, uhd: bool, vram_mb: int | None, gpu_index: int = 0) -> tuple[RifePolicy, ...]:
    """Bounded candidates only; none is considered proven until physically benchmarked."""
    fallback = fallback_policy(uhd=uhd, gpu_index=gpu_index)
    vram = max(0, int(vram_mb or 0))
    jobs: list[str] = [fallback.jobs]
    if uhd:
        if vram >= 6144:
            jobs += ["1:2:1", "2:1:2"]
        if vram >= 10000:
            jobs += ["2:2:2"]
    else:
        if vram >= 4096:
            jobs += ["2:2:3", "3:2:3"]
        if vram >= 10000:
            jobs += ["3:3:3"]
    unique: list[RifePolicy] = []
    seen: set[RifePolicy] = set()
    for value in jobs:
        policy = RifePolicy(value, max(0, int(gpu_index)))
        if policy not in seen:
            seen.add(policy)
            unique.append(policy)
    return tuple(unique)


def choose_proven_policy(samples: Iterable[RifeSample], *, fallback: RifePolicy) -> RifePolicy:
    valid = [sample for sample in samples if sample.accepted]
    if not valid:
        return fallback
    return min(valid, key=lambda sample: sample.wall_seconds).policy


def downshift_policy(failed: RifePolicy, candidates: Iterable[RifePolicy], *, fallback: RifePolicy) -> RifePolicy:
    options = [
        item for item in candidates
        if item.gpu_index == failed.gpu_index and item.pressure < failed.pressure
    ]
    if fallback not in options and fallback != failed:
        options.append(fallback)
    if not options:
        return fallback
    return min(options, key=lambda item: item.pressure)


class RifeTuningStore:
    VERSION = 1

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _load(self) -> dict[str, object]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return {"version": self.VERSION, "records": {}}
        if not isinstance(payload, dict) or payload.get("version") != self.VERSION:
            return {"version": self.VERSION, "records": {}}
        if not isinstance(payload.get("records"), dict):
            return {"version": self.VERSION, "records": {}}
        return payload

    def lookup(self, key: RifeTuningKey, *, gpu_index: int = 0) -> RifePolicy | None:
        record = self._load().get("records", {}).get(key.token())
        if not isinstance(record, dict) or not record.get("integrity_ok"):
            return None
        raw = record.get("policy")
        if not isinstance(raw, dict):
            return None
        try:
            policy = RifePolicy(str(raw["jobs"]), int(raw["gpu_index"]))
        except (KeyError, TypeError, ValueError):
            return None
        if policy.gpu_index != max(0, int(gpu_index)):
            return None
        return policy

    def invalidate(self, key: RifeTuningKey) -> bool:
        payload = self._load()
        records = payload.get("records", {})
        if not isinstance(records, dict) or key.token() not in records:
            return False
        del records[key.token()]
        payload["version"] = self.VERSION
        self._atomic_write(payload)
        return True

    def record_samples(self, key: RifeTuningKey, samples: Iterable[RifeSample], *, fallback: RifePolicy) -> RifePolicy | None:
        values = tuple(samples)
        if not values or values[0].policy != fallback or not values[0].accepted:
            return None
        accepted = [sample for sample in values if sample.accepted]
        if not accepted:
            return None
        winner = choose_proven_policy(values, fallback=fallback)
        winner_sample = min((sample for sample in accepted if sample.policy == winner), key=lambda sample: sample.wall_seconds)
        payload = self._load()
        records = payload.setdefault("records", {})
        if not isinstance(records, dict):
            records = {}
            payload["records"] = records
        records[key.token()] = {
            "key": asdict(key),
            "policy": asdict(winner),
            "wall_seconds": float(winner_sample.wall_seconds),
            "integrity_ok": True,
            "sample_count": len(values),
            "accepted_sample_count": len(accepted),
            "oom_sample_count": sum(1 for sample in values if sample.oom),
            "updated_unix": time.time(),
        }
        payload["version"] = self.VERSION
        self._atomic_write(payload)
        return winner

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
