"""Verification contracts for CinePulse final outputs.

Core Integrity Phase 7 separates *quick verification* (metadata, streams, CFR,
frame count and coarse A/V sync) from *deep verification* (decode every selected
stream through EOF).  The same structured result is persisted in render history
and summarized in the human-readable report.
"""

from __future__ import annotations

import json
import math
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class VerifyExpectation:
    width: int
    height: int
    fps: float
    duration: float
    expect_audio: bool
    video_codec: str | None = None
    audio_codec: str | None = None
    audio_channels: int | None = None
    audio_sample_rate: int | None = None
    frame_tolerance: int = 2
    duration_tolerance: float = 0.35
    sync_tolerance: float = 0.35


@dataclass(frozen=True)
class VerificationIssue:
    severity: str
    code: str
    message: str


@dataclass(frozen=True)
class VerificationResult:
    mode: str
    passed: bool
    width: int
    height: int
    fps: float
    duration: float
    frame_count: int | None
    expected_frame_count: int
    cfr: bool | None
    video_codec: str
    audio_codec: str | None
    audio_channels: int | None
    audio_sample_rate: int | None
    av_sync_delta: float | None
    decoded_to_eof: bool
    issues: tuple[VerificationIssue, ...] = field(default_factory=tuple)
    probe: dict = field(default_factory=dict)

    @property
    def errors(self) -> tuple[VerificationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> tuple[VerificationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warning")

    def to_dict(self) -> dict:
        return asdict(self)


_CODEC_ALIASES = {
    "HEVC": "hevc",
    "ProRes 422 HQ": "prores",
    "VP9": "vp9",
    "FFV1": "ffv1",
    "AAC": "aac",
    "PCM 24-bit": "pcm_s24le",
    "FLAC": "flac",
    "Opus": "opus",
}


def codec_name(label: str | None) -> str | None:
    if not label:
        return None
    return _CODEC_ALIASES.get(label, label.casefold())


def _ratio(value: object) -> float:
    text = str(value or "0/0")
    if "/" in text:
        left, right = text.split("/", 1)
        try:
            denominator = float(right)
            return float(left) / denominator if denominator else 0.0
        except (TypeError, ValueError, ZeroDivisionError):
            return 0.0
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _number(value: object) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _integer(value: object) -> int | None:
    try:
        text = str(value)
        if not text or text.upper() == "N/A":
            return None
        return int(text)
    except (TypeError, ValueError):
        return None


def _probe(ffprobe: str, path: str | Path, *, count_frames: bool = True) -> dict:
    command = [
        ffprobe, "-v", "error", "-show_streams", "-show_format",
        "-of", "json",
    ]
    if count_frames:
        command.insert(3, "-count_frames")
    command.append(str(path))
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode:
        raise RuntimeError("FFprobe não conseguiu ler a saída final: " + (result.stderr.strip() or "erro desconhecido"))
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"FFprobe retornou JSON inválido: {exc}") from exc


def _stream_end(stream: dict) -> float | None:
    start = _number(stream.get("start_time")) or 0.0
    duration = _number(stream.get("duration"))
    if duration is None:
        return None
    return start + duration


def quick_verify(
    ffprobe: str,
    path: str | Path,
    expected: VerifyExpectation,
    *,
    probe_data: dict | None = None,
) -> VerificationResult:
    """Validate metadata and exact frame count without decoding the whole file."""

    info = probe_data if probe_data is not None else _probe(ffprobe, path, count_frames=True)
    streams = info.get("streams", []) if isinstance(info, dict) else []
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
    fmt = info.get("format", {}) if isinstance(info, dict) else {}
    issues: list[VerificationIssue] = []

    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    fps = _ratio(video.get("avg_frame_rate")) or _ratio(video.get("r_frame_rate"))
    duration = _number(fmt.get("duration")) or _number(video.get("duration")) or 0.0
    frame_count = _integer(video.get("nb_read_frames"))
    if frame_count is None:
        frame_count = _integer(video.get("nb_frames"))
    expected_frames = max(1, int(round(expected.duration * expected.fps)))

    if (width, height) != (expected.width, expected.height):
        issues.append(VerificationIssue("error", "VERIFY-SIZE", f"Resolução {width}×{height}; esperado {expected.width}×{expected.height}."))
    if abs(fps - expected.fps) > 0.02:
        issues.append(VerificationIssue("error", "VERIFY-FPS", f"FPS {fps:.3f}; esperado {expected.fps:.3f}."))
    if abs(duration - expected.duration) > expected.duration_tolerance:
        issues.append(VerificationIssue("error", "VERIFY-DURATION", f"Duração {duration:.3f}s; esperado {expected.duration:.3f}s."))

    r_fps = _ratio(video.get("r_frame_rate"))
    a_fps = _ratio(video.get("avg_frame_rate"))
    cfr: bool | None = None
    if r_fps > 0 and a_fps > 0:
        cfr = abs(r_fps - a_fps) <= 0.02 and abs(a_fps - expected.fps) <= 0.02
        if not cfr:
            issues.append(VerificationIssue("error", "VERIFY-CFR", f"Cadência não é CFR {expected.fps:.3f}: r={r_fps:.3f}, avg={a_fps:.3f}."))

    if frame_count is None:
        issues.append(VerificationIssue("warning", "VERIFY-FRAMES-UNKNOWN", "FFprobe não informou a contagem exata de quadros."))
    elif abs(frame_count - expected_frames) > expected.frame_tolerance:
        issues.append(VerificationIssue(
            "error", "VERIFY-FRAMES",
            f"Contagem {frame_count} quadros; esperado ~{expected_frames} (tolerância ±{expected.frame_tolerance}).",
        ))

    video_codec = str(video.get("codec_name") or "")
    audio_codec = str(audio.get("codec_name") or "") if audio else None
    expected_video_codec = codec_name(expected.video_codec)
    expected_audio_codec = codec_name(expected.audio_codec)
    if expected_video_codec and video_codec != expected_video_codec:
        issues.append(VerificationIssue("error", "VERIFY-VIDEO-CODEC", f"Codec de vídeo {video_codec or 'ausente'}; esperado {expected_video_codec}."))

    if expected.expect_audio:
        if not audio:
            issues.append(VerificationIssue("error", "VERIFY-AUDIO-MISSING", "A saída deveria conter áudio, mas nenhum stream de áudio foi encontrado."))
        elif expected_audio_codec and audio_codec != expected_audio_codec:
            issues.append(VerificationIssue("error", "VERIFY-AUDIO-CODEC", f"Codec de áudio {audio_codec}; esperado {expected_audio_codec}."))
    elif audio:
        issues.append(VerificationIssue("error", "VERIFY-AUDIO-UNEXPECTED", "A saída deveria ser silenciosa, mas contém stream de áudio."))

    channels = _integer(audio.get("channels")) if audio else None
    sample_rate = _integer(audio.get("sample_rate")) if audio else None
    if expected.expect_audio and expected.audio_channels is not None and channels != expected.audio_channels:
        issues.append(VerificationIssue("error", "VERIFY-AUDIO-CHANNELS", f"Áudio com {channels} canal(is); esperado {expected.audio_channels}."))
    if expected.expect_audio and expected.audio_sample_rate is not None and sample_rate != expected.audio_sample_rate:
        issues.append(VerificationIssue("error", "VERIFY-AUDIO-RATE", f"Áudio a {sample_rate} Hz; esperado {expected.audio_sample_rate} Hz."))

    av_sync_delta: float | None = None
    if audio and video:
        video_end = _stream_end(video)
        audio_end = _stream_end(audio)
        if video_end is not None and audio_end is not None:
            av_sync_delta = abs(video_end - audio_end)
            if av_sync_delta > expected.sync_tolerance:
                issues.append(VerificationIssue("error", "VERIFY-AV-SYNC", f"Diferença de término A/V {av_sync_delta:.3f}s; limite {expected.sync_tolerance:.3f}s."))
        else:
            issues.append(VerificationIssue("warning", "VERIFY-AV-SYNC-UNKNOWN", "Streams não expuseram duração suficiente para estimar sincronismo A/V."))

    passed = not any(issue.severity == "error" for issue in issues)
    return VerificationResult(
        mode="quick", passed=passed, width=width, height=height, fps=fps, duration=duration,
        frame_count=frame_count, expected_frame_count=expected_frames, cfr=cfr,
        video_codec=video_codec, audio_codec=audio_codec, audio_channels=channels,
        audio_sample_rate=sample_rate, av_sync_delta=av_sync_delta, decoded_to_eof=False,
        issues=tuple(issues), probe=info,
    )


def deep_verify(
    ffmpeg: str,
    ffprobe: str,
    path: str | Path,
    expected: VerifyExpectation,
    *,
    process_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> VerificationResult:
    """Run quick verification and decode all expected streams through EOF."""

    quick = quick_verify(ffprobe, path, expected)
    command = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-xerror", "-i", str(path), "-map", "0:v:0"]
    if expected.expect_audio:
        command += ["-map", "0:a:0"]
    command += ["-f", "null", "-"]
    result = process_runner(
        command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    issues = list(quick.issues)
    decoded = result.returncode == 0
    if not decoded:
        detail = (result.stderr or "").strip().splitlines()
        tail = " | ".join(detail[-4:]) if detail else "erro de decodificação sem detalhe"
        issues.append(VerificationIssue("error", "VERIFY-DECODE-EOF", f"Decodificação completa falhou: {tail}"))
    passed = not any(issue.severity == "error" for issue in issues)
    return VerificationResult(
        mode="deep", passed=passed,
        width=quick.width, height=quick.height, fps=quick.fps, duration=quick.duration,
        frame_count=quick.frame_count, expected_frame_count=quick.expected_frame_count, cfr=quick.cfr,
        video_codec=quick.video_codec, audio_codec=quick.audio_codec,
        audio_channels=quick.audio_channels, audio_sample_rate=quick.audio_sample_rate,
        av_sync_delta=quick.av_sync_delta, decoded_to_eof=decoded,
        issues=tuple(issues), probe=quick.probe,
    )
