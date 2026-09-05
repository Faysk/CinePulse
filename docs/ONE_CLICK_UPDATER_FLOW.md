# Update flow

Open CinePulse → asynchronous Stable release check → no-op if current → show `Atualizar vX.Y.Z` if newer → click → download exact Portable/MSI asset → SHA-256 verify → wait for active work to be idle → prepare handoff → close CinePulse → helper waits for process exit → apply Portable transaction or MSI MajorUpgrade → reopen CinePulse.
