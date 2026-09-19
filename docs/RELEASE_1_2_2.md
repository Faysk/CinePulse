# CinePulse 1.2.2

CinePulse 1.2.2 is a corrective hardening release for the direct visual Composer introduced in 1.2.1. It does not broaden the Stable capability envelope; it restores Preview/final parity and tightens cancellation, resource and release guarantees.

## Composer audio-reactive export parity

The CPU reference exporter now resolves the same cached music analysis used by editor Preview when precomputed envelopes are not supplied.

This fixes a 1.2.1 regression where the editor Preview could react correctly to project music while the final CPU export received empty audio features. The affected behavior included:

- Spectrum, Waveform and Circular visualizers;
- media pulse;
- beat reaction;
- stem/master fallback behavior.

A real FFmpeg integration test now exports a music-reactive visualizer and verifies that the final product is not the zero-envelope rendering.

## Cancellation and application lifecycle

Composer CPU muxing no longer uses a blocking `subprocess.run()` path. FFmpeg muxing is process-tree-aware and polls the cancellation contract.

The Composer export worker is also registered with the Studio lifecycle:

- closing the Composer during export requests cancellation and waits for the worker to finish before destroying its window;
- closing CinePulse while a Composer export is active requests cancellation before the root UI is destroyed;
- the application gives the worker a bounded shutdown window so FFmpeg descendants are not abandoned;
- AtomicOutput remains the final promotion boundary, so cancellation preserves an existing good destination.

## Resource preflight

The CPU Composer now performs an early local resource preflight before the expensive frame loop.

The preflight estimates:

- RGBA per-frame working memory;
- a bounded peak RAM envelope;
- the lossless FFV1 visual master planning floor;
- simultaneous visual-master + atomic mux scratch pressure.

Clearly insufficient RAM or destination free space fails before rendering starts instead of after a long 8K/10K/12K job.

## H6 GPU fail-closed behavior

Still-image backgrounds are kept on the deterministic CPU reference until a dedicated H6 physical parity record exists for that base-media class.

An approval collected for a video base can therefore no longer authorize the still-image path implicitly. Composer GPU source/test changes now also trigger the physical GPU Acceptance workflow.

Physical GPU performance acceptance remains separate and is not claimed by hosted CI.

## Dependency and release hardening

- neural runtime refreshes `certifi` to 2026.7.22 under the existing SHA-256 hash lock;
- Python 3.12 is added to the source compatibility matrix alongside 3.11, 3.13 and the release Python;
- GitHub Actions used by permanent workflows are pinned to exact commit SHAs;
- the Stable publisher consumes the exact FFmpeg URL/version/SHA-256 already declared in `installer/bootstrap-manifest.json` instead of resolving an unpinned Chocolatey package.

## Safety model

The Stable/Preview boundary is unchanged. Capability detection alone does not authorize CUDA/NVDEC/NVENC/TensorRT fast paths. Unproven routes remain blocked or fall back to the deterministic CPU/NCNN reference.

CinePulse 1.2.2 is intended as a patch release over 1.2.1; no new physical 8K/120, 10K/12K or TensorRT acceptance claim is introduced.
