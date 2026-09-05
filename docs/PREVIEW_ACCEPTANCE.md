# CinePulse 1.2.0 Final Acceptance Matrix

This document tracks final software acceptance for CinePulse 1.2.0 after integrating the audited Stable one-click updater with Restoration Preview, Hardware Utilization MegaPack H0–H8 and Overlay Composer / Music Visualizer Preview.

## Integrated 1.2.0 baseline

PR #24 (automatic Stable update notification + one-click updater) was accepted and merged into `main`, then the latest Stable baseline was merged into `preview-restoration-lab`. The three overlapping files were resolved deliberately:

- `src/cinepulse/studio.py` keeps both the Preview Overlay Composer entry and the audited `Atualizar vX.Y.Z` CTA/one-click update flow;
- `scripts/final_audit.py` keeps H6/H7/H8/Preview guards and adds the trusted GitHub Stable release/update-publisher checks;
- `docs/PRIVACY.md` documents both local hardware telemetry and the short GitHub Stable-version request.

Release metadata, package metadata, Portable/MSI defaults, RC default, changelog, README and `docs/RELEASE_1_2_0.md` are aligned to **1.2.0**. The release-preparation static `release_gate.py` and `final_audit.py` both passed before the temporary writer workflow removed itself.

The prepared 1.2.0 tree before this user-authored checkpoint was `d823c9316d7a4805c46deafa8616a199213ece8b`. This checkpoint intentionally changes documentation only so the permanent pull-request workflows execute as the repository user on the exact final candidate tree. Any later code or release-metadata change invalidates this acceptance and requires the matrix to run again.

## Software acceptance

The following areas must stay green on the final 1.2.0 head:

- Quality matrix on Windows/Linux and supported Python versions;
- Recovery Reliability;
- Installer v2 Acceptance;
- Windows Release Candidate, including Portable/MSI/update contracts;
- publisher/release contract for the 1.2.0 notes and exact distributable asset names;
- one-click updater discovery, final Stable SemVer filter, exact asset/hash trust boundary, deferred handoff and bootstrap boundary;
- restoration detector, temporal reconstruction, color controls and Preview export regression suites;
- H0-H8 telemetry, scheduling, neural tuning, bounded overlap/backpressure, evidence-gated acceleration and Overnight runtime guards;
- Overlay Composer / Music Visualizer Preview save/load, media timing, audio/stem binding, preview and deterministic CPU-reference export;
- cancellation/process-tree cleanup, recovery and atomic output promotion;
- Stable defaults/Preview isolation and static writer-workflow audit.

## Release policy

CinePulse 1.2.0 may contain the Preview laboratories in the same distribution because the unproven acceleration paths remain explicitly **Preview/Experimental, evidence-gated or on conservative fallback**. Shipping the code is not a physical performance claim.

The Stable render defaults remain conservative. A detected CUDA/NVDEC/NVENC/TensorRT capability does not by itself authorize a faster path; exact evidence is required by the corresponding runtime policy before it can replace the validated reference route.

## Physical acceptance — still pending

Hosted CI is not physical NVIDIA evidence. The following claims remain PENDING until a real target-machine run provides telemetry and output validation:

- sustained RTX 4070 utilization and VRAM behavior;
- sustained CPU/RAM/NVMe behavior under overnight rendering;
- Real-ESRGAN and RIFE tuned-policy throughput on the target driver/model/resolution tuple;
- CUDA/NVDEC/NVENC compositor/media-path performance evidence;
- optional TensorRT Preview performance evidence;
- 8K/60 and 8K/120 physical stability/performance;
- experimental 12K/120 physical stability/performance.

No UI, changelog or release note may convert those physical-only items to PASS from hosted CI alone. Unproven fast paths remain gated and conservative CPU/NCNN fallbacks stay available.

## Software-complete exit criteria

The software portion of 1.2.0 is complete when:

1. permanent Quality, Recovery Reliability, Installer v2 Acceptance and Release Candidate gates are green on the same final head;
2. the release/publisher contract accepts `docs/RELEASE_1_2_0.md` and synchronized 1.2.0 metadata;
3. no temporary writer workflow remains in the repository;
4. no reproducible regression from the final audit remains open;
5. updater and Preview coexist without losing UI/event-loop, cancellation, recovery or distribution contracts;
6. physical-only claims remain explicitly pending unless real hardware evidence exists.

After these software criteria pass, PR #23 can be merged into `main` and the verified publisher can create the 1.2.0 Stable release. Physical acceptance remains a separate hardware-validation program and is not fabricated by hosted CI.
