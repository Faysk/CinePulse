# Hardware Utilization MegaPack — H5 NVDEC / CUDA media path

This document uses the **H0–H8 MegaPack numbering from the current performance plan**. An older `HARDWARE_UTILIZATION_PHASE5.md` in this branch describes thermal/memory pressure downshift work; under the current plan that work is better understood as an H8 precursor. It is not evidence that the NVDEC/CUDA H5 described here was already complete.

## Quality-first rule

CUDA capability is not runtime permission.

FFmpeg may advertise `cuda`, CUVID/NVDEC decoders, `scale_cuda`/`scale_npp`, and NVENC. CinePulse only enables a GPU media path after a physical benchmark has recorded an exact approved evidence key. Without that record, the existing CPU/zscale path remains authoritative.

The evidence key includes:

- GPU name and NVIDIA driver;
- FFmpeg build fingerprint;
- source codec and source resolution;
- target resolution for scale operations;
- pixel format and bit depth;
- color primaries, transfer, matrix and range;
- operation (`decode`, `decode-scale`, later `decode-scale-encode`).

A 1080p→4K result therefore cannot authorize 1080p→8K, and a result from one driver/FFmpeg build cannot silently authorize another.

## Initial safe envelope

H5 phase A is intentionally narrow:

- known SDR color metadata only;
- H.264 / HEVC / AV1 / VP9 / MPEG-2 only when the matching CUVID decoder is present;
- HDR/PQ/HLG remains on CPU/zscale;
- missing/unknown color metadata remains on CPU;
- no GPU tone mapping or gamut conversion;
- decode acceleration is integrated first into the bounded PNG extraction that feeds Real-ESRGAN;
- CUDA scaling is benchmarkable but is not inferred from decode evidence;
- NVENC delivery requires its own future exact evidence key and is never inferred from NVDEC success.

## Physical benchmark gates

`scripts/gpu_media_benchmark.py` builds an authoritative CPU reference using FFV1. When scaling is requested, the reference uses zscale. The CUDA candidate uses NVDEC/CUDA and downloads once to the same software pixel format before FFV1 comparison.

A candidate is recordable only when all of the following pass:

- output exists and is structurally valid;
- frame count matches the CPU reference;
- video metadata matches, including dimensions, pixel format and declared color metadata;
- audio presence is preserved and duration differs by no more than 20 ms;
- visual parity passes PSNR and SSIM gates;
- candidate throughput is meaningfully faster than baseline (minimum 1.03× speedup).

Decode-only is held to a stricter quality bar because changing the decoder is not supposed to change the image: **PSNR ≥ 80 dB and SSIM ≥ 0.999999**. CUDA scaling currently uses the conservative general floor **PSNR ≥ 55 dB and SSIM ≥ 0.999** and still requires exact metadata/timing integrity.

These thresholds are acceptance guards, not claims that a specific NVIDIA GPU already passed them.

## Runtime rollback

The Real-ESRGAN extraction path checks the exact H5 cache before each render setup. If no approved record exists, nothing changes: CPU decode is used.

If an approved NVDEC policy is selected and then fails during a real render:

1. the exact evidence record is invalidated;
2. partial PNG output for the affected chunk is deleted;
3. that chunk is repeated once through the CPU path;
4. subsequent chunks remain on CPU for the current render.

The same rule applies to an H4 prefetched extraction chunk. No failed CUDA policy remains active after fallback.

## Stable / Preview separation

This work lives on the Preview branch and does not merge into Stable while acceptance is incomplete. Stable behavior remains conservative and CPU/zscale remains the reference path.

## Physical acceptance status

**PENDING.** GitHub-hosted runners can validate policy selection, cache exactness, fail-closed behavior, rollback, Windows/Linux portability and tests. They cannot prove RTX 4070 NVDEC throughput, 8K/120 sustained behavior, laptop power sharing, thermals, or real NVMe interaction.

The representative physical runs still required are:

- short 720p/24 source → 8K/120 music project;
- 1080p source → 4K60;
- before/after stage wall time and throughput;
- GPU/CPU/RAM/VRAM/disk utilization and thermals;
- image/temporal/color/audio/integrity metrics.

No global H5 physical PASS should be recorded until those real-machine results exist.
