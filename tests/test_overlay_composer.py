from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cinepulse.gpu_compositor import (
    GpuCompositorCapabilities,
    GpuCompositorEvidence,
    GpuCompositorKey,
    GpuCompositorStore,
    OverlayLayer,
)
from cinepulse.overlay_composer import (
    ComposerItem,
    OverlayComposerState,
    VisualizerLayer,
    evaluate_media_frame,
    evaluate_visualizer_frame,
    media_layer_from_path,
    route_item,
    route_project,
)


def caps() -> GpuCompositorCapabilities:
    return GpuCompositorCapabilities("ffmpeg", "ffmpeg-test", True, True, True, True)


def key(layer: OverlayLayer) -> GpuCompositorKey:
    return GpuCompositorKey(
        gpu_name="RTX Test",
        driver="999.1",
        ffmpeg_fingerprint="ffmpeg-test",
        width=1920,
        height=1080,
        fps_milli=60000,
        pixel_format="yuv420p",
        primaries="bt709",
        transfer="bt709",
        space="bt709",
        color_range="tv",
        layer_contract=layer.contract_token(),
    )


class OverlayComposerTests(unittest.TestCase):
    def test_media_extension_mapping_covers_requested_layer_types(self) -> None:
        self.assertEqual("png", media_layer_from_path("a.png").kind)
        self.assertEqual("gif", media_layer_from_path("a.gif").kind)
        self.assertEqual("apng", media_layer_from_path("a.apng").kind)
        self.assertEqual("webp", media_layer_from_path("a.webp").kind)
        self.assertEqual("video-alpha", media_layer_from_path("a.webm").kind)
        with self.assertRaises(ValueError):
            media_layer_from_path("a.exe")

    def test_state_is_deterministically_sorted_by_z_then_id(self) -> None:
        state = OverlayComposerState()
        state.add(ComposerItem("b", media=OverlayLayer("b.png", "png", z_order=1)))
        state.add(ComposerItem("a", media=OverlayLayer("a.png", "png", z_order=1)))
        state.add(ComposerItem("front", visualizer=VisualizerLayer("spectrum", z_order=3)))
        self.assertEqual(("a", "b", "front"), tuple(item.id for item in state.ordered()))

    def test_duplicate_ids_are_rejected(self) -> None:
        state = OverlayComposerState([ComposerItem("logo", media=OverlayLayer("a.png", "png"))])
        with self.assertRaises(ValueError):
            state.add(ComposerItem("logo", media=OverlayLayer("b.png", "png")))

    def test_visualizer_exposes_audio_binding_and_requested_shapes(self) -> None:
        for kind in ("waveform", "spectrum", "circular"):
            layer = VisualizerLayer(kind, binding="drums", reaction=1.25, bars=96)
            self.assertEqual("drums", layer.binding)
            self.assertEqual(kind, layer.kind)
        with self.assertRaises(ValueError):
            VisualizerLayer("waveform", binding="not-a-stem")  # type: ignore[arg-type]

    def test_visualizer_stays_cpu_until_shader_parity_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            route = route_item(
                ComposerItem("viz", visualizer=VisualizerLayer("circular")),
                caps=caps(),
                store=GpuCompositorStore(Path(temporary) / "store.json"),
                compositor_key=None,
            )
            self.assertEqual("cpu-visualizer", route.route)

    def test_media_layer_needs_exact_evidence_before_cuda(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = GpuCompositorStore(Path(temporary) / "store.json")
            layer = OverlayLayer("logo.png", "png")
            item = ComposerItem("logo", media=layer)
            self.assertEqual("cpu-overlay", route_item(item, caps=caps(), store=store, compositor_key=key(layer)).route)
            evidence = GpuCompositorEvidence(10.0, 5.0, 90.0, 1.0, True, True, True, True)
            self.assertTrue(store.record(key(layer), evidence))
            self.assertEqual("cuda-overlay", route_item(item, caps=caps(), store=store, compositor_key=key(layer)).route)

    def test_changed_layer_contract_fails_closed_even_with_old_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = GpuCompositorStore(Path(temporary) / "store.json")
            original = OverlayLayer("logo.png", "png")
            store.record(key(original), GpuCompositorEvidence(10.0, 5.0, 90.0, 1.0, True, True, True, True))
            changed = OverlayLayer("logo.png", "png", opacity=0.5)
            route = route_item(
                ComposerItem("logo", media=changed),
                caps=caps(),
                store=store,
                compositor_key=key(original),
            )
            self.assertEqual("cpu-overlay", route.route)

    def test_project_routing_preserves_z_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = OverlayComposerState([
                ComposerItem("viz", visualizer=VisualizerLayer("waveform", z_order=2)),
                ComposerItem("logo", media=OverlayLayer("logo.png", "png", z_order=1)),
            ])
            routes = route_project(
                state,
                caps=caps(),
                store=GpuCompositorStore(Path(temporary) / "store.json"),
                keys={},
            )
            self.assertEqual(("logo", "viz"), tuple(route.item_id for route in routes))

    def test_preview_state_roundtrips_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "composer.json"
            state = OverlayComposerState([
                ComposerItem("logo", media=OverlayLayer("logo.png", "png", opacity=0.7, pulse=0.5)),
                ComposerItem("viz", visualizer=VisualizerLayer("circular", binding="bass", spin_rpm=2.0)),
                ComposerItem("hidden", media=OverlayLayer("hidden.webp", "webp"), enabled=False),
            ])
            state.save(path)
            restored = OverlayComposerState.load(path)
            self.assertEqual(state.as_dict(), restored.as_dict())
            self.assertEqual(1, json.loads(path.read_text(encoding="utf-8"))["schema"])
            self.assertFalse(any(child.suffix == ".tmp" for child in path.parent.iterdir()))

    def test_invalid_or_duplicate_persisted_state_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            OverlayComposerState.from_dict({"schema": 999, "items": []})
        duplicate = {
            "schema": 1,
            "items": [
                {"id": "same", "enabled": True, "media": {"source": "a.png", "kind": "png"}, "visualizer": None},
                {"id": "same", "enabled": True, "media": {"source": "b.png", "kind": "png"}, "visualizer": None},
            ],
        }
        with self.assertRaises(ValueError):
            OverlayComposerState.from_dict(duplicate)

    def test_media_reactive_frame_uses_pulse_beat_and_spin_deterministically(self) -> None:
        layer = OverlayLayer(
            "logo.png", "png", scale=2.0, rotation_degrees=10.0,
            spin_rpm=5.0, pulse=1.0, beat_reaction=1.0,
        )
        calm = evaluate_media_frame(layer, time_seconds=2.0, rms=0.0, onset=0.0)
        active = evaluate_media_frame(layer, time_seconds=2.0, rms=1.0, onset=1.0)
        self.assertEqual(70.0, calm.rotation_degrees)
        self.assertEqual(calm.rotation_degrees, active.rotation_degrees)
        self.assertGreater(active.scale, calm.scale)
        self.assertGreater(active.reaction, calm.reaction)

    def test_visualizer_frame_is_bounded_and_audio_reactive(self) -> None:
        layer = VisualizerLayer("spectrum", scale=1.5, reaction=2.0, spin_rpm=10.0)
        calm = evaluate_visualizer_frame(layer, time_seconds=1.0, rms=0.0, onset=0.0, band_energy=0.0)
        hot = evaluate_visualizer_frame(layer, time_seconds=1.0, rms=10.0, onset=10.0, band_energy=10.0)
        self.assertEqual(60.0, calm.rotation_degrees)
        self.assertEqual(0.0, calm.reaction)
        self.assertEqual(1.0, hot.reaction)
        self.assertGreater(hot.scale, calm.scale)


if __name__ == "__main__":
    unittest.main()
