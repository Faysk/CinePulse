from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from cinepulse.studio import VideoOptimizerStudio


class FakeBackgroundCommand:
    cancelled = False

    def __init__(self, command, **_kwargs):
        self.command = list(command)

    def start(self):
        return self

    def wait(self):
        output = Path(self.command[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"RIFF-test-wav")
        return SimpleNamespace(cancelled=bool(self.cancelled))


def _studio() -> VideoOptimizerStudio:
    studio = VideoOptimizerStudio.__new__(VideoOptimizerStudio)
    studio._cancelled = False
    studio._log = lambda *_args, **_kwargs: None
    studio._set_stage = lambda *_args, **_kwargs: None
    return studio


def _prepare_tree(root: Path, source: Path) -> Path:
    cache = root / "cache"
    separated = cache / "stems" / "fixed-key" / "htdemucs_ft" / source.stem
    separated.mkdir(parents=True)
    for name in ("bass", "drums", "vocals", "other"):
        (separated / f"{name}.wav").write_bytes(b"stem")
    return cache


def test_demucs_stem_mix_promotes_partial_atomically() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "music.wav"
        source.write_bytes(b"audio")
        cache = _prepare_tree(root, source)
        models = root / "models"
        ai_root = root / "ai"
        with (
            patch("cinepulse.studio.PATHS", SimpleNamespace(cache=cache)),
            patch("cinepulse.studio.ai_suite.MODELS", models),
            patch("cinepulse.studio.ai_suite.AI_ROOT", ai_root),
            patch("cinepulse.studio.stem_cache_key", return_value="fixed-key"),
            patch("cinepulse.studio.BackgroundCommand", FakeBackgroundCommand),
        ):
            result = _studio()._prepare_reactive_audio(
                str(source), "Graves e batidas", False, 4
            )
        mixed = Path(result)
        assert mixed.is_file()
        assert mixed.read_bytes() == b"RIFF-test-wav"
        assert not mixed.with_name(mixed.name + ".partial").exists()


def test_demucs_stem_mix_cancel_never_leaves_reusable_partial_cache() -> None:
    class CancelledBackgroundCommand(FakeBackgroundCommand):
        cancelled = True

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "music.wav"
        source.write_bytes(b"audio")
        cache = _prepare_tree(root, source)
        models = root / "models"
        ai_root = root / "ai"
        studio = _studio()
        with (
            patch("cinepulse.studio.PATHS", SimpleNamespace(cache=cache)),
            patch("cinepulse.studio.ai_suite.MODELS", models),
            patch("cinepulse.studio.ai_suite.AI_ROOT", ai_root),
            patch("cinepulse.studio.stem_cache_key", return_value="fixed-key"),
            patch("cinepulse.studio.BackgroundCommand", CancelledBackgroundCommand),
        ):
            with pytest.raises(InterruptedError):
                studio._prepare_reactive_audio(
                    str(source), "Graves e batidas", False, 4
                )
        mixed = cache / "stems" / "fixed-key" / "reactive_bass_drums.wav"
        assert not mixed.exists()
        assert not mixed.with_name(mixed.name + ".partial").exists()
