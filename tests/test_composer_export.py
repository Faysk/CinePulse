from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cinepulse.composer_export import (
    ComposerBaseProfile,
    ComposerExportRequest,
    _base_decode_command,
    _composer_frame_count,
    _composer_timeline_duration,
    _mux_command,
    _read_exact,
    _resolve_audio_envelopes,
    _video_encode_command,
    export_composer_reference,
)
from cinepulse.gpu_compositor import OverlayLayer
from cinepulse.overlay_composer import ComposerItem, OverlayComposerState, VisualizerLayer


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

    def test_decode_command_has_explicit_bt709_scale_range_and_no_implicit_fps_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            command = _base_decode_command(self.request(Path(temporary)), 4)
        joined = " ".join(command)
        self.assertIn("scale=w=iw:h=ih", joined)
        self.assertIn("in_color_matrix=bt709", joined)
        self.assertIn("out_color_matrix=bt709", joined)
        self.assertIn("in_range=tv", joined)
        self.assertIn("out_range=pc", joined)
        self.assertIn("format=rgba", joined)
        self.assertNotIn("zscale", joined)
        self.assertIn("-fps_mode passthrough", joined)
        self.assertNotIn(" -r ", joined)
        self.assertIn("-pix_fmt rgba", joined)

    def test_still_background_decode_loops_and_cover_fits_output_canvas(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = self.request(
                root,
                self.profile(width=3840, height=2160, fps=60.0, duration=3.0, still_image=True),
            )
            command = _base_decode_command(request, 180)
        joined = " ".join(command)
        self.assertIn("-loop 1", joined)
        self.assertIn("-framerate 60", joined)
        self.assertIn("scale=w=3840:h=2160:force_original_aspect_ratio=increase", joined)
        self.assertIn("crop=3840:2160", joined)
        self.assertIn("-frames:v 180", joined)

    def test_reference_encoder_is_lossless_rgb_ffv1(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = _video_encode_command(self.request(root), root / "visual.mkv")
        joined = " ".join(command)
        self.assertIn("-c:v ffv1", joined)
        self.assertIn("-level 3", joined)
        self.assertIn("-pix_fmt gbrap", joined)
        self.assertIn("-color_primaries bt709", joined)
        self.assertIn("-color_trc bt709", joined)
        self.assertIn("-color_range pc", joined)
        self.assertNotIn("-colorspace gbr", joined)
        self.assertNotIn("nvenc", joined.lower())

    def test_mux_preserves_source_audio_independent_from_analysis_master(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = ComposerExportRequest(
                root / "source.mkv", root / "output.mkv", self.profile(),
                OverlayComposerState([ComposerItem("logo", media=OverlayLayer(str(root / "logo.png"), "png"))]),
                "ffmpeg", "ffprobe", {"master": root / "analysis-only.flac"},
            )
            command = _mux_command(request, root / "visual.mkv", root / "final.mkv")
        joined = " ".join(command)
        self.assertIn(str(root / "source.mkv"), joined)
        self.assertNotIn(str(root / "analysis-only.flac"), joined)
        self.assertIn("-c:v copy", joined)
        self.assertIn("-c:a copy", joined)
        self.assertIn("1:a:0?", joined)
        self.assertIn("-frames:v 4", joined)
        self.assertEqual(1, command.count("-t"))
        audio_index = command.index(str(root / "source.mkv"), 1)
        self.assertEqual(["-t", "1.000000", "-i"], command[audio_index - 3:audio_index])
        self.assertNotIn("-shortest", joined)

    def test_fractional_fps_mux_uses_frame_bound_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = self.profile(fps=30000 / 1001, duration=1.0)
            request = self.request(root, profile)
            command = _mux_command(request, root / "visual.mkv", root / "final.mkv")
        self.assertEqual(30, _composer_frame_count(profile))
        self.assertAlmostEqual(1001 / 1000, _composer_timeline_duration(profile), places=12)
        self.assertIn("-frames:v", command)
        self.assertEqual("30", command[command.index("-frames:v") + 1])
        self.assertEqual("1.001000", command[command.index("-t") + 1])
        self.assertNotIn("1.000000", command)

    def test_mux_allows_explicit_output_audio_override(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = self.request(root)
            request = ComposerExportRequest(
                base.source, base.output, base.profile, base.state, base.ffmpeg, base.ffprobe,
                base.audio_sources, output_audio=root / "replacement.flac",
            )
            joined = " ".join(_mux_command(request, root / "visual.mkv", root / "final.mkv"))
        self.assertIn(str(root / "replacement.flac"), joined)
        self.assertNotIn(str(root / "source.mkv"), joined)

    def test_read_exact_handles_short_pipe_reads(self) -> None:
        self.assertEqual(b"abcdef", _read_exact(ShortReader([b"a", b"bc", b"def"]), 6))
        self.assertEqual(b"ab", _read_exact(ShortReader([b"ab"]), 6))

    def test_export_resolves_music_envelopes_from_request_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = self.request(root)
            song = root / "song.flac"
            vocals = root / "vocals.wav"
            request = ComposerExportRequest(
                base.source, base.output, base.profile, base.state, base.ffmpeg, base.ffprobe,
                {"vocals": vocals}, output_audio=song,
            )
            expected = {"master": object()}
            with patch(
                "cinepulse.composer_export.load_bound_visualizer_envelopes",
                return_value=expected,
            ) as loader:
                resolved = _resolve_audio_envelopes(request, None, lambda _message: None)
            self.assertIs(resolved, expected)
            kwargs = loader.call_args.kwargs
            self.assertEqual(song, kwargs["sources"]["master"])
            self.assertEqual(vocals, kwargs["sources"]["vocals"])
            self.assertEqual(request.profile.duration, kwargs["duration"])

    def test_injected_envelopes_skip_duplicate_audio_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            request = self.request(Path(temporary))
            injected = {"master": object()}
            with patch("cinepulse.composer_export.load_bound_visualizer_envelopes") as loader:
                resolved = _resolve_audio_envelopes(request, injected, lambda _message: None)
            self.assertEqual(injected, resolved)
            loader.assert_not_called()

    def test_encoder_spawn_failure_reaps_already_started_base_decoder(self) -> None:
        class RunningProcess:
            def __init__(self) -> None:
                self.stdout = io.BytesIO()
                self.stderr = io.BytesIO()
                self.stdin = None

            def poll(self):
                return None

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = self.request(root)
            request.source.write_bytes(b"source")
            base = RunningProcess()
            with (
                patch("cinepulse.composer_export._validate_media", return_value={"logo": object()}),
                patch("cinepulse.composer_export.validate_composer_resources"),
                patch("cinepulse.composer_export._resolve_audio_envelopes", return_value={}),
                patch(
                    "cinepulse.composer_export.subprocess.Popen",
                    side_effect=[base, OSError("encoder spawn failed")],
                ),
                patch("cinepulse.composer_export.terminate_process_tree") as terminate,
            ):
                with self.assertRaisesRegex(OSError, "encoder spawn failed"):
                    export_composer_reference(request)

            terminate.assert_called_once()
            self.assertTrue(base.stdout.closed)
            self.assertTrue(base.stderr.closed)

    def test_empty_project_and_hdr_reject_before_output_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mkv"
            output = root / "out.mkv"
            # The fixture must reach the HDR/project validation gates; a missing
            # source would correctly fail earlier with FileNotFoundError and
            # would not test the output-preservation contract named here.
            source.write_bytes(b"existing-source")
            output.write_bytes(b"previous-good")
            request = ComposerExportRequest(
                source, output, self.profile(transfer="smpte2084"),
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

    def test_fractional_fps_still_export_preserves_all_frames(self) -> None:
        output = self.root / "fractional-result.mkv"
        request = ComposerExportRequest(
            self.logo,
            output,
            ComposerBaseProfile(
                64, 36, 30000 / 1001, 1.0,
                "rgba", "bt709", "bt709", "bt709", "pc",
                still_image=True,
            ),
            OverlayComposerState([
                ComposerItem("logo", media=OverlayLayer(str(self.logo), "png", x=0.5, y=0.5))
            ]),
            self.ffmpeg,
            self.ffprobe,
            {"master": self.source},
            output_audio=self.source,
        )
        result = export_composer_reference(request)
        self.assertEqual(30, result.frames)
        probe = subprocess.run(
            [
                self.ffprobe, "-v", "error", "-count_frames", "-select_streams", "v:0",
                "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1",
                str(output),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual("30", probe.stdout.strip())

    def test_audio_reactive_visualizer_is_not_flat_in_final_export(self) -> None:
        source = self.root / "music-source.mkv"
        output = self.root / "music-result.mkv"
        subprocess.run(
            [
                self.ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black:size=128x72:rate=4",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                "-t", "1", "-c:v", "ffv1", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le",
                "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                str(source),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        state = OverlayComposerState([
            ComposerItem(
                "spectrum",
                visualizer=VisualizerLayer("spectrum", x=0.5, y=0.5, scale=0.85, bars=16, reaction=1.0),
            )
        ])
        request = ComposerExportRequest(
            source,
            output,
            ComposerBaseProfile(128, 72, 4.0, 1.0, "yuv420p", "bt709", "bt709", "bt709", "tv"),
            state,
            self.ffmpeg,
            self.ffprobe,
            {"master": source},
        )
        export_composer_reference(request)
        frame = subprocess.run(
            [
                self.ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(output),
                "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
        bright_pixels = sum(
            1
            for index in range(0, len(frame), 3)
            if max(frame[index:index + 3]) >= 180
        )
        self.assertGreater(bright_pixels, 100)

    def test_cancel_preserves_existing_destination(self) -> None:
        output = self.root / "cancel.mkv"
        output.write_bytes(b"previous-good")
        with self.assertRaises(InterruptedError):
            export_composer_reference(self.request(output), cancelled=lambda: True)
        self.assertEqual(b"previous-good", output.read_bytes())
        self.assertFalse(any("partial" in path.name for path in self.root.iterdir()))


if __name__ == "__main__":
    unittest.main()
