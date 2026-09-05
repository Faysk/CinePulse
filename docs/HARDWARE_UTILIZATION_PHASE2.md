# Hardware Utilization MegaPack — Phase 2

Phase 2 converts the Phase 1 measurement foundation into explicit machine-resource budgets. Image quality, color, interpolation targets, verification rules and recovery semantics are unchanged.

## Machine profiles

The Preview branch exposes three CPU-utilization profiles while preserving manual control:

- `Equilibrado`: uses about 60% of the detected logical CPUs, leaving desktop/OS headroom.
- `Máquina dedicada`: uses the machine aggressively while reserving two logical CPUs on systems with at least eight logical processors.
- `Overnight — máximo`: uses the complete detected logical CPU envelope for unattended renders.

For a 28-thread CPU, the reference budgets are 17 / 26 / 28 threads respectively. Manual values are clamped to the detected logical CPU count so a UI value cannot silently oversubscribe FFmpeg workers.

## Real-ESRGAN feed/save scheduling

The previous fixed `-j 2:2:2` Real-ESRGAN NCNN pipeline is replaced by a hardware-aware load/process/save budget.

CPU-side load/save workers scale with the selected CPU budget. GPU processing workers scale more conservatively because additional Vulkan processing workers can multiply working sets and VRAM pressure:

- cards below 10 GB VRAM remain capped at two GPU processing workers;
- 10–20 GB cards may use three processing workers;
- 20 GB+ cards may use four when the CPU budget is large enough.

On the 28-thread / 8 GB reference machine this resolves to:

- balanced: `2:2:2`;
- dedicated: `3:2:3`;
- overnight: `4:2:4`.

This is intentionally conservative until Phase 1 telemetry from physical hardware proves that higher GPU concurrency improves throughput without VRAM thrash, thermal regression or render instability.

## Acceptance rule

Phase 2 may improve utilization but does not claim a performance win from CI alone. The code must pass Quality, Recovery Reliability and Windows Release Candidate gates, then physical before/after telemetry must be compared with the Phase 1 baseline using the same workload.

A Phase 2 optimization is accepted only when throughput improves without changing output-quality contracts or weakening cancellation, atomic output, verification or recovery behavior.

## Runtime stage-aware integration

The render worker now derives a bounded CPU budget per stage from detected topology while treating the saved/user thread value as a hard ceiling. CPU-heavy stages can use the profile envelope; GPU neural stages deliberately keep host concurrency modest to protect laptop package power and driver feed. Concurrency changes only: image algorithms, model selection, color/HDR transforms, cadence, audio, verification and recovery contracts are unchanged. Physical throughput and thermal acceptance still require real hardware telemetry.

## Integrity-gated measured autotuning

H1 can now consume a local `cpu-tuning.json` evidence cache keyed by exact stage, logical/physical topology, machine mode and whether the stage is feeding an active GPU path. The benchmark CLI records a winner only when at least one candidate has an explicit integrity PASS; a faster failed candidate can never win. Corrupt, missing, mismatched or over-cap evidence is ignored and the conservative topology scheduler remains the fallback.

CI proves the policy contracts only. The repository still claims no physical throughput or thermal PASS until the representative workloads are run on real hardware and their telemetry is recorded.
