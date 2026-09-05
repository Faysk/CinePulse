from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
