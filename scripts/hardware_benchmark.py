from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from cinepulse.cpu_tuning import CpuTuningKey, CpuTuningSample, CpuTuningStore
from cinepulse.hardware_advisor import analyze_hardware_summary
from cinepulse.hardware_telemetry import BENCHMARK_SCENARIOS, benchmark_summary, compare_benchmarks, load_telemetry
from cinepulse.hardware_throughput import throughput_from_telemetry
from cinepulse.realesrgan_tuning import (
    RealEsrganPolicy,
    RealEsrganSample,
    RealEsrganTuningKey,
    RealEsrganTuningStore,
    safe_candidates as realesrgan_candidates,
)
from cinepulse.resource_scheduler import CpuTopology, candidate_thread_counts, schedule_cpu_threads


def _bool(value: str, *, label: str) -> bool:
    text = value.strip().lower()
    if text not in {"true", "false", "1", "0", "yes", "no"}:
        raise argparse.ArgumentTypeError(f"{label} must be true/false")
    return text in {"true", "1", "yes"}


def _sample(value: str) -> CpuTuningSample:
    parts = value.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("sample must be THREADS:SECONDS:OK, e.g. 12:18.42:true")
    try:
        threads = int(parts[0])
        seconds = float(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("sample threads/seconds must be numeric") from exc
    return CpuTuningSample(threads, seconds, _bool(parts[2], label="sample OK"))


def _optional_int(value: str, *, label: str) -> int | None:
    if value.strip() in {"", "-", "none", "null"}:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{label} must be an integer or -") from exc


def _realesrgan_sample(value: str) -> RealEsrganSample:
    parts = value.split(":")
    if len(parts) != 9:
        raise argparse.ArgumentTypeError(
            "Real-ESRGAN sample must be TILE:LOAD:PROC:SAVE:SECONDS:OK:OOM:OUT:EXPECTED; "
            "use - for unknown frame counts"
        )
    try:
        tile, load, proc, save = (int(parts[index]) for index in range(4))
        seconds = float(parts[4])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Real-ESRGAN tile/jobs/seconds must be numeric") from exc
    return RealEsrganSample(
        policy=RealEsrganPolicy(tile, load, proc, save, 0),
        wall_seconds=seconds,
        integrity_ok=_bool(parts[5], label="sample OK"),
        oom=_bool(parts[6], label="sample OOM"),
        output_frames=_optional_int(parts[7], label="OUT"),
        expected_frames=_optional_int(parts[8], label="EXPECTED"),
    )


def _add_realesrgan_key_args(command: argparse.ArgumentParser) -> None:
    command.add_argument("--gpu-name", required=True)
    command.add_argument("--vram-mb", type=int, required=True)
    command.add_argument("--driver", required=True)
    command.add_argument("--model", default="realesr-animevideov3")
    command.add_argument("--width", type=int, required=True)
    command.add_argument("--height", type=int, required=True)
    command.add_argument("--scale", type=int, default=2)
    command.add_argument("--gpu-index", type=int, default=0)


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

    advise = sub.add_parser("advise", help="Classify stage bottlenecks from persisted telemetry without changing runtime policy.")
    advise.add_argument("telemetry", type=Path)

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

    neural_candidates = sub.add_parser(
        "realesrgan-candidates",
        help="Print bounded Real-ESRGAN tile/pipeline candidates; output is not physical acceptance.",
    )
    neural_candidates.add_argument("--vram-mb", type=int, required=True)
    neural_candidates.add_argument("--cpu-threads", type=int, required=True)
    neural_candidates.add_argument("--gpu-index", type=int, default=0)
    neural_candidates.add_argument("--width", type=int, required=True)
    neural_candidates.add_argument("--height", type=int, required=True)

    record_neural = sub.add_parser(
        "record-realesrgan",
        help="Persist an exact Real-ESRGAN policy only from integrity-approved physical samples.",
    )
    record_neural.add_argument("cache", type=Path)
    _add_realesrgan_key_args(record_neural)
    record_neural.add_argument("--sample", type=_realesrgan_sample, action="append", required=True)
    return result


def _realesrgan_key(args: argparse.Namespace) -> RealEsrganTuningKey:
    return RealEsrganTuningKey(
        str(args.gpu_name),
        max(0, int(args.vram_mb)),
        str(args.driver),
        str(args.model),
        max(1, int(args.width)),
        max(1, int(args.height)),
        max(1, int(args.scale)),
    )


def _summary_with_throughput(path: Path, scenario: str | None) -> dict:
    telemetry = load_telemetry(path)
    payload = benchmark_summary(telemetry, scenario=scenario)
    payload["throughput"] = throughput_from_telemetry(telemetry)
    return payload


def _throughput_comparison(baseline: dict, candidate: dict) -> dict[str, object]:
    before = baseline.get("throughput", {}).get("stages", {}) if isinstance(baseline.get("throughput"), dict) else {}
    after = candidate.get("throughput", {}).get("stages", {}) if isinstance(candidate.get("throughput"), dict) else {}
    result: dict[str, object] = {}
    for stage in sorted(set(before) | set(after)):
        left = before.get(stage) if isinstance(before.get(stage), dict) else {}
        right = after.get(stage) if isinstance(after.get(stage), dict) else {}
        try:
            left_rate = float(left.get("units_per_second")) if left else None
            right_rate = float(right.get("units_per_second")) if right else None
        except (TypeError, ValueError):
            left_rate = right_rate = None
        rate_speedup = right_rate / left_rate if left_rate and right_rate and left_rate > 0 else None
        result[stage] = {
            "baseline_units_per_second": left_rate,
            "candidate_units_per_second": right_rate,
            "throughput_speedup": rate_speedup,
            "work_unit": right.get("work_unit") or left.get("work_unit") or "unknown",
        }
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "summarize":
        payload = _summary_with_throughput(args.telemetry, args.scenario)
    elif args.command == "compare":
        baseline = _summary_with_throughput(args.baseline, args.scenario)
        candidate = _summary_with_throughput(args.candidate, args.scenario)
        comparison = compare_benchmarks(baseline, candidate)
        comparison["throughput"] = _throughput_comparison(baseline, candidate)
        payload = {
            "scenario": args.scenario,
            "baseline": baseline,
            "candidate": candidate,
            "comparison": comparison,
        }
    elif args.command == "advise":
        telemetry = load_telemetry(args.telemetry)
        summary = telemetry.get("summary") if isinstance(telemetry.get("summary"), dict) else {}
        payload = analyze_hardware_summary(summary).to_dict()
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
    elif args.command == "record-cpu":
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
    elif args.command == "realesrgan-candidates":
        candidates = realesrgan_candidates(
            vram_mb=args.vram_mb,
            cpu_threads=args.cpu_threads,
            gpu_index=max(0, args.gpu_index),
            width=max(1, args.width),
            height=max(1, args.height),
        )
        payload = {
            "candidates": [asdict(item) for item in candidates],
            "physical_acceptance": "pending",
            "note": "candidates require integrity-approved physical benchmarking before runtime promotion",
        }
    else:
        key = _realesrgan_key(args)
        samples = tuple(
            RealEsrganSample(
                policy=RealEsrganPolicy(
                    sample.policy.tile,
                    sample.policy.load_jobs,
                    sample.policy.process_jobs,
                    sample.policy.save_jobs,
                    max(0, args.gpu_index),
                ),
                wall_seconds=sample.wall_seconds,
                integrity_ok=sample.integrity_ok,
                oom=sample.oom,
                output_frames=sample.output_frames,
                expected_frames=sample.expected_frames,
            )
            for sample in args.sample
        )
        store = RealEsrganTuningStore(args.cache)
        chosen = store.record_samples(key, samples)
        if chosen is None:
            payload = {
                "recorded": False,
                "reason": "no integrity-approved Real-ESRGAN sample; cache left unchanged",
                "key": key.token(),
            }
        else:
            payload = {
                "recorded": True,
                "key": key.token(),
                "policy": asdict(chosen),
                "cache": str(args.cache),
                "physical_acceptance": "evidence-recorded-for-exact-key-not-global-pass",
            }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())