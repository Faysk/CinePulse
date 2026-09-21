from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from cinepulse.audio_mastering import bound_delivery_audio_filter, frame_bound_duration
from cinepulse.verification import VerifyExpectation, quick_verify


def require(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"required tool missing: {name}")
    return path


def run(command: list[str]) -> None:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            "\n".join(
                [
                    subprocess.list2cmdline(command),
                    result.stdout,
                    result.stderr,
                ]
            )
        )


def render_case(
    *,
    ffmpeg: str,
    ffprobe: str,
    root: Path,
    name: str,
    source_audio_duration: float,
) -> None:
    fps = 30.0
    frame_count = 31
    exact_duration = frame_bound_duration(frame_count, fps)
    output = root / f"{name}.mkv"

    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=160x90:rate={fps:g}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=880:sample_rate=48000:duration={source_audio_duration:.6f}",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-af",
        bound_delivery_audio_filter(exact_duration),
        "-frames:v",
        str(frame_count),
        "-c:v",
        "ffv1",
        "-level",
        "3",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "pcm_s24le",
        str(output),
    ]
    run(command)

    expectation = VerifyExpectation(
        width=160,
        height=90,
        fps=fps,
        duration=exact_duration,
        expect_audio=True,
        video_codec="FFV1",
        audio_codec="PCM 24-bit",
        audio_channels=1,
        audio_sample_rate=48000,
        frame_tolerance=0,
        duration_tolerance=0.02,
        sync_tolerance=0.02,
    )
    result = quick_verify(ffprobe, output, expectation)
    if result.frame_count != frame_count:
        raise RuntimeError(
            f"{name}: video frame count {result.frame_count}; expected {frame_count}"
        )
    if not result.passed:
        details = " | ".join(
            f"{issue.code}: {issue.message}" for issue in result.errors
        )
        raise RuntimeError(f"{name}: verification failed: {details}")
    if result.av_sync_delta is None or result.av_sync_delta > 0.02:
        raise RuntimeError(
            f"{name}: A/V end delta {result.av_sync_delta}; expected <= 0.02s"
        )
    print(
        "AUDIO_FRAME_TIMELINE_CASE_OK "
        f"name={name} frames={result.frame_count} "
        f"duration={result.duration:.6f} av_delta={result.av_sync_delta:.6f}"
    )


def main() -> int:
    ffmpeg = require("ffmpeg")
    ffprobe = require("ffprobe")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        # Short audio proves padding to the frame-bound end.
        render_case(
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            root=root,
            name="short-pad",
            source_audio_duration=0.75,
        )
        # Long audio proves trimming to the same frame-bound end.
        render_case(
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            root=root,
            name="long-trim",
            source_audio_duration=1.50,
        )
    print("AUDIO_FRAME_TIMELINE_INTEGRATION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
