from __future__ import annotations

"""Runtime execution for an optional, externally installed H7 TensorRT backend.

This module is Preview-only plumbing. It never downloads, installs or bundles
TensorRT, engines or third-party runners. The caller supplies an NCNN fallback;
TensorRT is attempted only with exact physical evidence. A production failure
invalidates only that evidence key and immediately delegates to NCNN.
"""

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable

from .hardware import HardwareProfile
from .process_control import popen_group_kwargs, terminate_process_tree
from .rife_safe_runner import validate_png_sequence
from .tensorrt_preview import (
    BackendModel,
    Precision,
    TensorRtExternalBackend,
    TensorRtKey,
    TensorRtPreviewStore,
    build_external_command,
    fingerprint_model_path,
)


@dataclass(frozen=True)
class TensorRtRuntimeRequest:
    backend: TensorRtExternalBackend
    store: TensorRtPreviewStore
    hardware: HardwareProfile
    model: BackendModel
    model_path: Path
    input_path: Path
    output_path: Path
    width: int
    height: int
    precision: Precision
    ncnn_baseline_fingerprint: str
    expected_frames: int

    def key(self) -> TensorRtKey:
        return TensorRtKey(
            gpu_name=self.hardware.gpu or "unknown-gpu",
            driver=self.hardware.driver or "unknown-driver",
            tensorrt_version=self.backend.tensorrt_version,
            backend_fingerprint=self.backend.fingerprint,
            model=self.model,
            model_fingerprint=fingerprint_model_path(self.model_path),
            ncnn_baseline_fingerprint=self.ncnn_baseline_fingerprint,
            width=max(1, int(self.width)),
            height=max(1, int(self.height)),
            precision=self.precision,
        )


@dataclass(frozen=True)
class TensorRtRuntimeResult:
    backend: str
    output_path: Path
    tensorrt_attempted: bool
    failure: str | None = None


def _run_external(
    request: TensorRtRuntimeRequest,
    key: TensorRtKey,
    *,
    cancelled: Callable[[], bool],
    log: Callable[[str], None],
) -> None:
    target = Path(request.output_path)
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cinepulse-h7-runtime-", dir=parent) as temporary:
        staging = Path(temporary) / "output"
        staging.mkdir()
        stderr_path = Path(temporary) / "runner.stderr.log"
        command = build_external_command(
            request.backend,
            model=request.model,
            model_path=request.model_path,
            input_path=request.input_path,
            output_path=staging,
            width=request.width,
            height=request.height,
            precision=request.precision,
        )
        with stderr_path.open("wb") as stderr_handle:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=stderr_handle,
                **popen_group_kwargs(),
            )
            try:
                while process.poll() is None:
                    if cancelled():
                        terminate_process_tree(process, log)
                        raise InterruptedError("TensorRT Preview execution cancelled")
                    time.sleep(0.05)
                code = int(process.returncode or 0)
            finally:
                if process.poll() is None:
                    terminate_process_tree(process, log)
        if code:
            try:
                details = stderr_path.read_text(encoding="utf-8", errors="replace")[-4000:].strip()
            except OSError:
                details = ""
            raise RuntimeError(details or f"TensorRT external runner exited with {code}")
        frames = validate_png_sequence(staging, max(1, int(request.expected_frames)))
        if len(frames) != max(1, int(request.expected_frames)):
            raise RuntimeError("TensorRT output frame-count validation failed")
        if cancelled():
            raise InterruptedError("TensorRT Preview execution cancelled")

        backup: Path | None = None
        if target.exists():
            backup = Path(temporary) / "previous-output"
            shutil.move(str(target), str(backup))
        try:
            shutil.move(str(staging), str(target))
        except Exception:
            if backup is not None and backup.exists() and not target.exists():
                shutil.move(str(backup), str(target))
            raise


def run_tensorrt_preview_or_fallback(
    request: TensorRtRuntimeRequest,
    *,
    fallback: Callable[[], Path],
    cancelled: Callable[[], bool] | None = None,
    log: Callable[[str], None] | None = None,
) -> TensorRtRuntimeResult:
    """Run exact approved TensorRT evidence or delegate to NCNN.

    The fallback callable is owned by the Preview orchestration layer so this
    module cannot weaken or duplicate the established H2/H3 NCNN contracts.
    """
    cancel = cancelled or (lambda: False)
    logger = log or (lambda _message: None)
    key = request.key()
    if not request.hardware.gpu or not request.store.approved(key, request.backend):
        logger("H7 TensorRT: evidência exata ausente/stale; preservando fallback NCNN Vulkan.")
        return TensorRtRuntimeResult("ncnn", Path(fallback()), False)

    try:
        logger(
            f"H7 TensorRT Preview: executando backend externo aprovado {request.backend.version} "
            f"({request.precision}, {request.width}x{request.height})."
        )
        _run_external(request, key, cancelled=cancel, log=logger)
        return TensorRtRuntimeResult("tensorrt-preview", Path(request.output_path), True)
    except InterruptedError:
        raise
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        request.store.invalidate(key)
        logger(f"H7 TensorRT: evidência invalidada após falha de produção; rollback NCNN. {reason}")
        if cancel():
            raise InterruptedError("TensorRT Preview execution cancelled")
        return TensorRtRuntimeResult("ncnn", Path(fallback()), True, reason)
