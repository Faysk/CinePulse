from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class GateStep:
    name: str
    command: tuple[str, ...]
    needs_display: bool = False
    needs_ffmpeg: bool = False
    timeout_seconds: int = 180


SOURCE_STEPS = (
    GateStep("release-contract", (sys.executable, "scripts/release_gate.py")),
    GateStep("final-audit", (sys.executable, "scripts/final_audit.py", "--output", "artifacts/ci/final-audit-static.json")),
    GateStep("compileall", (sys.executable, "-m", "compileall", "-q", "src", "tests", "scripts")),
    GateStep("unit-tests", (sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v")),
    GateStep("sbom", (sys.executable, "scripts/generate_sbom.py", "--output", "artifacts/ci/sbom-probe.cdx.json")),
)

CPU_STEPS = (
    GateStep("smoke-basic", (sys.executable, "tests/integration_smoke.py", "--mode", "basic"), True, True),
    GateStep("smoke-audio", (sys.executable, "tests/integration_smoke.py", "--mode", "audio"), True, True),
    GateStep("cancel-recovery", (sys.executable, "tests/integration_cancel.py"), True, True),
    GateStep("delivery-matrix", (sys.executable, "tests/integration_delivery.py"), True, True),
    GateStep("storage", (sys.executable, "tests/integration_storage.py"), True, True),
    GateStep("verification", (sys.executable, "tests/integration_verification.py"), True, True),
    GateStep("neural-chunks-contract", (sys.executable, "tests/integration_neural_chunks.py"), True, True),
)

MEDIA_STEPS = (
    GateStep("smoke-vfx", (sys.executable, "tests/integration_smoke.py", "--mode", "vfx"), True, True),
    GateStep("hdr", (sys.executable, "tests/integration_hdr.py"), True, True),
    GateStep("sdr10-color", (sys.executable, "tests/integration_color.py"), True, True),
)

GPU_STEPS = (
    GateStep("gpu-rife", (sys.executable, "tests/integration_smoke.py", "--mode", "rife"), True, True, 1800),
    GateStep("gpu-realesrgan", (sys.executable, "tests/integration_smoke.py", "--mode", "ai"), True, True, 1800),
    GateStep("gpu-demucs", (sys.executable, "tests/integration_smoke.py", "--mode", "stems"), True, True, 1800),
)

PROFILES = {
    "source": SOURCE_STEPS,
    "cpu": CPU_STEPS,
    "media": MEDIA_STEPS,
    "release-light": SOURCE_STEPS + CPU_STEPS + MEDIA_STEPS,
    "gpu": GPU_STEPS,
}


def _display_wrapper(step: GateStep) -> list[str]:
    command = list(step.command)
    if not step.needs_display or os.name == "nt":
        return command
    if os.environ.get("CINEPULSE_CI_NATIVE_DISPLAY") == "1":
        return command
    xvfb = shutil.which("xvfb-run")
    if not xvfb:
        raise RuntimeError(f"{step.name}: DISPLAY ausente e xvfb-run não está disponível")
    return [xvfb, "-a", *command]


def _check_tools(step: GateStep) -> None:
    if step.needs_ffmpeg:
        missing = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
        if missing:
            raise RuntimeError(f"{step.name}: ferramentas ausentes: {', '.join(missing)}")


def _run(step: GateStep, env: dict[str, str]) -> dict:
    _check_tools(step)
    command = _display_wrapper(step)
    started = time.monotonic()
    print(f"\n=== CI GATE: {step.name} ===", flush=True)
    print(subprocess.list2cmdline(command), flush=True)
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, timeout=step.timeout_seconds)
    elapsed = time.monotonic() - started
    record = {
        "name": step.name,
        "command": command,
        "returncode": result.returncode,
        "seconds": round(elapsed, 3),
        "timeout_seconds": step.timeout_seconds,
        "passed": result.returncode == 0,
    }
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, command)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Portão reproduzível de CI/release do CinePulse")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="source")
    parser.add_argument("--output", default="")
    parser.add_argument("--list", action="store_true", dest="list_steps")
    args = parser.parse_args()

    if args.list_steps:
        for step in PROFILES[args.profile]:
            print(step.name)
        return 0

    env = os.environ.copy()
    paths = [str(ROOT / "src"), str(ROOT)]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env.setdefault("PYTHONUNBUFFERED", "1")
    artifact_dir = ROOT / "artifacts" / "ci"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "schema": 1,
        "profile": args.profile,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "steps": [],
        "passed": False,
    }
    output = Path(args.output) if args.output else artifact_dir / f"gate-{args.profile}.json"
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        for step in PROFILES[args.profile]:
            report["steps"].append(_run(step, env))
        report["passed"] = True
        print(f"\nCINEPULSE_CI_GATE_OK profile={args.profile} steps={len(report['steps'])}")
        return 0
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        print(f"\nCINEPULSE_CI_GATE_FAILED profile={args.profile}: {exc}", file=sys.stderr)
        return 1
    finally:
        report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"CINEPULSE_CI_REPORT {output}")


if __name__ == "__main__":
    raise SystemExit(main())
