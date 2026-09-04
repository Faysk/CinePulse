"""Color management policy for CinePulse Core Integrity Phase 4.

This module keeps color decisions explicit and testable.  It deliberately
separates *preserving* HDR from *converting* HDR to SDR: metadata alone never
counts as a color conversion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .media_profile import ColorProfile


ColorIntent = Literal["preserve_hdr", "tone_map_sdr", "preserve_sdr"]


def _known(value: str) -> bool:
    return bool(value and value not in {"unknown", "unspecified", "reserved", "None"})


def _range_name(value: str) -> str:
    value = (value or "unknown").lower()
    if value in {"pc", "full"}:
        return "full"
    return "limited"


def _range_arg(value: str) -> str:
    return "pc" if _range_name(value) == "full" else "tv"


def _default_sdr_profile(source: ColorProfile, bit_depth: int) -> ColorProfile:
    return ColorProfile(
        primaries="bt709",
        transfer="bt709",
        space="bt709",
        range="tv",
        pixel_format="yuv420p10le" if bit_depth > 8 else "yuv420p",
        bit_depth=bit_depth,
        hdr=False,
    )


def _preserved_sdr_profile(source: ColorProfile) -> ColorProfile:
    # HD/user-generated SDR is overwhelmingly BT.709, but unknown metadata must
    # remain visible as an assumption instead of pretending the input declared it.
    primaries = source.primaries if _known(source.primaries) else "bt709"
    transfer = source.transfer if _known(source.transfer) else "bt709"
    space = source.space if _known(source.space) else "bt709"
    bit_depth = 10 if source.bit_depth > 8 else 8
    return ColorProfile(
        primaries=primaries,
        transfer=transfer,
        space=space,
        range="pc" if _range_name(source.range) == "full" else "tv",
        pixel_format="yuv420p10le" if bit_depth > 8 else "yuv420p",
        bit_depth=bit_depth,
        hdr=False,
    )


def _preserved_hdr_profile(source: ColorProfile) -> ColorProfile:
    return ColorProfile(
        primaries=source.primaries if _known(source.primaries) else "bt2020",
        transfer=source.transfer if _known(source.transfer) else "smpte2084",
        space=source.space if _known(source.space) else "bt2020nc",
        range="pc" if _range_name(source.range) == "full" else "tv",
        pixel_format="yuv420p10le",
        bit_depth=max(10, source.bit_depth),
        hdr=True,
    )


@dataclass(frozen=True)
class ColorPipeline:
    intent: ColorIntent
    source: ColorProfile
    working: ColorProfile
    output: ColorProfile
    reason: str
    sdr_only_stages: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    precision_reduction: bool = False

    @property
    def preserves_hdr(self) -> bool:
        return self.intent == "preserve_hdr"

    @property
    def tone_maps_to_sdr(self) -> bool:
        return self.intent == "tone_map_sdr"

    @property
    def requires_10bit_intermediate(self) -> bool:
        return self.working.bit_depth > 8

    @property
    def needs_lossless_intermediate(self) -> bool:
        """All active visual intermediates use FFV1 for the stable quality contract.

        The old SDR8 exception used high-quality H.264 to reduce scratch usage,
        but multiple master/transition/VFX generations could accumulate visible
        loss.  Storage planning already models FFV1, so stable 1.0 prefers
        deterministic lossless staging and reports the larger disk requirement
        before rendering instead of spending image quality silently.
        """

        return True

    @property
    def working_pix_fmt(self) -> str:
        return "yuv420p10le" if self.working.bit_depth > 8 else "yuv420p"

    @property
    def final_pix_fmt(self) -> str:
        return "yuv420p10le" if self.output.bit_depth > 8 else "yuv420p"

    @property
    def label(self) -> str:
        if self.preserves_hdr:
            return f"HDR preservado • {self.output.primaries}/{self.output.transfer} • {self.output.bit_depth}-bit"
        if self.tone_maps_to_sdr:
            return f"HDR → SDR tone mapped • BT.709 • {self.output.bit_depth}-bit"
        return f"SDR preservado • {self.output.primaries}/{self.output.transfer} • {self.output.bit_depth}-bit"

    def metadata_args(self, *, output: bool = True) -> list[str]:
        profile = self.output if output else self.working
        return [
            "-color_primaries", profile.primaries,
            "-color_trc", profile.transfer,
            "-colorspace", profile.space,
            "-color_range", _range_arg(profile.range),
        ]

    def setparams_filter(self, *, output: bool = False) -> str:
        profile = self.output if output else self.working
        return (
            f"setparams=range={_range_name(profile.range)}:"
            f"color_primaries={profile.primaries}:color_trc={profile.transfer}:colorspace={profile.space}"
        )

    def tone_map_filter(self) -> str:
        """Return an explicit HDR->SDR BT.709 conversion.

        The filter linearizes the HDR transfer function, performs tone mapping in
        float RGB, converts gamut/transfer/range with zscale, applies
        error-diffusion dithering, and returns 10-bit SDR.  It is intentionally
        not equivalent to merely attaching BT.709 metadata.
        """

        if not self.tone_maps_to_sdr:
            return ""
        src = self.source
        rin = _range_arg(src.range)
        primaries = src.primaries if _known(src.primaries) else "bt2020"
        transfer = src.transfer if _known(src.transfer) else "smpte2084"
        matrix = src.space if _known(src.space) else "bt2020nc"
        target_fmt = "yuv420p10le" if self.working.bit_depth > 8 else "yuv420p"
        return (
            f"zscale=rin={rin}:pin={primaries}:tin={transfer}:min={matrix}:t=linear:npl=100,"
            "format=gbrpf32le,"
            "tonemap=tonemap=mobius:param=0.3:desat=2,"
            "zscale=p=bt709:t=bt709:m=bt709:r=tv:dither=error_diffusion,"
            f"format={target_fmt},"
            "setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709"
        )

    def precision_filter(self) -> str:
        """Explicitly reduce SDR precision for an 8-bit-only stage."""

        if not self.precision_reduction:
            return ""
        src = self.source
        rin = _range_arg(src.range)
        primaries = src.primaries if _known(src.primaries) else "bt709"
        transfer = src.transfer if _known(src.transfer) else "bt709"
        matrix = src.space if _known(src.space) else "bt709"
        out = self.working
        return (
            f"zscale=rin={rin}:pin={primaries}:tin={transfer}:min={matrix}:"
            f"p={out.primaries}:t={out.transfer}:m={out.space}:r={_range_arg(out.range)}:dither=error_diffusion,"
            "format=yuv420p,"
            f"{self.setparams_filter()}"
        )

    def normalize_filter(self, *, stage: str = "working") -> str:
        """Return the color filter needed after spatial/temporal operations."""

        profile = self.working if stage == "working" else self.output
        if self.tone_maps_to_sdr and stage == "working":
            return self.tone_map_filter()
        if self.precision_reduction and stage == "working":
            return self.precision_filter()
        return f"format={'yuv420p10le' if profile.bit_depth > 8 else 'yuv420p'},{self.setparams_filter(output=stage == 'output')}"


def build_color_pipeline(
    source: ColorProfile,
    *,
    effects_active: bool,
    transition_active: bool,
    enhancement_mode: str,
    rife_active: bool = False,
) -> ColorPipeline:
    """Choose the color contract for one render.

    Current Real-ESRGAN and NumPy VFX are SDR-only.  Loop transitions are also
    treated conservatively as SDR-only until a linear-light HDR transition path
    is validated.  HDR therefore remains HDR only on a clean path; otherwise it
    is tone-mapped once, explicitly, before those stages.
    """

    unsafe: list[str] = []
    if enhancement_mode == "realesrgan":
        unsafe.append("Real-ESRGAN")
    if rife_active:
        unsafe.append("RIFE")
    if effects_active:
        unsafe.append("VFX")
    if transition_active:
        unsafe.append("transição")

    assumptions: list[str] = []
    if not source.hdr and not (_known(source.primaries) and _known(source.transfer) and _known(source.space)):
        assumptions.append("Metadados SDR incompletos: BT.709 é assumido para os campos ausentes.")

    if source.hdr:
        if unsafe:
            # Real-ESRGAN is still an 8-bit SDR stage.  Do not put its output
            # back into a 10-bit/HDR costume; VFX/transition paths can retain a
            # 10-bit SDR base because only the generated layer is 8-bit.
            output_depth = 8 if enhancement_mode == "realesrgan" or rife_active else 10
            output = _default_sdr_profile(source, output_depth)
            return ColorPipeline(
                intent="tone_map_sdr",
                source=source,
                working=output,
                output=output,
                reason=(
                    "HDR convertido explicitamente para SDR BT.709 antes de estágios ainda não HDR-aware: "
                    + ", ".join(unsafe)
                    + "."
                ),
                sdr_only_stages=tuple(unsafe),
                assumptions=tuple(assumptions),
                precision_reduction=output_depth == 8,
            )
        output = _preserved_hdr_profile(source)
        return ColorPipeline(
            intent="preserve_hdr",
            source=source,
            working=output,
            output=output,
            reason="Caminho HDR limpo: profundidade, primárias, transferência, matriz e range são preservados.",
            assumptions=tuple(assumptions),
        )

    output = _preserved_sdr_profile(source)
    if (enhancement_mode == "realesrgan" or rife_active) and output.bit_depth > 8:
        output = ColorProfile(
            primaries=output.primaries,
            transfer=output.transfer,
            space=output.space,
            range=output.range,
            pixel_format="yuv420p",
            bit_depth=8,
            hdr=False,
        )
        return ColorPipeline(
            intent="preserve_sdr",
            source=source,
            working=output,
            output=output,
            reason=(
                "Estágio neural atual tratado como SDR 8-bit ("
                + ", ".join(stage for stage in ("Real-ESRGAN" if enhancement_mode == "realesrgan" else "", "RIFE" if rife_active else "") if stage)
                + "); a redução 10→8 usa dithering explícito e não é rotulada como preservação 10-bit."
            ),
            sdr_only_stages=tuple(stage for stage in ("Real-ESRGAN" if enhancement_mode == "realesrgan" else "", "RIFE" if rife_active else "") if stage),
            assumptions=tuple(assumptions),
            precision_reduction=True,
        )
    return ColorPipeline(
        intent="preserve_sdr",
        source=source,
        working=output,
        output=output,
        reason=(
            "SDR 10-bit preservado em intermediários 10-bit."
            if output.bit_depth > 8
            else "SDR 8-bit permanece 8-bit; o CinePulse não rotula a saída como 10-bit sem informação de origem."
        ),
        assumptions=tuple(assumptions),
    )
