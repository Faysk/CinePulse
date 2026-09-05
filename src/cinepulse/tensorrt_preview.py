from __future__ import annotations

"""Optional, Preview-only TensorRT backend contract for CinePulse H7.

CinePulse does not bundle TensorRT, TensorRT GA libraries, third-party RIFE
TensorRT ports, converted engines, or model weights through this module. A
backend is discoverable only when the user has installed it separately and it
speaks the small external-runner protocol below.

NCNN/Vulkan remains the Stable and unconditional fallback. TensorRT permission
is exact-hardware evidence, never capability detection alone.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Literal


TENSORRT_PREVIEW_SCHEMA = 1
BackendModel = Literal["realesrgan", "rife"]
Precision = Literal["fp32", "fp16"]


@dataclass(frozen=True)
class TensorRtExternalBackend:
    runner: str
    version: str
    license_id: str
    redistributable_with_mit: bool = False

    @property
    def fingerprint(self) -> str:
        raw = f"{self.runner}|{self.version}|{self.license_id}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

    @property
    def stable_distribution_allowed(self) -> bool:
        # H7 is Preview-only by design. Even an Apache/MIT runner does not make
        # the proprietary/externally-installed runtime a Stable dependency.
        return False


def probe_external_backend(runner: str) -> TensorRtExternalBackend | None:
    """Probe a separately installed runner using a side-effect-free JSON call."""
    candidate = Path(runner)
    executable = str(candidate) if candidate.is_file() else runner
    try:
        result = subprocess.run(
            [executable, "--cinepulse-backend-info"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode:
        return None
    try:
        payload = json.loads(result.stdout)
        if payload.get("protocol") != "cinepulse-tensorrt-preview-v1":
            return None
        return TensorRtExternalBackend(
            runner=executable,
            version=str(payload["version"]),
            license_id=str(payload["license_id"]),
            redistributable_with_mit=bool(payload.get("redistributable_with_mit", False)),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


@dataclass(frozen=True)
class TensorRtKey:
    gpu_name: str
    driver: str
    tensorrt_version: str
    backend_fingerprint: str
    model: BackendModel
    model_fingerprint: str
    width: int
    height: int
    precision: Precision

    def token(self) -> str:
        return "|".join((
            " ".join(self.gpu_name.split()).lower() or "unknown-gpu",
            self.driver.strip().lower() or "unknown-driver",
            self.tensorrt_version.strip().lower() or "unknown-tensorrt",
            self.backend_fingerprint.strip().lower(),
            self.model,
            self.model_fingerprint.strip().lower(),
            f"{max(1, int(self.width))}x{max(1, int(self.height))}",
            self.precision,
        ))


@dataclass(frozen=True)
class TensorRtEvidence:
    baseline_seconds: float
    candidate_seconds: float
    integrity_ok: bool
    frame_count_ok: bool
    black_frame_ok: bool
    temporal_ok: bool
    psnr_db: float
    ssim: float
    vmaf_delta: float | None = None
    oom: bool = False

    @property
    def speedup(self) -> float:
        return self.baseline_seconds / self.candidate_seconds if self.candidate_seconds > 0 else 0.0

    @property
    def accepted(self) -> bool:
        # TensorRT is optional and invasive enough to demand a material win.
        # FP16/FP32 precision is encoded in the key; both still need the same
        # near-identical visual threshold against the tuned NCNN baseline.
        return bool(
            not self.oom
            and self.baseline_seconds > 0
            and self.candidate_seconds > 0
            and self.speedup >= 1.15
            and self.integrity_ok
            and self.frame_count_ok
            and self.black_frame_ok
            and self.temporal_ok
            and self.psnr_db >= 60.0
            and self.ssim >= 0.9999
            and (self.vmaf_delta is None or self.vmaf_delta >= -0.25)
        )


class TensorRtPreviewStore:
    VERSION = TENSORRT_PREVIEW_SCHEMA

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _load(self) -> dict[str, object]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return {"version": self.VERSION, "records": {}}
        if not isinstance(payload, dict) or payload.get("version") != self.VERSION or not isinstance(payload.get("records"), dict):
            return {"version": self.VERSION, "records": {}}
        return payload

    def approved(self, key: TensorRtKey, backend: TensorRtExternalBackend) -> bool:
        if key.backend_fingerprint != backend.fingerprint:
            return False
        record = self._load().get("records", {}).get(key.token())
        return bool(isinstance(record, dict) and record.get("accepted"))

    def record(self, key: TensorRtKey, backend: TensorRtExternalBackend, evidence: TensorRtEvidence) -> bool:
        if key.backend_fingerprint != backend.fingerprint or not evidence.accepted:
            return False
        payload = self._load()
        records = payload.setdefault("records", {})
        if not isinstance(records, dict):
            records = {}
            payload["records"] = records
        records[key.token()] = {
            "key": asdict(key),
            "backend": asdict(backend),
            "evidence": asdict(evidence),
            "speedup": evidence.speedup,
            "accepted": True,
            "preview_only": True,
            "updated_unix": time.time(),
        }
        self._atomic_write(payload)
        return True

    def invalidate(self, key: TensorRtKey) -> bool:
        payload = self._load()
        records = payload.get("records", {})
        if not isinstance(records, dict) or key.token() not in records:
            return False
        del records[key.token()]
        self._atomic_write(payload)
        return True

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


def build_external_command(
    backend: TensorRtExternalBackend,
    *,
    model: BackendModel,
    model_path: Path,
    input_path: Path,
    output_path: Path,
    width: int,
    height: int,
    precision: Precision,
) -> list[str]:
    """Build the strict external protocol invocation; does not install anything."""
    return [
        backend.runner,
        "--cinepulse-run",
        "--protocol", "cinepulse-tensorrt-preview-v1",
        "--model", model,
        "--model-path", str(model_path),
        "--input", str(input_path),
        "--output", str(output_path),
        "--width", str(max(1, int(width))),
        "--height", str(max(1, int(height))),
        "--precision", precision,
    ]
