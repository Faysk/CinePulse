from __future__ import annotations

import inspect
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import cinepulse.vfx as vfx_module
from cinepulse.vfx import build_vfx_filter_graph


class _FakeStdin:
    def __init__(self) -> None:
        self.closed = False

    def write(self, _data: bytes) -> int:
        return len(_data)

    def close(self) -> None:
        self.closed = True


class _FakeProcess:
    def __init__(self, return_code: int, lines: list[bytes] | None = None) -> None:
        self.return_code = return_code
        self.stdin = _FakeStdin()
        self.stdout = list(lines or [])

    def wait(self) -> int:
        return self.return_code

    def terminate(self) -> None:
        return None


class _FakeEnvelope:
    def shaped_slice(self, **_kwargs):
        return SimpleNamespace(
            energy=[0.5],
            rms=[0.25],
            onset=[0.1],
            sections=[],
        )


class VfxTimingTests(unittest.TestCase):
    def test_direct_vfx_nvenc_failure_retries_once_with_libx264(self) -> None:
        commands: list[list[str]] = []
        return_codes = iter((1, 0))

        def fake_popen(command, **_kwargs):
            commands.append(list(command))
            code = next(return_codes)
            return _FakeProcess(
                code,
                [b"Failed to initialize NVENC\n"] if code else [],
            )

        with (
            patch("cinepulse.vfx.load_music_envelope", return_value=_FakeEnvelope()),
            patch(
                "cinepulse.vfx.choose_vfx_render_spec",
                return_value=SimpleNamespace(
                    width=2,
                    height=2,
                    fps=1.0,
                    label="test",
                    native_spatial=True,
                    native_temporal=True,
                ),
            ),
            patch(
                "cinepulse.vfx.StudioFrameGenerator",
                return_value=SimpleNamespace(make=lambda *args, **kwargs: b"frame"),
            ),
            patch("cinepulse.vfx._spawn_vfx_process", side_effect=fake_popen),
        ):
            vfx_module.render_vfx_intermediate(
                "ffmpeg",
                "master.mp4",
                "audio.wav",
                "out.mp4",
                1.0,
                {"Aurora"},
                "#ffffff",
                1.0,
                0.5,
                1920,
                1080,
                30.0,
                "50M",
                "100M",
                "200M",
                False,
                8,
                "Todos equilibrados",
                80.0,
                80.0,
                False,
                70.0,
                lambda _value: None,
                lambda: False,
                lambda _process: None,
                lambda _line: None,
                gpu_index=2,
            )

        self.assertEqual(2, len(commands))
        self.assertEqual("h264_nvenc", commands[0][commands[0].index("-c:v") + 1])
        self.assertEqual("2", commands[0][commands[0].index("-gpu") + 1])
        self.assertEqual("libx264", commands[1][commands[1].index("-c:v") + 1])
        self.assertNotIn("-gpu", commands[1])

    def test_fused_vfx_nvenc_failure_uses_explicit_cpu_delivery_args(self) -> None:
        commands: list[list[str]] = []
        return_codes = iter((1, 0))

        def fake_popen(command, **_kwargs):
            commands.append(list(command))
            code = next(return_codes)
            return _FakeProcess(
                code,
                [b"Failed to initialize NVENC\n"] if code else [],
            )

        with (
            patch("cinepulse.vfx.load_music_envelope", return_value=_FakeEnvelope()),
            patch(
                "cinepulse.vfx.choose_vfx_render_spec",
                return_value=SimpleNamespace(
                    width=2,
                    height=2,
                    fps=1.0,
                    label="test",
                    native_spatial=True,
                    native_temporal=True,
                ),
            ),
            patch(
                "cinepulse.vfx.StudioFrameGenerator",
                return_value=SimpleNamespace(make=lambda *args, **kwargs: b"frame"),
            ),
            patch("cinepulse.vfx._spawn_vfx_process", side_effect=fake_popen),
        ):
            vfx_module.render_vfx_intermediate(
                "ffmpeg",
                "master.mp4",
                "audio.wav",
                "out.mp4",
                1.0,
                {"Aurora"},
                "#ffffff",
                1.0,
                0.5,
                1920,
                1080,
                30.0,
                "50M",
                "100M",
                "200M",
                False,
                8,
                "Todos equilibrados",
                80.0,
                80.0,
                False,
                70.0,
                lambda _value: None,
                lambda: False,
                lambda _process: None,
                lambda _line: None,
                final_video_args=["-c:v", "hevc_nvenc", "-gpu", "2"],
                fallback_video_args=["-c:v", "libx265", "-preset", "medium"],
                final_muxer_args=["-movflags", "+faststart"],
                gpu_index=2,
            )

        self.assertEqual(2, len(commands))
        self.assertEqual("hevc_nvenc", commands[0][commands[0].index("-c:v") + 1])
        self.assertEqual("libx265", commands[1][commands[1].index("-c:v") + 1])
        self.assertNotIn("-gpu", commands[1])
        self.assertIn("+faststart", commands[1])

    def test_vfx_cancellation_terminates_process_tree(self) -> None:
        process = _FakeProcess(0)

        with (
            patch("cinepulse.vfx.load_music_envelope", return_value=_FakeEnvelope()),
            patch(
                "cinepulse.vfx.choose_vfx_render_spec",
                return_value=SimpleNamespace(
                    width=2,
                    height=2,
                    fps=1.0,
                    label="test",
                    native_spatial=True,
                    native_temporal=True,
                ),
            ),
            patch(
                "cinepulse.vfx.StudioFrameGenerator",
                return_value=SimpleNamespace(make=lambda *args, **kwargs: b"frame"),
            ),
            patch("cinepulse.vfx._spawn_vfx_process", return_value=process),
            patch("cinepulse.vfx.terminate_process_tree") as terminate,
        ):
            with self.assertRaises(vfx_module.RenderCancelled):
                vfx_module.render_vfx_intermediate(
                    "ffmpeg",
                    "master.mp4",
                    "audio.wav",
                    "out.mp4",
                    1.0,
                    {"Aurora"},
                    "#ffffff",
                    1.0,
                    0.5,
                    1920,
                    1080,
                    30.0,
                    "50M",
                    "100M",
                    "200M",
                    False,
                    8,
                    "Todos equilibrados",
                    80.0,
                    80.0,
                    False,
                    70.0,
                    lambda _value: None,
                    lambda: True,
                    lambda _process: None,
                    lambda _line: None,
                    gpu_index=2,
                )

        self.assertGreaterEqual(terminate.call_count, 1)
        self.assertTrue(process.stdin.closed)

    def test_direct_vfx_non_gpu_failure_does_not_retry_cpu(self) -> None:
        commands: list[list[str]] = []

        def fake_popen(command, **_kwargs):
            commands.append(list(command))
            return _FakeProcess(1, [b"No space left on device\n"])

        with (
            patch("cinepulse.vfx.load_music_envelope", return_value=_FakeEnvelope()),
            patch(
                "cinepulse.vfx.choose_vfx_render_spec",
                return_value=SimpleNamespace(
                    width=2,
                    height=2,
                    fps=1.0,
                    label="test",
                    native_spatial=True,
                    native_temporal=True,
                ),
            ),
            patch(
                "cinepulse.vfx.StudioFrameGenerator",
                return_value=SimpleNamespace(make=lambda *args, **kwargs: b"frame"),
            ),
            patch("cinepulse.vfx._spawn_vfx_process", side_effect=fake_popen),
        ):
            with self.assertRaisesRegex(RuntimeError, "No space left on device"):
                vfx_module.render_vfx_intermediate(
                    "ffmpeg",
                    "master.mp4",
                    "audio.wav",
                    "out.mp4",
                    1.0,
                    {"Aurora"},
                    "#ffffff",
                    1.0,
                    0.5,
                    1920,
                    1080,
                    30.0,
                    "50M",
                    "100M",
                    "200M",
                    False,
                    8,
                    "Todos equilibrados",
                    80.0,
                    80.0,
                    False,
                    70.0,
                    lambda _value: None,
                    lambda: False,
                    lambda _process: None,
                    lambda _line: None,
                    gpu_index=2,
                )

        self.assertEqual(1, len(commands))

    def test_vfx_has_one_shot_cpu_encoder_fallbacks(self) -> None:
        source = inspect.getsource(vfx_module.render_vfx_intermediate)
        self.assertIn("fallback_video_args: list[str] | None = None", source)
        self.assertIn("VFX intermediário: H.264 NVENC falhou; repetindo com libx264.", source)
        self.assertIn("VFX fused: NVENC final falhou; repetindo entrega com encoder CPU equivalente.", source)
        self.assertIn("attempts = [primary_video_args]", source)
        self.assertIn("attempts.append(fallback_args)", source)
        self.assertIn("if return_code == 0:", source)
        self.assertNotIn("while True", source)

    def test_direct_nvenc_fallback_has_explicit_gpu_selection(self) -> None:
        source = inspect.getsource(vfx_module.render_vfx_intermediate)
        self.assertIn("gpu_index: int = 0", source)
        self.assertIn('"h264_nvenc"', source)
        self.assertIn('str(max(0, int(gpu_index)))', source)

    def test_overlay_explicitly_repeats_last_effect_frame_without_shortening_base(self) -> None:
        graph = build_vfx_filter_graph(1920, 1080)
        self.assertIn("eof_action=repeat", graph)
        self.assertIn("shortest=0", graph)
        self.assertIn("repeatlast=1", graph)


if __name__ == "__main__":
    unittest.main()
