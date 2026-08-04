from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def parse_vmaf_report(payload: dict) -> float:
    try:
        return float(payload["pooled_metrics"]["vmaf"]["mean"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Relatório VMAF sem pontuação média.") from exc


def measure_vmaf(ffmpeg: str, reference: str, distorted: str, duration: float, sample_seconds: float = 2.0) -> float:
    sample = max(0.5, min(sample_seconds, duration))
    start = max(0.0, min(max(0.0, duration - sample), duration * 0.42))
    with tempfile.TemporaryDirectory(prefix="cinepulse_vmaf_") as temporary:
        report = Path(temporary) / "vmaf.json"
        report_arg = str(report).replace("\\", "/").replace(":", "\\:")
        graph = (
            "[0:v]setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease:flags=lanczos,"
            "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,format=yuv420p[dist];"
            "[1:v]setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease:flags=lanczos,"
            "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,format=yuv420p[ref];"
            f"[dist][ref]libvmaf=log_fmt=json:log_path='{report_arg}':n_threads=4"
        )
        command = [
            ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
            "-ss", f"{start:.6f}", "-i", distorted,
            "-ss", f"{start:.6f}", "-i", reference,
            "-t", f"{sample:.6f}", "-filter_complex", graph, "-an", "-f", "null",
            "NUL" if os.name == "nt" else "/dev/null",
        ]
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW, timeout=180,
        )
        if result.returncode or not report.is_file():
            raise RuntimeError((result.stderr or result.stdout)[-2000:])
        return parse_vmaf_report(json.loads(report.read_text(encoding="utf-8")))

