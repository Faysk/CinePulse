# CinePulse 1.0.0 — Release Record

**Status:** RELEASED
**Published:** 2026-09-04
**Tag:** `v1.0.0`
**Release commit:** `4afd4f4bf658dabe127754dd7752d0636832e2c1`
**Release page:** https://github.com/Faysk/CinePulse/releases/tag/v1.0.0

## Final decision

CinePulse 1.0.0 is released for the validated Stable scope. The release tag points exactly to the audited merge commit. Generic recovery and unproven extreme GPU paths are not promoted into Stable by omission.

## Canonical pre-merge gates

All required Stable software/distribution gates passed on the final audited PR head before merge:

- Quality — run `33903119140`: **PASS**;
- Recovery Reliability — run `33903119092`: **PASS**;
- Release Candidate — run `33903119098`: **PASS**.

The Windows Release Candidate gate covered release-light, PowerShell release contract, portable package generation, updater/apply transaction, MSI build/payload validation and MSI install/repair/uninstall.

## Publication gate

Publication workflow run `33904079206`: **PASS**.

The publisher checked out the audited merge commit and repeated the Windows publication path before creating the tag/release:

1. release identity / exact SHA validation;
2. release-light gate;
3. PowerShell release contract;
4. portable build;
5. portable updater/apply test;
6. MSI build;
7. MSI payload validation;
8. MSI install/repair/uninstall;
9. release checksums and notes;
10. GitHub Release creation;
11. removal of the temporary publisher workflow from `main`.

Publication evidence artifact: `cinepulse-1.0.0-publication-evidence`, workflow artifact id `9948868172`.

## Published assets

| Asset | SHA-256 |
|---|---|
| `CinePulse-1.0.0-windows-portable.zip` | `7beac4e0482b4c01456a8e8d35b6ab0860fea8049a052345ec1ff6171b9b7865` |
| `CinePulse-1.0.0-Setup.msi` | `e548cc83eaec63b5145924518122de44f637e71dc445e7929e441c7423a31858` |
| `CinePulse-1.0.0-Setup-manifest.json` | `00bc029316980185d114f86a828346af1f21f5dad0ab61d767a8be6289c8fda4` |
| `SHA256SUMS.txt` | `ac9da0f99731c8787c2f16205f2d513ecb5414d4f7b542f7af32e3aa446daf87` |

## Stable scope

The Stable 1.0 contract includes the validated core/render/distribution behavior from the final acceptance program, including:

- target-aware resolution/FPS/color/delivery planning;
- lossless active visual intermediates;
- atomic media promotion and crash-safe staging;
- durable recovery manifests/checkpoints/lease infrastructure while generic recovery remains shadow/Preview by default;
- hash-locked core and neural dependency graphs;
- portable and MSI distribution paths validated on Windows;
- remote portable updater disabled by default unless an explicitly signed trust configuration is supplied.

## Preview / unaccepted physical scope

GPU Acceptance run `33903119108` remains queued because the dedicated `[self-hosted, Windows, X64, cinepulse-gpu]` runner has not supplied a successful physical result.

Therefore:

- 8K/120 neural/GPU execution is **not** represented as physically accepted Stable capability;
- other extreme GPU paths remain Preview/unproven;
- 10K/12K and 144/240/480 fps remain experimental/bounded outside the Stable profile;
- generic recovery product surface remains Preview/shadow until its corresponding physical gates complete.

A queued, skipped or unavailable physical gate is never counted as PASS.

## Signing / trust note

The released MSI is not Authenticode-signed because no production certificate was configured. Distribution integrity is provided by the official GitHub Release and published SHA-256 values. The portable remote update channel remains disabled by default, avoiding an unsigned automatic-update path.

## Repository cleanup

The temporary release publisher was removed automatically after successful publication. The current `main` tree after cleanup matches the audited release tree; the extra post-release commits only introduced and then removed the temporary publisher used to create the release.
