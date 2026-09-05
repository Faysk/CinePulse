# One-click Stable updater

## UX contract

CinePulse performs one lightweight asynchronous Stable-release check shortly after the desktop UI opens. The request must never block startup and a network failure during the automatic check stays non-modal.

When the installed version is current, no prominent update control is shown. When a newer Stable GitHub Release is available, CinePulse exposes an active `Atualizar vX.Y.Z` button in the header and mirrors that action in the existing update control.

One click starts download and SHA-256 verification in the background. CinePulse never interrupts an active render, queue run or AI component installation to update itself. After the package is verified, a helper waits for the current process to exit, applies the update, and reopens CinePulse.

## Package selection

- Portable installations download `CinePulse-X.Y.Z-windows-portable.zip` and reuse the existing transactional `pending-update.json` applier with rollback behavior.
- MSI installations download `CinePulse-X.Y.Z-Setup.msi`, keep the package outside the install tree, wait for CinePulse to close, then use Windows Installer MajorUpgrade with `CINEPULSE_SKIP_BOOTSTRAP=1` before reopening `CinePulse-Installed.cmd`.

Release discovery uses the public GitHub `releases/latest` endpoint by default. A configured manifest channel remains available for controlled portable deployments. GitHub asset `sha256:` digests are preferred; `SHA256SUMS.txt` is the compatibility fallback.

## Trust and failure behavior

The updater requires HTTPS, an exact CinePulse GitHub Release asset URL, a valid semantic version and an exact SHA-256 digest. Downloads and extracted portable payloads retain bounded-size/path/symlink/duplicate-entry checks. A failed check leaves the running version untouched. A failed download or hash verification is discarded. A failed MSI handoff keeps or reopens the previous installation rather than promoting an unverified package.

## Bootstrap note

CinePulse 1.1.3 predates this automatic startup discovery. Therefore the first Stable release containing this updater must still be installed once through the existing release/install path. From that updater-enabled release onward, later Stable releases can be discovered and installed through the in-app one-click flow.
