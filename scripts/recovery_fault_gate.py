from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SOURCE_MODULES = (
    "tests.test_rife_engine",
    "tests.test_rife_safe_runner",
    "tests.test_render_job",
    "tests.test_job_store",
    "tests.test_job_lease",
    "tests.test_worker_protocol",
    "tests.test_render_worker",
    "tests.test_stage_adapter",
    "tests.test_stage_fault_matrix",
    "tests.test_frame_quality",
    "tests.test_storage_resilience",
    "tests.test_recovery_service",
)


def run(command: list[str], timeout: int) -> dict:
    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, text=True, check=False, timeout=timeout)
    return {
        "command": command,
        "returncode": result.returncode,
        "seconds": round(time.monotonic() - started, 3),
        "passed": result.returncode == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="CinePulse recovery/reliability fault gate")
    parser.add_argument("--profile", choices=("source", "media"), default="source")
    parser.add_argument("--output", default="artifacts/ci/recovery-fault.json")
    args = parser.parse_args()
    output = ROOT / args.output if not Path(args.output).is_absolute() else Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "unittest", "-v", *SOURCE_MODULES]
    timeout = 300
    if args.profile == "media":
        command = [sys.executable, "tests/integration_recovery_media.py"]
        timeout = 600
    report = {
        "schema": 1,
        "profile": args.profile,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "result": None,
        "passed": False,
    }
    try:
        report["result"] = run(command, timeout)
        report["passed"] = bool(report["result"]["passed"])
        return 0 if report["passed"] else 1
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        return 1
    finally:
        report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"CINEPULSE_RECOVERY_FAULT_GATE {output} passed={report['passed']}")


if __name__ == "__main__":
    raise SystemExit(main())
