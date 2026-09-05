from __future__ import annotations

import argparse
import json
from pathlib import Path

from cinepulse.hardware_telemetry import BENCHMARK_SCENARIOS, benchmark_summary, compare_benchmarks, load_telemetry


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Summarize or compare CinePulse hardware telemetry evidence.")
    sub = result.add_subparsers(dest="command", required=True)
    summary = sub.add_parser("summarize")
    summary.add_argument("telemetry", type=Path)
    summary.add_argument("--scenario", choices=sorted(BENCHMARK_SCENARIOS))
    compare = sub.add_parser("compare")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--scenario", choices=sorted(BENCHMARK_SCENARIOS))
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "summarize":
        payload = benchmark_summary(load_telemetry(args.telemetry), scenario=args.scenario)
    else:
        baseline = benchmark_summary(load_telemetry(args.baseline), scenario=args.scenario)
        candidate = benchmark_summary(load_telemetry(args.candidate), scenario=args.scenario)
        payload = {
            "scenario": args.scenario,
            "baseline": baseline,
            "candidate": candidate,
            "comparison": compare_benchmarks(baseline, candidate),
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
