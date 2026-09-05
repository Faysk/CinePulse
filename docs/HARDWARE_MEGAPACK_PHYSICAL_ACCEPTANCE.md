# Hardware Utilization MegaPack — Physical Acceptance

This checklist is the **only remaining authority for physical-performance claims** after software CI is green. GitHub-hosted CI can validate contracts, fallbacks, integrity and portability; it cannot prove RTX utilization, laptop power sharing, sustained thermals, NVMe behavior, CUDA/Vulkan throughput, 8K/120 or TensorRT performance.

No item below may be marked PASS from code review, mocked tests, capability detection, or a hosted runner. Record the exact branch SHA, GPU name, VRAM, NVIDIA driver, FFmpeg fingerprint, model IDs and generated evidence files for every run.

## Required representative scenarios

Run the complete end-to-end benchmark matrix for both:

1. **Heavy music scenario:** short 1280×720 / 24 fps clip → 7680×4320 / 120 fps music project.
2. **Production sanity scenario:** 1920×1080 source → 3840×2160 / 60 fps.

For each scenario retain the baseline and candidate wall time, per-stage throughput/fps, GPU utilization/VRAM/power/clock/temperature, CPU total/per-core, RAM, disk throughput, scratch volume, quality metrics, output verification and render-history telemetry. A faster result with worse quality or weaker integrity is a FAIL.

## H0/H1 — telemetry and CPU scheduling

Use `scripts/hardware_benchmark.py` with representative project inputs and preserve the generated telemetry/report. Verify that render history contains stage events and summaries for GPU, CPU, RAM, disk and wall time. Compare Balanced, Dedicated and Overnight policies rather than assuming the maximum thread count wins. On laptops, reject a higher CPU setting when it reduces end-to-end throughput through thermal or GPU power contention.

PASS requires complete telemetry coverage, deterministic output verification, no audio drift, and a repeatable end-to-end improvement or neutral result without quality loss.

## H2 — Real-ESRGAN NCNN tuning

Run `scripts/realesrgan_autotune.py` on a short representative PNG sequence for every source geometry/model that will be authorized. The generated H2 cache is keyed by GPU, VRAM, driver, model, source geometry and scale.

A candidate may replace the conservative policy only when the script accepts frame integrity/quality and no OOM occurred. Exercise one intentional invalid/over-pressure candidate and verify rollback/invalidation. Never copy a cache file between different drivers or GPUs and call it evidence.

## H3 — RIFE NCNN tuning

Run `scripts/rife_benchmark.py` for 1080p/4K/UHD geometries used by the project. The conservative baseline must pass first; otherwise stop. Preserve UHD mode for UHD tests.

PASS requires exact frame count, complete PNGs, consistent dimensions, no machine-black output, quality parity against the baseline, no OOM, and the exact hardware/driver/model/resolution cache record. Exercise runtime invalidation/downshift once. No global 8K/120 PASS exists until the full heavy scenario succeeds end-to-end.

## H4 — bounded overlap and adaptive scratch pipeline

Run the two representative scenarios once with conservative sequential scheduling and once with the H4 benchmark-proven overlap envelope. Preserve the generated pipeline-budget/headroom evidence and scratch probe for each run.

PASS requires bounded in-flight work (never more than the configured three-workset ceiling), no unbounded RAM/VRAM/scratch growth, exact output parity, successful cancellation/recovery, and a real end-to-end benefit. Repeat on the intended NVMe scratch volume and verify that slow/saturated scratch disables overlap instead of increasing buffering. Exercise memory/VRAM pressure once and confirm future chunks only downshift; the same render must never auto-ramp above its initial proven envelope.

## H5 — NVDEC / CUDA-resident media path

First run `scripts/gpu_media_benchmark.py` for decode/scale candidates. Then run `scripts/gpu_resident_encode_benchmark.py` for the complete resident decode/scale/NVENC delivery route.

Capability detection alone is never permission. PASS requires the exact source codec/geometry/pixel format/color metadata, target geometry, GPU, driver, FFmpeg build and encoder contract to match the accepted record. Validate non-zero seek alignment, frame count, metadata/color/range, audio sync, decoded PSNR/SSIM, valid bitstream and speedup. Test runtime failure once and confirm the exact record is invalidated and the untouched CPU/zscale baseline completes successfully.

HDR, unknown color metadata, crop/pad/aspect changes or any unproven conversion remain on the CPU/zscale path.

## H6 — GPU compositor

Run `scripts/gpu_compositor_benchmark.py` for every compositor contract intended to use GPU acceleration. The CPU/NumPy compositor is the correctness reference.

PASS requires exact output dimensions/frame count/alpha contract, audio sync where present, PSNR/SSIM parity and a real speedup. Test PNG plus at least one animated/alpha source relevant to the approved envelope. Unsupported dynamic transforms, visualizers or blend modes must remain on the CPU reference path until independently proven.

The Overlay Composer / Music Visualizer Preview feature itself must still work through the CPU reference route when no GPU evidence exists. For audio-reactive acceptance, exercise the default master source plus at least one explicitly configured stem binding (for example vocals or drums), save/reload the Preview project, and verify that the same source mapping survives the round trip. Master/stem source mappings are analysis inputs for visual reactivity; they must not silently replace the final soundtrack. Verify that normal export preserves the source audio and duration, while any explicit future output-audio override remains opt-in and independently sync-checked. Missing optional stems must fall back to master exactly as the analysis contract states.

## H7 — optional Preview TensorRT

TensorRT is **optional and Preview-only**. CinePulse does not install or bundle TensorRT through the Stable MIT distribution. The external runner must implement `cinepulse-tensorrt-preview-v1` and report its real runner version, TensorRT version and license metadata.

Before running `scripts/tensorrt_preview_benchmark.py`, create an accepted H2/H3 NCNN record on the same GPU/driver/model/source geometry. Pass that cache with `--ncnn-cache` and the exact model ID with `--ncnn-model-id`. H7 refuses arbitrary PNG folders as an “approved baseline”; the TensorRT evidence is bound to the fingerprint of the exact proven NCNN policy.

PASS requires at least the script's quality/integrity/temporal thresholds and speedup floor. An NCNN tuning invalidation, driver change, TensorRT runtime change, runner change or baseline-policy change invalidates TensorRT permission. Stable fallback remains NCNN Vulkan.

## H8 — sustained Overnight mode

Run `scripts/overnight_acceptance.py` against telemetry from a sustained representative render; use the script's default minimum duration unless investigating a failure. For the final heavy-scenario acceptance, prefer a run long enough to expose steady-state laptop thermals and NVMe behavior rather than a short burst.

Verify that the adaptive runtime reacts to sustained GPU temperature/power/clock pressure, RAM pressure and disk saturation by reducing CPU budget, chunk size and overlap depth. Confirm no Realtime process priority, `powercfg`, GPU power-limit mutation, NVIDIA global-setting mutation or other silent system-wide change occurred.

PASS requires stable completion, adequate telemetry coverage, output quality/integrity PASS, safe sustained temperatures, no unbounded scratch/RAM growth, no repeated OOM/fallback loop and no throughput collapse after thermal steady state.

## Final end-to-end gate

For each of the two representative scenarios, compare the final Hardware MegaPack result against the conservative baseline and archive:

- exact Git SHA and application version;
- complete render-history record and `hardware-telemetry.json`;
- wall clock and per-stage throughput;
- GPU/CPU/RAM/NVMe utilization and sustained thermal/power data;
- frame count, duration, audio sync and metadata/color/HDR verification;
- PSNR/SSIM/VMAF evidence where applicable;
- all tuning/cache records that were actually consumed;
- cancellation and forced-fast-path-failure recovery evidence.

Only after both representative scenarios pass may hardware-specific performance be described as physically accepted. 8K/120, TensorRT, CUDA compositor and RTX utilization remain **PENDING** until their corresponding real-hardware evidence exists.

## Merge policy

Software CI green is necessary but not sufficient for physical acceptance. Keep the Preview PR Draft and do not merge experimental acceleration into Stable while any required physical gate above remains pending. A failed candidate is evidence to keep or restore the conservative path, not a reason to lower the quality threshold.
