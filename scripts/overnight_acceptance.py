from __future__ import annotations

"""Analyze one physical H8 overnight telemetry run without changing the system.

This script never tunes clocks, priorities, power limits or fan policy.  It only
validates evidence already captured by CinePulse.  A PASS applies to the exact
run/scenario; it is not a global RTX/8K/120 certification.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from cinepulse.hardware_telemetry import BENCHMARK_SCENARIOS, load_telemetry
from cinepulse.hardware_throughput import throughput_from_telemetry


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def analyze(
    telemetry: Mapping[str, Any],
    *,
    scenario: str,
    minimum_seconds: float,
    quality_passed: bool,
) -> dict[str, Any]:
    summary = telemetry.get("summary") if isinstance(telemetry.get("summary"), Mapping) else {}
    overall = summary.get("overall") if isinstance(summary.get("overall"), Mapping) else {}
    gpu = overall.get("gpu") if isinstance(overall.get("gpu"), Mapping) else {}
    disk = overall.get("disk") if isinstance(overall.get("disk"), Mapping) else {}
    ram = overall.get("ram") if isinstance(overall.get("ram"), Mapping) else {}

    wall = _number(summary.get("wall_seconds")) or 0.0
    sample_count = int(overall.get("sample_count") or 0)
    interval = _number(telemetry.get("sample_interval_seconds")) or 2.0
    expected_samples = max(1, int(wall / max(0.5, interval) * 0.70))
    peak_temp = _number(gpu.get("peak_temperature_c"))
    min_vram = _number(gpu.get("minimum_vram_free_mb"))
    peak_ram = _number(ram.get("peak_percent"))
    peak_write = _number(disk.get("peak_write_mbps"))
    avg_write = _number(disk.get("average_write_mbps"))

    checks: dict[str, bool] = {
        "known_scenario": scenario in BENCHMARK_SCENARIOS,
        "render_success": str(telemetry.get("status") or "").lower() == "success",
        "sustained_duration": wall >= max(1.0, float(minimum_seconds)),
        "telemetry_coverage": sample_count >= expected_samples,
        "quality_and_integrity_passed": bool(quality_passed),
        "gpu_temperature_observed": peak_temp is not None,
        "no_critical_gpu_heat": peak_temp is not None and peak_temp < 90.0,
        "ram_pressure_safe": peak_ram is None or peak_ram < 96.0,
        "vram_not_exhausted": min_vram is None or min_vram >= 256.0,
    }
    passed = all(checks.values())
    throughput = throughput_from_telemetry(telemetry)

    notes: list[str] = []
    if peak_temp is not None and peak_temp >= 84.0:
        notes.append("GPU reached the H8 caution/critical thermal envelope; inspect downshift events and clock stability.")
    if avg_write is not None and peak_write is not None and peak_write > 0 and avg_write / peak_write >= 0.85:
        notes.append("Scratch write throughput stayed near its observed peak; storage saturation may be a sustained bottleneck.")
    if not throughput.get("stages"):
        notes.append("No stage emitted explicit frame work units; utilization/wall evidence remains valid but stage frames/s is unavailable.")

    return {
        "schema": 1,
        "scenario": scenario,
        "scenario_contract": BENCHMARK_SCENARIOS.get(scenario),
        "physical_acceptance": "exact-run-pass-not-global" if passed else "rejected-or-incomplete",
        "passed": passed,
        "checks": checks,
        "evidence": {
            "wall_seconds": wall,
            "sample_count": sample_count,
            "sample_interval_seconds": interval,
            "peak_gpu_temperature_c": peak_temp,
            "minimum_vram_free_mb": min_vram,
            "peak_ram_percent": peak_ram,
            "average_disk_write_mbps": avg_write,
            "peak_disk_write_mbps": peak_write,
            "throughput": throughput,
        },
        "notes": notes,
        "system_mutations_performed": False,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Validate one sustained CinePulse H8 physical overnight run.")
    result.add_argument("telemetry", type=Path)
    result.add_argument("--scenario", required=True, choices=sorted(BENCHMARK_SCENARIOS))
    result.add_argument("--minimum-seconds", type=float, default=1800.0)
    result.add_argument(
        "--quality-passed",
        action="store_true",
        help="Set only after the normal CinePulse verification/quality gates for this exact output passed.",
    )
    result.add_argument("--output", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    payload = analyze(
        load_telemetry(args.telemetry),
        scenario=args.scenario,
        minimum_seconds=args.minimum_seconds,
        quality_passed=args.quality_passed,
    )
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if payload["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
