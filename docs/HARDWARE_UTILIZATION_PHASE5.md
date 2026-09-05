# Hardware Utilization MegaPack — Phase 5

Phase 5 adds a **downshift-only adaptive runtime guard** on top of the H4 live resource envelope. Its purpose is not to chase a benchmark score: it protects long neural renders when real telemetry shows rising thermal or memory pressure, without changing image quality, model choice, scale, interpolation target, color/HDR, delivery quality or verification.

## Why H5 exists

H4 chooses a safe initial chunk/concurrency envelope from RAM, VRAM and scratch evidence before neural work begins. Long local renders can still change machine conditions after that decision: another application may consume memory, laptop thermals may rise, or VRAM headroom may collapse.

H5 consumes the already-running H1 telemetry stream during Real-ESRGAN and RIFE chunk boundaries. It does not create a second high-frequency monitoring stack and does not change clocks, power limits, fan curves or OS scheduling policy.

## Downshift policy

The controller has three monotonic levels for a single render:

- **Level 0 — H4 envelope:** keep the H4 chunk size and overlap permissions.
- **Level 1 — caution:** future neural chunks are reduced to 75% of the H4 frame count and new extract/pack overlap is disabled.
- **Level 2 — critical:** future neural chunks are reduced to 50% and new overlap remains disabled.

Conservative pressure evidence currently includes GPU temperature, RAM pressure and free VRAM. Level 1 starts at the caution thresholds (GPU >= 84 °C, RAM >= 88%, or free VRAM < 768 MB). Level 2 starts at the critical thresholds (GPU >= 88 °C, RAM >= 94%, or free VRAM < 384 MB).

The policy is deliberately monotonic: once a render downshifts, it does not automatically ramp back up. This prevents oscillation and ensures H5 can never use transient telemetry as permission to exceed the H4 envelope.

## Runtime integration

`HardwareTelemetrySession` exposes only its newest already-collected observational sample. `RenderHistory` provides a safe accessor for the active render, and Studio creates independent controllers for Real-ESRGAN and RIFE.

At each neural chunk boundary:

1. the controller observes the latest sample;
2. if pressure increased, Studio records an `H5 DOWNSHIFT` log entry with the evidence and new scheduling envelope;
3. a future extraction that has not yet become the active chunk is cancelled and cleaned before a smaller chunk is planned;
4. subsequent extract/pack overlap permissions can only move from `true` to `false`;
5. model, pixels, target FPS and verification contracts remain unchanged.

Already-running bounded work is allowed to finish rather than being discarded solely because a later sample requested a downshift. New work follows the reduced envelope.

RIFE keeps a minimum two-frame source chunk because one-frame interpolation is not a valid independent RIFE work unit. Real-ESRGAN keeps its existing non-zero source-tail tolerance.

## Fail-closed guarantees

Missing telemetry does not invent pressure evidence and does not expand anything: the original H4 envelope remains the ceiling. H5 has no code path that increases chunk size or reenables overlap after a downshift.

H5 does **not**:

- switch Real-ESRGAN or RIFE models;
- lower resolution or FPS;
- skip frames;
- change color/HDR or pixel-format contracts;
- reduce codec quality/bitrate targets;
- weaken verification, cancellation, atomic-output or recovery gates;
- overclock, change fan curves, power limits or process priority.

## Acceptance

Focused tests cover healthy/no-op behavior, caution and critical downshift, monotonic no-ramp-up behavior, selected-GPU evidence, minimum RIFE chunk size, opt-in method boundaries and cancellation of future prefetched work before a reduced chunk is planned.

Hosted CI can validate these policy and integration contracts. Physical RTX 4070 utilization, sustained thermals, NVMe behavior and 8K/12K/120 wall-clock performance remain **PENDING physical acceptance** on the real Windows workstation.
