from __future__ import annotations

from dataclasses import dataclass


HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}


@dataclass(frozen=True)
class ColorProfile:
    primaries: str
    transfer: str
    space: str
    range: str
    pixel_format: str
    bit_depth: int
    hdr: bool

    @classmethod
    def from_probe(cls, media: dict) -> "ColorProfile":
        streams = media.get("streams", []) if isinstance(media, dict) else []
        video = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
        pixel_format = str(video.get("pix_fmt") or "unknown")
        bits = video.get("bits_per_raw_sample")
        try:
            bit_depth = int(bits or 0)
        except (TypeError, ValueError):
            bit_depth = 0
        if not bit_depth:
            bit_depth = 10 if any(token in pixel_format for token in ("10", "p010", "p210")) else 8
        primaries = str(video.get("color_primaries") or "unknown")
        transfer = str(video.get("color_transfer") or "unknown")
        space = str(video.get("color_space") or "unknown")
        color_range = str(video.get("color_range") or "unknown")
        # BT.2020 primaries alone do not mean HDR; wide-gamut SDR exists.
        # Treat only PQ/HLG transfer functions as explicit HDR so the pipeline
        # does not tone-map a BT.2020 SDR source merely because of its gamut.
        hdr = transfer in HDR_TRANSFERS
        return cls(primaries, transfer, space, color_range, pixel_format, bit_depth, hdr)

    @property
    def label(self) -> str:
        if self.hdr:
            standard = "HDR10" if self.transfer == "smpte2084" else "HLG" if self.transfer == "arib-std-b67" else "HDR"
        else:
            standard = "SDR"
        return f"{standard} • {self.primaries}/{self.transfer} • {self.bit_depth}-bit"

    def warnings_for_sdr_pipeline(self, effects_enabled: bool) -> list[str]:
        """Legacy compatibility helper.

        Phase 4 no longer has a globally SDR-only final pipeline.  The active
        Studio uses ``color_pipeline.py`` for the authoritative decision; this
        method remains only for callers outside the main worker.
        """
        warnings: list[str] = []
        if self.hdr:
            if effects_enabled:
                warnings.append("A fonte é HDR; VFX atuais acionam tone mapping explícito para SDR BT.709 antes da composição.")
            else:
                warnings.append("A fonte é HDR; o caminho limpo preserva HDR/10-bit, enquanto estágios SDR-only são sinalizados pelo RenderPlan.")
        return warnings


def audio_codec_for_container(suffix: str, lossless: bool = False) -> list[str]:
    """Legacy/container-aware audio helper retained for external callers.

    The active Studio uses :mod:`cinepulse.delivery`; this helper now mirrors
    the same legal defaults instead of returning AAC for WebM.
    """
    suffix = suffix.lower()
    if suffix == ".webm":
        return ["-c:a", "libopus", "-b:a", "256k", "-ar", "48000"]
    if lossless and suffix == ".mkv":
        return ["-c:a", "flac"]
    if lossless and suffix == ".mov":
        return ["-c:a", "pcm_s24le"]
    return ["-c:a", "aac", "-b:a", "384k", "-ar", "48000"]

