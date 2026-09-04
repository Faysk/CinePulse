# CinePulse 1.0.1 — Neural installer hotfix

## Incident

The 1.0.0 Windows installer could fail while preparing the Demucs runtime with:

`Because there is no version of torch==2.11.0+cu126 ... requirements are unsatisfiable.`

## Root cause

`requirements-neural.in` was compiled against the official PyTorch CUDA 12.6 index, and `bootstrap-manifest.json` already declared the same `torch_index`. The generated hash lock itself does not retain the index declaration used during compilation.

`installer/Start-CinePulse.ps1` installed only from `requirements-neural.lock` without passing the manifest PyTorch index to `uv`. The resolver therefore did not have the same package source contract as the lock-generation step.

The pinned Windows/Python 3.13 CUDA wheel exists on the official PyTorch index; the version pin was not the defect.

## Fix

- Resolve the neural lock with `uv pip install --require-hashes --index <bootstrap torch_index>`.
- Reject a bootstrap torch index outside `https://download.pytorch.org/whl/`.
- Keep the exact hash-locked package set; no dependency downgrade or unpinned fallback.
- Add static contract tests linking manifest, neural input, neural lock and installer.
- Add a Windows release-gate resolver smoke using the exact portable uv version and a fresh Python venv with `--dry-run`.

## Resume behavior

Real-ESRGAN and RIFE installations are marker-based. A user whose 1.0.0 installation failed at Demucs can rerun the corrected installer; completed Real-ESRGAN/RIFE components should be reused, while the incomplete Demucs venv is recreated cleanly.
