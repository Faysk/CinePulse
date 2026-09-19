from __future__ import annotations

from cinepulse.gpu_failure import looks_like_gpu_runtime_failure


def test_gpu_failure_classifier_accepts_driver_and_vram_signals() -> None:
    for message in (
        "CUDA error: out of memory",
        "h264_cuvid failed to initialize",
        "Failed to initialise NVENC",
        "VK_ERROR_OUT_OF_DEVICE_MEMORY",
        "Cannot load nvcuda.dll",
        "NVDEC hardware accelerator failed",
    ):
        assert looks_like_gpu_runtime_failure(message), message


def test_gpu_failure_classifier_rejects_unrelated_io_and_mux_failures() -> None:
    for message in (
        "No space left on device while writing output.mp4",
        "Permission denied opening destination file",
        "Invalid data found when processing input",
        "Broken pipe while writing audio mux",
        "Output path does not exist",
    ):
        assert not looks_like_gpu_runtime_failure(message), message
