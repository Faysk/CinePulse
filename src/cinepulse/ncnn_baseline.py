from __future__ import annotations

"""Exact NCNN baseline proof used by optional H7 TensorRT experiments.

TensorRT is never benchmarked against an arbitrary PNG directory.  The caller
must present the H2/H3 tuning cache for the same GPU, driver, model and source
geometry.  The resulting fingerprint binds H7 evidence to the exact proven NCNN
policy; invalidating or changing that policy necessarily changes permission.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Literal

from .realesrgan_tuning import RealEsrganTuningKey, RealEsrganTuningStore
from .rife_tuning import RifeTuningKey, RifeTuningStore


NcnnModel = Literal["realesrgan", "rife"]


@dataclass(frozen=True)
class NcnnBaselineProof:
    model: NcnnModel
    tuning_key: str
    policy: dict[str, object]

    @property
    def fingerprint(self) -> str:
        raw = json.dumps(
            {"model": self.model, "tuning_key": self.tuning_key, "policy": self.policy},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def prove_ncnn_baseline(
    *,
    model: NcnnModel,
    cache: Path,
    gpu_name: str,
    vram_mb: int,
    driver: str,
    model_id: str,
    source_width: int,
    source_height: int,
    gpu_index: int = 0,
    scale: int = 2,
) -> NcnnBaselineProof | None:
    """Return proof only when an exact H2/H3 accepted tuning record exists."""
    if model == "realesrgan":
        key = RealEsrganTuningKey(
            gpu_name,
            max(0, int(vram_mb)),
            driver or "unknown-driver",
            model_id,
            max(1, int(source_width)),
            max(1, int(source_height)),
            max(1, int(scale)),
        )
        policy = RealEsrganTuningStore(Path(cache)).lookup(key, gpu_index=max(0, int(gpu_index)))
        if policy is None:
            return None
        return NcnnBaselineProof(model, key.token(), asdict(policy))

    if model == "rife":
        key = RifeTuningKey(
            gpu_name,
            max(0, int(vram_mb)),
            driver or "unknown-driver",
            model_id,
            max(1, int(source_width)),
            max(1, int(source_height)),
        )
        policy = RifeTuningStore(Path(cache)).lookup(key, gpu_index=max(0, int(gpu_index)))
        if policy is None:
            return None
        return NcnnBaselineProof(model, key.token(), asdict(policy))

    raise ValueError(f"unsupported NCNN baseline model: {model}")
