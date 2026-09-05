# One-click updater test plan

1. Unit: version ordering, exact GitHub asset selection, digest and checksum fallback, malformed/untrusted URL rejection, bounded download/extraction.
2. UX contract: asynchronous silent startup check, hidden CTA when current, visible `Atualizar vX.Y.Z` when newer, active-work guard.
3. Portable: stage verified ZIP, write pending transaction, relaunch only after app exit, preserve rollback behavior.
4. MSI: stage verified MSI outside install tree, wait for app exit, run MajorUpgrade with bootstrap suppressed, reopen installed launcher.
5. Release gates: Quality, Recovery Reliability, Installer v2 Acceptance and Release Candidate on the exact final PR head.
