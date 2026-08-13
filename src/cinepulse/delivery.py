"""Container, codec and delivery-profile planning for CinePulse.

Core Integrity Phase 5 closes the audit gap where the UI accepted MP4/MOV/MKV/
WebM while the final worker always emitted HEVC + AAC.  This module is pure and
keeps three concerns explicit:

* container compatibility (what muxer can legally contain);
* delivery intent (streaming, master, archive, web);
* current stable capability envelope (<= 8K and <= 120 fps).

10K/12K and 144/240/480 fps remain visible in the experimental-oriented UI but
are blocked by the stable delivery plan until a proven encoder/hardware profile
exists.  Failing before render is intentionally preferable to discovering an
unsupported combination after hours of processing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from functools import lru_cache
import subprocess

from .color_pipeline import ColorPipeline


PROFILE_AUTO = "Automático pelo arquivo"
PROFILE_STREAMING = "YouTube / Streaming"
PROFILE_MASTER = "Master de arquivo"
PROFILE_ARCHIVE = "Arquivo eficiente"
PROFILE_WEB = "Web"
DELIVERY_PROFILES = (
    PROFILE_AUTO,
    PROFILE_STREAMING,
    PROFILE_MASTER,
    PROFILE_ARCHIVE,
    PROFILE_WEB,
)

SUPPORTED_SUFFIXES = (".mp4", ".mov", ".mkv", ".webm")

Severity = Literal["warning", "error"]


@dataclass(frozen=True)
class DeliveryIssue:
    code: str
    severity: Severity
    message: str


@dataclass(frozen=True)
class DeliveryPlan:
    profile: str
    container: str
    suffix: str
    video_codec: str
    audio_codec: str
    video_encoder: str
    audio_encoder: str
    pixel_format: str
    bit_depth: int
    hdr: bool
    lossless_video: bool
    lossless_audio: bool
    issues: tuple[DeliveryIssue, ...] = ()

    @property
    def blocking(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    @property
    def label(self) -> str:
        depth = f"{self.bit_depth}-bit"
        hdr = "HDR" if self.hdr else "SDR"
        audio = self.audio_codec.upper()
        return f"{self.container} • {self.video_codec} • {depth} {hdr} • {audio}"

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(issue.message for issue in self.issues if issue.severity == "warning")

    @property
    def errors(self) -> tuple[str, ...]:
        return tuple(issue.message for issue in self.issues if issue.severity == "error")

    def video_args(self, *, use_cpu: bool, nvenc_available: bool, bitrate_mbps: int, fps: int) -> list[str]:
        """Return final FFmpeg video encoder args for this delivery contract."""

        bitrate_mbps = max(4, int(bitrate_mbps))
        fps = max(1, int(fps))
        if self.video_codec == "HEVC":
            if not use_cpu and nvenc_available:
                return [
                    "-c:v", "hevc_nvenc", "-preset", "p7", "-tune", "hq",
                    "-profile:v", "main10" if self.bit_depth > 8 else "main",
                    "-rc", "vbr", "-cq", "14", "-b:v", f"{bitrate_mbps}M",
                    "-maxrate", f"{bitrate_mbps * 2}M", "-bufsize", f"{bitrate_mbps * 4}M",
                    "-spatial-aq", "1", "-temporal-aq", "1", "-aq-strength", "8",
                    "-multipass", "fullres", "-b_ref_mode", "middle",
                    "-g", str(max(12, fps // 2)), "-bf", "2",
                    "-pix_fmt", self.pixel_format,
                ]
            return [
                "-c:v", "libx265", "-preset", "medium", "-crf", "16",
                "-pix_fmt", self.pixel_format,
            ]
        if self.video_codec == "ProRes 422 HQ":
            return [
                "-c:v", "prores_ks", "-profile:v", "3", "-vendor", "apl0",
                "-bits_per_mb", "8000", "-pix_fmt", "yuv422p10le",
            ]
        if self.video_codec == "VP9":
            profile = "2" if self.bit_depth > 8 else "0"
            return [
                "-c:v", "libvpx-vp9", "-deadline", "good", "-cpu-used", "2",
                "-row-mt", "1", "-tile-columns", "2", "-frame-parallel", "1",
                "-crf", "18", "-b:v", "0", "-profile:v", profile,
                "-pix_fmt", self.pixel_format,
            ]
        if self.video_codec == "FFV1":
            return [
                "-c:v", "ffv1", "-level", "3", "-coder", "1", "-context", "1",
                "-g", "1", "-slicecrc", "1", "-pix_fmt", self.pixel_format,
            ]
        raise ValueError(f"Unsupported delivery video codec: {self.video_codec}")

    def audio_args(self) -> list[str]:
        """Return audio encoder args without silently forcing channel layout.

        Streaming profiles normalize to 48 kHz because that is the delivery
        contract; master/archive profiles preserve the source sample rate and
        channels whenever the selected codec/container allows it.
        """

        if self.audio_codec == "AAC":
            return ["-c:a", "aac", "-b:a", "384k", "-ar", "48000"]
        if self.audio_codec == "PCM 24-bit":
            return ["-c:a", "pcm_s24le"]
        if self.audio_codec == "FLAC":
            return ["-c:a", "flac", "-compression_level", "8"]
        if self.audio_codec == "Opus":
            return ["-c:a", "libopus", "-b:a", "256k", "-vbr", "on", "-ar", "48000"]
        raise ValueError(f"Unsupported delivery audio codec: {self.audio_codec}")

    def muxer_args(self) -> list[str]:
        if self.suffix == ".mp4":
            # hvc1 improves HEVC identification in Apple/QuickTime ecosystems.
            return ["-tag:v", "hvc1", "-movflags", "+faststart"] if self.video_codec == "HEVC" else ["-movflags", "+faststart"]
        if self.suffix == ".mov":
            return ["-movflags", "+faststart"] if self.video_codec == "HEVC" else []
        return []


def default_profile_for_suffix(suffix: str) -> str:
    suffix = suffix.lower()
    return {
        ".mp4": PROFILE_STREAMING,
        ".mov": PROFILE_MASTER,
        ".mkv": PROFILE_ARCHIVE,
        ".webm": PROFILE_WEB,
    }.get(suffix, PROFILE_AUTO)


def required_suffix_for_profile(profile: str) -> str | None:
    return {
        PROFILE_STREAMING: ".mp4",
        PROFILE_MASTER: ".mov",
        PROFILE_ARCHIVE: ".mkv",
        PROFILE_WEB: ".webm",
    }.get(profile)


def suggested_extension(profile: str, current_suffix: str = ".mp4") -> str:
    return required_suffix_for_profile(profile) or (current_suffix.lower() if current_suffix.lower() in SUPPORTED_SUFFIXES else ".mp4")


def _container_name(suffix: str) -> str:
    return {".mp4": "MP4", ".mov": "MOV", ".mkv": "MKV", ".webm": "WebM"}.get(suffix, suffix.upper().lstrip("."))


@lru_cache(maxsize=4)
def detect_ffmpeg_encoders(ffmpeg: str) -> frozenset[str]:
    """Return encoder names advertised by the exact FFmpeg binary in use."""
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False, timeout=12,
        )
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    names: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] and parts[0][0] in {"V", "A", "S", "."}:
            # Encoder rows are flags + encoder name + description.
            if len(parts[0]) >= 6:
                names.add(parts[1])
    return frozenset(names)


def _availability_issues(
    *, video_codec: str, audio_codec: str, available_encoders: frozenset[str] | set[str],
    use_cpu: bool, nvenc_available: bool,
) -> list[DeliveryIssue]:
    available = set(available_encoders)
    issues: list[DeliveryIssue] = []
    if video_codec == "HEVC":
        preferred = "libx265" if use_cpu or not nvenc_available else "hevc_nvenc"
        fallback = "libx265"
        if preferred not in available and fallback not in available:
            issues.append(DeliveryIssue("CP-009-ENCODER", "error", "Nenhum encoder HEVC compatível (hevc_nvenc/libx265) foi encontrado no FFmpeg ativo."))
    else:
        required_video = {"ProRes 422 HQ": "prores_ks", "VP9": "libvpx-vp9", "FFV1": "ffv1"}.get(video_codec)
        if required_video and required_video not in available:
            issues.append(DeliveryIssue("CP-009-ENCODER", "error", f"O encoder {required_video} necessário para {video_codec} não existe no FFmpeg ativo."))
    required_audio = {"AAC": "aac", "PCM 24-bit": "pcm_s24le", "FLAC": "flac", "Opus": "libopus"}.get(audio_codec)
    if required_audio and required_audio not in available:
        issues.append(DeliveryIssue("CP-015-AUDIO-ENCODER", "error", f"O encoder de áudio {required_audio} necessário para {audio_codec} não existe no FFmpeg ativo."))
    return issues


def build_delivery_plan(
    *,
    output: str | Path,
    profile: str,
    color_plan: ColorPipeline,
    width: int,
    height: int,
    fps: float,
    preview: bool = False,
    use_cpu: bool = False,
    nvenc_available: bool = False,
    available_encoders: frozenset[str] | set[str] | None = None,
) -> DeliveryPlan:
    """Resolve a legal and intentionally conservative final delivery plan."""

    suffix = ".mp4" if preview else Path(output).suffix.lower()
    issues: list[DeliveryIssue] = []
    if suffix not in SUPPORTED_SUFFIXES:
        issues.append(DeliveryIssue("CP-008-CONTAINER", "error", "Use MP4, MOV, MKV ou WebM para a saída final."))
        suffix = suffix or ".mp4"

    effective_profile = PROFILE_STREAMING if preview else (default_profile_for_suffix(suffix) if profile == PROFILE_AUTO else profile)
    expected_suffix = required_suffix_for_profile(effective_profile)
    if expected_suffix and suffix != expected_suffix:
        issues.append(DeliveryIssue(
            "CP-008-PROFILE",
            "error",
            f"O perfil ‘{effective_profile}’ exige saída {expected_suffix.upper()}; o arquivo atual usa {suffix.upper() or 'sem extensão'}.",
        ))

    bit_depth = 10 if color_plan.output.bit_depth > 8 else 8
    hdr = bool(color_plan.output.hdr)

    if effective_profile == PROFILE_MASTER:
        video_codec, audio_codec = "ProRes 422 HQ", "PCM 24-bit"
        video_encoder, audio_encoder = "prores_ks", "pcm_s24le"
        pixel_format = "yuv422p10le"
        lossless_audio = True
        lossless_video = False  # visually lossless mezzanine, not mathematically lossless
    elif effective_profile == PROFILE_ARCHIVE:
        video_codec, audio_codec = "HEVC", "FLAC"
        video_encoder, audio_encoder = "libx265/hevc_nvenc", "flac"
        pixel_format = "yuv420p10le" if bit_depth > 8 else "yuv420p"
        lossless_audio = True
        lossless_video = False
    elif effective_profile == PROFILE_WEB:
        video_codec, audio_codec = "VP9", "Opus"
        video_encoder, audio_encoder = "libvpx-vp9", "libopus"
        pixel_format = "yuv420p10le" if bit_depth > 8 else "yuv420p"
        lossless_audio = False
        lossless_video = False
    else:  # streaming + preview
        video_codec, audio_codec = "HEVC", "AAC"
        video_encoder, audio_encoder = "libx265/hevc_nvenc", "aac"
        pixel_format = "p010le" if bit_depth > 8 else "yuv420p"
        lossless_audio = False
        lossless_video = False

    # Stable release envelope.  The UI may expose larger/HFR values for future
    # experiments, but Phase 5 refuses to pretend they are generally compatible.
    if width > 7680 or height > 4320:
        issues.append(DeliveryIssue(
            "CP-009-RESOLUTION",
            "error",
            f"{width}×{height} excede o perfil estável atual de 8K. 10K/12K permanecem experimentais até validação real de encoder/hardware.",
        ))
    if fps > 120.01:
        issues.append(DeliveryIssue(
            "CP-009-FPS",
            "error",
            f"{fps:g} fps excede o perfil estável atual de 120 fps. 144/240/480 fps permanecem experimentais até validação real.",
        ))
    elif fps > 60.01:
        issues.append(DeliveryIssue(
            "CP-009-HFR",
            "warning",
            f"{fps:g} fps é HFR; confirme compatibilidade do player/plataforma de destino.",
        ))

    if suffix == ".webm" and video_codec != "VP9":
        issues.append(DeliveryIssue("CP-008-WEBM-VIDEO", "error", "WebM exige VP9/AV1 neste CinePulse; HEVC não será muxado em WebM."))
    if suffix == ".webm" and audio_codec != "Opus":
        issues.append(DeliveryIssue("CP-008-WEBM-AUDIO", "error", "WebM usa Opus neste CinePulse; AAC não será muxado em WebM."))
    if suffix == ".mp4" and audio_codec not in {"AAC"}:
        issues.append(DeliveryIssue("CP-008-MP4-AUDIO", "error", "O perfil MP4 estável usa AAC para máxima compatibilidade."))
    if suffix == ".mov" and effective_profile == PROFILE_MASTER and audio_codec != "PCM 24-bit":
        issues.append(DeliveryIssue("CP-015-MASTER-AUDIO", "error", "Master MOV deve usar PCM 24-bit nesta fase."))
    if hdr and effective_profile == PROFILE_WEB:
        issues.append(DeliveryIssue(
            "CP-009-WEB-HDR",
            "warning",
            "WebM/VP9 10-bit pode carregar HDR, mas compatibilidade HDR em browsers/players varia; valide o destino real.",
        ))
    if effective_profile == PROFILE_MASTER and bit_depth < 10:
        # ProRes 422 HQ stores 10-bit, but this is a delivery container property,
        # not a claim that an 8-bit source gained information.
        bit_depth = 10

    if available_encoders is not None:
        issues.extend(_availability_issues(
            video_codec=video_codec, audio_codec=audio_codec, available_encoders=available_encoders,
            use_cpu=use_cpu, nvenc_available=nvenc_available,
        ))

    return DeliveryPlan(
        profile=effective_profile,
        container=_container_name(suffix),
        suffix=suffix,
        video_codec=video_codec,
        audio_codec=audio_codec,
        video_encoder=video_encoder,
        audio_encoder=audio_encoder,
        pixel_format=pixel_format,
        bit_depth=bit_depth,
        hdr=hdr,
        lossless_video=lossless_video,
        lossless_audio=lossless_audio,
        issues=tuple(issues),
    )
