from __future__ import annotations

"""Bind cached full-track audio analyses to Preview Composer layers.

``ComposerFrameInputs.audio`` accepts both traditional binding keys (master,
drums, vocals, ...) and item ids.  Binding-level features drive media pulse/beat
and provide backward-compatible fallback; item-level features carry the exact
waveform/spectrum shape requested by each visualizer so two visualizers can use
the same stem without being forced to share incompatible values.
"""

from pathlib import Path
from typing import Callable, Mapping

from .composer_audio import VisualizerAudioEnvelope, frame_audio, load_visualizer_envelope
from .composer_runtime import AudioFrameFeatures
from .overlay_composer import OverlayComposerState


def required_analysis_bands(state: OverlayComposerState, binding: str) -> int:
    """Return enough cached spectral detail for every visualizer on a binding."""
    requested = 16
    for item in state.ordered():
        layer = item.visualizer
        if layer is None or layer.binding != binding:
            continue
        if layer.kind in {"spectrum", "circular"}:
            requested = max(requested, int(layer.bars))
    return max(8, min(512, requested))


def load_bound_visualizer_envelopes(
    state: OverlayComposerState,
    *,
    ffmpeg: str,
    sources: Mapping[str, str | Path],
    duration: float,
    cache_dir: Path | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, VisualizerAudioEnvelope]:
    """Analyze the master/stem files actually needed by enabled composer items."""
    wanted: set[str] = set()
    for item in state.ordered():
        if item.visualizer is not None:
            wanted.add(item.visualizer.binding)
        elif item.media is not None and (item.media.pulse > 0 or item.media.beat_reaction > 0):
            binding = item.media.audio_binding
            wanted.add("master" if binding == "none" else binding)
    # Master is the deterministic fallback for an unavailable requested stem.
    if wanted and "master" in sources:
        wanted.add("master")

    result: dict[str, VisualizerAudioEnvelope] = {}
    for binding in sorted(wanted):
        source = sources.get(binding)
        if source is None:
            continue
        result[binding] = load_visualizer_envelope(
            ffmpeg,
            str(source),
            duration,
            bands=required_analysis_bands(state, binding),
            cache_dir=cache_dir,
            log=log,
        )
    return result


def _runtime_features(frame) -> AudioFrameFeatures:
    return AudioFrameFeatures(
        rms=frame.rms,
        onset=frame.onset,
        band_energy=frame.band_energy,
        values=frame.values,
    )


def composer_audio_features(
    state: OverlayComposerState,
    envelopes: Mapping[str, VisualizerAudioEnvelope],
    *,
    project_time: float,
) -> dict[str, AudioFrameFeatures]:
    """Build binding + per-item features for one Preview render timestamp."""
    features: dict[str, AudioFrameFeatures] = {}

    # Binding entries are intentionally low-detail. They exist for media pulse,
    # beat reaction and old callers; visualizers get exact item entries below.
    for binding, envelope in envelopes.items():
        sampled = frame_audio(
            envelope,
            time_seconds=project_time,
            kind="spectrum",
            bars=8,
            smoothing=0.45,
        )
        features[binding] = _runtime_features(sampled)

    for item in state.ordered():
        layer = item.visualizer
        if layer is None:
            continue
        envelope = envelopes.get(layer.binding) or envelopes.get("master")
        if envelope is None:
            continue
        sampled = frame_audio(
            envelope,
            time_seconds=project_time,
            kind=layer.kind,
            bars=layer.bars,
            smoothing=layer.smoothing,
        )
        features[item.id] = _runtime_features(sampled)
    return features
