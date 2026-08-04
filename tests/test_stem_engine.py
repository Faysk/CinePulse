from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cinepulse.stem_engine import build_demucs_command, stem_cache_key, stems_for_focus


class StemEngineTests(unittest.TestCase):
    def test_focus_mapping(self) -> None:
        self.assertEqual(("bass", "drums"), stems_for_focus("Graves e batidas"))
        self.assertEqual((), stems_for_focus("Todos equilibrados"))

    def test_command_uses_local_model_and_device(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            python = root / "python.exe"
            python.write_bytes(b"exe")
            repo = root / "repo"
            repo.mkdir()
            (repo / "htdemucs_ft.yaml").write_text("models: []", encoding="utf-8")
            command = build_demucs_command(python, repo, root / "out", root / "music.wav", use_cpu=False)
            self.assertEqual("cuda", command[command.index("--device") + 1])

    def test_cache_changes_with_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            audio = Path(temporary) / "music.wav"
            audio.write_bytes(b"one")
            first = stem_cache_key(audio)
            audio.write_bytes(b"two-two")
            self.assertNotEqual(first, stem_cache_key(audio))

