from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from cinepulse.composer_decode import build_exact_rgba_command, decode_exact_rgba_frame
from cinepulse.composer_media import ComposerMediaInfo, ComposerPlaybackPosition
from cinepulse.gpu_compositor import OverlayLayer


class Result:
    def __init__(self, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class ComposerDecodeTests(unittest.TestCase):
    def info(self, source: str = "clip.webm") -> ComposerMediaInfo:
        return ComposerMediaInfo(source, 4, 2, 24.0, 1.0, 24, "yuva420p", "vp9", True, True)

    def test_command_selects_exact_frame_index_not_timestamp_seek(self) -> None:
        layer = OverlayLayer("clip.webm", "video-alpha")
        command = build_exact_rgba_command(
            "ffmpeg", layer, self.info(), ComposerPlaybackPosition(True, 0.5, 12, 0)
        )
        self.assertNotIn("-ss", command)
        self.assertIn("select=eq(n\\,12),format=rgba", command)
        self.assertIn("rgba", command)

    def test_inactive_position_returns_none_without_spawning_ffmpeg(self) -> None:
        layer = OverlayLayer("clip.webm", "video-alpha")
        with patch("cinepulse.composer_decode.subprocess.run") as run:
            result = decode_exact_rgba_frame(
                "ffmpeg", layer, self.info(), ComposerPlaybackPosition(False, 1.0, 23, 0)
            )
        self.assertIsNone(result)
        run.assert_not_called()

    def test_valid_exact_byte_count_returns_owned_rgba_array(self) -> None:
        layer = OverlayLayer("clip.webm", "video-alpha")
        payload = bytes(range(32))
        with patch("cinepulse.composer_decode.subprocess.run", return_value=Result(stdout=payload)):
            frame = decode_exact_rgba_frame(
                "ffmpeg", layer, self.info(), ComposerPlaybackPosition(True, 0.0, 0, 0)
            )
        assert frame is not None
        self.assertEqual((2, 4, 4), frame.shape)
        self.assertEqual(np.uint8, frame.dtype)
        self.assertTrue(frame.flags["OWNDATA"])
        self.assertEqual(31, int(frame[-1, -1, -1]))

    def test_truncated_or_oversized_output_is_rejected(self) -> None:
        layer = OverlayLayer("clip.webm", "video-alpha")
        for payload in (b"x" * 31, b"x" * 33):
            with patch("cinepulse.composer_decode.subprocess.run", return_value=Result(stdout=payload)):
                with self.assertRaisesRegex(RuntimeError, "expected 32"):
                    decode_exact_rgba_frame(
                        "ffmpeg", layer, self.info(), ComposerPlaybackPosition(True, 0.0, 0, 0)
                    )

    def test_ffmpeg_failure_surfaces_stderr(self) -> None:
        layer = OverlayLayer("clip.webm", "video-alpha")
        with patch(
            "cinepulse.composer_decode.subprocess.run",
            return_value=Result(1, stderr=b"decoder exploded"),
        ):
            with self.assertRaisesRegex(RuntimeError, "decoder exploded"):
                decode_exact_rgba_frame(
                    "ffmpeg", layer, self.info(), ComposerPlaybackPosition(True, 0.0, 0, 0)
                )

    def test_asset_mismatch_and_frame_bounds_fail_closed(self) -> None:
        layer = OverlayLayer("clip.webm", "video-alpha")
        with self.assertRaises(ValueError):
            build_exact_rgba_command(
                "ffmpeg", layer, self.info("other.webm"), ComposerPlaybackPosition(True, 0.0, 0, 0)
            )
        with self.assertRaises(ValueError):
            build_exact_rgba_command(
                "ffmpeg", layer, self.info(), ComposerPlaybackPosition(True, 2.0, 24, 0)
            )


if __name__ == "__main__":
    unittest.main()
