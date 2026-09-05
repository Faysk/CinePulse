# Hardware Utilization MegaPack — Phase 1

Phase 1 adds measurement before optimization. It does not change clocks, power limits, driver settings, process priority, fan policy, codec quality, neural model settings, chunk sizes or render concurrency.

## Evidence captured per render

A render history directory may now contain `hardware-telemetry.json` (schema 1) with approximately 2-second samples for:

- NVIDIA GPU utilization and memory-controller utilization when `nvidia-smi` is available;
- VRAM total/used/free;
- GPU power draw/limit, temperature, P-state and graphics/memory clocks when the driver exposes them;
- total CPU utilization and per-logical-processor utilization on Windows/Linux;
- physical RAM total/used/available;
- aggregate physical-disk read/write throughput on Windows/Linux;
- current CinePulse stage and wall time per stage.

Telemetry is best-effort and observational. Missing counters are stored as unavailable instead of failing a render.

## Benchmark contracts

Two reference scenarios are named in the benchmark helper:

1. `720p24_to_8k120_music`: 1280x720 24 fps, 10 s reusable clip, 7680x4320 120 fps, 264 s project timeline.
2. `1080p30_to_4k60`: 1920x1080 30 fps to 3840x2160 60 fps.

`python scripts/hardware_benchmark.py summarize <hardware-telemetry.json> --scenario <name>` summarizes one run.

`python scripts/hardware_benchmark.py compare <baseline.json> <candidate.json> --scenario <name>` reports wall-time/stage speedups between two physical runs.

For optimization phases, keep the first representative run from the target notebook as the immutable **baseline** and compare every candidate policy against that same scenario. A candidate only wins when it improves sustained throughput without lowering the existing image, temporal, color, audio-sync, verification or recovery contracts.

The recommended physical evidence sequence is:

1. run the representative CinePulse project with the Phase 1 telemetry build;
2. retain the resulting render-history directory and `hardware-telemetry.json` as baseline evidence;
3. summarize it with `hardware_benchmark.py summarize`;
4. after each optimization phase, repeat the same project and use `hardware_benchmark.py compare` against the retained baseline.

This makes GPU/VRAM/CPU/RAM/NVMe/thermal observations comparable across Phase 2 onward instead of relying on Task Manager screenshots or peak utilization alone.

## Acceptance rule

Phase 1 establishes evidence only. CI proves parsing, summarization, atomic persistence and graceful counter failure. It does **not** claim physical RTX 4070, 8K/120, 12K/120, thermals or NVMe throughput acceptance; those require telemetry captured on real hardware.

Phase 1 is considered software-complete only when the clean Preview branch passes its normal repository gates with the temporary integration writer removed. Physical baseline capture remains a separate hardware acceptance step and must not be inferred from CI.
