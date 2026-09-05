# CinePulse Preview Acceptance Matrix

This document tracks the final acceptance state of the Preview restoration, Hardware Utilization MegaPack and Overlay Composer after integrating the latest Stable updater into PR #23.

## Integrated latest baseline

PR #24 (automatic Stable update notification + one-click updater) was accepted and merged into `main`, then `main` was merged into `preview-restoration-lab` with the three overlapping files resolved deliberately:

- `src/cinepulse/studio.py` keeps both the Preview Overlay Composer entry and the audited `Atualizar vX.Y.Z` CTA/one-click update flow;
- `scripts/final_audit.py` keeps H6/H7/H8/Preview guards and adds the trusted GitHub Stable release/update-publisher checks;
- `docs/PRIVACY.md` documents both local hardware telemetry and the short GitHub Stable-version request.

The temporary merge writer workflow was removed before this checkpoint. Any later code commit invalidates exact-head acceptance and requires the permanent matrix to run again.

## Software acceptance

The following areas must stay green on the final integrated Preview head:

- Quality matrix on Windows/Linux and supported Python versions;
- Recovery Reliability;
- Installer v2 Acceptance;
- Windows Release Candidate, including Portable/MSI/update contracts;
- one-click updater discovery, exact asset/hash trust boundary, deferred handoff and bootstrap boundary;
- restoration detector, temporal reconstruction, color controls and Preview export regression suites;
- H0-H8 telemetry, scheduling, neural tuning, bounded overlap/backpressure, evidence-gated acceleration and Overnight runtime guards;
- Overlay Composer / Music Visualizer Preview save/load, media timing, audio/stem binding, preview and deterministic CPU-reference export;
- cancellation/process-tree cleanup, recovery and atomic output promotion;
- Stable/Preview separation and static writer-workflow audit.

This commit is intentionally user-authored so the permanent pull-request workflows execute on the exact integrated tree rather than inheriting the GitHub Actions authorization block that applies to bot-authored pushes.

## Physical acceptance — still pending

Hosted CI is not physical NVIDIA evidence. The following claims remain PENDING until a real target-machine run provides telemetry and output validation:

- sustained RTX 4070 utilization and VRAM behavior;
- sustained CPU/RAM/NVMe behavior under overnight rendering;
- Real-ESRGAN and RIFE tuned-policy throughput on the target driver/model/resolution tuple;
- CUDA/NVDEC/NVENC compositor/media-path performance evidence;
- optional TensorRT Preview performance evidence;
- 8K/60 and 8K/120 physical stability/performance;
- experimental 12K/120 physical stability/performance.

No Preview or Stable UI/release note may convert those physical-only items to PASS from hosted CI alone. Unproven fast paths remain evidence-gated and conservative CPU/NCNN fallbacks stay available.

## Software-complete exit criteria

The software portion is complete when:

1. permanent Quality, Recovery Reliability, Installer v2 Acceptance and Release Candidate gates are green on the same final integrated head;
2. no temporary writer workflow remains in the repository;
3. no reproducible regression from the final audit remains open;
4. Preview-only behavior remains isolated from Stable defaults/contracts;
5. the updater and Preview coexist without losing either UI/event-loop contract;
6. physical-only claims remain explicitly pending unless real hardware evidence exists.

Physical acceptance is a separate hardware validation step and is not fabricated by hosted CI.
