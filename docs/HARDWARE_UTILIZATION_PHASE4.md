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

The live headroom contract is now consumed by the actual Studio render path before neural processing. The same per-render snapshot derives separate Real-ESRGAN and RIFE budgets, and those budgets are passed into the existing bounded PNG chunk planner.

The throughput probe runs only when the RenderPlan contains a neural enhancement or RIFE step. Non-neural renders therefore do not pay the physical scratch-probe cost. Real-ESRGAN and RIFE keep their existing model, scale, frame target, integrity and fallback behavior; H4 changes only how many frames may be materialized in one bounded workset.

Focused source tests cover the live RAM/VRAM/scratch snapshot, low-space fail-closed behavior, probe cleanup, bounded budget derivation and both neural tuning safety contracts. The Studio integration is also compiled and exercised under Python 3.11 so H4 does not accidentally rely on newer f-string grammar while the supported release matrix still includes 3.11.

## What the evidence is allowed to change

The H4 budget may only change the size of a materialized neural PNG chunk and, in later H4 steps, whether a strictly bounded extract/pack overlap is permitted.

It must not change:

- Real-ESRGAN model or scale;
- RIFE model or requested target frame count;
- color transforms, HDR/SDR decisions or pixel-format contracts;
- output codec quality targets;
- visual effects or audio processing;
- integrity, verification, cancellation, atomic-output or recovery gates.

## Fail-closed behavior

Unknown RAM, VRAM or scratch throughput never enables a larger or more concurrent pipeline by itself. The existing conservative chunk envelope remains the fallback. A slow or unproven scratch device disables overlap, and the hard in-flight queue ceiling remains three chunks even on a large workstation.

The physical throughput probe is runtime evidence for the current scratch volume only. It is not a global performance PASS and does not prove 8K/12K/120 acceptance.

## Physical acceptance

RTX 4070 utilization, laptop power sharing, thermals, sustained NVMe throughput and 8K/12K/120 wall-clock performance remain **PENDING physical acceptance** until measured on the real Windows workstation. Hosted CI only validates policy, cleanup, fail-closed behavior and Stable/Preview separation.
