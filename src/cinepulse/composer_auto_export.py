from __future__ import annotations

"""Evidence-gated Preview Composer export dispatcher.

The deterministic NumPy/RGBA exporter remains the correctness path. CUDA is
attempted only for an exact H6-approved ordered stack. Any production fast-path
failure invalidates that exact evidence record and retries once through the CPU
reference; cancellation never triggers a surprise retry.
"""

from dataclasses import dataclass, replace
from pathlib import Path
import json
import re
import subprocess
import tempfile
import time
from collections.abc import Callable

from .composer_export import (
    ComposerExportRequest,
    ComposerExportResult,
    _mux_command,
    composer_frame_count,
    composer_has_audio_stream as _has_audio_stream,
    export_composer_reference,
    verify_composer_product as _verify_gpu_product,
)
from .composer_gpu_route import (
    ComposerGpuRoute,
    build_compositor_stack_key,
    default_compositor_evidence_path,
    select_gpu_export_route,
)
from .gpu_compositor import (
    GpuCompositorCapabilities,
    GpuCompositorEvidence,
    GpuCompositorStore,
    OverlayLayer,
    build_cuda_overlay_stack_filter,
    detect_gpu_compositor_capabilities,
)
from .gpu_failure import looks_like_gpu_runtime_failure
from .gpu_media import detect_gpu_media_capabilities
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
        base_resident=bool(route.base_decoder),
    ) + ";[vout]format=rgba[vfinal]"
    command = [str(request.ffmpeg), "-y", "-hide_banner", "-nostdin", "-loglevel", "error"]
    gpu_index = route.key.gpu_index if route.key is not None else 0
    command += [
        "-init_hw_device", f"cuda=cinepulse_gpu:{gpu_index}",
        "-filter_hw_device", "cinepulse_gpu",
    ]
    if route.base_decoder:
        command += [
            "-hwaccel", "cuda",
            "-hwaccel_device", str(gpu_index),
            "-hwaccel_output_format", "cuda",
            "-c:v", route.base_decoder,
        ]
    command += ["-i", str(request.source)]
    for layer in route.layers:
        command += _layer_input_args(layer)
    command += [
        "-filter_complex", graph,
        "-map", "[vfinal]", "-an", "-sn",
        "-frames:v", str(composer_frame_count(request)),
        "-c:v", "ffv1", "-level", "3", "-pix_fmt", "gbrap",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "pc",
        str(target),
    ]
    return command


def _probe_source_codec(ffprobe: str, path: str | Path) -> str:
    try:
        result = subprocess.run(
            [
                str(ffprobe), "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path),
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
        return ""
    return (result.stdout or "").strip().lower() if result.returncode == 0 else ""


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


def _probe_benchmark_contract(ffprobe: str, path: Path) -> dict[str, object]:
    try:
        result = subprocess.run(
            [
                str(ffprobe), "-v", "error", "-count_frames",
                "-show_entries",
                "stream=codec_type,width,height,pix_fmt,color_range,color_space,color_transfer,color_primaries,avg_frame_rate,r_frame_rate,nb_read_frames,nb_frames:format=duration",
                "-of", "json", str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Composer H6 ffprobe failed: {exc}") from exc
    if result.returncode:
        raise RuntimeError((result.stderr or "")[-2000:] or "Composer H6 ffprobe failed")
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("Composer H6 ffprobe returned invalid JSON") from exc
    streams = payload.get("streams") if isinstance(payload, dict) else None
    rows = streams if isinstance(streams, list) else []
    video = next((row for row in rows if isinstance(row, dict) and row.get("codec_type") == "video"), {})
    audio = next((row for row in rows if isinstance(row, dict) and row.get("codec_type") == "audio"), None)

    frame_count = None
    for field in ("nb_read_frames", "nb_frames"):
        raw = video.get(field) if isinstance(video, dict) else None
        if raw not in (None, "", "N/A"):
            try:
                frame_count = int(raw)
                break
            except (TypeError, ValueError):
                pass
    signature = tuple(
        video.get(field) if isinstance(video, dict) else None
        for field in (
            "width", "height", "pix_fmt", "color_range", "color_space",
            "color_transfer", "color_primaries", "avg_frame_rate", "r_frame_rate",
        )
    )
    try:
        duration = float(payload.get("format", {}).get("duration"))
    except (AttributeError, TypeError, ValueError):
        duration = None
    return {
        "frame_count": frame_count,
        "signature": signature,
        "duration": duration,
        "has_audio": audio is not None,
    }


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
            route.base_decoder,
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
        baseline_contract = _probe_benchmark_contract(str(request.ffprobe), baseline)
        candidate_contract = _probe_benchmark_contract(str(request.ffprobe), candidate)
        baseline_duration = baseline_contract["duration"]
        candidate_duration = candidate_contract["duration"]
        frame_count_ok = bool(
            baseline_contract["frame_count"] is not None
            and baseline_contract["frame_count"] == candidate_contract["frame_count"]
            and baseline_result.frames == candidate_result.frames
        )
        metadata_ok = baseline_contract["signature"] == candidate_contract["signature"]
        audio_sync_ok = bool(
            baseline_contract["has_audio"] == candidate_contract["has_audio"]
            and baseline_duration is not None
            and candidate_duration is not None
            and abs(float(baseline_duration) - float(candidate_duration)) <= 0.020
        )
        evidence = GpuCompositorEvidence(
            baseline_seconds=baseline_seconds,
            candidate_seconds=candidate_seconds,
            psnr_db=psnr,
            ssim=ssim,
            frame_count_ok=frame_count_ok,
            metadata_ok=metadata_ok,
            alpha_contract_ok=psnr >= 80.0 and ssim >= 0.999999,
            audio_sync_ok=audio_sync_ok,
        )
        recorded = store.record(route.key, evidence)
        if not recorded:
            store.record_rejection(route.key, evidence)
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
    # Prefer a fully resident base when the exact source codec has an NVIDIA
    # decoder candidate. Capability only makes the route benchmarkable; runtime
    # permission still comes exclusively from the exact H6 evidence store.
    if not request.profile.still_image and route.layers and hw.gpu:
        source_codec = _probe_source_codec(str(request.ffprobe), request.source)
        media_caps = detect_gpu_media_capabilities(str(request.ffmpeg))
        resident_decoder = media_caps.decoder_for(source_codec) if source_codec else None
        if resident_decoder:
            resident_key = build_compositor_stack_key(
                hardware=hw,
                caps=caps,
                width=request.profile.width,
                height=request.profile.height,
                fps=request.profile.fps,
                pixel_format=request.profile.pixel_format,
                primaries=request.profile.primaries,
                transfer=request.profile.transfer,
                matrix=request.profile.matrix,
                color_range=request.profile.color_range,
                layers=route.layers,
                base_mode="nvdec-resident",
                base_codec=source_codec,
                base_decoder=resident_decoder,
            )
            resident_route = ComposerGpuRoute(
                evidence_store.approved(resident_key, caps),
                "exact H6 NVDEC-resident evidence approved",
                route.layer,
                resident_key,
                route.layers,
                resident_decoder,
            )
            if (
                not resident_route.use_gpu
                and evidence_store.benchmark_due(resident_key)
            ):
                try:
                    if _learn_exact_gpu_route(
                        request,
                        resident_route,
                        evidence_store,
                        cancelled=cancel,
                        log=logger,
                        envelopes=envelopes,
                    ):
                        resident_route = replace(
                            resident_route,
                            use_gpu=True,
                            reason="exact H6 NVDEC-resident evidence learned on this machine",
                        )
                except InterruptedError:
                    raise
                except Exception as exc:
                    evidence_store.record_benchmark_failure(resident_key, exc)
                    logger(
                        "H6 Composer NVDEC-resident: benchmark local falhou; "
                        "cooldown aplicado e rota anterior mantida. "
                        f"{type(exc).__name__}: {exc}"
                    )
            if resident_route.use_gpu:
                route = resident_route

    if (
        not route.use_gpu
        and route.key is not None
        and route.layers
        and evidence_store.benchmark_due(route.key)
        and "evidence is absent or stale" in route.reason
    ):
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
                    route.base_decoder,
                )
        except InterruptedError:
            raise
        except Exception as exc:
            evidence_store.record_benchmark_failure(route.key, exc)
            logger(
                "H6 Composer: benchmark físico local falhou; cooldown aplicado e "
                "CPU reference preservado. "
                f"{type(exc).__name__}: {exc}"
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
            failure_text = str(exc).lower()
            oom_like = any(
                token in failure_text
                for token in ("out of memory", "oom", "failed to allocate", "cuda_error_out_of_memory")
            )
            integrity_failure = "composer verification failed" in failure_text
            gpu_failure = looks_like_gpu_runtime_failure(exc)
            should_invalidate = integrity_failure or (gpu_failure and not oom_like)
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
