from __future__ import annotations

import argparse
import json
from pathlib import Path

from cinepulse.cpu_tuning import CpuTuningKey, CpuTuningSample, CpuTuningStore
from cinepulse.hardware_telemetry import BENCHMARK_SCENARIOS, benchmark_summary, compare_benchmarks, load_telemetry
from cinepulse.resource_scheduler import CpuTopology, candidate_thread_counts, schedule_cpu_threads


def _sample(value: str) -> CpuTuningSample:
    parts = value.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("sample must be THREADS:SECONDS:OK, e.g. 12:18.42:true")
    try:
        threads = int(parts[0])
        seconds = float(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("sample threads/seconds must be numeric") from exc
    ok_text = parts[2].strip().lower()
    if ok_text not in {"true", "false", "1", "0", "yes", "no"}:
        raise argparse.ArgumentTypeError("sample OK must be true/false")
    return CpuTuningSample(threads, seconds, ok_text in {"true", "1", "yes"})


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Summarize, compare or record CinePulse hardware benchmark evidence.")
    sub = result.add_subparsers(dest="command", required=True)

    summary = sub.add_parser("summarize")
    summary.add_argument("telemetry", type=Path)
    summary.add_argument("--scenario", choices=sorted(BENCHMARK_SCENARIOS))

    compare = sub.add_parser("compare")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--scenario", choices=sorted(BENCHMARK_SCENARIOS))

    cpu_candidates = sub.add_parser("cpu-candidates", help="Print bounded H1 thread candidates for a stage/topology.")
    cpu_candidates.add_argument("--stage", required=True, choices=("decode", "color", "scale", "encode", "audio", "vfx_cpu", "neural_gpu", "neural_cpu", "verification", "other"))
    cpu_candidates.add_argument("--logical", type=int, required=True)
    cpu_candidates.add_argument("--physical", type=int, required=True)
    cpu_candidates.add_argument("--mode", choices=("balanced", "dedicated"), default="balanced")
    cpu_candidates.add_argument("--gpu-active", action="store_true")
    cpu_candidates.add_argument("--max-threads", type=int)

    record_cpu = sub.add_parser("record-cpu", help="Persist a CPU policy only from integrity-approved benchmark samples.")
    record_cpu.add_argument("cache", type=Path)
    record_cpu.add_argument("--stage", required=True, choices=("decode", "color", "scale", "encode", "audio", "vfx_cpu", "neural_gpu", "neural_cpu", "verification", "other"))
    record_cpu.add_argument("--logical", type=int, required=True)
    record_cpu.add_argument("--physical", type=int, required=True)
    record_cpu.add_argument("--mode", choices=("balanced", "dedicated"), default="balanced")
    record_cpu.add_argument("--gpu-active", action="store_true")
    record_cpu.add_argument("--fallback-threads", type=int, required=True)
    record_cpu.add_argument("--sample", type=_sample, action="append", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "summarize":
        payload = benchmark_summary(load_telemetry(args.telemetry), scenario=args.scenario)
    elif args.command == "compare":
        baseline = benchmark_summary(load_telemetry(args.baseline), scenario=args.scenario)
        candidate = benchmark_summary(load_telemetry(args.candidate), scenario=args.scenario)
        payload = {
            "scenario": args.scenario,
            "baseline": baseline,
            "candidate": candidate,
            "comparison": compare_benchmarks(baseline, candidate),
        }
    elif args.command == "cpu-candidates":
        topology = CpuTopology(max(1, args.logical), max(1, args.physical), source="benchmark-cli")
        fallback = schedule_cpu_threads(
            args.stage,
            topology=topology,
            mode=args.mode,
            gpu_active=args.gpu_active,
            max_threads=args.max_threads,
        )
        payload = {
            "topology": topology.as_dict(),
            "stage": args.stage,
            "mode": args.mode,
            "gpu_active": args.gpu_active,
            "fallback": fallback.as_dict(),
            "candidates": list(
                candidate_thread_counts(
                    args.stage,
                    topology=topology,
                    mode=args.mode,
                    gpu_active=args.gpu_active,
                    max_threads=args.max_threads,
                )
            ),
            "physical_acceptance": "pending",
        }
    else:
        topology = CpuTopology(max(1, args.logical), max(1, args.physical), source="benchmark-cli")
        key = CpuTuningKey.from_topology(
            args.stage,
            topology,
            mode=args.mode,
            gpu_active=args.gpu_active,
        )
        store = CpuTuningStore(args.cache)
        chosen = store.record_samples(key, args.sample, fallback_threads=args.fallback_threads)
        if chosen is None:
            payload = {
                "recorded": False,
                "reason": "no integrity-approved sample; cache left unchanged",
                "key": key.token(),
            }
        else:
            payload = {
                "recorded": True,
                "key": key.token(),
                "threads": chosen,
                "cache": str(args.cache),
                "physical_acceptance": "evidence-recorded-not-global-pass",
            }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
