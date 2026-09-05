# Hardware Utilization MegaPack — Phase 4

Phase 4 turns the bounded resource policy from Phase 2/3 into live runtime chunk planning without changing image quality, model choice, interpolation cadence, color/HDR contracts, output verification, cancellation or recovery behavior.

## Live headroom evidence

Before the expensive neural stages, CinePulse can collect a small, local-only headroom snapshot for the active scratch volume:

- currently available physical RAM;
- free VRAM for the selected NVIDIA adapter when `nvidia-smi` exposes it;
- current free space on the scratch volume;
- a bounded synchronous sequential-write probe on that same scratch volume.

The write probe is intentionally small, non-sparse, `fsync`-flushed and deleted immediately. If free-space headroom is insufficient or the probe fails, no throughput value is invented.

## Runtime integration status

The live headroom contract is consumed by the actual Studio render path before neural processing. The same per-render snapshot derives separate Real-ESRGAN and RIFE budgets, and those budgets are passed into the existing bounded PNG chunk planner.

The throughput probe runs only when the RenderPlan contains a neural enhancement or RIFE step. Non-neural renders therefore do not pay the physical scratch-probe cost. Real-ESRGAN and RIFE keep their existing model, scale, frame target, integrity and fallback behavior; H4 changes only buffering and bounded scheduling around those operations.

When live evidence permits it, Real-ESRGAN can pre-extract one future input chunk while the GPU works on the current chunk. Its previous FFV1 pack may also overlap the next neural pass, but the pipeline has strict backpressure: at most one future extraction and one previous pack may be in flight around the active neural chunk. RIFE uses the same one-chunk future extraction rule but does not add an independent pack overlap. Slow scratch, missing VRAM evidence, insufficient RAM or non-dedicated policy reduce concurrency automatically.

The Real-ESRGAN frame-count boundary preserves the historical safe behavior: zero decoded frames is fatal, while a non-zero short extraction disables further prefetch instead of turning a previously tolerated source-tail discrepancy into a new hard failure.

Focused source tests cover the live RAM/VRAM/scratch snapshot, low-space fail-closed behavior, probe cleanup, bounded budget derivation, both neural tuning safety contracts and the three-workset ceiling. The Studio integration is compiled and exercised under Python 3.11 so H4 does not accidentally rely on newer f-string grammar while the supported release matrix still includes 3.11.

## Cancellation and recovery

H4 background extraction/packing processes are independently cancellable and use isolated process groups. The foreground FFmpeg runner no longer relies on a blocking stdout iterator to observe cancellation: output is drained on a reader thread while the render worker continues polling the child process.

On Windows, process-tree termination now verifies that the `taskkill /T /F` target actually exits and falls back to direct termination if the process handle does not become signaled. The dedicated Windows cancellation integration test proves that the render worker exits, the previous destination survives unchanged, partial output is removed and the render journal is cleared.

## What the evidence is allowed to change

The H4 budget may only change the size of a materialized neural PNG chunk and whether the strictly bounded extract/pack overlap is permitted.

It must not change:

- Real-ESRGAN model or scale;
- RIFE model or requested target frame count;
- color transforms, HDR/SDR decisions or pixel-format contracts;
- output codec quality targets;
- visual effects or audio processing;
- integrity, verification, cancellation, atomic-output or recovery gates.

## Fail-closed behavior

Unknown RAM, VRAM or scratch throughput never enables a larger or more concurrent pipeline by itself. Missing VRAM evidence also prevents expansion beyond the legacy 4 GiB neural chunk envelope. A slow or unproven scratch device disables overlap, and the hard in-flight workset ceiling remains three even on a large workstation.

The physical throughput probe is runtime evidence for the current scratch volume only. It is not a global performance PASS and does not prove 8K/12K/120 acceptance.

## Physical acceptance

RTX 4070 utilization, laptop power sharing, thermals, sustained NVMe throughput and 8K/12K/120 wall-clock performance remain **PENDING physical acceptance** until measured on the real Windows workstation. Hosted CI validates policy, cleanup, fail-closed behavior, cancellation/recovery and Stable/Preview separation; it does not replace the real hardware acceptance gate.
