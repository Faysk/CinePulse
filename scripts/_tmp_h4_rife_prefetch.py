from pathlib import Path


path = Path("src/cinepulse/studio.py")
text = path.read_text(encoding="utf-8")

old_signature = (
    "        *,\n"
    "        color_plan: ColorPipeline,\n"
    "        chunk_budget_gb: float = 4.0,\n"
    "    ) -> str:\n"
)
new_signature = (
    "        *,\n"
    "        color_plan: ColorPipeline,\n"
    "        chunk_budget_gb: float = 4.0,\n"
    "        overlap_extract: bool = False,\n"
    "    ) -> str:\n"
)
method_start = text.find("    def _interpolate_rife(")
if method_start < 0:
    raise SystemExit("RIFE method not found")
method_end = text.find("\n    @staticmethod\n    def _release_temp_path", method_start)
if method_end < 0:
    raise SystemExit("RIFE method end not found")
method = text[method_start:method_end]
if "overlap_extract: bool = False" not in method:
    position = text.find(old_signature, method_start, method_end)
    if position < 0:
        raise SystemExit("RIFE signature anchor not found")
    text = text[:position] + new_signature + text[position + len(old_signature):]
    method_end += len(new_signature) - len(old_signature)

# Add overlap flag to every RIFE call outside the method definition. CPU RIFE
# deliberately keeps extraction sequential to avoid competing for the same CPU.
marker = "self._interpolate_rife("
cursor = 0
calls = 0
while True:
    start = text.find(marker, cursor)
    if start < 0:
        break
    calls += 1
    depth = 0
    close = None
    index = start + len(marker) - 1
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
        raise SystemExit("unclosed RIFE call")
    call = text[start:close + 1]
    if "overlap_extract=" not in call:
        anchor = "chunk_budget_gb=rife_budget.chunk_budget_gb,"
        position = text.find(anchor, start, close)
        if position < 0:
            raise SystemExit("RIFE budget call anchor not found")
        insert_at = position + len(anchor)
        insertion = "\n                        overlap_extract=(rife_budget.overlap_extract and not settings.use_cpu),"
        text = text[:insert_at] + insertion + text[insert_at:]
        close += len(insertion)
    cursor = close + 1
if calls < 1:
    raise SystemExit("RIFE call sites not found")

method_start = text.find("    def _interpolate_rife(")
method_end = text.find("\n    @staticmethod\n    def _release_temp_path", method_start)
start_marker = "        processed_source = 0\n        produced_target = 0\n        chunk_index = 0\n"
start = text.find(start_marker, method_start, method_end)
if start < 0:
    raise SystemExit("RIFE loop state anchor not found")
loop_start = text.find("        try:\n            while processed_source < source_count:\n", start, method_end)
if loop_start < 0:
    raise SystemExit("RIFE loop start not found")
concat_marker = "\n            if not chunks:\n"
loop_end = text.find(concat_marker, loop_start, method_end)
if loop_end < 0:
    raise SystemExit("RIFE concat anchor not found")

prefix = '''        processed_source = 0
        produced_target = 0
        chunk_index = 0
        prefetch: tuple[int, int, Path, BackgroundCommand] | None = None
        self._log(
            f"STORAGE RIFE: {source_count}→{total_target_count} frames em lotes de até {chunk_frames} frames fonte; "
            "PNGs são liberados após cada lote."
        )

        def source_chunk_count(offset: int) -> int:
            remaining = source_count - offset
            count = min(chunk_frames, remaining)
            if remaining - count == 1:
                count += 1
            count = min(count, remaining)
            return count if count >= 2 else 0

        def extraction_command(frame_offset: int, frame_count: int, destination: Path, *, progress: bool) -> list[str]:
            extraction_start = start_time + frame_offset / max(1.0, source_fps)
            command = [FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error"]
            if extraction_start > 0:
                command += ["-ss", f"{extraction_start:.6f}"]
            command += [
                "-i", video, "-map", "0:v:0", "-an", "-vf", f"fps={source_fps:.8f}",
                "-frames:v", str(frame_count), "-start_number", "0",
            ]
            if progress:
                command += ["-progress", "pipe:1", "-nostats"]
            command += [str(destination / "%08d.png")]
            return command

        try:
            while processed_source < source_count:
                if self._cancelled:
                    raise InterruptedError
                count = source_chunk_count(processed_source)
                if count < 2:
                    # A one-frame tail cannot be interpolated independently;
                    # it is intentionally represented by the preceding chunk.
                    break
                chunk_index += 1
                chunk_duration = count / max(1.0, source_fps)
                desired = min(
                    total_target_count - produced_target,
                    max(2, round(chunk_duration * target_fps)),
                )
                incoming = chunk_root / f"chunk_{chunk_index:05d}_in"
                outgoing = chunk_root / f"chunk_{chunk_index:05d}_out"
                fraction_before = processed_source / source_count
                fraction_chunk = count / source_count
                stage_base = base + weight * fraction_before * 0.90

                prefetched = prefetch is not None and prefetch[0] == processed_source and prefetch[1] == count
                if prefetched:
                    _offset, _count, prefetched_incoming, task = prefetch
                    if prefetched_incoming != incoming:
                        task.cancel()
                        raise RuntimeError("H4 prefetch RIFE perdeu sincronismo com o lote atual.")
                    self._set_stage(
                        "RIFE 1/3",
                        f"Lote {chunk_index}: consumindo prefetch de {count} quadro(s) fonte já extraído em paralelo.",
                    )
                    result = task.wait()
                    prefetch = None
                    if result.cancelled or self._cancelled:
                        raise InterruptedError
                    self._log(f"H4 PREFETCH RIFE: lote {chunk_index} pronto sem ocupar o processo foreground.")
                    outgoing.mkdir(parents=True, exist_ok=True)
                else:
                    incoming.mkdir(parents=True, exist_ok=True)
                    outgoing.mkdir(parents=True, exist_ok=True)
                    self._set_stage(
                        "RIFE 1/3",
                        f"Lote {chunk_index}: extraindo {count} quadro(s) fonte ({processed_source + 1}–{processed_source + count}/{source_count}).",
                    )
                    extract = extraction_command(processed_source, count, incoming, progress=True)
                    self._run_ffmpeg(extract, chunk_duration, stage_base, weight * fraction_chunk * 0.18)

                extracted = len(list(incoming.glob("*.png")))
                if extracted < 2:
                    raise RuntimeError("RIFE recebeu menos de dois quadros no lote.")

                next_processed = processed_source + count
                next_count = source_chunk_count(next_processed) if next_processed < source_count else 0
                if overlap_extract and next_count >= 2 and prefetch is None:
                    next_index = chunk_index + 1
                    next_incoming = chunk_root / f"chunk_{next_index:05d}_in"
                    next_incoming.mkdir(parents=True, exist_ok=True)
                    next_command = extraction_command(next_processed, next_count, next_incoming, progress=False)
                    task = BackgroundCommand(
                        next_command,
                        cancel_requested=lambda: self._cancelled,
                        log=self._log,
                    ).start()
                    prefetch = (next_processed, next_count, next_incoming, task)
                    self._log(
                        f"H4 PREFETCH RIFE: extração do lote {next_index} iniciada em paralelo; "
                        "fila rígida=1 lote futuro / máximo 2 worksets ativos nesta etapa."
                    )

                self._set_stage("RIFE 2/3", f"Lote {chunk_index}: gerando {desired} quadros com rife-v4.6.")
                command = build_rife_command(paths, incoming, outgoing, desired, use_cpu)
                self._log("Comando RIFE: " + subprocess.list2cmdline(command))
                recent: deque[str] = deque(maxlen=60)
                process = subprocess.Popen(
                    command,
                    cwd=str(RIFE_EXE.parent),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    **popen_group_kwargs(),
                )
                self._process = process

                def reader() -> None:
                    assert process.stdout is not None
                    for line in process.stdout:
                        clean = line.strip()
                        if clean:
                            recent.append(clean)
                            self._log(clean)

                reader_thread = threading.Thread(target=reader, daemon=True)
                reader_thread.start()
                while process.poll() is None:
                    if self._cancelled:
                        terminate_process_tree(process, self._log)
                        break
                    completed = len(list(outgoing.glob("*.png")))
                    self._push_progress(
                        stage_base + weight * fraction_chunk * (0.18 + 0.58 * min(1.0, completed / max(1, desired)))
                    )
                    time.sleep(0.25)
                code = process.wait()
                reader_thread.join(timeout=2)
                if self._cancelled:
                    raise InterruptedError
                if code:
                    raise RuntimeError("RIFE falhou.\n" + "\n".join(recent))
                frames = sorted(outgoing.glob("*.png"))
                if len(frames) < max(2, desired - 1):
                    raise RuntimeError(f"RIFE produziu {len(frames)} de {desired} quadros esperados no lote.")

                self._set_stage("RIFE 3/3", f"Lote {chunk_index}: compactando lossless e liberando PNGs.")
                first_number = int(frames[0].stem)
                chunk_video = chunk_root / f"segment_{chunk_index:05d}.mkv"
                merge = [
                    FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
                    "-framerate", f"{target_fps:.8f}", "-start_number", str(first_number),
                    "-i", str(outgoing / "%08d.png"), "-map", "0:v:0", "-an",
                    "-frames:v", str(len(frames)),
                    "-c:v", "ffv1", "-level", "3", "-coder", "1", "-context", "1", "-g", "1", "-slicecrc", "1",
                    "-pix_fmt", color_plan.working_pix_fmt if color_plan.working_pix_fmt in {"yuv420p", "yuv420p10le"} else "yuv420p",
                    "-threads", str(cpu_threads), "-progress", "pipe:1", "-nostats", str(chunk_video),
                ]
                self._run_ffmpeg(
                    merge, max(0.01, len(frames) / target_fps),
                    stage_base + weight * fraction_chunk * 0.76,
                    weight * fraction_chunk * 0.14,
                )
                chunks.append(chunk_video)
                safe_rmtree(incoming)
                safe_rmtree(outgoing)
                processed_source += count
                produced_target += len(frames)
'''

# Preserve concat/finalization body but replace the old state/log/loop section.
text = text[:start] + prefix + text[loop_end:]

# Ensure background task is stopped before the existing chunk_root cleanup.
method_start = text.find("    def _interpolate_rife(")
method_end = text.find("\n    @staticmethod\n    def _release_temp_path", method_start)
old_finally = "        finally:\n            safe_rmtree(chunk_root)\n"
new_finally = (
    "        finally:\n"
    "            if prefetch is not None:\n"
    "                task = prefetch[3]\n"
    "                task.cancel()\n"
    "                try:\n"
    "                    task.wait(timeout=5.0)\n"
    "                except Exception:\n"
    "                    pass\n"
    "            safe_rmtree(chunk_root)\n"
)
position = text.find(old_finally, method_start, method_end)
if position < 0:
    raise SystemExit("RIFE cleanup anchor not found")
text = text[:position] + new_finally + text[position + len(old_finally):]

path.write_text(text, encoding="utf-8", newline="\n")
