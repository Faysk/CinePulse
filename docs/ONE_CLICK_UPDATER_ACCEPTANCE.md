# One-click updater acceptance

A Stable updater release is acceptable only when all of the following are true on the exact PR head:

- startup schedules an asynchronous update check and remains usable if GitHub is unavailable;
- no prominent CTA is shown when the installed version is current;
- a newer Stable GitHub Release exposes `Atualizar vX.Y.Z` without requiring the user to open a settings screen;
- Portable selects the exact `CinePulse-X.Y.Z-windows-portable.zip` asset;
- MSI selects the exact `CinePulse-X.Y.Z-Setup.msi` asset;
- GitHub asset URL, final `x.y.z` Stable SemVer and SHA-256 are validated before promotion;
- `SHA256SUMS.txt` fallback must come from the exact same GitHub release as the selected package;
- a deferred MSI is SHA-256 checked again immediately before handoff, so a changed staged file is blocked;
- active render, queue processing or AI installation blocks update application rather than being interrupted;
- if work starts while the package is downloading, the verified package remains prepared and installation is deferred until CinePulse is idle instead of closing the new render or downloading again;
- Portable update continues through the existing transactional pending-update applier;
- MSI handoff waits for the CinePulse process to exit, uses MajorUpgrade with bootstrap suppressed, then reopens the installed launcher;
- failed discovery is silent at startup; failed staging/application keeps the current installation usable;
- privacy documentation discloses the automatic GitHub version request and confirms that media/project data is not attached;
- no temporary write workflow or patch helper remains tracked;
- Quality, Recovery Reliability, Installer v2 Acceptance and Release Candidate pass on the exact final head.

The first Stable release containing this implementation is the bootstrap boundary: an older 1.1.3 installation cannot execute code it does not yet contain. After that release is installed once, later Stable releases are discoverable through the in-app flow.
