from __future__ import annotations


_GPU_RUNTIME_TOKENS = (
    "cuda",
    "cuvid",
    "nvenc",
    "nvdec",
    "nvidia",
    "vulkan",
    "vk_error",
    "out of memory",
    "device memory",
    "failed to allocate",
    "no capable devices",
    "cannot load nvcuda",
    "failed to initialise nvenc",
    "failed to initialize nvenc",
    "hardware accelerator",
    "hwaccel",
)


def looks_like_gpu_runtime_failure(reason: BaseException | str) -> bool:
    """Return True only for failures that plausibly invalidate GPU evidence.

    Callers still fail closed to their CPU/conservative path for every runtime
    exception. This classifier only decides whether an already-proven hardware
    evidence record should be deleted as stale/unsafe.
    """
    text = str(reason or "").lower()
    return any(token in text for token in _GPU_RUNTIME_TOKENS)
