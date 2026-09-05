# Hardware Utilization MegaPack — legacy Phase 5 / H8 precursor

This document describes the adaptive-runtime work that originally landed under the older **Phase 5** numbering. In the current H0–H8 plan, that work is an **H8 precursor** layered on top of H4. The original temperature-only thresholds documented by early Phase 5 revisions are retired.

The current rule is throughput-first: long neural renders keep their benchmark-proven H4 envelope while they continue completing useful work at the best sustained rate. High temperature or hardware-managed thermal throttling is recorded as evidence, but is **not by itself permission to reduce load**.

## Current adaptive policy

H4 chooses the initial bounded chunk/concurrency envelope from RAM, VRAM and scratch evidence before neural work begins. The adaptive runtime consumes the already-running hardware telemetry stream at Real-ESRGAN and RIFE chunk boundaries; it does not create another high-frequency monitor and does not modify clocks, fan curves, power limits, Windows power plans or process priority.

Capacity/stability pressure can still act directly:

- RAM pressure high enough to risk paging/exhaustion;
- free VRAM low enough to risk OOM;
- scratch/NVMe saturation that is demonstrably limiting the bounded pipeline;
- a real neural-stage failure/instability signal.

Temperature, power-limit proximity and GPU clock drops are different. In Overnight mode they may request a downshift **only when measured completed neural work per second has also regressed against the fixed warm-up reference from the same render**. A hot GPU that remains faster is left alone.

## Downshift envelope

The live controller remains monotonic inside one render:

- **Level 0 — proven H4 envelope:** original chunk size and overlap permissions;
- **Level 1 — caution:** reduce future chunk/concurrency pressure and disable new overlap where required;
- **Level 2 — critical/capacity:** reduce future chunks further and keep overlap disabled;
- H8 may additionally reduce the CPU share or provide a bounded cooldown hint when a real sustained throughput/stability problem has been established.

The controller never auto-ramps above the envelope selected at render start. A new render starts fresh from its benchmark-proven policy.

## Measured throughput feedback

Successful Real-ESRGAN and RIFE chunks report their actual completed frame count divided by neural-stage wall time. H8 uses the first sustained window as a fixed warm-up reference and compares later windows against it. Requested target FPS is never treated as measured processing throughput.

This means:

- 92–95 °C with equal or better completed-work throughput does **not** trigger a thermal downshift;
- a cooler run that is measurably slower can still fail physical acceptance;
- temperature/power/clock pressure plus a real sustained throughput decline can reduce upstream CPU/chunk/overlap pressure;
- quality/model/resolution/FPS/color/HDR/verification contracts do not change.

## Runtime integration

`HardwareTelemetrySession` exposes the latest already-collected observational sample. `RenderHistory` provides that sample to Studio. Studio creates independent adaptive controllers for Real-ESRGAN and RIFE and also feeds each controller successful chunk throughput.

At neural chunk boundaries the controller may only reduce future work. Prefetched work that no longer fits the reduced envelope is cancelled and cleaned before replanning; already-completed good output is never discarded just because a later window became constrained.

RIFE retains the minimum valid source workset and Real-ESRGAN retains its existing source-tail/integrity behavior.

## Fail-closed guarantees

Missing telemetry or missing throughput evidence does not invent a thermal constraint and never expands concurrency. H8 has no code path that silently changes system-wide machine policy.

The adaptive runtime does **not**:

- switch Real-ESRGAN or RIFE models;
- lower resolution or FPS;
- skip frames;
- change color/HDR or pixel-format contracts;
- reduce codec quality/bitrate targets;
- weaken verification, cancellation, atomic-output or recovery gates;
- overclock, change fan curves, power limits, Windows power plans or process priority.

## Acceptance

Hosted CI validates capacity-pressure behavior, temperature-only no-op behavior, measured-throughput thermal/power response, monotonic no-ramp-up, selected-GPU evidence, valid RIFE chunk bounds and cancellation of future prefetched work.

Physical RTX 4070 utilization, the best sustained Overnight policy, NVMe behavior and 8K/12K/120 wall-clock performance remain **PENDING physical acceptance** on the real Windows laptop. Use `docs/HARDWARE_MEGAPACK_PHYSICAL_ACCEPTANCE.md` and `scripts/overnight_acceptance.py` for the current authoritative physical gate.
