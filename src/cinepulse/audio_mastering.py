from __future__ import annotations

import json
import os
import re
import subprocess


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

TARGETS = {
    "Normalizar para YouTube — -14 LUFS": (-14.0, -1.0, 11.0, ""),
    "Masterização leve e segura": (
        -14.0, -1.0, 9.0,
        "highpass=f=28,lowpass=f=19000,acompressor=threshold=-18dB:ratio=2.2:attack=18:release=180:makeup=1.5dB",
    ),
}


def parse_loudnorm_json(text: str) -> dict[str, float]:
    blocks = re.findall(r"\{[^{}]*\}", text, flags=re.DOTALL)
    for block in reversed(blocks):
        try:
            payload = json.loads(block)
            return {
                key: float(payload[key])
                for key in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
            }
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
    raise ValueError("A análise loudnorm não retornou medições válidas.")


def analyze_loudness(ffmpeg: str, source: str, duration: float, mode: str) -> dict[str, float]:
    if mode not in TARGETS:
        return {}
    target_i, target_tp, target_lra, prefix = TARGETS[mode]
    loudnorm = f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json"
    audio_filter = f"{prefix},{loudnorm}" if prefix else loudnorm
    command = [
        ffmpeg, "-hide_banner", "-nostdin", "-i", source, "-t", f"{duration:.6f}",
        "-vn", "-af", audio_filter, "-f", "null", "NUL" if os.name == "nt" else "/dev/null",
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=CREATE_NO_WINDOW, timeout=max(60, min(1800, round(duration * 0.5 + 60))),
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-2000:])
    return parse_loudnorm_json(result.stderr + "\n" + result.stdout)


def build_audio_filter(mode: str, measured: dict[str, float] | None = None) -> str:
    if mode not in TARGETS:
        return ""
    target_i, target_tp, target_lra, prefix = TARGETS[mode]
    options = f"I={target_i}:TP={target_tp}:LRA={target_lra}"
    if measured:
        options += (
            f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}:linear=true"
        )
    loudnorm = "loudnorm=" + options
    return f"{prefix},{loudnorm}" if prefix else loudnorm

