from __future__ import annotations

import io
import struct
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cinepulse.studio import VideoOptimizerStudio, _valid_cached_wav


def _fake_wav(payload: bytes = b"\x00" * 64) -> bytes:
    fmt_payload = struct.pack(
        "<HHIIHH",
        1,      # PCM
        1,      # mono
        48_000,
        48_000 * 3,
        3,
        24,
    )
    fmt_chunk = b"fmt " + struct.pack("<I", len(fmt_payload)) + fmt_payload
    data_chunk = b"data" + struct.pack("<I", len(payload)) + payload
    riff_size = 4 + len(fmt_chunk) + len(data_chunk)
    return b"RIFF" + struct.pack("<I", riff_size) + b"WAVE" + fmt_chunk + data_chunk


def test_cached_wav_validator_rejects_large_garbage_and_truncation() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        valid = root / "valid.wav"
        garbage = root / "garbage.wav"
        truncated = root / "truncated.wav"

        valid.write_bytes(_fake_wav())
        garbage.write_bytes(b"X" * 256)
        payload = bytearray(_fake_wav())
        data_size_offset = payload.index(b"data") + 4
        payload[data_size_offset:data_size_offset + 4] = struct.pack("<I", 999_999)
        truncated.write_bytes(payload)

        assert _valid_cached_wav(valid)
        assert not _valid_cached_wav(garbage)
        assert not _valid_cached_wav(truncated)


class FakeBackgroundCommand:
    cancelled = False

    def __init__(self, command, **_kwargs):
        self.command = list(command)

    def start(self):
        return self

    def wait(self):
        output = Path(self.command[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        assert output.suffix.lower() == ".wav"
        output.write_bytes(_fake_wav())
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
        (separated / f"{name}.wav").write_bytes(_fake_wav())
    return cache


class FakeDemucsProcess:
    def __init__(self, command, *, valid=True, returncode=0, **_kwargs):
        self.command = list(command)
        self.stdout = io.StringIO("demucs test output\n")
        self.returncode = int(returncode)
        output = Path(self.command[self.command.index("-o") + 1])
        source = Path(self.command[-1])
        separated = output / "htdemucs_ft" / source.stem
        separated.mkdir(parents=True, exist_ok=True)
        payload = _fake_wav() if valid else (b"W" * 128)
        for name in ("bass", "drums", "vocals", "other"):
            (separated / f"{name}.wav").write_bytes(payload)

    def poll(self):
        return self.returncode

    def wait(self):
        return self.returncode


def _demucs_paths(root: Path):
    models = root / "models"
    repo = models / "demucs" / "local_repo"
    repo.mkdir(parents=True)
    (repo / "htdemucs_ft.yaml").write_text("models: []", encoding="utf-8")
    ai_root = root / "ai"
    python = ai_root / "venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"python")
    return models, ai_root, python


def test_demucs_stems_are_promoted_only_after_complete_success() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "music.wav"
        source.write_bytes(b"audio")
        cache = root / "cache"
        models, ai_root, python = _demucs_paths(root)

        def popen(command, **kwargs):
            return FakeDemucsProcess(command, valid=True, returncode=0, **kwargs)

        with (
            patch("cinepulse.studio.PATHS", SimpleNamespace(cache=cache)),
            patch("cinepulse.studio.ai_suite.MODELS", models),
            patch("cinepulse.studio.ai_suite.AI_ROOT", ai_root),
            patch("cinepulse.studio.ai_suite.VENV_PYTHON", python),
            patch("cinepulse.studio.stem_cache_key", return_value="fixed-key"),
            patch("cinepulse.studio.subprocess.Popen", side_effect=popen),
        ):
            result = _studio()._prepare_reactive_audio(
                str(source), "Graves", False, 4
            )

        bass = Path(result)
        assert bass.is_file()
        assert bass.read_bytes()[8:12] == b"WAVE"
        cache_root = cache / "stems" / "fixed-key"
        assert not list(cache_root.glob(".demucs-partial-*"))


def test_demucs_invalid_stems_never_promote_partial_cache() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "music.wav"
        source.write_bytes(b"audio")
        cache = root / "cache"
        models, ai_root, python = _demucs_paths(root)

        def popen(command, **kwargs):
            return FakeDemucsProcess(command, valid=False, returncode=0, **kwargs)

        with (
            patch("cinepulse.studio.PATHS", SimpleNamespace(cache=cache)),
            patch("cinepulse.studio.ai_suite.MODELS", models),
            patch("cinepulse.studio.ai_suite.AI_ROOT", ai_root),
            patch("cinepulse.studio.ai_suite.VENV_PYTHON", python),
            patch("cinepulse.studio.stem_cache_key", return_value="fixed-key"),
            patch("cinepulse.studio.subprocess.Popen", side_effect=popen),
        ):
            with unittest.TestCase().assertRaisesRegex(RuntimeError, "stems WAV válidos"):
                _studio()._prepare_reactive_audio(
                    str(source), "Graves", False, 4
                )

        separated = cache / "stems" / "fixed-key" / "htdemucs_ft" / source.stem
        assert not separated.exists()
        cache_root = cache / "stems" / "fixed-key"
        assert not list(cache_root.glob(".demucs-partial-*"))


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
        assert mixed.read_bytes().startswith(b"RIFF")
        assert mixed.stat().st_size > 44
        assert not list(mixed.parent.glob(mixed.stem + ".partial-*.wav"))


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
            with unittest.TestCase().assertRaises(InterruptedError):
                studio._prepare_reactive_audio(
                    str(source), "Graves e batidas", False, 4
                )
        mixed = cache / "stems" / "fixed-key" / "reactive_bass_drums.wav"
        assert not mixed.exists()
        assert not list(mixed.parent.glob(mixed.stem + ".partial-*.wav"))



def test_invalid_cached_mix_is_rebuilt_instead_of_reused() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "music.wav"
        source.write_bytes(b"audio")
        cache = _prepare_tree(root, source)
        models = root / "models"
        ai_root = root / "ai"
        mixed = cache / "stems" / "fixed-key" / "reactive_bass_drums.wav"
        mixed.write_bytes(b"RIFF" + (b"\\x00" * 128))

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

        rebuilt = Path(result)
        assert rebuilt == mixed
        assert rebuilt.stat().st_size > 44
        assert rebuilt.read_bytes().startswith(b"RIFF")



def test_stale_demucs_partial_tree_is_never_reused_as_cache() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "music.wav"
        source.write_bytes(b"audio")
        cache = root / "cache"
        cache_root = cache / "stems" / "fixed-key"
        stale = cache_root / ".demucs-partial-stale" / "htdemucs_ft" / source.stem
        stale.mkdir(parents=True)
        for name in ("bass", "drums", "vocals", "other"):
            (stale / f"{name}.wav").write_bytes(_fake_wav())

        models, ai_root, python = _demucs_paths(root)

        def popen(command, **kwargs):
            return FakeDemucsProcess(command, valid=True, returncode=0, **kwargs)

        with (
            patch("cinepulse.studio.PATHS", SimpleNamespace(cache=cache)),
            patch("cinepulse.studio.ai_suite.MODELS", models),
            patch("cinepulse.studio.ai_suite.AI_ROOT", ai_root),
            patch("cinepulse.studio.ai_suite.VENV_PYTHON", python),
            patch("cinepulse.studio.stem_cache_key", return_value="fixed-key"),
            patch("cinepulse.studio.subprocess.Popen", side_effect=popen),
        ):
            result = _studio()._prepare_reactive_audio(
                str(source), "Graves", False, 4
            )

        promoted = Path(result)
        assert promoted == cache_root / "htdemucs_ft" / source.stem / "bass.wav"
        assert promoted.is_file()
        assert promoted.read_bytes()[8:12] == b"WAVE"


def test_large_garbage_cached_stems_are_rebuilt_instead_of_reused() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "music.wav"
        source.write_bytes(b"audio")
        cache = root / "cache"
        separated = cache / "stems" / "fixed-key" / "htdemucs_ft" / source.stem
        separated.mkdir(parents=True)
        for name in ("bass", "drums", "vocals", "other"):
            (separated / f"{name}.wav").write_bytes(b"X" * 256)

        models, ai_root, python = _demucs_paths(root)
        calls = {"count": 0}

        def popen(command, **kwargs):
            calls["count"] += 1
            return FakeDemucsProcess(command, valid=True, returncode=0, **kwargs)

        with (
            patch("cinepulse.studio.PATHS", SimpleNamespace(cache=cache)),
            patch("cinepulse.studio.ai_suite.MODELS", models),
            patch("cinepulse.studio.ai_suite.AI_ROOT", ai_root),
            patch("cinepulse.studio.ai_suite.VENV_PYTHON", python),
            patch("cinepulse.studio.stem_cache_key", return_value="fixed-key"),
            patch("cinepulse.studio.subprocess.Popen", side_effect=popen),
        ):
            result = _studio()._prepare_reactive_audio(
                str(source), "Graves", False, 4
            )

        rebuilt = Path(result)
        assert calls["count"] == 1
        assert rebuilt == separated / "bass.wav"
        assert rebuilt.read_bytes()[:4] == b"RIFF"
        assert rebuilt.read_bytes()[8:12] == b"WAVE"
