from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cinepulse.composer_audio import _source_key as visualizer_source_key
from cinepulse.music_envelope import _source_key as music_source_key
from cinepulse.source_identity import (
    FULL_HASH_LIMIT_BYTES,
    SAMPLE_BYTES,
    file_content_identity,
)
from cinepulse.stem_engine import stem_cache_key
from cinepulse.studio import VideoOptimizerStudio


class SourceContentIdentityTests(unittest.TestCase):
    @staticmethod
    def _rewrite_preserving_mtime(path: Path, payload: bytes) -> None:
        before = path.stat()
        path.write_bytes(payload)
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))

    def test_small_file_identity_detects_same_size_content_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.bin"
            path.write_bytes(b"A" * 4096)
            first = file_content_identity(path)
            self._rewrite_preserving_mtime(path, b"B" * 4096)
            second = file_content_identity(path)

            self.assertEqual(first["size"], second["size"])
            self.assertEqual(first["mtime_ns"], second["mtime_ns"])
            self.assertEqual("full-sha256-v1", first["content_mode"])
            self.assertNotEqual(first["content_sha256"], second["content_sha256"])

    def test_large_file_identity_is_bounded_and_content_aware(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "large.bin"
            size = FULL_HASH_LIMIT_BYTES + SAMPLE_BYTES * 2
            with path.open("wb") as stream:
                stream.seek(size - 1)
                stream.write(b"\0")
            first = file_content_identity(path)
            self.assertEqual("sampled-sha256-v1", first["content_mode"])

            before = path.stat()
            with path.open("r+b") as stream:
                stream.seek(size // 2)
                stream.write(b"changed-middle-window")
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
            second = file_content_identity(path)
            self.assertNotEqual(first["content_sha256"], second["content_sha256"])

    def test_audio_caches_change_when_content_changes_but_size_and_mtime_do_not(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "audio.wav"
            path.write_bytes(b"A" * 8192)
            music_first = music_source_key(str(path), 1.0, 60.0)
            visual_first = visualizer_source_key(str(path), 1.0, 30.0, 64, 960.0)
            stem_first = stem_cache_key(path)

            self._rewrite_preserving_mtime(path, b"B" * 8192)

            self.assertNotEqual(music_first, music_source_key(str(path), 1.0, 60.0))
            self.assertNotEqual(
                visual_first,
                visualizer_source_key(str(path), 1.0, 30.0, 64, 960.0),
            )
            self.assertNotEqual(stem_first, stem_cache_key(path))

    def test_ai_master_cache_changes_for_same_metadata_source_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.mp4"
            source.write_bytes(b"A" * 8192)
            with patch(
                "cinepulse.studio.bootstrap_component_fingerprint",
                return_value="real_esrgan:v1:" + "a" * 64,
            ):
                first = VideoOptimizerStudio._ai_cache_key(
                    str(source), 0.0, 2.0, 24.0, 1920, 1080
                )
                self._rewrite_preserving_mtime(source, b"B" * 8192)
                second = VideoOptimizerStudio._ai_cache_key(
                    str(source), 0.0, 2.0, 24.0, 1920, 1080
                )
            self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
