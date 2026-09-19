from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cinepulse.stem_engine import (
    build_demucs_command,
    demucs_model_identity,
    stem_cache_key,
    stems_for_focus,
)


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

    def test_cache_changes_when_demucs_runtime_or_weights_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "music.wav"
            audio.write_bytes(b"audio")
            repo = root / "repo"
            repo.mkdir()
            state = root / "demucs-install-state.json"
            state.write_text(
                '{"schema": 2, "python": "3.14.7", "demucs": "4.1.0", "torch": "2.13.0+cu132"}',
                encoding="utf-8",
            )
            for name in (
                "htdemucs_ft.yaml",
                "f7e0c4bc-ba3fe64a.th",
                "d12395a8-e57c48e6.th",
                "92cfc3b6-ef3bcb9c.th",
                "04573f0d-f3cf25b2.th",
            ):
                (repo / name).write_bytes(name.encode("utf-8"))

            first = stem_cache_key(audio, model_repo=repo, state_file=state)
            state.write_text(
                '{"schema": 2, "python": "3.14.7", "demucs": "4.1.1", "torch": "2.13.0+cu132"}',
                encoding="utf-8",
            )
            second = stem_cache_key(audio, model_repo=repo, state_file=state)
            self.assertNotEqual(first, second)

            state.write_text(
                '{"schema": 2, "python": "3.14.7", "demucs": "4.1.0", "torch": "2.13.0+cu132"}',
                encoding="utf-8",
            )
            (repo / "f7e0c4bc-ba3fe64a.th").write_bytes(b"updated-weight")
            third = stem_cache_key(audio, model_repo=repo, state_file=state)
            self.assertNotEqual(first, third)
            self.assertNotEqual(
                demucs_model_identity(repo, state),
                demucs_model_identity(None, None),
            )

    def test_cache_changes_when_verified_weight_fingerprint_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "music.wav"
            audio.write_bytes(b"audio")
            repo = root / "repo"
            repo.mkdir()
            state = root / "demucs-install-state.json"
            for name in (
                "htdemucs_ft.yaml",
                "f7e0c4bc-ba3fe64a.th",
                "d12395a8-e57c48e6.th",
                "92cfc3b6-ef3bcb9c.th",
                "04573f0d-f3cf25b2.th",
            ):
                (repo / name).write_bytes(name.encode("utf-8"))

            state.write_text(
                '{"schema": 3, "python": "3.14.7", "demucs": "4.1.0", '
                '"torch": "2.13.0+cu132", "weights_fingerprint": "a.th:' + "a" * 64 + '"}',
                encoding="utf-8",
            )
            first = stem_cache_key(audio, model_repo=repo, state_file=state)
            state.write_text(
                '{"schema": 3, "python": "3.14.7", "demucs": "4.1.0", '
                '"torch": "2.13.0+cu132", "weights_fingerprint": "a.th:' + "b" * 64 + '"}',
                encoding="utf-8",
            )
            second = stem_cache_key(audio, model_repo=repo, state_file=state)
            self.assertNotEqual(first, second)

    def test_cache_changes_with_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            audio = Path(temporary) / "music.wav"
            audio.write_bytes(b"one")
            first = stem_cache_key(audio)
            audio.write_bytes(b"two-two")
            self.assertNotEqual(first, stem_cache_key(audio))

