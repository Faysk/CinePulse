from __future__ import annotations

"""Evidence-gated Preview Composer export dispatcher.

The deterministic NumPy/RGBA exporter remains the correctness path. CUDA is
attempted only for an exact H6-approved ordered stack. Any production fast-path
failure invalidates that exact evidence record and retries once through the CPU
reference; cancellation never triggers a surprise retry.
"""

from dataclasses import dataclass, replace
from pathlib import Path
import re
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
    GpuCompositorEvidence,
    GpuCompositorStore,
    OverlayLayer,
    build_cuda_overlay_stack_filter,
    compositor_vram_floor_mb,
    detect_gpu_compositor_capabilities,
)
from .gpu_failure import looks_like_gpu_runtime_failure
from .hardware import HardwareProfile, detect_hardware
from .paths import PATHS
from .pipeline_runtime import vram_free_mb
from .process_control import popen_group_kwargs, terminate_process_tree
from .safe_output import AtomicOutput
from .verification import VerifyExpectation, quick_verify


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


def _has_audio_stream(ffprobe: str, path: str | Path) -> bool:
    try:
        result = subprocess.run(
            [
                str(ffprobe), "-v", "error", "-select_streams", "a:0",
                "-show_entries", "stream=index", "-of", "csv=p=0", str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and bool((result.stdout or "").strip())


def _verify_gpu_product(request: ComposerExportRequest, path: Path, *, expect_audio: bool) -> None:
    p = request.profile
    verification = quick_verify(
        str(request.ffprobe),
        path,
        VerifyExpectation(
            width=p.width,
            height=p.height,
            fps=p.fps,
            duration=p.duration,
            expect_audio=expect_audio,
            video_codec="ffv1",
            frame_tolerance=1,
            duration_tolerance=0.12,
            sync_tolerance=0.12,
        ),
    )
    if not verification.passed:
        detail = "; ".join(issue.message for issue in verification.errors)
        raise RuntimeError("composer GPU verification failed: " + (detail or "unknown integrity error"))


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
    verify_product: bool = True,
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
        if verify_product:
            _verify_gpu_product(request, visual, expect_audio=False)
        audio_source = request.output_audio or request.source
        expected_audio = _has_audio_stream(str(request.ffprobe), audio_source)

        atomic = AtomicOutput.for_path(output)
        atomic.prepare()
        try:
            _run_cancellable(
                _mux_command(request, visual, atomic.partial),
                cancelled=cancelled,
                log=log,
                stderr_path=mux_log,
            )
            if cancelled():
                raise InterruptedError("composer GPU export cancelled")
            if verify_product:
                _verify_gpu_product(request, atomic.partial, expect_audio=expected_audio)
            atomic.commit()
        finally:
            atomic.discard()
    return ComposerExportResult(output, frames)


_PSNR_RE = re.compile(r"average:([0-9]+(?:\.[0-9]+)?|inf)", re.IGNORECASE)
_SSIM_RE = re.compile(r"All:([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)


def _comparison_metric(
    request: ComposerExportRequest,
    baseline: Path,
    candidate: Path,
    name: str,
    *,
    cancelled: Callable[[], bool],
    log: Callable[[str], None],
    scratch: Path,
) -> float:
    metric_log = scratch / f"{name}.stderr.log"
    command = [
        str(request.ffmpeg), "-hide_banner", "-nostdin",
        "-i", str(baseline), "-i", str(candidate),
        "-lavfi", f"[0:v:0][1:v:0]{name}",
        "-an", "-f", "null", "-",
    ]
    _run_cancellable(
        command,
        cancelled=cancelled,
        log=log,
        stderr_path=metric_log,
    )
    text = metric_log.read_text(encoding="utf-8", errors="replace")
    match = _PSNR_RE.search(text) if name == "psnr" else _SSIM_RE.search(text)
    if not match:
        raise RuntimeError(f"Composer H6 benchmark could not parse {name}")
    raw = match.group(1).lower()
    return 999.0 if raw == "inf" else float(raw)


def _learn_exact_gpu_route(
    request: ComposerExportRequest,
    route: ComposerGpuRoute,
    store: GpuCompositorStore,
    *,
    cancelled: Callable[[], bool],
    log: Callable[[str], None],
    envelopes,
) -> bool:
    """Benchmark one exact user stack before granting H6 runtime permission."""
    if route.key is None or not route.layers:
        return False
    duration = min(2.0, max(0.10, float(request.profile.duration)))
    profile = replace(request.profile, duration=duration)
    output_parent = Path(request.output).parent
    output_parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="cinepulse-h6-learn-", dir=output_parent) as temporary:
        root = Path(temporary)
        baseline = root / "baseline.mkv"
        candidate = root / "candidate.mkv"
        baseline_request = replace(request, output=baseline, profile=profile)
        candidate_request = replace(request, output=candidate, profile=profile)
        approved_route = ComposerGpuRoute(
            True,
            "bounded on-demand H6 benchmark",
            route.layer,
            route.key,
            route.layers,
        )

        log(
            f"H6 Composer: sem evidência para este stack exato; "
            f"benchmark físico local de {duration:.2f}s antes do export completo."
        )
        started = time.perf_counter()
        baseline_result = export_composer_reference(
            baseline_request,
            cancelled=cancelled,
            progress=None,
            log=log,
            envelopes=envelopes,
        )
        baseline_seconds = max(0.000001, time.perf_counter() - started)
        if cancelled():
            raise InterruptedError("composer H6 learning cancelled")

        started = time.perf_counter()
        candidate_result = _export_gpu(
            candidate_request,
            approved_route,
            cancelled=cancelled,
            log=log,
            verify_product=False,
        )
        candidate_seconds = max(0.000001, time.perf_counter() - started)

        audio_source = request.output_audio or request.source
        expect_audio = _has_audio_stream(str(request.ffprobe), audio_source)
        _verify_gpu_product(baseline_request, baseline, expect_audio=expect_audio)
        _verify_gpu_product(candidate_request, candidate, expect_audio=expect_audio)
        psnr = _comparison_metric(
            candidate_request, baseline, candidate, "psnr",
            cancelled=cancelled, log=log, scratch=root,
        )
        ssim = _comparison_metric(
            candidate_request, baseline, candidate, "ssim",
            cancelled=cancelled, log=log, scratch=root,
        )
        expected_frames = max(1, round(duration * profile.fps))
        evidence = GpuCompositorEvidence(
            baseline_seconds=baseline_seconds,
            candidate_seconds=candidate_seconds,
            psnr_db=psnr,
            ssim=ssim,
            frame_count_ok=(
                baseline_result.frames == expected_frames
                and candidate_result.frames == expected_frames
            ),
            metadata_ok=True,
            alpha_contract_ok=psnr >= 80.0 and ssim >= 0.999999,
            audio_sync_ok=True,
        )
        recorded = store.record(route.key, evidence)
        log(
            "H6 Composer: benchmark físico local "
            f"{'aprovado' if recorded else 'rejeitado'} "
            f"(speedup={evidence.speedup:.2f}x, PSNR={psnr:.2f}, SSIM={ssim:.6f})."
        )
        return recorded


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
        base_is_still=request.profile.still_image,
    )
    if (
        not route.use_gpu
        and route.key is not None
        and route.layers
        and "evidence is absent or stale" in route.reason
    ):
        learn_floor = compositor_vram_floor_mb(
            request.profile.width,
            request.profile.height,
            len(route.layers),
        )
        learn_vram = vram_free_mb(0)
        if learn_vram is not None and learn_vram >= learn_floor:
            try:
                if _learn_exact_gpu_route(
                    request,
                    route,
                    evidence_store,
                    cancelled=cancel,
                    log=logger,
                    envelopes=envelopes,
                ):
                    route = ComposerGpuRoute(
                        True,
                        "exact H6 evidence learned on this machine",
                        route.layer,
                        route.key,
                        route.layers,
                    )
            except InterruptedError:
                raise
            except Exception as exc:
                logger(
                    "H6 Composer: benchmark físico local falhou; CPU reference preservado. "
                    f"{type(exc).__name__}: {exc}"
                )

    if route.use_gpu:
        vram_floor = compositor_vram_floor_mb(
            request.profile.width,
            request.profile.height,
            len(route.layers),
        )
        live_vram = vram_free_mb(0)
        if live_vram is None or live_vram < vram_floor:
            logger(
                "H6 Composer: evidência CUDA preservada, mas VRAM livre atual "
                f"({live_vram if live_vram is not None else 'n/a'} MiB) não cobre "
                f"o piso do stack ({vram_floor:.0f} MiB); CPU reference neste export."
            )
            result = export_composer_reference(
                request,
                cancelled=cancel,
                progress=progress,
                log=logger,
                envelopes=envelopes,
            )
            return ComposerAutoExportResult(
                result.output,
                result.frames,
                "cpu-reference",
                False,
                "insufficient-live-vram",
            )
        try:
            result = _export_gpu(request, route, cancelled=cancel, log=logger)
            if progress:
                progress(result.frames, result.frames)
            return ComposerAutoExportResult(result.output, result.frames, "cuda", True)
        except InterruptedError:
            raise
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            current_vram = vram_free_mb(0)
            integrity_failure = "composer gpu verification failed" in str(exc).lower()
            gpu_failure = looks_like_gpu_runtime_failure(exc)
            enough_headroom = current_vram is not None and current_vram >= vram_floor
            should_invalidate = integrity_failure or (gpu_failure and enough_headroom)
            if route.key is not None and should_invalidate:
                evidence_store.invalidate(route.key)
                evidence_text = "evidência exata invalidada"
            else:
                evidence_text = "evidência preservada"
            logger(
                "H6 Composer: fast-path CUDA falhou; "
                f"{evidence_text}. rollback CPU. {reason}"
            )
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
