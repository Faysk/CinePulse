# Hardware Utilization MegaPack — Phase 3

Phase 3 closes the loop between the observational telemetry from Phase 1 and the bounded resource/tuning contracts from Phase 2.

The goal is not to force every component to 100% utilization. The goal is to keep the expensive neural stages fed without trading away image integrity, temporal correctness, color contracts, cancellation/recovery behavior, or machine stability.

## What changes

- Every completed render now receives a hardware bottleneck analysis derived from its persisted telemetry.
- Classification is stage-aware. CPU-only VFX/audio/verification work is never labelled `gpu-starved` just because the discrete GPU is idle.
- Neural stages can be classified as `gpu-starved`, `gpu-saturated`, `io-suspected`, `memory-pressure`, `thermal-pressure`, `cpu-bound`, `balanced`, or `unknown`.
- Short/insufficient telemetry fails closed as `unknown` instead of inventing a performance diagnosis.
- A Real-ESRGAN tuning record can only affect runtime when it matches the exact GPU name, VRAM envelope, driver, model, source geometry and scale and was previously recorded with integrity-approved output.
- Proven Real-ESRGAN policies may change tile size and NCNN `load:process:save` concurrency, which is the evidence-gated overlap mechanism for keeping the GPU fed.
- If a proven policy fails during a real render, CinePulse invalidates that exact record and retries the affected chunk once with the conservative 256 / 2:2:2 fallback. It does not keep reusing a policy that failed in production.
- Without a proven record, the existing Phase 2 profile-aware policy remains in place; Phase 3 does not silently invent a more aggressive GPU policy from heuristic telemetry alone.

## Why this is safer than blindly adding workers

Low GPU utilization can mean several different things: slow frame extraction, scratch/NVMe pressure, CPU saturation, a small workload, memory pressure, thermal throttling, or simply a stage that should not use the GPU. Phase 3 separates those cases before recommending a tuning direction.

The advisor is intentionally a diagnostic heuristic, not a benchmark result. It can say that a neural stage looks starved or thermally constrained, but only physical benchmark evidence can promote a faster concurrency/tile policy.

## Real-ESRGAN evidence loop

`realesrgan_tuning.py` stores exact hardware/driver/source-specific winners. Candidate generation always includes the conservative 256 / 2:2:2 policy and can expose larger tiles or wider load/save concurrency as benchmark candidates.

The runtime contract is:

1. exact integrity-approved record exists -> use it;
2. record fails in a real render -> invalidate it and retry 256 / 2:2:2 once;
3. no exact record -> keep the normal Phase 2 policy;
4. OOM/corrupt/incomplete benchmark samples never become winners.

## Physical acceptance

GitHub-hosted CI can prove the classifier, persistence, fallback routing and Stable/Preview contracts. It cannot prove RTX 4070 utilization, laptop power sharing, sustained temperature, 8K/12K/120 throughput, or NVMe behavior.

Those remain **PENDING physical acceptance** until telemetry from the real Windows GPU runner/notebook is available. No 8K/12K/120 performance PASS is inferred from software CI.
