from __future__ import annotations

import unittest

from cinepulse.color_pipeline import build_color_pipeline
from cinepulse.delivery import (
    PROFILE_ARCHIVE,
    PROFILE_AUTO,
    PROFILE_MASTER,
    PROFILE_STREAMING,
    PROFILE_WEB,
    build_delivery_plan,
    default_profile_for_suffix,
    required_suffix_for_profile,
)
from cinepulse.media_profile import ColorProfile


def color(*, hdr: bool = False, bits: int = 8):
    source = ColorProfile(
        "bt2020" if hdr else "bt709",
        "smpte2084" if hdr else "bt709",
        "bt2020nc" if hdr else "bt709",
        "tv",
        "yuv420p10le" if bits > 8 else "yuv420p",
        bits,
        hdr,
    )
    return build_color_pipeline(source, effects_active=False, transition_active=False, enhancement_mode="preserve", rife_active=False)


class DeliveryPlanTests(unittest.TestCase):
    def test_auto_profile_tracks_container(self):
        self.assertEqual(PROFILE_STREAMING, default_profile_for_suffix(".mp4"))
        self.assertEqual(PROFILE_MASTER, default_profile_for_suffix(".mov"))
        self.assertEqual(PROFILE_ARCHIVE, default_profile_for_suffix(".mkv"))
        self.assertEqual(PROFILE_WEB, default_profile_for_suffix(".webm"))

    def test_profile_extensions_are_explicit(self):
        self.assertEqual(".mp4", required_suffix_for_profile(PROFILE_STREAMING))
        self.assertEqual(".mov", required_suffix_for_profile(PROFILE_MASTER))
        self.assertEqual(".mkv", required_suffix_for_profile(PROFILE_ARCHIVE))
        self.assertEqual(".webm", required_suffix_for_profile(PROFILE_WEB))

    def test_mp4_streaming_is_hevc_aac(self):
        plan = build_delivery_plan(output="out.mp4", profile=PROFILE_AUTO, color_plan=color(), width=1920, height=1080, fps=60)
        self.assertFalse(plan.blocking)
        self.assertEqual("HEVC", plan.video_codec)
        self.assertEqual("AAC", plan.audio_codec)
        self.assertIn("-c:a", plan.audio_args())
        self.assertIn("+faststart", plan.muxer_args())

    def test_mov_master_is_prores_pcm(self):
        plan = build_delivery_plan(output="out.mov", profile=PROFILE_AUTO, color_plan=color(bits=10), width=3840, height=2160, fps=24)
        self.assertFalse(plan.blocking)
        self.assertEqual("ProRes 422 HQ", plan.video_codec)
        self.assertEqual("PCM 24-bit", plan.audio_codec)
        self.assertEqual("yuv422p10le", plan.pixel_format)

    def test_mkv_archive_is_hevc_flac(self):
        plan = build_delivery_plan(output="out.mkv", profile=PROFILE_ARCHIVE, color_plan=color(bits=10), width=3840, height=2160, fps=60)
        self.assertFalse(plan.blocking)
        self.assertEqual("FLAC", plan.audio_codec)
        self.assertTrue(plan.lossless_audio)

    def test_webm_uses_vp9_opus(self):
        plan = build_delivery_plan(output="out.webm", profile=PROFILE_WEB, color_plan=color(), width=1920, height=1080, fps=60)
        self.assertFalse(plan.blocking)
        self.assertEqual("VP9", plan.video_codec)
        self.assertEqual("Opus", plan.audio_codec)
        self.assertIn("libvpx-vp9", plan.video_args(use_cpu=True, nvenc_available=False, bitrate_mbps=12, fps=60))

    def test_profile_suffix_mismatch_blocks_before_render(self):
        plan = build_delivery_plan(output="out.webm", profile=PROFILE_STREAMING, color_plan=color(), width=1920, height=1080, fps=60)
        self.assertTrue(plan.blocking)
        self.assertTrue(any(issue.code == "CP-008-PROFILE" for issue in plan.issues))

    def test_12k_is_blocked_in_stable_profile(self):
        plan = build_delivery_plan(output="out.mkv", profile=PROFILE_AUTO, color_plan=color(), width=11520, height=6480, fps=60)
        self.assertTrue(plan.blocking)
        self.assertTrue(any(issue.code == "CP-009-RESOLUTION" for issue in plan.issues))

    def test_240fps_is_blocked_in_stable_profile(self):
        plan = build_delivery_plan(output="out.mp4", profile=PROFILE_AUTO, color_plan=color(), width=1920, height=1080, fps=240)
        self.assertTrue(plan.blocking)
        self.assertTrue(any(issue.code == "CP-009-FPS" for issue in plan.issues))

    def test_120fps_is_supported_but_warned(self):
        plan = build_delivery_plan(output="out.mp4", profile=PROFILE_AUTO, color_plan=color(), width=7680, height=4320, fps=120)
        self.assertFalse(plan.blocking)
        self.assertTrue(any(issue.code == "CP-009-HFR" for issue in plan.issues))

    def test_hdr_mp4_selects_10bit_hevc(self):
        plan = build_delivery_plan(output="out.mp4", profile=PROFILE_AUTO, color_plan=color(hdr=True, bits=10), width=3840, height=2160, fps=60)
        self.assertEqual(10, plan.bit_depth)
        self.assertEqual("p010le", plan.pixel_format)
        self.assertTrue(plan.hdr)

    def test_audio_master_does_not_force_downmix_or_sample_rate(self):
        plan = build_delivery_plan(output="out.mov", profile=PROFILE_MASTER, color_plan=color(), width=1920, height=1080, fps=24)
        args = plan.audio_args()
        self.assertNotIn("-ac", args)
        self.assertNotIn("-ar", args)

    def test_missing_required_encoder_blocks_when_capabilities_are_known(self):
        plan = build_delivery_plan(
            output="out.webm", profile=PROFILE_WEB, color_plan=color(), width=1920, height=1080, fps=60,
            available_encoders={"aac", "libx265"}, use_cpu=True, nvenc_available=False,
        )
        self.assertTrue(plan.blocking)
        self.assertTrue(any(issue.code == "CP-009-ENCODER" for issue in plan.issues))
        self.assertTrue(any(issue.code == "CP-015-AUDIO-ENCODER" for issue in plan.issues))


if __name__ == "__main__":
    unittest.main()
