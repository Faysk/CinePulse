# One-click updater trust boundaries

The automatic checker only discovers public Stable GitHub Releases. It does not execute content returned by the release API. A candidate must have a valid newer SemVer, the exact expected CinePulse asset name and GitHub release-download URL, and a valid SHA-256 digest before staging.

Package application is deferred until CinePulse has finished active work and the verified package is ready. The helper waits for the current process to exit before invoking either the existing portable transaction or Windows Installer MajorUpgrade. This prevents self-overwrite while Python/FFmpeg handles are live.

Portable extraction keeps path traversal, symlink, encrypted-entry, duplicate-path, entry-count and expanded-size guards. MSI updates do not extract arbitrary content in CinePulse; the verified `.msi` is handed to Windows Installer with passive UI, no automatic reboot and bootstrap suppression.

## Audit hardening

Only final `x.y.z` tags are accepted by the automatic Stable path even if a GitHub release were accidentally marked non-prerelease. The checksum fallback is accepted only from `SHA256SUMS.txt` on the exact same release URL. For MSI installs, the staged file is hashed again immediately before handoff; if it changed while CinePulse was busy, installation is blocked.

The startup discovery request is documented in `docs/PRIVACY.md`. It does not include media, project paths or a CinePulse-generated machine identifier.
