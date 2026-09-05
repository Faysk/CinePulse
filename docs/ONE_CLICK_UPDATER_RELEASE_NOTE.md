# Automatic update notification and one-click install

This increment adds the updater UX required for future CinePulse Stable releases: shortly after startup the app checks the latest public Stable release in the background. When a newer version exists, an `Atualizar vX.Y.Z` action becomes visible; one click downloads and verifies the correct Portable or MSI package, then applies it after CinePulse closes and reopens the application.

The update path does not interrupt active rendering, queue execution, or AI component installation. Portable builds keep the existing transactional updater. Installed builds use the WiX MajorUpgrade path after SHA-256 verification and suppress the first-install bootstrap during the upgrade.

CinePulse 1.1.3 does not contain this code, so the first release that ships this increment must be installed once through the existing release flow. Subsequent Stable releases can use the new in-app update experience.
