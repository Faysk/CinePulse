# CinePulse 1.1.2 — Complete Product Hardening Audit

Status: **in progress**. This document is evidence, not a declaration that every possible defect has been eliminated.

## Base

- Stable base: `v1.1.1`
- Base commit: `30e2a4b5f8d8be50b8b2fcc42aa6c7c4124ce3ba`
- Audit branch: `audit-1.1.2-complete-hardening`

## Confirmed findings addressed in the first audit batch

1. Preflight incorrectly inferred file-vs-directory from suffix, so existing dotted directories such as `scratch.v2` could be checked through their parent instead of themselves.
2. `AtomicOutput.commit()` moved the previous final away before promoting the partial, leaving a crash window where the user's valid final disappeared.
3. `safe_output.process_alive()` treated `PermissionError` as a dead process, allowing stale-lock logic to make unsafe decisions.
4. Win64 JobLease process identity used implicit ctypes HANDLE signatures and could truncate handles.
5. JobLease heartbeat/release lacked a cross-process mutation fence, allowing a stale owner to overwrite a newer lease in a takeover race.
6. POSIX cancellation sent SIGTERM without waiting/escalating, so a stubborn FFmpeg/child process could survive cancellation.
7. Updater manifest/signature/archive ingestion had no explicit resource ceilings and ZIP extraction did not reject symlinks, case-insensitive duplicate paths, or excessive expanded size.

Each finding has or will have a regression test before merge.

## Still under audit

- queue/preset/UI-state backup recovery;
- interrupted-render reconciliation;
- render history and durable manifest failure behavior;
- staging/storage/recovery edge cases;
- installer/updater/release scripts;
- Studio worker/thread/event lifecycle;
- Overlay Composer Preview reconstruction on the post-audit Stable base;
- physical NVIDIA/8K acceptance remains a hardware gate and is never converted into a synthetic PASS.
