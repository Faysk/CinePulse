# CinePulse Preview Acceptance Matrix

This document tracks the final acceptance state of the Preview restoration and hardware-utilization work before PR #23 can leave Draft.

## Software acceptance

The following areas must stay green on the final Preview head:

- Quality matrix on Windows/Linux and supported Python versions;
- Recovery Reliability;
- Windows Release Candidate, including portable/MSI/update contracts;
- restoration detector, temporal reconstruction, color controls and Preview export regression suites;
- H1-H5 telemetry, scheduling, neural tuning, overlap/backpressure and downshift-only runtime guards;
- cancellation/process-tree cleanup and atomic output promotion;
- Stable/Preview separation and static writer-workflow audit.

The final static audit/polish pass completed successfully on the Preview branch before this matrix was added. This commit intentionally creates a user-authored final acceptance checkpoint so the permanent pull-request workflows can run again on the exact post-polish tree.

## Physical acceptance — still pending

Hosted CI is not physical NVIDIA evidence. The following claims remain PENDING until a real workstation run provides telemetry and output validation:

- sustained RTX 4070 utilization and VRAM behavior;
- sustained CPU/RAM/NVMe behavior under overnight rendering;
- Real-ESRGAN and RIFE tuned-policy throughput on the target driver/model/resolution tuple;
- 8K/60 and 8K/120 physical stability/performance;
- experimental 12K/120 physical stability/performance.

No Preview or Stable UI/release note may convert those items to PASS from hosted CI alone.

## Exit criteria for Draft

PR #23 can leave Draft only when:

1. permanent software gates are green on the same final head;
2. no temporary writer workflow remains in the repository;
3. no reproducible regression from the final audit remains open;
4. Preview-only behavior remains isolated from Stable contracts;
5. physical-only claims remain explicitly pending unless real hardware evidence exists.
