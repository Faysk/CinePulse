from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from cinepulse.studio import VideoOptimizerStudio


def test_realesrgan_cache_key_changes_with_component_identity_and_model_files() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "source.mp4"
        source.write_bytes(b"video")
        component = root / "real-esrgan"
        models = component / "models"
        models.mkdir(parents=True)
        exe = component / "realesrgan-ncnn-vulkan.exe"
        model_bin = models / "realesr-animevideov3-x2.bin"
        model_param = models / "realesr-animevideov3-x2.param"
        exe.write_bytes(b"exe-v1")
        model_bin.write_bytes(b"bin-v1")
        model_param.write_bytes(b"param-v1")

        with (
            patch("cinepulse.studio.REAL_ESRGAN", exe),
            patch("cinepulse.studio.REAL_ESRGAN_MODELS", models),
            patch(
                "cinepulse.studio.bootstrap_component_fingerprint",
                return_value="real_esrgan:v1:" + "a" * 64,
            ),
        ):
            first = VideoOptimizerStudio._ai_cache_key(
                str(source), 0.0, 10.0, 30.0, 1920, 1080
            )

        model_param.write_bytes(b"param-v2-with-different-size")
        with (
            patch("cinepulse.studio.REAL_ESRGAN", exe),
            patch("cinepulse.studio.REAL_ESRGAN_MODELS", models),
            patch(
                "cinepulse.studio.bootstrap_component_fingerprint",
                return_value="real_esrgan:v1:" + "a" * 64,
            ),
        ):
            second = VideoOptimizerStudio._ai_cache_key(
                str(source), 0.0, 10.0, 30.0, 1920, 1080
            )
        assert first != second

        with (
            patch("cinepulse.studio.REAL_ESRGAN", exe),
            patch("cinepulse.studio.REAL_ESRGAN_MODELS", models),
            patch(
                "cinepulse.studio.bootstrap_component_fingerprint",
                return_value="real_esrgan:v2:" + "b" * 64,
            ),
        ):
            third = VideoOptimizerStudio._ai_cache_key(
                str(source), 0.0, 10.0, 30.0, 1920, 1080
            )
        assert second != third
