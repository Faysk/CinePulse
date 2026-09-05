from pathlib import Path

path = Path("src/cinepulse/studio.py")
text = path.read_text(encoding="utf-8")

# Real-ESRGAN method: add an opt-in pack-overlap flag. Defaults remain fully
# sequential, so callers outside the H4 live budget cannot accidentally enable it.
method_start = text.find("    def _enhance_clip_ai(")
method_end = text.find("\n    def _run_ai(", method_start)
if method_start < 0 or method_end < 0:
    raise SystemExit("Real-ESRGAN method anchors not found")
method = text[method_start:method_end]
old_sig = "        cache_quota_gb: float = 50.0, chunk_budget_gb: float = 4.0, overlap_extract: bool = False,\n"
new_sig = "        cache_quota_gb: float = 50.0, chunk_budget_gb: float = 4.0, overlap_extract: bool = False,\n        overlap_pack: bool = False,\n"
if "overlap_pack: bool = False" not in method:
    pos = text.find(old_sig, method_start, method_end)
    if pos < 0:
        raise SystemExit("Real-ESRGAN signature anchor not found")
    text = text[:pos] + new_sig + text[pos + len(old_sig):]

# Pass the live H4 permission at every Real-ESRGAN call site.
marker = "self._enhance_clip_ai("
cursor = 0
while True:
    start = text.find(marker, cursor)
    if start < 0:
        break
    depth = 0
    close = None
    index = start + len(marker) - 1
    while index < len(text):
        ch = text[index]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                close = index
                break
        index += 1
    if close is None:
        raise SystemExit("unclosed Real-ESRGAN call")
    call = text[start:close + 1]
    if "overlap_pack=" not in call:
        anchor = "overlap_extract=realesrgan_budget.overlap_extract,"
        pos = text.find(anchor, start, close)
        if pos < 0:
            raise SystemExit("Real-ESRGAN H4 call anchor not found")
        insert = pos + len(anchor)
        addition = "\n                    overlap_pack=realesrgan_budget.overlap_pack,"
        text = text[:insert] + addition + text[insert:]
        close += len(addition)
    cursor = close + 1

method_start = text.find("    def _enhance_clip_ai(")
method_end = text.find("\n    def _run_ai(", method_start)

old_state = "        prefetch: tuple[int, int, Path, Path, BackgroundCommand] | None = None\n\n        def extraction_command"
new_state = "        prefetch: tuple[int, int, Path, Path, BackgroundCommand] | None = None\n        pack: tuple[int, Path, Path, BackgroundCommand] | None = None\n\n        def extraction_command"
if "pack: tuple[int, Path, Path, BackgroundCommand] | None = None" not in text[method_start:method_end]:
    pos = text.find(old_state, method_start, method_end)
    if pos < 0:
        raise SystemExit("Real-ESRGAN pack state anchor not found")
    text = text[:pos] + new_state + text[pos + len(old_state):]

method_start = text.find("    def _enhance_clip_ai(")
method_end = text.find("\n    def _run_ai(", method_start)
old_pack = '''                self._set_stage("IA 3/3", f"Lote {chunk_index}: compactando o resultado lossless e liberando PNGs.")
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
'''
new_pack = '''                # Only one previous pack may remain in flight. Waiting here means
                # pack(N-1) overlaps neural(N), but two pack encoders never stack.
                if pack is not None:
                    packed_index, packed_dir, packed_video, packed_task = pack
                    packed_result = packed_task.wait()
                    pack = None
                    if packed_result.cancelled or self._cancelled:
                        raise InterruptedError
                    if not packed_video.is_file() or packed_video.stat().st_size <= 0:
                        raise RuntimeError(f"H4 pack Real-ESRGAN lote {packed_index} não produziu FFV1 válido.")
                    chunks.append(packed_video)
                    safe_rmtree(packed_dir)
                    self._log(f"H4 PACK Real-ESRGAN: lote {packed_index} concluído em ordem e workset liberado.")

                self._set_stage("IA 3/3", f"Lote {chunk_index}: compactando o resultado lossless e liberando PNGs.")
                chunk_video = chunk_root / f"segment_{chunk_index:05d}.mkv"
                merge_base = [
                    FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
                    "-framerate", f"{source_fps:.8f}", "-start_number", "1", "-i", str(outgoing / "frame%08d.png"),
                    "-map", "0:v:0", "-an", "-frames:v", str(frames),
                    "-c:v", "ffv1", "-level", "3", "-coder", "1", "-context", "1", "-g", "1", "-slicecrc", "1",
                    "-pix_fmt", "yuv420p", "-threads", str(cpu_threads),
                ]
                if overlap_pack and next_processed < total_frames:
                    background_merge = merge_base + [str(chunk_video)]
                    packed_task = BackgroundCommand(
                        background_merge,
                        cancel_requested=lambda: self._cancelled,
                        log=self._log,
                    ).start()
                    pack = (chunk_index, chunk_dir, chunk_video, packed_task)
                    self._log(
                        f"H4 PACK Real-ESRGAN: lote {chunk_index} compactando em paralelo; "
                        "fila rígida=1 pack anterior / teto total=3 worksets com prefetch."
                    )
                else:
                    foreground_merge = merge_base + ["-progress", "pipe:1", "-nostats", str(chunk_video)]
                    self._run_ffmpeg(
                        foreground_merge, chunk_duration,
                        stage_base + weight * fraction_chunk * 0.76,
                        weight * fraction_chunk * 0.14,
                    )
                    if not chunk_video.is_file() or chunk_video.stat().st_size <= 0:
                        raise RuntimeError(f"H4 pack Real-ESRGAN lote {chunk_index} não produziu FFV1 válido.")
                    chunks.append(chunk_video)
                    safe_rmtree(chunk_dir)
                processed += count
'''
pos = text.find(old_pack, method_start, method_end)
if pos < 0:
    raise SystemExit("Real-ESRGAN pack block anchor not found")
text = text[:pos] + new_pack + text[pos + len(old_pack):]

method_start = text.find("    def _enhance_clip_ai(")
method_end = text.find("\n    def _run_ai(", method_start)
old_finally = '''        finally:
            if prefetch is not None:
                task = prefetch[4]
                task.cancel()
                try:
                    task.wait(timeout=5.0)
                except Exception:
                    pass
'''
new_finally = '''        finally:
            if prefetch is not None:
                task = prefetch[4]
                task.cancel()
                try:
                    task.wait(timeout=5.0)
                except Exception:
                    pass
            if pack is not None:
                packed_task = pack[3]
                packed_task.cancel()
                try:
                    packed_task.wait(timeout=5.0)
                except Exception:
                    pass
'''
pos = text.find(old_finally, method_start, method_end)
if pos < 0:
    raise SystemExit("Real-ESRGAN finally anchor not found")
text = text[:pos] + new_finally + text[pos + len(old_finally):]

path.write_text(text, encoding="utf-8", newline="\n")
