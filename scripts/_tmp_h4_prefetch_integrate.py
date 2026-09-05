from pathlib import Path


path = Path("src/cinepulse/studio.py")
text = path.read_text(encoding="utf-8")

old_import = "from .pipeline_runtime import measure_resource_headroom\n"
new_import = "from .pipeline_runtime import BackgroundCommand, measure_resource_headroom\n"
if old_import in text:
    text = text.replace(old_import, new_import, 1)
elif new_import not in text:
    raise SystemExit("H4 pipeline_runtime import anchor not found")

old_signature = (
    "        cpu_threads: int, base: float, weight: float, *, cache_source_video: str | None = None,\n"
    "        cache_quota_gb: float = 50.0, chunk_budget_gb: float = 4.0,\n"
    "    ) -> tuple[str, int, int]:\n"
)
new_signature = (
    "        cpu_threads: int, base: float, weight: float, *, cache_source_video: str | None = None,\n"
    "        cache_quota_gb: float = 50.0, chunk_budget_gb: float = 4.0, overlap_extract: bool = False,\n"
    "    ) -> tuple[str, int, int]:\n"
)
if "overlap_extract: bool = False" not in text:
    if old_signature not in text:
        raise SystemExit("Real-ESRGAN H4 signature anchor not found")
    text = text.replace(old_signature, new_signature, 1)

call_marker = "self._enhance_clip_ai("
cursor = 0
calls = 0
while True:
    start = text.find(call_marker, cursor)
    if start < 0:
        break
    calls += 1
    depth = 0
    close = None
    index = start + len(call_marker) - 1
    while index < len(text):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                close = index
                break
        index += 1
    if close is None:
        raise SystemExit("unclosed Real-ESRGAN call")
    call = text[start : close + 1]
    if "overlap_extract=" not in call:
        anchor = "chunk_budget_gb=realesrgan_budget.chunk_budget_gb,"
        position = text.find(anchor, start, close)
        if position < 0:
            raise SystemExit("Real-ESRGAN budget call anchor not found")
        insert_at = position + len(anchor)
        text = text[:insert_at] + "\n                    overlap_extract=realesrgan_budget.overlap_extract," + text[insert_at:]
        close += len("\n                    overlap_extract=realesrgan_budget.overlap_extract,")
    cursor = close + 1
if calls < 1:
    raise SystemExit("Real-ESRGAN call not found")

start_marker = "        processed = 0\n        chunk_index = 0\n        while processed < total_frames:\n"
end_marker = "\n        if not chunks:\n"
start = text.find(start_marker, text.find("def _enhance_clip_ai"))
if start < 0:
    raise SystemExit("Real-ESRGAN loop start not found")
end = text.find(end_marker, start)
if end < 0:
    raise SystemExit("Real-ESRGAN loop end not found")

replacement = '''        processed = 0
        chunk_index = 0
        prefetch: tuple[int, int, Path, Path, BackgroundCommand] | None = None

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

        try:
            while processed < total_frames:
                if self._cancelled:
                    raise InterruptedError
                count = min(chunk_frames, total_frames - processed)
                chunk_index += 1
                chunk_start = start_time + processed / max(1.0, source_fps)
                chunk_duration = count / max(1.0, source_fps)
                chunk_dir = chunk_root / f"chunk_{chunk_index:05d}"
                incoming, outgoing = chunk_dir / "entrada", chunk_dir / "melhorado"
                fraction_before = processed / total_frames
                fraction_chunk = count / total_frames
                stage_base = base + weight * fraction_before * 0.90

                prefetched = prefetch is not None and prefetch[0] == processed and prefetch[1] == count
                if prefetched:
                    _offset, _count, prefetched_dir, prefetched_incoming, task = prefetch
                    if prefetched_dir != chunk_dir or prefetched_incoming != incoming:
                        task.cancel()
                        raise RuntimeError("H4 prefetch perdeu sincronismo com o lote atual.")
                    self._set_stage(
                        "IA 1/3",
                        f"Lote {chunk_index}: consumindo prefetch de {count} quadro(s) já extraído em paralelo.",
                    )
                    result = task.wait()
                    prefetch = None
                    if result.cancelled or self._cancelled:
                        raise InterruptedError
                    self._log(f"H4 PREFETCH Real-ESRGAN: lote {chunk_index} pronto sem ocupar o processo foreground.")
                    outgoing.mkdir(parents=True, exist_ok=True)
                else:
                    incoming.mkdir(parents=True, exist_ok=True)
                    outgoing.mkdir(parents=True, exist_ok=True)
                    self._set_stage(
                        "IA 1/3",
                        f"Lote {chunk_index}: extraindo {count} quadro(s) ({processed + 1}–{processed + count}/{total_frames}).",
                    )
                    extract = extraction_command(processed, count, incoming, progress=True)
                    self._run_ffmpeg(extract, chunk_duration, stage_base, weight * fraction_chunk * 0.18)

                frames = len(list(incoming.glob("frame*.png")))
                if frames != count:
                    raise RuntimeError(f"A IA recebeu {frames} de {count} quadros esperados no lote.")

                next_processed = processed + count
                if overlap_extract and next_processed < total_frames and prefetch is None:
                    next_count = min(chunk_frames, total_frames - next_processed)
                    next_index = chunk_index + 1
                    next_dir = chunk_root / f"chunk_{next_index:05d}"
                    next_incoming = next_dir / "entrada"
                    next_incoming.mkdir(parents=True, exist_ok=True)
                    next_command = extraction_command(next_processed, next_count, next_incoming, progress=False)
                    task = BackgroundCommand(
                        next_command,
                        cancel_requested=lambda: self._cancelled,
                        log=self._log,
                    ).start()
                    prefetch = (next_processed, next_count, next_dir, next_incoming, task)
                    self._log(
                        f"H4 PREFETCH Real-ESRGAN: extração do lote {next_index} iniciada em paralelo; "
                        "fila rígida=1 lote futuro / máximo 2 worksets ativos nesta etapa."
                    )

                self._set_stage("IA 2/3", f"Lote {chunk_index}: Real-ESRGAN em {frames} quadro(s).")
                attempted: set[RealEsrganPolicy] = set()
                policy = active_policy
                while True:
                    attempted.add(policy)
                    safe_rmtree(outgoing)
                    outgoing.mkdir(parents=True, exist_ok=True)
                    command = [
                        str(REAL_ESRGAN), "-i", str(incoming), "-o", str(outgoing), "-m", str(REAL_ESRGAN_MODELS),
                        "-n", "realesr-animevideov3", "-s", "2", "-f", "png",
                    ] + policy.command_args()
                    try:
                        self._log(
                            f"H3 Real-ESRGAN lote {chunk_index}: tile={policy.tile} "
                            f"pipeline={policy.pipeline} gpu={policy.gpu_index}."
                        )
                        self._run_ai(
                            command, outgoing, frames,
                            stage_base + weight * fraction_chunk * 0.18,
                            weight * fraction_chunk * 0.58,
                        )
                        produced = len(list(outgoing.glob("frame*.png")))
                        if produced != frames:
                            raise RuntimeError(
                                f"Real-ESRGAN produziu {produced} de {frames} quadros esperados no lote."
                            )
                        active_policy = policy
                        break
                    except InterruptedError:
                        raise
                    except RuntimeError as exc:
                        failure_text = str(exc).lower()
                        oom_like = any(
                            token in failure_text
                            for token in ("out of memory", "oom", "failed to allocate", "vk_error_out_of_device_memory")
                        )
                        was_tuned = tuned_policy is not None and policy == tuned_policy
                        if was_tuned:
                            if tuning_store.invalidate(tuning_key, reason=str(exc)):
                                self._log(
                                    "H3 Real-ESRGAN: política física aprovada falhou e foi invalidada para esta chave exata."
                                )
                            tuned_policy = None
                        if policy != conservative_policy and conservative_policy not in attempted:
                            self._log(
                                f"H3 Real-ESRGAN: {'OOM/pressão de VRAM' if oom_like else 'falha/integridade'} "
                                f"com tile={policy.tile} pipeline={policy.pipeline}; única repetição segura com "
                                f"tile={conservative_policy.tile} pipeline={conservative_policy.pipeline}."
                            )
                            policy = conservative_policy
                            continue
                        raise

                self._set_stage("IA 3/3", f"Lote {chunk_index}: compactando o resultado lossless e liberando PNGs.")
                chunk_video = chunk_root / f"segment_{chunk_index:05d}.mkv"
                merge = [
                    FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
                    "-framerate", f"{source_fps:.8f}", "-start_number", "1", "-i", str(outgoing / "frame%08d.png"),
                    "-map", "0:v:0", "-an", "-frames:v", str(frames),
                    "-c:v", "ffv1", "-level", "3", "-coder", "1", "-context", "1", "-g", "1", "-slicecrc", "1",
                    "-pix_fmt", "yuv420p", "-threads", str(cpu_threads),
                    "-progress", "pipe:1", "-nostats", str(chunk_video),
                ]
                self._run_ffmpeg(
                    merge, chunk_duration,
                    stage_base + weight * fraction_chunk * 0.76,
                    weight * fraction_chunk * 0.14,
                )
                chunks.append(chunk_video)
                safe_rmtree(chunk_dir)
                processed += count
        finally:
            if prefetch is not None:
                task = prefetch[4]
                task.cancel()
                try:
                    task.wait(timeout=5.0)
                except Exception:
                    pass
'''

text = text[:start] + replacement + text[end:]
path.write_text(text, encoding="utf-8", newline="\n")
