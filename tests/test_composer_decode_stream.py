from __future__ import annotations

import io
import unittest

import numpy as np

from cinepulse.composer_decode_stream import (
    ComposerMediaDecoderPool,
    SequentialRgbaDecoder,
    build_sequential_rgba_command,
)
from cinepulse.composer_media import ComposerMediaInfo, ComposerPlaybackPosition
from cinepulse.gpu_compositor import OverlayLayer


class FakeProcess:
    def __init__(self, payload: bytes) -> None:
        self.stdout = io.BytesIO(payload)
        self.pid = 12345

    def poll(self):
        return 0


class ProcessFactory:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls = 0
        self.commands: list[list[str]] = []

    def __call__(self, command, **_kwargs):
        self.calls += 1
        self.commands.append(list(command))
        return FakeProcess(self.payload)


def info(source: str = "anim.webp", frames: int = 3) -> ComposerMediaInfo:
    return ComposerMediaInfo(
        source=source,
        width=2,
        height=1,
        fps=2.0,
        duration=max(0.5, frames / 2.0),
        frame_count=frames,
        pixel_format="rgba",
        codec="webp" if source.endswith("webp") else "png",
        has_alpha=True,
        animated=frames > 1,
    )


def frame_bytes(*values: int) -> bytes:
    chunks: list[bytes] = []
    for value in values:
        chunks.append(bytes([value, 0, 0, 255, value, 0, 0, 255]))
    return b"".join(chunks)


def position(index: int, *, active: bool = True, loop: int = 0) -> ComposerPlaybackPosition:
    return ComposerPlaybackPosition(active, index / 2.0, index, loop)


class ComposerSequentialDecodeTests(unittest.TestCase):
    def test_command_streams_source_order_without_timestamp_or_select_seek(self) -> None:
        layer = OverlayLayer("anim.webp", "webp")
        command = build_sequential_rgba_command("ffmpeg", layer, info())
        joined = " ".join(command)
        self.assertIn("-fps_mode passthrough", joined)
        self.assertIn("-pix_fmt rgba", joined)
        self.assertNotIn("select=", joined)
        self.assertNotIn(" -ss ", f" {joined} ")
        self.assertNotIn("-frames:v 1", joined)

    def test_forward_requests_use_one_process_and_consume_exact_frame_indices(self) -> None:
        factory = ProcessFactory(frame_bytes(10, 20, 30))
        decoder = SequentialRgbaDecoder(
            "ffmpeg", OverlayLayer("anim.webp", "webp"), info(), process_factory=factory
        )
        first = decoder.frame(position(0))
        third = decoder.frame(position(2))
        self.assertEqual(10, int(first[0, 0, 0]))
        self.assertEqual(30, int(third[0, 0, 0]))
        self.assertFalse(first.flags.writeable)
        self.assertEqual(1, factory.calls)
        self.assertEqual(3, decoder.stats.frames_read)
        decoder.close()

    def test_repeated_frame_is_cache_hit_without_extra_decode(self) -> None:
        factory = ProcessFactory(frame_bytes(10, 20, 30))
        decoder = SequentialRgbaDecoder(
            "ffmpeg", OverlayLayer("anim.webp", "webp"), info(), process_factory=factory
        )
        first = decoder.frame(position(1))
        second = decoder.frame(position(1))
        self.assertIs(first, second)
        self.assertEqual(1, factory.calls)
        self.assertEqual(2, decoder.stats.frames_read)
        self.assertEqual(1, decoder.stats.cache_hits)
        decoder.close()

    def test_loop_wrap_restarts_decoder_from_frame_zero_exactly(self) -> None:
        factory = ProcessFactory(frame_bytes(10, 20, 30))
        decoder = SequentialRgbaDecoder(
            "ffmpeg", OverlayLayer("anim.webp", "webp"), info(), process_factory=factory
        )
        self.assertEqual(30, int(decoder.frame(position(2))[0, 0, 0]))
        wrapped = decoder.frame(position(0, loop=1))
        self.assertEqual(10, int(wrapped[0, 0, 0]))
        self.assertEqual(2, factory.calls)
        self.assertEqual(1, decoder.stats.restarts)
        self.assertEqual(4, decoder.stats.frames_read)
        decoder.close()

    def test_inactive_position_never_starts_ffmpeg(self) -> None:
        factory = ProcessFactory(frame_bytes(10, 20, 30))
        decoder = SequentialRgbaDecoder(
            "ffmpeg", OverlayLayer("anim.webp", "webp"), info(), process_factory=factory
        )
        self.assertIsNone(decoder.frame(position(0, active=False)))
        self.assertEqual(0, factory.calls)
        decoder.close()

    def test_static_asset_decodes_once_and_holds_cached_frame(self) -> None:
        static = info("logo.png", frames=1)
        factory = ProcessFactory(frame_bytes(77))
        decoder = SequentialRgbaDecoder(
            "ffmpeg", OverlayLayer("logo.png", "png", loop=False), static, process_factory=factory
        )
        first = decoder.frame(position(0))
        second = decoder.frame(position(0))
        self.assertEqual(77, int(first[0, 0, 0]))
        self.assertIs(first, second)
        self.assertEqual(1, factory.calls)
        self.assertEqual(1, decoder.stats.frames_read)
        self.assertEqual(1, decoder.stats.cache_hits)
        decoder.close()

    def test_pool_keeps_decoders_isolated_per_item(self) -> None:
        payload = frame_bytes(1, 2, 3)
        factory = ProcessFactory(payload)
        layers = {
            "left": (OverlayLayer("anim.webp", "webp"), info()),
            "right": (OverlayLayer("anim.webp", "webp"), info()),
        }
        pool = ComposerMediaDecoderPool("ffmpeg", layers, process_factory=factory)
        left = pool.frame("left", position(1))
        right = pool.frame("right", position(2))
        self.assertEqual(2, int(left[0, 0, 0]))
        self.assertEqual(3, int(right[0, 0, 0]))
        self.assertEqual(2, pool.stats.process_starts)
        self.assertEqual(5, pool.stats.frames_read)
        with self.assertRaises(KeyError):
            pool.frame("missing", position(0))
        pool.close()


if __name__ == "__main__":
    unittest.main()
