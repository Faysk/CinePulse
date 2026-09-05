from __future__ import annotations

"""Evidence-gated Preview Composer export dispatcher.

The deterministic NumPy/RGBA exporter remains the correctness path. CUDA is
attempted only for an exact H6-approved ordered stack. Any production fast-path
failure invalidates that exact evidence record and retries once through the CPU
reference; cancellation never triggers a surprise retry.
"""

from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile
import time
from collections.abc import Callable

from .composer_export import ComposerExportRequest, ComposerExportResult, export_composer_reference
from .composer_gpu_route import (
    ComposerGpuRoute,
    default_compositor_evidence_path,
    select_gpu_export_route,
)
from .gpu_compositor import (
    GpuCompositorCapabilities,
    GpuCompositorStore,
    OverlayLayer,
    build_cuda_overlay_stack_filter,
    detect_gpu_compositor_capabilities,
)
from .hardware import HardwareProfile, detect_hardware
from .paths import PATHS
from .process_control import popen_group_kwargs, terminate_process_tree
from .safe_output import AtomicOutput


@dataclass(frozen=True)
class ComposerAutoExportResult:
    output: Path
    frames: int
    backend: str
    gpu_attempted: bool
    gpu_failure: str | None = None


def _layer_input_args(layer: OverlayLayer) -> list[str]:
    args: list[str] = []
    if layer.loop and layer.kind in {"gif", "apng", "webp", "video-alpha"}:
        args += ["-stream_loop", "-1"]
    return args + ["-i", str(layer.source)]


def _gpu_visual_command(request: ComposerExportRequest, route: ComposerGpuRoute, target: Path) -> list[str]:
    if not route.use_gpu or not route.layers:
        raise ValueError("H6 GPU visual command requires an approved non-empty route")
    p = request.profile
    graph = build_cuda_overlay_stack_filter(
        route.layers,
        canvas_width=p.width,
        canvas_height=p.height,
    ) + ";[vout]format=rgba[vfinal]"
    command = [str(request.ffmpeg), "-y", "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(request.source)]
    for layer in route.layers:
        command += _layer_input_args(layer)
    command += [
        "-filter_complex", graph,
        "-map", "[vfinal]", "-an", "-sn",
        "-t", f"{p.duration:.6f}",
        "-c:v", "ffv1", "-level", "3", "-pix_fmt", "gbrap",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "pc",
        str(target),
    ]
    return command


def _mux_command(request: ComposerExportRequest, visual: Path, target: Path) -> list[str]:
    audio = request.output_audio or request.source
    return [
        str(request.ffmpeg), "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
        "-i", str(visual), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0?",
        "-c:v", "copy", "-c:a", "copy",
        "-t", f"{request.profile.duration:.6f}",
        str(target),
    ]


def _run_cancellable(
    command: list[str],
    *,
    cancelled: Callable[[], bool],
    log: Callable[[str], None],
    stderr_path: Path,
) -> None:
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
                    raise InterruptedError("composer GPU export cancelled")
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
        raise RuntimeError(details or f"composer GPU process exited with {code}")


def _export_gpu(
    request: ComposerExportRequest,
    route: ComposerGpuRoute,
    *,
    cancelled: Callable[[], bool],
    log: Callable[[str], None],
) -> ComposerExportResult:
    output = Path(request.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frames = max(1, round(request.profile.duration * request.profile.fps))
    with tempfile.TemporaryDirectory(prefix="cinepulse-composer-gpu-", dir=output.parent) as temporary:
        root = Path(temporary)
        visual = root / "composer-gpu-visual.mkv"
        gpu_log = root / "gpu-visual.stderr.log"
        mux_log = root / "gpu-mux.stderr.log"
        log(f"H6 Composer: executando stack CUDA aprovado com {len(route.layers)} camada(s).")
        _run_cancellable(
            _gpu_visual_command(request, route, visual),
            cancelled=cancelled,
            log=log,
            stderr_path=gpu_log,
        )
        if cancelled():
            raise InterruptedError("composer GPU export cancelled")
        if not visual.is_file() or visual.stat().st_size <= 0:
            raise RuntimeError("composer GPU visual master was not produced")
        with AtomicOutput(output) as atomic:
            _run_cancellable(
                _mux_command(request, visual, atomic.partial),
                cancelled=cancelled,
                log=log,
                stderr_path=mux_log,
            )
            if cancelled():
                raise InterruptedError("composer GPU export cancelled")
            atomic.commit()
    return ComposerExportResult(output, frames)


def export_composer_auto(
    request: ComposerExportRequest,
    *,
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[int, int], None] | None = None,
    log: Callable[[str], None] | None = None,
    envelopes=None,
    hardware: HardwareProfile | None = None,
    capabilities: GpuCompositorCapabilities | None = None,
    store: GpuCompositorStore | None = None,
) -> ComposerAutoExportResult:
    """Use exact proven H6 acceleration or the deterministic CPU reference."""
    cancel = cancelled or (lambda: False)
    logger = log or (lambda _message: None)
    hw = hardware or detect_hardware()
    caps = capabilities or detect_gpu_compositor_capabilities(str(request.ffmpeg))
    evidence_store = store or GpuCompositorStore(default_compositor_evidence_path(PATHS.cache))
    route = select_gpu_export_route(
        request.state,
        hardware=hw,
        caps=caps,
        store=evidence_store,
        width=request.profile.width,
        height=request.profile.height,
        fps=request.profile.fps,
        pixel_format=request.profile.pixel_format,
        primaries=request.profile.primaries,
        transfer=request.profile.transfer,
        matrix=request.profile.matrix,
        color_range=request.profile.color_range,
    )
    if route.use_gpu:
        try:
            result = _export_gpu(request, route, cancelled=cancel, log=logger)
            if progress:
                progress(result.frames, result.frames)
            return ComposerAutoExportResult(result.output, result.frames, "cuda", True)
        except InterruptedError:
            raise
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            if route.key is not None:
                evidence_store.invalidate(route.key)
            logger(f"H6 Composer: fast-path CUDA invalidado após falha de produção; rollback CPU. {reason}")
            if cancel():
                raise InterruptedError("composer export cancelled")
            result = export_composer_reference(
                request,
                cancelled=cancel,
                progress=progress,
                log=logger,
                envelopes=envelopes,
            )
            return ComposerAutoExportResult(result.output, result.frames, "cpu-reference", True, reason)

    logger(f"H6 Composer: CPU reference preservado — {route.reason}.")
    result = export_composer_reference(
        request,
        cancelled=cancel,
        progress=progress,
        log=logger,
        envelopes=envelopes,
    )
    return ComposerAutoExportResult(result.output, result.frames, "cpu-reference", False)
