from __future__ import annotations

from dataclasses import dataclass

from .overlay_composer import OverlayScene, OverlaySceneError


@dataclass(frozen=True)
class LongformOverlayAssessment:
    duration_seconds: float
    active_layers: int
    png_streams: int
    gif_streams: int
    visualizers: int
    auxiliary_input_streams: int
    materialized_frame_count: int
    duration_scaled_temp_bytes: int
    warnings: tuple[str, ...] = ()

    @property
    def streaming_safe(self) -> bool:
        return self.materialized_frame_count == 0 and self.duration_scaled_temp_bytes == 0

    @property
    def summary(self) -> str:
        hours = self.duration_seconds / 3600.0
        return (
            f"{hours:.2f} h • {self.active_layers} layer(s) • "
            f"{self.png_streams} PNG • {self.gif_streams} GIF • {self.visualizers} visualizer(s) • "
            f"{self.auxiliary_input_streams} stream(s) auxiliar(es) • sem sequência temporária por frame"
        )


def assess_longform(scene: OverlayScene, duration_seconds: float) -> LongformOverlayAssessment:
    """Describe the Overlay Composer's duration-scaling behavior.

    The final renderer streams static PNGs, loops GIFs at demuxer level and
    generates audio visualizers inside FFmpeg. Therefore the number of external
    overlay inputs depends on layer count, not on video frame count or duration.

    This assessment deliberately does *not* claim a fixed RAM/CPU cost: decode
    and filter cost still depends on resolution, FPS, codec and layer size. It
    only guarantees the architecture does not materialize a duration-sized PNG
    sequence or duration-sized overlay scratch cache.
    """
    scene.validate()
    duration = float(duration_seconds)
    if duration <= 0:
        raise OverlaySceneError("Duração precisa ser positiva para avaliação longform.")

    active = scene.active_layers
    png_streams = sum(
        1 for layer in active if layer.asset is not None and layer.asset.media_kind == "png"
    )
    gif_streams = sum(
        1 for layer in active if layer.asset is not None and layer.asset.media_kind == "gif"
    )
    visualizers = sum(1 for layer in active if layer.visualizer is not None)
    asset_streams = png_streams + gif_streams
    # Studio uses one dedicated audio read for all visualizers, then asplit
    # inside the filter graph. It does not reopen audio once per visualizer.
    auxiliary_inputs = asset_streams + (1 if visualizers else 0)

    warnings: list[str] = []
    if len(active) > 12:
        warnings.append("Mais de 12 overlays ativos podem elevar bastante o custo de composição.")
    if gif_streams > 4:
        warnings.append("Mais de 4 GIFs simultâneos podem elevar o custo de decode em CPU.")
    if duration >= 3600 and gif_streams:
        warnings.append(
            "Projeto longo com GIF: o arquivo continua em streaming, mas o GIF será decodificado repetidamente durante toda a duração."
        )

    return LongformOverlayAssessment(
        duration_seconds=duration,
        active_layers=len(active),
        png_streams=png_streams,
        gif_streams=gif_streams,
        visualizers=visualizers,
        auxiliary_input_streams=auxiliary_inputs,
        materialized_frame_count=0,
        duration_scaled_temp_bytes=0,
        warnings=tuple(warnings),
    )
