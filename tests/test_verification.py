from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from cinepulse.verification import VerifyExpectation, deep_verify, quick_verify


def probe(*, frames="60", audio=True, fps="30/1", width=640, height=360, duration="2.000000", vcodec="hevc", acodec="aac"):
    streams = [{
        "codec_type": "video", "codec_name": vcodec, "width": width, "height": height,
        "avg_frame_rate": fps, "r_frame_rate": fps, "nb_read_frames": frames,
        "start_time": "0.000000", "duration": duration,
    }]
    if audio:
        streams.append({
            "codec_type": "audio", "codec_name": acodec, "sample_rate": "48000", "channels": 2,
            "start_time": "0.000000", "duration": duration,
        })
    return {"streams": streams, "format": {"duration": duration}}


class VerificationTests(unittest.TestCase):
    def expected(self, **overrides):
        values = dict(width=640, height=360, fps=30.0, duration=2.0, expect_audio=True,
                      video_codec="HEVC", audio_codec="AAC", audio_channels=2, audio_sample_rate=48000)
        values.update(overrides)
        return VerifyExpectation(**values)

    def test_quick_verify_accepts_exact_contract(self):
        result = quick_verify("ffprobe", "out.mp4", self.expected(), probe_data=probe())
        self.assertTrue(result.passed)
        self.assertEqual(result.frame_count, 60)
        self.assertTrue(result.cfr)
        self.assertEqual(result.av_sync_delta, 0.0)

    def test_frame_count_mismatch_is_blocking(self):
        result = quick_verify("ffprobe", "out.mp4", self.expected(), probe_data=probe(frames="52"))
        self.assertFalse(result.passed)
        self.assertTrue(any(issue.code == "VERIFY-FRAMES" for issue in result.errors))

    def test_missing_expected_audio_is_blocking(self):
        result = quick_verify("ffprobe", "out.mp4", self.expected(), probe_data=probe(audio=False))
        self.assertFalse(result.passed)
        self.assertTrue(any(issue.code == "VERIFY-AUDIO-MISSING" for issue in result.errors))

    def test_unexpected_audio_is_blocking(self):
        result = quick_verify("ffprobe", "out.mp4", self.expected(expect_audio=False, audio_codec=None, audio_channels=None, audio_sample_rate=None), probe_data=probe(audio=True))
        self.assertFalse(result.passed)
        self.assertTrue(any(issue.code == "VERIFY-AUDIO-UNEXPECTED" for issue in result.errors))

    def test_codec_mismatch_is_blocking(self):
        result = quick_verify("ffprobe", "out.mp4", self.expected(), probe_data=probe(vcodec="h264"))
        self.assertFalse(result.passed)
        self.assertTrue(any(issue.code == "VERIFY-VIDEO-CODEC" for issue in result.errors))

    @patch("cinepulse.verification.quick_verify")
    def test_deep_verify_marks_decode_eof(self, quick_mock):
        quick_mock.return_value = quick_verify("ffprobe", "out.mp4", self.expected(), probe_data=probe())
        runner = lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "", "")
        result = deep_verify("ffmpeg", "ffprobe", "out.mp4", self.expected(), process_runner=runner)
        self.assertTrue(result.passed)
        self.assertTrue(result.decoded_to_eof)
        self.assertEqual(result.mode, "deep")

    @patch("cinepulse.verification.quick_verify")
    def test_deep_verify_decode_failure_is_blocking(self, quick_mock):
        quick_mock.return_value = quick_verify("ffprobe", "out.mp4", self.expected(), probe_data=probe())
        runner = lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "corrupt packet")
        result = deep_verify("ffmpeg", "ffprobe", "out.mp4", self.expected(), process_runner=runner)
        self.assertFalse(result.passed)
        self.assertTrue(any(issue.code == "VERIFY-DECODE-EOF" for issue in result.errors))


if __name__ == "__main__":
    unittest.main()
