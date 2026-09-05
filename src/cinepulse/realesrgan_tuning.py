from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, order=True)
class RealEsrganPolicy:
    tile: int = 256
    load_jobs: int = 2
    process_jobs: int = 2
    save_jobs: int = 2
    gpu_index: int = 0

    @property
    def pipeline(self) -> str:
        return f"{self.load_jobs}:{self.process_jobs}:{self.save_jobs}"

    def command_args(self) -> list[str]:
        return ["-t", str(self.tile), "-j", self.pipeline, "-g", str(self.gpu_index)]


@dataclass(frozen=True)
class RealEsrganTuningKey:
    gpu_name: str
    vram_mb: int
    driver: str
    model: str
    width: int
    height: int
    scale: int

    def token(self) -> str:
        clean_gpu = " ".join(self.gpu_name.split()).lower() or "unknown-gpu"
        clean_driver = self.driver.strip().lower() or "unknown-driver"
        return "|".join(
            (
                clean_gpu,
                str(max(0, int(self.vram_mb))),
                clean_driver,
                self.model.strip().lower(),
                f"{max(1, int(self.width))}x{max(1, int(self.height))}",
                f"x{max(1, int(self.scale))}",
            )
        )


@dataclass(frozen=True)
class RealEsrganSample:
    policy: RealEsrganPolicy
    wall_seconds: float
    integrity_ok: bool
    oom: bool = False
    output_frames: int | None = None
    expected_frames: int | None = None

    @property
    def accepted(self) -> bool:
        if self.oom or not self.integrity_ok or self.wall_seconds <= 0:
            return False
        if self.expected_frames is not None and self.output_frames != self.expected_frames:
            return False
        return True


def safe_candidates(
    *,
    vram_mb: int | None,
    cpu_threads: int,
    gpu_index: int = 0,
    width: int = 1920,
    height: int = 1080,
) -> tuple[RealEsrganPolicy, ...]:
    """Return bounded benchmark candidates; the caller must benchmark before use.

    Candidate generation intentionally does not declare any option faster or safe on
    physical hardware. The legacy 256 / 2:2:2 policy is always included first as the
    known fallback. Larger tiles/concurrency are merely candidates for H2 evidence.
    """
    vram = max(0, int(vram_mb or 0))
    threads = max(1, int(cpu_threads))
    pixels = max(1, int(width)) * max(1, int(height))

    tiles = [256]
    if vram >= 4096:
        tiles.insert(0, 192)
        tiles.append(320)
    if vram >= 6144 and pixels <= 3840 * 2160:
        tiles.append(384)
    if vram >= 10000 and pixels <= 2560 * 1440:
        tiles.append(512)

    pipelines = [(2, 2, 2)]
    if threads >= 12:
        pipelines.append((3, 2, 3))
    if threads >= 20:
        pipelines.append((4, 2, 4))

    candidates: list[RealEsrganPolicy] = []
    for tile in tiles:
        for load, process, save in pipelines:
            candidates.append(RealEsrganPolicy(tile, load, process, save, max(0, int(gpu_index))))

    fallback = RealEsrganPolicy(256, 2, 2, 2, max(0, int(gpu_index)))
    unique = [fallback]
    seen = {fallback}
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return tuple(unique)


def choose_proven_policy(
    samples: Iterable[RealEsrganSample],
    *,
    fallback: RealEsrganPolicy | None = None,
) -> RealEsrganPolicy:
    fallback = fallback or RealEsrganPolicy()
    valid = [sample for sample in samples if sample.accepted]
    if not valid:
        return fallback
    return min(valid, key=lambda item: item.wall_seconds).policy


def downshift_policy(
    failed: RealEsrganPolicy,
    candidates: Iterable[RealEsrganPolicy],
    *,
    fallback: RealEsrganPolicy | None = None,
) -> RealEsrganPolicy:
    """Prefer less GPU pressure after OOM/instability without changing the model."""
    fallback = fallback or RealEsrganPolicy(gpu_index=failed.gpu_index)
    options = [
        item
        for item in candidates
        if item.gpu_index == failed.gpu_index
        and (item.tile < failed.tile or item.process_jobs < failed.process_jobs)
    ]
    if not options:
        return fallback
    # Smaller tile first, then lower total pipeline concurrency.
    return min(options, key=lambda item: (item.tile, item.load_jobs + item.process_jobs + item.save_jobs))


class RealEsrganTuningStore:
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
        if not isinstance(payload.get("records"), dict):
            return {"version": self.VERSION, "records": {}}
        return payload

    def lookup(self, key: RealEsrganTuningKey, *, gpu_index: int = 0) -> RealEsrganPolicy | None:
        record = self._load().get("records", {}).get(key.token())
        if not isinstance(record, dict) or not record.get("integrity_ok"):
            return None
        policy = record.get("policy")
        if not isinstance(policy, dict):
            return None
        try:
            value = RealEsrganPolicy(**{name: int(policy[name]) for name in ("tile", "load_jobs", "process_jobs", "save_jobs", "gpu_index")})
        except (KeyError, TypeError, ValueError):
            return None
        if value.gpu_index != max(0, int(gpu_index)):
            return None
        if value.tile < 32 or min(value.load_jobs, value.process_jobs, value.save_jobs) < 1:
            return None
        return value

    def record_samples(
        self,
        key: RealEsrganTuningKey,
        samples: Iterable[RealEsrganSample],
        *,
        fallback: RealEsrganPolicy | None = None,
    ) -> RealEsrganPolicy | None:
        materialized = tuple(samples)
        accepted = [sample for sample in materialized if sample.accepted]
        if not accepted:
            return None
        winner = choose_proven_policy(materialized, fallback=fallback)
        winner_sample = min(
            (sample for sample in accepted if sample.policy == winner),
            key=lambda item: item.wall_seconds,
        )
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
            "sample_count": len(materialized),
            "accepted_sample_count": len(accepted),
            "oom_sample_count": sum(1 for sample in materialized if sample.oom),
            "samples": [
                {
                    "policy": asdict(sample.policy),
                    "wall_seconds": sample.wall_seconds,
                    "integrity_ok": sample.integrity_ok,
                    "oom": sample.oom,
                    "output_frames": sample.output_frames,
                    "expected_frames": sample.expected_frames,
                }
                for sample in materialized
            ],
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
