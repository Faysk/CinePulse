# CinePulse 1.1.2 — Complete Product Hardening Audit

Status: **release candidate**. All code-correctable findings identified in this audit round are addressed with regression coverage. Automated release gates must still complete successfully before merge/publication. Physical NVIDIA/8K and perceptual acceptance remain separate hardware/manual evidence and are never converted into a synthetic PASS.

## Base

- Stable base: `v1.1.1`
- Base commit: `30e2a4b5f8d8be50b8b2fcc42aa6c7c4124ce3ba`
- Audit branch: `audit-1.1.2-complete-hardening`
- Target release: `v1.1.2`

## Confirmed findings addressed

1. Preflight no longer infers file-vs-directory from suffix; existing dotted directories are checked directly.
2. `AtomicOutput.commit()` no longer removes a valid final before the replacement can be promoted atomically.
3. `safe_output.process_alive()` treats `PermissionError` conservatively instead of declaring a live process dead.
4. Win64 JobLease/instance mutex paths use pointer-sized HANDLE signatures.
5. JobLease mutations are fenced across processes/hosts so stale owners cannot overwrite newer leases during takeover races.
6. POSIX cancellation waits after SIGTERM and escalates to SIGKILL when the process tree does not terminate.
7. Updater manifest/signature/archive ingestion has explicit resource ceilings and hardened ZIP validation for traversal, symlinks, encrypted entries, duplicate paths and expanded size.
8. Queue/preset persistence can restore a validated `.bak` after corruption while preserving evidence; future schemas are never silently downgraded.
9. Non-Windows single-instance locking records process-start identity plus ownership nonce, preventing PID reuse/stale release races.
10. Render-worker cancellation persists only valid state-machine transitions, including cancel-after-pause.
11. Installed-update guidance reflects the self-contained Installer v2 layout instead of stale `%LOCALAPPDATA%` wording.
12. Temporary branch-writer automation is removed before release; the permanent writer allowlist returns to `publish-release.yml` only.
13. Release metadata is synchronized to 1.1.2 across package, portable/MSI builders and RC defaults.
14. Publisher is version-bound: release notes are derived from the declared version and main publication is triggered by release-version metadata changes.

## Automated acceptance required before publication

- Quality source matrix on Windows/Linux and supported Python versions;
- CPU integration and media integrity;
- Recovery Reliability;
- Installer v2 Acceptance;
- Release Candidate Windows, portable/updater/MSI lifecycle included;
- Publish Release preflight, SBOM and SHA256SUMS generation.

## Separate acceptance still required

- physical NVIDIA runner (`cinepulse-gpu`);
- real 8K/120 neural workload on the intended target machine;
- long real-media render/perceptual inspection;
- HDR/tone-mapping inspection on suitable display hardware;
- real multi-project queue and perceptual VFX/transition review.

These items do not block the Stable core when documented as unaccepted Preview/extreme capabilities, but they must remain explicit and must not be reported as physically validated.
