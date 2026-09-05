# PR summary — one-click Stable updater

- background update discovery on startup via the latest public GitHub Stable release;
- visible `Atualizar vX.Y.Z` action only when a newer release exists;
- Portable and MSI package selection bound to the exact release version;
- GitHub release URL and SHA-256 validation before staging;
- one-click download, verify, close, apply and reopen flow;
- active rendering/queue/AI installation is never interrupted automatically;
- Portable keeps the existing transactional applier; MSI uses MajorUpgrade with bootstrap suppressed;
- startup network failures are non-modal and do not affect normal use;
- focused updater/UX/bootstrap contract tests and release acceptance checklist included.
