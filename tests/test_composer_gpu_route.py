from __future__ import annotations

import unittest

from cinepulse.composer_gpu_route import select_gpu_export_route
from cinepulse.gpu_compositor import GpuCompositorCapabilities, OverlayLayer
from cinepulse.hardware import HardwareProfile
from cinepulse.overlay_composer import ComposerItem, OverlayComposerState, VisualizerLayer


CAPS = GpuCompositorCapabilities("ffmpeg", "abc123", True, True, True, True)
GPU = HardwareProfile("cpu", 28, "RTX Test", 8192, "999.1")
NO_GPU = HardwareProfile("cpu", 28, None, None, None)


class Store:
    def __init__(self, approved: bool) -> None:
        self.value = approved
        self.keys = []

    def approved(self, key, caps) -> bool:
        self.keys.append((key, caps))
        return self.value


def state_with(layer: OverlayLayer) -> OverlayComposerState:
    return OverlayComposerState([ComposerItem("media", media=layer)])


def route(state, *, hardware=GPU, store=None):
    return select_gpu_export_route(
        state,
        hardware=hardware,
        caps=CAPS,
        store=store or Store(False),
        width=1920,
        height=1080,
        fps=30.0,
        pixel_format="yuv420p",
        primaries="bt709",
        transfer="bt709",
        matrix="bt709",
        color_range="tv",
    )


class ComposerGpuRouteTests(unittest.TestCase):
    def test_capability_without_exact_evidence_stays_cpu(self) -> None:
        result = route(state_with(OverlayLayer("logo.png", "png")), store=Store(False))
        self.assertFalse(result.use_gpu)
        self.assertIsNotNone(result.key)
        self.assertIn("evidence", result.reason)

    def test_exact_approved_static_layer_can_use_gpu(self) -> None:
        store = Store(True)
        layer = OverlayLayer("logo.png", "png", x=0.2, y=0.8, opacity=0.75)
        result = route(state_with(layer), store=store)
        self.assertTrue(result.use_gpu)
        self.assertEqual(layer.contract_token(), result.key.layer_contract)
        self.assertEqual("RTX Test", result.key.gpu_name)
        self.assertEqual(30000, result.key.fps_milli)
        self.assertEqual(1, len(store.keys))

    def test_dynamic_transform_never_queries_evidence_store(self) -> None:
        store = Store(True)
        result = route(state_with(OverlayLayer("logo.png", "png", pulse=0.5)), store=store)
        self.assertFalse(result.use_gpu)
        self.assertEqual([], store.keys)

    def test_no_physical_gpu_fails_closed(self) -> None:
        store = Store(True)
        result = route(state_with(OverlayLayer("logo.png", "png")), hardware=NO_GPU, store=store)
        self.assertFalse(result.use_gpu)
        self.assertEqual([], store.keys)

    def test_multiple_individually_static_layers_do_not_compose_on_gpu_yet(self) -> None:
        state = OverlayComposerState([
            ComposerItem("a", media=OverlayLayer("a.png", "png", z_order=0)),
            ComposerItem("b", media=OverlayLayer("b.png", "png", z_order=1)),
        ])
        result = route(state, store=Store(True))
        self.assertFalse(result.use_gpu)
        self.assertIn("exactly one", result.reason)

    def test_visualizer_remains_cpu_until_shader_parity_is_proven(self) -> None:
        state = OverlayComposerState([ComposerItem("viz", visualizer=VisualizerLayer("spectrum"))])
        result = route(state, store=Store(True))
        self.assertFalse(result.use_gpu)
        self.assertIn("visualizer", result.reason)


if __name__ == "__main__":
    unittest.main()
