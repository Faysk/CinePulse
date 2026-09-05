from __future__ import annotations

"""Evidence contract for H5 CUDA-resident decode/scale/NVENC delivery.

Both sides of the physical benchmark use the exact same NVENC contract. The
baseline feeds it from CPU decode/zscale, while the candidate feeds it from
NVDEC/CUDA (and optional CUDA scale). This isolates residency/transfer changes
from encoder-quality changes.

No policy in this module is permission by itself. Runtime use requires an exact
accepted record for hardware, driver, FFmpeg, source/color geometry and the
complete encoder contract.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Literal


GPU_ENCODE_SCHEMA = 1
Codec = Literal["h264_nvenc", "hevc_nvenc", "av1_nvenc"]
RateControl = Literal["constqp", "vbr", "cbr"]


@dataclass(frozen=True)
class NvencContract:
    encoder: Codec
    preset: str
    rate_control: RateControl
    pixel_format: str
    profile: str = ""
    cq: int | None = None
    qp: int | None = None
    bitrate_kbps: int | None = None
    maxrate_kbps: int | None = None
    bufsize_kbps: int | None = None
    lookahead: int = 0
    bframes: int = 0

    def __post_init__(self) -> None:
        if not self.preset.strip():
            raise ValueError("NVENC contract requires preset")
        if not self.pixel_format.strip():
            raise ValueError("NVENC contract requires pixel format")
        if self.cq is not None and not 0 <= int(self.cq) <= 51:
            raise ValueError("NVENC cq must be 0..51")
        if self.qp is not None and not 0 <= int(self.qp) <= 51:
            raise ValueError("NVENC qp must be 0..51")
        if self.lookahead < 0 or self.bframes < 0:
            raise ValueError("NVENC lookahead/bframes must be non-negative")
        if self.rate_control == "constqp" and self.qp is None:
            raise ValueError("constqp requires qp")
        if self.rate_control in {"vbr", "cbr"} and not self.bitrate_kbps:
            raise ValueError(f"{self.rate_control} requires bitrate_kbps")

    def token(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def ffmpeg_args(self) -> list[str]:
        args = ["-c:v", self.encoder, "-preset", self.preset, "-rc", self.rate_control, "-pix_fmt", self.pixel_format]
        if self.profile:
            args += ["-profile:v", self.profile]
        if self.qp is not None:
            args += ["-qp", str(self.qp)]
        if self.cq is not None:
            args += ["-cq", str(self.cq)]
        if self.bitrate_kbps is not None:
            args += ["-b:v", f"{self.bitrate_kbps}k"]
        if self.maxrate_kbps is not None:
            args += ["-maxrate", f"{self.maxrate_kbps}k"]
        if self.bufsize_kbps is not None:
            args += ["-bufsize", f"{self.bufsize_kbps}k"]
        if self.lookahead:
            args += ["-rc-lookahead", str(self.lookahead)]
        args += ["-bf", str(self.bframes)]
        return args


@dataclass(frozen=True)
class ResidentEncodeKey:
    gpu_name: str
    driver: str
    ffmpeg_fingerprint: str
    source_codec: str
    source_width: int
    source_height: int
    target_width: int
    target_height: int
    source_pixel_format: str
    primaries: str
    transfer: str
    space: str
    color_range: str
    scaler: str
    encode_contract: str

    def token(self) -> str:
        return "|".join((
            " ".join(self.gpu_name.split()).lower() or "unknown-gpu",
            self.driver.strip().lower() or "unknown-driver",
            self.ffmpeg_fingerprint.strip().lower() or "unknown-ffmpeg",
            self.source_codec.strip().lower(),
            f"{max(1, self.source_width)}x{max(1, self.source_height)}",
            f"{max(1, self.target_width)}x{max(1, self.target_height)}",
            self.source_pixel_format.strip().lower(),
            self.primaries.strip().lower(), self.transfer.strip().lower(), self.space.strip().lower(), self.color_range.strip().lower(),
            self.scaler.strip().lower() or "none",
            self.encode_contract.strip().lower(),
        ))


@dataclass(frozen=True)
class ResidentEncodeEvidence:
    baseline_seconds: float
    candidate_seconds: float
    decoded_psnr_db: float
    decoded_ssim: float
    frame_count_ok: bool
    metadata_ok: bool
    audio_sync_ok: bool
    seek_alignment_ok: bool
    bitstream_decodes_ok: bool
    baseline_size_bytes: int
    candidate_size_bytes: int

    @property
    def speedup(self) -> float:
        return self.baseline_seconds / self.candidate_seconds if self.candidate_seconds > 0 else 0.0

    @property
    def accepted(self) -> bool:
        # Both outputs use the exact same lossy encoder contract, so a very high
        # pairwise threshold is appropriate. CUDA residency must not make the
        # encoder see materially different frames.
        return bool(
            self.baseline_seconds > 0 and self.candidate_seconds > 0
            and self.speedup >= 1.03
            and self.decoded_psnr_db >= 55.0
            and self.decoded_ssim >= 0.999
            and self.frame_count_ok and self.metadata_ok and self.audio_sync_ok
            and self.seek_alignment_ok and self.bitstream_decodes_ok
            and self.baseline_size_bytes > 0 and self.candidate_size_bytes > 0
        )


class ResidentEncodeStore:
    VERSION = GPU_ENCODE_SCHEMA

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

    def approved(self, key: ResidentEncodeKey) -> bool:
        record = self._load().get("records", {}).get(key.token())
        return bool(isinstance(record, dict) and record.get("accepted"))

    def record(self, key: ResidentEncodeKey, contract: NvencContract, evidence: ResidentEncodeEvidence) -> bool:
        if key.encode_contract != contract.token() or not evidence.accepted:
            return False
        payload = self._load()
        records = payload.setdefault("records", {})
        if not isinstance(records, dict):
            records = {}
            payload["records"] = records
        records[key.token()] = {
            "key": asdict(key), "contract": asdict(contract), "evidence": asdict(evidence),
            "accepted": True, "speedup": evidence.speedup, "updated_unix": time.time(),
        }
        self._atomic_write(payload)
        return True

    def invalidate(self, key: ResidentEncodeKey) -> bool:
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
                handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, self.path)
        finally:
            try: temp.unlink(missing_ok=True)
            except OSError: pass
