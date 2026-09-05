from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from cinepulse.composer_export import (
    ComposerBaseProfile,
    ComposerExportRequest,
    _base_decode_command,
    _mux_command,
    _read_exact,
    _video_encode_command,
    export_composer_reference,
)
from cinepulse.gpu_compositor import OverlayLayer
from cinepulse.overlay_composer import ComposerItem, OverlayComposerState


class ShortReader:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)

    def read(self, _size: int) -> bytes:
        return self.chunks.pop(0) if self.chunks else b""


class ComposerExportTests(unittest.TestCase):
    def profile(self, **changes) -> ComposerBaseProfile:
        values = dict(
            width=64, height=36, fps=4.0, duration=1.0, pixel_format="yuv420p",
            primaries="bt709", transfer="bt709", matrix="bt709", color_range="tv",
        )
        values.update(changes)
        return ComposerBaseProfile(**values)

    def request(self, root: Path, profile: ComposerBaseProfile | None = None) -> ComposerExportRequest:
        return ComposerExportRequest(
            root / "source.mkv", root / "output.mkv", profile or self.profile(),
            OverlayComposerState([ComposerItem("logo", media=OverlayLayer(str(root / "logo.png"), "png"))]),
            "ffmpeg", "ffprobe", {"master": root / "source.mkv"},
        )

    def test_reference_profile_fails_closed_for_hdr_or_high_bit_depth(self) -> None:
        self.assertTrue(self.profile().reference_supported)
        self.assertFalse(self.profile(pixel_format="yuv420p10le").reference_supported)
        self.assertFalse(self.profile(transfer="smpte2084").reference_supported)
        self.assertFalse(self.profile(primaries="bt2020").reference_supported)
        self.assertFalse(self.profile(matrix="bt2020nc").reference_supported)

    def test_decode_command_has_explicit_bt709_zscale_and_no_implicit_fps_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            command = _base_decode_command(self.request(Path(temporary)), 4)
        joined = " ".join(command)
        self.assertIn("zscale=matrixin=709", joined)
        self.assertIn("primariesin=709", joined)
        self.assertIn("transferin=709", joined)
        self.assertIn("matrix=gbr", joined)
        self.assertIn("-fps_mode passthrough", joined)
        self.assertNotIn(" -r ", joined)
        self.assertIn("-pix_fmt rgba", joined)

    def test_reference_encoder_is_lossless_rgb_ffv1(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = _video_encode_command(self.request(root), root / "visual.mkv")
        joined = " ".join(command)
        self.assertIn("-c:v ffv1", joined)
        self.assertIn("-level 3", joined)
        self.assertIn("-pix_fmt gbrap", joined)
        self.assertNotIn("nvenc", joined.lower())

    def test_mux_copies_reference_video_and_optional_master_audio(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = _mux_command(self.request(root), root / "visual.mkv", root / "final.mkv")
        joined = " ".join(command)
        self.assertIn("-c:v copy", joined)
        self.assertIn("-c:a copy", joined)
        self.assertIn("1:a:0?", joined)

    def test_read_exact_handles_short_pipe_reads(self) -> None:
        self.assertEqual(b"abcdef", _read_exact(ShortReader([b"a", b"bc", b"def"]), 6))
        self.assertEqual(b"ab", _read_exact(ShortReader([b"ab"]), 6))

    def test_empty_project_and_hdr_reject_before_output_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "out.mkv"
            output.write_bytes(b"previous-good")
            request = ComposerExportRequest(
                root / "source.mkv", output, self.profile(transfer="smpte2084"),
                OverlayComposerState(), "ffmpeg", "ffprobe", {},
            )
            with self.assertRaises(ValueError):
                export_composer_reference(request)
            self.assertEqual(b"previous-good", output.read_bytes())


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/FFprobe required")
class ComposerExportFfmpegIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        self.ffprobe = shutil.which("ffprobe") or "ffprobe"
        self.source = self.root / "source.mkv"
        self.logo = self.root / "logo.png"
        source_command = [
            self.ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=size=64x36:rate=4",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "1", "-c:v", "ffv1", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
            str(self.source),
        ]
        subprocess.run(source_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logo_command = [
            self.ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=red@0.5:s=8x8:d=1,format=rgba",
            "-frames:v", "1", str(self.logo),
        ]
        subprocess.run(logo_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def request(self, output: Path) -> ComposerExportRequest:
        return ComposerExportRequest(
            self.source,
            output,
            ComposerBaseProfile(64, 36, 4.0, 1.0, "yuv420p", "bt709", "bt709", "bt709", "tv"),
            OverlayComposerState([ComposerItem("logo", media=OverlayLayer(str(self.logo), "png", x=0.5, y=0.5))]),
            self.ffmpeg,
            self.ffprobe,
            {"master": self.source},
        )

    def test_small_real_export_is_atomic_and_complete(self) -> None:
        output = self.root / "result.mkv"
        output.write_bytes(b"previous-good")
        result = export_composer_reference(self.request(output))
        self.assertEqual(output, result.output)
        self.assertEqual(4, result.frames)
        self.assertGreater(output.stat().st_size, len(b"previous-good"))
        probe = subprocess.run(
            [self.ffprobe, "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1", str(output)],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.assertEqual("4", probe.stdout.strip())

    def test_cancel_preserves_existing_destination(self) -> None:
        output = self.root / "cancel.mkv"
        output.write_bytes(b"previous-good")
        with self.assertRaises(InterruptedError):
            export_composer_reference(self.request(output), cancelled=lambda: True)
        self.assertEqual(b"previous-good", output.read_bytes())
        self.assertFalse(any("partial" in path.name for path in self.root.iterdir()))


if __name__ == "__main__":
    unittest.main()
