from __future__ import annotations

"""Preview-only GPU compositor contracts for CinePulse H6.

The H6 envelope targets the part FFmpeg/CUDA can express reliably today:
normal alpha media-layer composition with ``overlay_cuda``. Procedural music
VFX, arbitrary rotation and non-normal blend modes remain on the established
NumPy renderer until an actual shader backend has its own visual-equivalence
evidence.

Capability is never permission. Runtime use requires an exact accepted record
for GPU/driver/FFmpeg/base-profile/compositor contract and otherwise fails
closed to the existing CPU compositor.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Iterable, Literal

from .gpu_media import CREATE_NO_WINDOW


COMPOSITOR_SCHEMA = 3
COMPOSITOR_REFERENCE_ID = "composer-numpy-rgba-v1"
COMPOSITOR_PSNR_FLOOR_DB = 80.0
COMPOSITOR_SSIM_FLOOR = 0.999999
COMPOSITOR_MIN_SPEEDUP = 1.03
COMPOSITOR_MAX_STACK_LAYERS = 4

LayerKind = Literal["png", "gif", "apng", "webp", "video-alpha"]
BlendMode = Literal["normal", "multiply", "screen", "add", "overlay"]
AudioBinding = Literal["none", "master", "vocals", "drums", "bass", "other"]


@dataclass(frozen=True)
class OverlayLayer:
    source: str
    kind: LayerKind
    x: float = 0.5
    y: float = 0.5
    scale: float = 1.0
    opacity: float = 1.0
    z_order: int = 0
    blend: BlendMode = "normal"
    rotation_degrees: float = 0.0
    loop: bool = True
    spin_rpm: float = 0.0
    pulse: float = 0.0
    beat_reaction: float = 0.0
    audio_binding: AudioBinding = "none"

    def __post_init__(self) -> None:
        if self.kind not in {"png", "gif", "apng", "webp", "video-alpha"}:
            raise ValueError("unsupported overlay layer kind")
        if not 0.0 <= float(self.x) <= 1.0 or not 0.0 <= float(self.y) <= 1.0:
            raise ValueError("layer x/y must be normalized to 0..1")
        if not 0.01 <= float(self.scale) <= 16.0:
            raise ValueError("layer scale must be within 0.01..16")
        if not 0.0 <= float(self.opacity) <= 1.0:
            raise ValueError("layer opacity must be within 0..1")
        if self.blend not in {"normal", "multiply", "screen", "add", "overlay"}:
            raise ValueError("unsupported overlay blend mode")
        if not 0.0 <= float(self.pulse) <= 2.0 or not 0.0 <= float(self.beat_reaction) <= 2.0:
            raise ValueError("pulse/beat reaction must be within 0..2")

    @property
    def requires_dynamic_transform(self) -> bool:
        return bool(abs(self.spin_rpm) > 1e-9 or self.pulse > 0 or self.beat_reaction > 0)

    @property
    def requires_rotation(self) -> bool:
        return abs(float(self.rotation_degrees)) > 1e-9 or abs(float(self.spin_rpm)) > 1e-9

    def contract_token(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def canonical_overlay_stack(layers: Iterable[OverlayLayer]) -> tuple[OverlayLayer, ...]:
    indexed = tuple(enumerate(layers))
    return tuple(layer for _index, layer in sorted(indexed, key=lambda item: (item[1].z_order, item[0])))


def overlay_stack_contract_token(layers: Iterable[OverlayLayer]) -> str:
    ordered = canonical_overlay_stack(layers)
    payload = [asdict(layer) for layer in ordered]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class GpuCompositorCapabilities:
    ffmpeg: str
    fingerprint: str
    cuda: bool
    overlay_cuda: bool
    scale_cuda: bool
    hwupload_cuda: bool

    @property
    def media_layers_supported(self) -> bool:
        return self.cuda and self.overlay_cuda and self.hwupload_cuda


def _probe(ffmpeg: str, *args: str) -> str:
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=12,
            check=False,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout or ""


def detect_gpu_compositor_capabilities(ffmpeg: str) -> GpuCompositorCapabilities:
    version = _probe(ffmpeg, "-version")
    filters = _probe(ffmpeg, "-filters").lower()
    hwaccels = _probe(ffmpeg, "-hwaccels").lower()
    fingerprint = hashlib.sha256(version.encode("utf-8", errors="replace")).hexdigest()[:20]
    return GpuCompositorCapabilities(
        ffmpeg=str(ffmpeg),
        fingerprint=fingerprint,
        cuda="cuda" in hwaccels,
        overlay_cuda="overlay_cuda" in filters,
        scale_cuda="scale_cuda" in filters or "scale_npp" in filters,
        hwupload_cuda="hwupload_cuda" in filters,
    )


@dataclass(frozen=True)
class GpuCompositorKey:
    gpu_name: str
    driver: str
    ffmpeg_fingerprint: str
    width: int
    height: int
    fps_milli: int
    pixel_format: str
    primaries: str
    transfer: str
    space: str
    color_range: str
    layer_contract: str

    def token(self) -> str:
        return "|".join(
            (
                " ".join(self.gpu_name.split()).lower() or "unknown-gpu",
                self.driver.strip().lower() or "unknown-driver",
                self.ffmpeg_fingerprint.strip().lower() or "unknown-ffmpeg",
                f"{max(1, int(self.width))}x{max(1, int(self.height))}",
                str(max(1, int(self.fps_milli))),
                self.pixel_format.strip().lower() or "unknown-pixfmt",
                self.primaries.strip().lower() or "unknown",
                self.transfer.strip().lower() or "unknown",
                self.space.strip().lower() or "unknown",
                self.color_range.strip().lower() or "unknown",
                self.layer_contract.strip().lower(),
            )
        )


@dataclass(frozen=True)
class GpuCompositorEvidence:
    baseline_seconds: float
    candidate_seconds: float
    psnr_db: float
    ssim: float
    frame_count_ok: bool
    metadata_ok: bool
    alpha_contract_ok: bool
    audio_sync_ok: bool
    reference_id: str = COMPOSITOR_REFERENCE_ID

    @property
    def speedup(self) -> float:
        return self.baseline_seconds / self.candidate_seconds if self.candidate_seconds > 0 else 0.0

    @property
    def accepted(self) -> bool:
        return bool(
            self.reference_id == COMPOSITOR_REFERENCE_ID
            and self.baseline_seconds > 0
            and self.candidate_seconds > 0
            and self.speedup >= COMPOSITOR_MIN_SPEEDUP
            and self.psnr_db >= COMPOSITOR_PSNR_FLOOR_DB
            and self.ssim >= COMPOSITOR_SSIM_FLOOR
            and self.frame_count_ok
            and self.metadata_ok
            and self.alpha_contract_ok
            and self.audio_sync_ok
        )


class GpuCompositorStore:
    VERSION = COMPOSITOR_SCHEMA

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _load(self) -> dict[str, object]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return {"version": self.VERSION, "records": {}}
        if (
            not isinstance(payload, dict)
            or payload.get("version") != self.VERSION
            or not isinstance(payload.get("records"), dict)
        ):
            return {"version": self.VERSION, "records": {}}
        return payload

    def approved(self, key: GpuCompositorKey, caps: GpuCompositorCapabilities) -> bool:
        if not caps.media_layers_supported:
            return False
        record = self._load().get("records", {}).get(key.token())
        if not isinstance(record, dict) or not record.get("accepted"):
            return False
        evidence = record.get("evidence")
        return bool(
            isinstance(evidence, dict)
            and evidence.get("reference_id") == COMPOSITOR_REFERENCE_ID
        )

    def record(self, key: GpuCompositorKey, evidence: GpuCompositorEvidence) -> bool:
        if not evidence.accepted:
            return False
        payload = self._load()
        records = payload.setdefault("records", {})
        if not isinstance(records, dict):
            records = {}
            payload["records"] = records
        records[key.token()] = {
            "key": asdict(key),
            "accepted": True,
            "evidence": asdict(evidence),
            "speedup": evidence.speedup,
            "updated_unix": time.time(),
        }
        payload["version"] = self.VERSION
        self._atomic_write(payload)
        return True

    def invalidate(self, key: GpuCompositorKey) -> bool:
        payload = self._load()
        records = payload.get("records", {})
        if not isinstance(records, dict) or key.token() not in records:
            return False
        del records[key.token()]
        self._atomic_write(payload)
        return True

    def _atomic_write(self, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=self.path.name + ".",
            suffix=".tmp",
            dir=self.path.parent,
        )
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


def _static_layer_supported(layer: OverlayLayer) -> bool:
    return bool(
        layer.blend == "normal"
        and layer.scale == 1.0
        and not layer.requires_rotation
        and not layer.requires_dynamic_transform
    )


def cuda_layer_eligible(layer: OverlayLayer, caps: GpuCompositorCapabilities) -> bool:
    """Return benchmark eligibility, not runtime permission."""
    return caps.media_layers_supported and _static_layer_supported(layer)


def cuda_stack_eligible(layers: Iterable[OverlayLayer], caps: GpuCompositorCapabilities) -> bool:
    ordered = canonical_overlay_stack(layers)
    return bool(
        caps.media_layers_supported
        and 1 <= len(ordered) <= COMPOSITOR_MAX_STACK_LAYERS
        and all(_static_layer_supported(layer) for layer in ordered)
    )


def overlay_cuda_position(
    layer: OverlayLayer,
    canvas_width: int,
    canvas_height: int,
) -> tuple[str, str]:
    x = max(0.0, min(1.0, float(layer.x)))
    y = max(0.0, min(1.0, float(layer.y)))
    return (
        f"({max(1, int(canvas_width))}-overlay_w)*{x:.8f}",
        f"({max(1, int(canvas_height))}-overlay_h)*{y:.8f}",
    )


def build_cuda_overlay_stack_filter(
    layers: Iterable[OverlayLayer],
    *,
    canvas_width: int,
    canvas_height: int,
) -> str:
    """Build a bounded, deterministic CUDA overlay stack.

    The whole ordered stack is one evidence unit. A record for an individual
    layer can never unlock a stack because repeated alpha rounding and ordering
    can change the result. The graph stays GPU-resident between overlay stages
    and downloads exactly once at the end.
    """
    ordered = canonical_overlay_stack(layers)
    if not 1 <= len(ordered) <= COMPOSITOR_MAX_STACK_LAYERS:
        raise ValueError(f"CUDA compositor stack must contain 1..{COMPOSITOR_MAX_STACK_LAYERS} layers")
    if any(not _static_layer_supported(layer) for layer in ordered):
        raise ValueError("stack contains an unproven transform/blend outside H6 CUDA envelope")

    chains: list[str] = ["[0:v]format=yuv420p,hwupload_cuda[basegpu]"]
    previous = "basegpu"
    for index, layer in enumerate(ordered, start=1):
        prep = ["format=yuva420p"]
        if layer.opacity < 0.999999:
            prep.append(f"colorchannelmixer=aa={layer.opacity:.8f}")
        prep.append("hwupload_cuda")
        layer_label = f"layergpu{index}"
        chains.append(f"[{index}:v]{','.join(prep)}[{layer_label}]")
        x_expr, y_expr = overlay_cuda_position(layer, canvas_width, canvas_height)
        output_label = f"stackgpu{index}"
        chains.append(
            f"[{previous}][{layer_label}]overlay_cuda=x='{x_expr}':y='{y_expr}'[{output_label}]"
        )
        previous = output_label
    chains.append(f"[{previous}]hwdownload,format=yuv420p[vout]")
    return ";".join(chains)


def build_cuda_overlay_filter(
    layer: OverlayLayer,
    *,
    canvas_width: int,
    canvas_height: int,
    layer_width: int,
    layer_height: int,
) -> str:
    """Compatibility wrapper for the original single-layer H6 benchmark."""
    del layer_width, layer_height
    return build_cuda_overlay_stack_filter(
        (layer,),
        canvas_width=canvas_width,
        canvas_height=canvas_height,
    )
