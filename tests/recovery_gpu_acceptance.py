from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from cinepulse import ai_suite
from cinepulse.loop_engine import FFMPEG
from cinepulse.rife_safe_runner import run_safe_rife, validate_png_sequence


def main() -> int:
    rife_exe = Path(ai_suite.RIFE_EXE)
    rife_model = Path(ai_suite.RIFE_DIR) / "rife-v4.6"
    if not rife_exe.is_file():
        raise RuntimeError(f"RIFE executable missing on acceptance runner: {rife_exe}")
    if not rife_model.is_dir():
        raise RuntimeError(f"RIFE model missing on acceptance runner: {rife_model}")
    ffmpeg = str(FFMPEG)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        incoming = root / "in"
        outgoing = root / "out"
        incoming.mkdir()
        outgoing.mkdir()
        fixture = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=7680x4320:rate=1:duration=2",
            "-frames:v",
            "2",
            "-start_number",
            "0",
            str(incoming / "%08d.png"),
        ]
        if subprocess.run(fixture, check=False).returncode:
            raise RuntimeError("failed to create 8K RIFE acceptance fixture")
        validate_png_sequence(incoming, 2)
        policy = run_safe_rife(
            rife_executable=rife_exe,
            model=rife_model,
            incoming=incoming,
            outgoing=outgoing,
            requested_target=5,
            device="gpu",
            ffmpeg=ffmpeg,
        )
        validate_png_sequence(outgoing, 5)
        if not policy.uhd or policy.jobs != "1:1:1" or policy.native_target != 4:
            raise RuntimeError(f"unsafe 8K policy observed: {policy}")
        print(
            "RECOVERY_GPU_8K_ACCEPTANCE_OK "
            f"uhd={policy.uhd} jobs={policy.jobs} native={policy.native_target} target={policy.requested_target}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
