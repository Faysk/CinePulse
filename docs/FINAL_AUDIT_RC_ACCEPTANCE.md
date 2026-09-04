# CinePulse — Final Audit & Release Candidate Acceptance

> **SUPERSEDED / historical record.** This document records the earlier RC audit state and is no longer the release decision source for CinePulse 1.0.0.
>
> The current release contract and decision criteria are maintained in [`FINAL_RELEASE_1_0_ACCEPTANCE.md`](FINAL_RELEASE_1_0_ACCEPTANCE.md). The canonical CI gates and the current `RenderPlan` audit metadata take precedence over the historical findings below.

## Historical context

This audit was produced before the final 1.0 hardening cycle. At that time Windows distribution evidence, lossless intermediates, production update trust and the transitive neural dependency lock were still incomplete.

Those release blockers were subsequently addressed:

- **CP-011** — active visual intermediates were moved to lossless FFV1 and storage estimation was updated accordingly;
- **CP-019** — the Stable updater policy became **signed-or-disabled**; the default 1.0 package ships with remote auto-update disabled unless a signed Minisign channel is explicitly configured;
- **CP-020** — the neural runtime now has a transitively generated hash lock and the installer consumes it with `--require-hashes`; the lock is included in the portable/update surface;
- Windows portable, updater/apply, MSI build/payload and install/repair/uninstall lifecycle are covered by the Release Candidate workflow;
- version/package defaults are synchronized to `1.0.0`;
- generic recovery remains Preview/shadow by policy until its physical acceptance is complete;
- extreme GPU paths such as physical 8K/120 acceptance are not considered Stable without a successful target-hardware gate.

## Remaining tracked debt

The final audit metadata intentionally keeps architectural/UX debt visible where it does not violate the Stable correctness contract. In particular CP-027, CP-032 and CP-033 are not silently marked complete.

## Why this file remains

It is retained so the evolution from the earlier RC findings to the final 1.0 acceptance remains auditable. It must not be used to infer the current release status.

For the current status, use:

1. [`FINAL_RELEASE_1_0_ACCEPTANCE.md`](FINAL_RELEASE_1_0_ACCEPTANCE.md);
2. `scripts/final_audit.py` and `scripts/release_gate.py`;
3. the current GitHub `Quality`, `Recovery Reliability` and `Release Candidate` workflow evidence;
4. `GPU Acceptance` only for GPU/extreme capabilities that are actually claimed as Stable.
