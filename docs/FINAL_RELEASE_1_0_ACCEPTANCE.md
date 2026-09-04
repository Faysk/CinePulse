# CinePulse 1.0 — Final Release Acceptance

**Status:** candidate under final gates
**Target:** `1.0.0`
**Date:** 2026-09-04

## Release principle

CinePulse 1.0 is approved only for behavior that has a reproducible contract and release evidence. Experimental recovery and extreme hardware paths are not silently promoted into Stable merely because their code exists.

The Stable release therefore follows two rules:

1. a supported Stable path must pass the canonical source, media, Windows distribution and integrity gates;
2. a path whose physical acceptance is still missing remains Preview/opt-in or explicitly blocked from Stable.

## Stable 1.0 contract

The candidate must prove all items below before tag/release:

- source/release contract, compile and unit suite green on Windows and Linux;
- CPU/media integration gates green;
- final static audit green;
- Windows portable package builds and its updater/apply transaction passes;
- MSI builds, validates, installs, repairs and uninstalls in the Windows release gate;
- all active visual intermediates are lossless FFV1; no hidden SDR8 H.264 intermediate generation remains;
- core Python dependencies are hash locked;
- optional neural runtime is transitively hash locked and the installer uses `--require-hashes`;
- the neural lock is included in portable packages and in update transactions;
- the production update policy is either cryptographically signed or disabled. The default 1.0 package ships with remote auto-update disabled until a production signing key/channel is configured;
- Recovery & Reliability infrastructure is present but Stable defaults to Ring 1 (shadow manifest only): no generic recovery worker/discovery is enabled by default;
- 10K/12K and 240+ fps remain outside Stable until their own physical acceptance exists.

## Recovery & Reliability status

Phases 0–8 are implemented. Automated Recovery Reliability gates cover durable manifests, revision/CAS, lease/heartbeat ownership, idempotent stage checkpoints, fault injection, media integrity, storage staging, migration, rollback and dry-run discovery.

The generic recovery product surface remains **Preview** until physical gates prove worker lifecycle, storage interruption and GPU behavior on target hardware. This is intentional and is not a missing Stable 1.0 feature.

The incident-specific RIFE recovery tooling remains available as a proven operational recovery path and reference implementation.

## Hardware / GPU acceptance

The repository contains a guarded pull-request GPU acceptance workflow targeting `[self-hosted, Windows, X64, cinepulse-gpu]`. It runs the existing RIFE, Real-ESRGAN and Demucs GPU integration gates plus the recovery-specific real 8K UHD RIFE acceptance.

A physical capability is not considered Stable merely because the workflow is queued or skipped. Only a completed successful run is evidence.

If the target runner is unavailable at finalization time, the corresponding unproven extreme path must remain Preview/blocked rather than delaying or weakening the correctness of the validated Stable surface.

## Distribution acceptance

The Release Candidate workflow is part of the PR gate and must build/test both Windows distribution modes. A successful source suite alone is insufficient for release.

Required evidence:

- `Quality`: success;
- `Recovery Reliability`: success;
- `Release Candidate`: success;
- `GPU Acceptance`: success for any GPU/extreme capability claimed as Stable; otherwise that capability stays Preview.

## Audit debt versus release blockers

Technical debt is not represented as completed work. CP-027, CP-032 and CP-033 may remain tracked architecture/UX debt after 1.0 provided they do not violate the Stable release contract or produce a known correctness/data-loss defect.

CP-011, CP-019 and CP-020 are release blockers and must be resolved before 1.0:

- CP-011: visual intermediates lossless;
- CP-019: signed-or-disabled production update trust;
- CP-020: transitive neural dependency lock and packaged install surface.

## Final decision states

- **GO — Stable 1.0:** every Stable gate above is green and version/package metadata are synchronized.
- **GO — Preview only for a capability:** Stable core is green but that capability lacks physical acceptance.
- **NO-GO:** any canonical source/media/Windows distribution gate fails, a release blocker is unresolved, or packaging does not match the audited source contract.

No exception converts a skipped, queued, unavailable or unexecuted gate into a pass.
