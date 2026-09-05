from __future__ import annotations

"""Evidence-gated NVIDIA media acceleration policy.

Hardware Utilization MegaPack H5 deliberately separates *capability* from
*permission*. Seeing ``cuda``/NVDEC/NVENC in FFmpeg only means a candidate may
be benchmarked. Runtime acceleration is allowed only after an exact
hardware/driver/FFmpeg/media key has an integrity-, metadata- and quality-
approved record.

The stable CPU/zscale path therefore remains the fail-closed default.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from .media_profile import ColorProfile


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
GPU_MEDIA_SCHEMA = 1
DEFAULT_PSNR_FLOOR_DB = 55.0
DEFAULT_SSIM_FLOOR = 0.999


_CODEC_DECODERS: dict[str, tuple[str, ...]] = {
    "h264": ("h264_cuvid",),
    "hevc": ("hevc_cuvid",),
    "av1": ("av1_cuvid",),
    "vp9": ("vp9_cuvid",),
    "mpeg2video": ("mpeg2_cuvid",),
}


@dataclass(frozen=True)
class GpuMediaCapabilities:
    ffmpeg: str
    fingerprint: str
    hwaccels: frozenset[str]
    decoders: frozenset[str]
    filters: frozenset[str]
    encoders: frozenset[str]

    @property
    def cuda(self) -> bool:
        return "cuda" in self.hwaccels

    @property
    def cuda_scale(self) -> str | None:
        if "scale_cuda" in self.filters:
            return "scale_cuda"
        if "scale_npp" in self.filters:
            return "scale_npp"
        return None

    @property
    def nvenc(self) -> bool:
        return any(name.endswith("_nvenc") for name in self.encoders)

    def decoder_for(self, codec: str) -> str | None:
        for candidate in _CODEC_DECODERS.get(str(codec).lower(), ()):
            if candidate in self.decoders:
                return candidate
        return None


def _run_probe(ffmpeg: str, *args: str, timeout: float = 12.0) -> str:
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout or ""


def _names_from_listing(text: str) -> frozenset[str]:
    names: set[str] = set()
    for line in str(text).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("-"):
            continue
        parts = stripped.split()
        if not parts:
            continue
        if len(parts) >= 2 and re.fullmatch(r"[A-Z\.]{1,8}", parts[0]):
            names.add(parts[1].lower())
        elif len(parts) == 1 and re.fullmatch(r"[A-Za-z0-9_\-]+", parts[0]):
            names.add(parts[0].lower())
    return frozenset(names)


def detect_gpu_media_capabilities(ffmpeg: str) -> GpuMediaCapabilities:
    version = _run_probe(ffmpeg, "-version")
    hwaccels_text = _run_probe(ffmpeg, "-hwaccels")
    decoders_text = _run_probe(ffmpeg, "-decoders")
    filters_text = _run_probe(ffmpeg, "-filters")
    encoders_text = _run_probe(ffmpeg, "-encoders")
    fingerprint = hashlib.sha256(version.encode("utf-8", errors="replace")).hexdigest()[:20]
    return GpuMediaCapabilities(
        ffmpeg=str(ffmpeg),
        fingerprint=fingerprint,
        hwaccels=_names_from_listing(hwaccels_text),
        decoders=_names_from_listing(decoders_text),
        filters=_names_from_listing(filters_text),
        encoders=_names_from_listing(encoders_text),
    )


@dataclass(frozen=True)
class GpuMediaKey:
    gpu_name: str
    driver: str
    ffmpeg_fingerprint: str
    codec: str
    width: int
    height: int
    pixel_format: str
    bit_depth: int
    primaries: str
    transfer: str
    space: str
    color_range: str
    operation: str
    target_width: int = 0
    target_height: int = 0

    def token(self) -> str:
        target_width = max(1, int(self.target_width or self.width))
        target_height = max(1, int(self.target_height or self.height))
        values = (
            " ".join(str(self.gpu_name).split()).lower() or "unknown-gpu",
            str(self.driver).strip().lower() or "unknown-driver",
            str(self.ffmpeg_fingerprint).strip().lower() or "unknown-ffmpeg",
            str(self.codec).strip().lower() or "unknown-codec",
            f"{max(1, int(self.width))}x{max(1, int(self.height))}",
            f"{target_width}x{target_height}",
            str(self.pixel_format).strip().lower() or "unknown-pixfmt",
            str(max(1, int(self.bit_depth))),
            str(self.primaries).strip().lower() or "unknown",
            str(self.transfer).strip().lower() or "unknown",
            str(self.space).strip().lower() or "unknown",
            str(self.color_range).strip().lower() or "unknown",
            str(self.operation).strip().lower(),
        )
        return "|".join(values)

    @classmethod
    def from_profile(
        cls,
        *,
        gpu_name: str,
        driver: str,
        ffmpeg_fingerprint: str,
        codec: str,
        width: int,
        height: int,
        profile: ColorProfile,
        operation: str,
        target_width: int | None = None,
        target_height: int | None = None,
    ) -> "GpuMediaKey":
        return cls(
            gpu_name=gpu_name,
            driver=driver,
            ffmpeg_fingerprint=ffmpeg_fingerprint,
            codec=codec,
            width=width,
            height=height,
            pixel_format=profile.pixel_format,
            bit_depth=profile.bit_depth,
            primaries=profile.primaries,
            transfer=profile.transfer,
            space=profile.space,
            color_range=profile.range,
            operation=operation,
            target_width=target_width or width,
            target_height=target_height or height,
        )


@dataclass(frozen=True)
class GpuMediaPolicy:
    decoder: str
    scaler: str | None = None
    encoder: str | None = None
    gpu_index: int = 0

    def __post_init__(self) -> None:
        if int(self.gpu_index) < 0:
            raise ValueError("GPU index must be >= 0")
        if not str(self.decoder).strip():
            raise ValueError("GPU media policy requires an explicit decoder")

    @property
    def operation(self) -> str:
        if self.encoder and self.scaler:
            return "decode-scale-encode"
        if self.scaler:
            return "decode-scale"
        return "decode"

    def input_args(self) -> list[str]:
        return [
            "-hwaccel", "cuda",
            "-hwaccel_device", str(self.gpu_index),
            "-hwaccel_output_format", "cuda",
            "-c:v", self.decoder,
        ]

    def scale_filter(self, width: int, height: int, *, output_format: str | None = None) -> str:
        if not self.scaler:
            raise ValueError("policy does not include a CUDA scaler")
        suffix = f":format={output_format}" if output_format else ""
        return f"{self.scaler}=w={max(1, int(width))}:h={max(1, int(height))}{suffix}"


@dataclass(frozen=True)
class GpuMediaEvidence:
    policy: GpuMediaPolicy
    baseline_seconds: float
    candidate_seconds: float
    psnr_db: float
    ssim: float
    integrity_ok: bool
    metadata_ok: bool
    frame_count_ok: bool
    audio_sync_ok: bool

    @property
    def quality_ok(self) -> bool:
        return self.psnr_db >= DEFAULT_PSNR_FLOOR_DB and self.ssim >= DEFAULT_SSIM_FLOOR

    @property
    def accepted(self) -> bool:
        return bool(
            self.integrity_ok
            and self.metadata_ok
            and self.frame_count_ok
            and self.audio_sync_ok
            and self.quality_ok
            and self.baseline_seconds > 0
            and self.candidate_seconds > 0
        )

    @property
    def speedup(self) -> float:
        if self.candidate_seconds <= 0:
            return 0.0
        return self.baseline_seconds / self.candidate_seconds


class GpuMediaTuningStore:
    VERSION = GPU_MEDIA_SCHEMA

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

    def lookup(self, key: GpuMediaKey, capabilities: GpuMediaCapabilities) -> GpuMediaPolicy | None:
        record = self._load().get("records", {}).get(key.token())
        if not isinstance(record, dict) or not record.get("accepted"):
            return None
        raw = record.get("policy")
        if not isinstance(raw, dict):
            return None
        try:
            policy = GpuMediaPolicy(
                decoder=str(raw["decoder"]),
                scaler=str(raw["scaler"]) if raw.get("scaler") else None,
                encoder=str(raw["encoder"]) if raw.get("encoder") else None,
                gpu_index=int(raw.get("gpu_index", 0)),
            )
        except (KeyError, TypeError, ValueError):
            return None
        if not capabilities.cuda or policy.decoder not in capabilities.decoders:
            return None
        if policy.scaler and policy.scaler not in capabilities.filters:
            return None
        if policy.encoder and policy.encoder not in capabilities.encoders:
            return None
        return policy

    def record(self, key: GpuMediaKey, evidence: GpuMediaEvidence) -> bool:
        if evidence.policy.operation != key.operation or not evidence.accepted:
            return False
        payload = self._load()
        records = payload.setdefault("records", {})
        if not isinstance(records, dict):
            records = {}
            payload["records"] = records
        records[key.token()] = {
            "key": asdict(key),
            "policy": asdict(evidence.policy),
            "accepted": True,
            "baseline_seconds": float(evidence.baseline_seconds),
            "candidate_seconds": float(evidence.candidate_seconds),
            "speedup": float(evidence.speedup),
            "psnr_db": float(evidence.psnr_db),
            "ssim": float(evidence.ssim),
            "integrity_ok": bool(evidence.integrity_ok),
            "metadata_ok": bool(evidence.metadata_ok),
            "frame_count_ok": bool(evidence.frame_count_ok),
            "audio_sync_ok": bool(evidence.audio_sync_ok),
            "updated_unix": time.time(),
        }
        payload["version"] = self.VERSION
        self._atomic_write(payload)
        return True

    def invalidate(self, key: GpuMediaKey) -> bool:
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


def safe_candidate_policies(
    capabilities: GpuMediaCapabilities,
    *,
    codec: str,
    profile: ColorProfile,
    gpu_index: int = 0,
    allow_scale: bool = False,
    encoder: str | None = None,
) -> tuple[GpuMediaPolicy, ...]:
    """Return benchmark candidates, never runtime permission.

    H5 starts deliberately narrow. HDR/PQ/HLG and unknown color metadata remain
    on the authoritative CPU/zscale path until a dedicated GPU color pipeline
    has its own equivalence proof. SDR candidates must preserve the declared
    transfer/primaries/matrix/range; this function does not perform conversion.
    """

    if not capabilities.cuda or profile.hdr:
        return ()
    if any(value in {"", "unknown", "unspecified", "reserved"} for value in (
        profile.primaries, profile.transfer, profile.space, profile.range
    )):
        return ()
    decoder = capabilities.decoder_for(codec)
    if not decoder:
        return ()
    if encoder and encoder not in capabilities.encoders:
        return ()
    candidates = [GpuMediaPolicy(decoder=decoder, gpu_index=max(0, int(gpu_index)))]
    if allow_scale and capabilities.cuda_scale:
        candidates.append(
            GpuMediaPolicy(
                decoder=decoder,
                scaler=capabilities.cuda_scale,
                encoder=encoder,
                gpu_index=max(0, int(gpu_index)),
            )
        )
    return tuple(candidates)


def select_proven_policy(
    *,
    store: GpuMediaTuningStore,
    key: GpuMediaKey,
    capabilities: GpuMediaCapabilities,
    profile: ColorProfile,
) -> GpuMediaPolicy | None:
    """Fail closed to CPU for HDR, unknown color or missing exact evidence."""

    if profile.hdr:
        return None
    if any(value in {"", "unknown", "unspecified", "reserved"} for value in (
        profile.primaries, profile.transfer, profile.space, profile.range
    )):
        return None
    return store.lookup(key, capabilities)


def invalidate_on_runtime_failure(store: GpuMediaTuningStore, key: GpuMediaKey) -> bool:
    """A previously-approved policy that fails in production loses permission."""

    return store.invalidate(key)
