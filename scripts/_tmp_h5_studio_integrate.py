from pathlib import Path

path = Path("src/cinepulse/studio.py")
text = path.read_text(encoding="utf-8")

old_import = "from .adaptive_runtime import AdaptiveRuntimeController, RuntimePressureDecision\nfrom .pipeline_runtime import BackgroundCommand, measure_resource_headroom\n"
new_import = "from .adaptive_runtime import AdaptiveRuntimeController, RuntimePressureDecision\nfrom .gpu_media import (\n    GpuMediaKey, GpuMediaPolicy, GpuMediaTuningStore, detect_gpu_media_capabilities,\n    invalidate_on_runtime_failure as invalidate_gpu_media_policy, select_proven_policy as select_gpu_media_policy,\n)\nfrom .pipeline_runtime import BackgroundCommand, measure_resource_headroom\n"
if old_import not in text:
    raise SystemExit("H5 import anchor not found")
text = text.replace(old_import, new_import, 1)

old_prelude = '''        processed = 0
        chunk_index = 0
        prefetch: tuple[int, int, Path, Path, BackgroundCommand] | None = None
        pack: tuple[int, Path, Path, BackgroundCommand] | None = None

        def extraction_command(frame_offset: int, frame_count: int, destination: Path, *, progress: bool) -> list[str]:
            extraction_start = start_time + frame_offset / max(1.0, source_fps)
            command = [FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error"]
            if extraction_start > 0:
                command += ["-ss", f"{extraction_start:.6f}"]
            command += [
                "-i", video,
                "-map", "0:v:0", "-an", "-vf", f"fps={source_fps:.8f}",
                "-frames:v", str(frame_count), "-start_number", "1",
            ]
            if progress:
                command += ["-progress", "pipe:1", "-nostats"]
            command += [str(destination / "frame%08d.png")]
            return command
'''
new_prelude = '''        processed = 0
        chunk_index = 0
        prefetch: tuple[int, int, Path, Path, BackgroundCommand] | None = None
        pack: tuple[int, Path, Path, BackgroundCommand] | None = None

        # H5: CUDA decode is evidence-gated, never inferred from mere capability.
        # HDR/unknown-color sources already fail closed inside gpu_media.py.
        gpu_media_store = GpuMediaTuningStore(PATHS.cache / "hardware" / "gpu-media-tuning.json")
        gpu_media_key: GpuMediaKey | None = None
        gpu_media_policy: GpuMediaPolicy | None = None
        gpu_media_profile: ColorProfile | None = None
        try:
            gpu_probe = probe_media(video)
            gpu_stream = next(
                (stream for stream in gpu_probe.get("streams", []) if stream.get("codec_type") == "video"),
                {},
            )
            gpu_media_profile = ColorProfile.from_probe(gpu_probe)
            gpu_caps = detect_gpu_media_capabilities(str(FFMPEG))
            gpu_media_key = GpuMediaKey.from_profile(
                gpu_name=self._hardware.gpu or "unknown-gpu",
                driver=self._hardware.driver or "unknown-driver",
                ffmpeg_fingerprint=gpu_caps.fingerprint,
                codec=str(gpu_stream.get("codec_name") or "unknown"),
                width=source_w,
                height=source_h,
                target_width=source_w,
                target_height=source_h,
                profile=gpu_media_profile,
                operation="decode",
            )
            gpu_media_policy = select_gpu_media_policy(
                store=gpu_media_store,
                key=gpu_media_key,
                capabilities=gpu_caps,
                profile=gpu_media_profile,
            )
        except Exception as exc:
            self._log(f"H5 CUDA decode: capability/evidence probe indisponível; CPU preservada ({exc}).")
            gpu_media_policy = None
        if gpu_media_policy is not None:
            self._log(
                f"H5 CUDA decode: evidência exata aprovada; usando {gpu_media_policy.decoder} "
                f"na GPU {gpu_media_policy.gpu_index} para alimentar a extração neural."
            )

        def invalidate_gpu_extract(reason: BaseException | str) -> None:
            nonlocal gpu_media_policy
            if gpu_media_policy is None or gpu_media_key is None:
                return
            invalidate_gpu_media_policy(gpu_media_store, gpu_media_key)
            self._log(
                "H5 CUDA decode: política aprovada falhou em produção, foi invalidada e este lote "
                f"será repetido uma vez pela CPU. Motivo: {reason}"
            )
            gpu_media_policy = None

        def extraction_command(
            frame_offset: int,
            frame_count: int,
            destination: Path,
            *,
            progress: bool,
            policy: GpuMediaPolicy | None,
        ) -> list[str]:
            extraction_start = start_time + frame_offset / max(1.0, source_fps)
            command = [FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error"]
            if extraction_start > 0:
                command += ["-ss", f"{extraction_start:.6f}"]
            if policy is not None:
                command += policy.input_args()
            command += ["-i", video, "-map", "0:v:0", "-an"]
            if policy is not None and gpu_media_profile is not None:
                filters = f"hwdownload,format={gpu_media_profile.pixel_format},fps={source_fps:.8f}"
            else:
                filters = f"fps={source_fps:.8f}"
            command += [
                "-vf", filters,
                "-frames:v", str(frame_count), "-start_number", "1",
            ]
            if progress:
                command += ["-progress", "pipe:1", "-nostats"]
            command += [str(destination / "frame%08d.png")]
            return command

        def run_extraction(
            frame_offset: int,
            frame_count: int,
            destination: Path,
            *,
            progress: bool,
            expected_duration: float,
            stage_progress_base: float,
            stage_progress_weight: float,
        ) -> None:
            policy = gpu_media_policy
            command = extraction_command(
                frame_offset, frame_count, destination, progress=progress, policy=policy
            )
            try:
                self._run_ffmpeg(
                    command, expected_duration, stage_progress_base, stage_progress_weight
                )
            except RuntimeError as exc:
                if policy is None:
                    raise
                invalidate_gpu_extract(exc)
                safe_rmtree(destination)
                destination.mkdir(parents=True, exist_ok=True)
                retry = extraction_command(
                    frame_offset, frame_count, destination, progress=progress, policy=None
                )
                self._run_ffmpeg(
                    retry, expected_duration, stage_progress_base, stage_progress_weight
                )
'''
if old_prelude not in text:
    raise SystemExit("H5 extraction prelude anchor not found")
text = text.replace(old_prelude, new_prelude, 1)

old_foreground = '''                    extract = extraction_command(processed, count, incoming, progress=True)
                    self._run_ffmpeg(extract, chunk_duration, stage_base, weight * fraction_chunk * 0.18)
'''
new_foreground = '''                    run_extraction(
                        processed,
                        count,
                        incoming,
                        progress=True,
                        expected_duration=chunk_duration,
                        stage_progress_base=stage_base,
                        stage_progress_weight=weight * fraction_chunk * 0.18,
                    )
'''
if old_foreground not in text:
    raise SystemExit("H5 foreground extraction anchor not found")
text = text.replace(old_foreground, new_foreground, 1)

old_prefetch_command = '''                    next_command = extraction_command(next_processed, next_count, next_incoming, progress=False)
'''
new_prefetch_command = '''                    next_command = extraction_command(
                        next_processed,
                        next_count,
                        next_incoming,
                        progress=False,
                        policy=gpu_media_policy,
                    )
'''
if old_prefetch_command not in text:
    raise SystemExit("H5 prefetch command anchor not found")
text = text.replace(old_prefetch_command, new_prefetch_command, 1)

old_wait = '''                    result = task.wait()
                    prefetch = None
                    if result.cancelled or self._cancelled:
                        raise InterruptedError
                    self._log(f"H4 PREFETCH Real-ESRGAN: lote {chunk_index} pronto sem ocupar o processo foreground.")
                    outgoing.mkdir(parents=True, exist_ok=True)
'''
new_wait = '''                    try:
                        result = task.wait()
                    except RuntimeError as exc:
                        if gpu_media_policy is None:
                            raise
                        invalidate_gpu_extract(exc)
                        safe_rmtree(incoming)
                        incoming.mkdir(parents=True, exist_ok=True)
                        run_extraction(
                            processed,
                            count,
                            incoming,
                            progress=True,
                            expected_duration=chunk_duration,
                            stage_progress_base=stage_base,
                            stage_progress_weight=weight * fraction_chunk * 0.18,
                        )
                        result = None
                    prefetch = None
                    if result is not None and (result.cancelled or self._cancelled):
                        raise InterruptedError
                    self._log(f"H4 PREFETCH Real-ESRGAN: lote {chunk_index} pronto sem ocupar o processo foreground.")
                    outgoing.mkdir(parents=True, exist_ok=True)
'''
if old_wait not in text:
    raise SystemExit("H5 prefetch wait anchor not found")
text = text.replace(old_wait, new_wait, 1)

path.write_text(text, encoding="utf-8", newline="\n")
print("H5 Studio integration applied")
