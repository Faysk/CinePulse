from pathlib import Path


def patch_process_control() -> None:
    path = Path("src/cinepulse/process_control.py")
    text = path.read_text(encoding="utf-8")
    old = '''            if result.returncode not in (0, 128):
                logger(f"taskkill retornou {result.returncode}: {(result.stderr or result.stdout).strip()}")
        else:
'''
    new = '''            if result.returncode not in (0, 128):
                logger(f"taskkill retornou {result.returncode}: {(result.stderr or result.stdout).strip()}")
            if not _wait_for_exit(process, grace_seconds):
                logger(f"Processo {pid} não confirmou encerramento após taskkill; usando TerminateProcess.")
                try:
                    process.kill()
                    process.wait(timeout=2.0)
                except (OSError, subprocess.TimeoutExpired):
                    logger(f"Processo {pid} não confirmou encerramento após TerminateProcess.")
        else:
'''
    if old not in text:
        raise SystemExit("process_control Windows cancellation anchor not found")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def patch_studio() -> None:
    path = Path("src/cinepulse/studio.py")
    text = path.read_text(encoding="utf-8")

    strict = '''                frames = len(list(incoming.glob("frame*.png")))
                if frames != count:
                    raise RuntimeError(f"A IA recebeu {frames} de {count} quadros esperados no lote.")
'''
    tolerant = '''                frames = len(list(incoming.glob("frame*.png")))
                if frames < 1:
                    raise RuntimeError("A IA não recebeu nenhum quadro do vídeo.")
                if frames != count:
                    self._log(
                        f"H4 PREFETCH Real-ESRGAN: FFmpeg entregou {frames}/{count} quadros; "
                        "desativando prefetch para os lotes restantes e preservando a tolerância histórica."
                    )
                    overlap_extract = False
'''
    if strict not in text:
        raise SystemExit("Real-ESRGAN historical frame tolerance anchor not found")
    text = text.replace(strict, tolerant, 1)

    start = text.find("    def _run_ffmpeg(self, command: list[str], duration: float, base: float, weight: float) -> None:\n")
    end = text.find("\n    def _verify_output(\n", start)
    if start < 0 or end < 0:
        raise SystemExit("_run_ffmpeg method anchors not found")
    replacement = '''    def _run_ffmpeg(self, command: list[str], duration: float, base: float, weight: float) -> None:
        """Run FFmpeg without letting a blocked stdout pipe stall cancellation.

        Progress parsing is performed on the render worker while a daemon reader
        drains FFmpeg output. The worker therefore keeps polling the process and
        can enforce cancellation even when Windows pipe EOF is delayed by a shim
        or descendant process.
        """
        if self._cancelled:
            raise InterruptedError
        self._log("Comando FFmpeg: " + subprocess.list2cmdline(command))
        recent: deque[str] = deque(maxlen=60)
        lines = queue.Queue()
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", **popen_group_kwargs(),
        )
        self._process = process
        assert process.stdout is not None

        def reader() -> None:
            try:
                for raw in process.stdout:
                    lines.put(raw)
            except (OSError, ValueError):
                # Cancellation may close the pipe from the worker thread after
                # the process has already been terminated.
                return

        reader_thread = threading.Thread(target=reader, daemon=True)
        reader_thread.start()

        def drain_output() -> None:
            while True:
                try:
                    raw = lines.get_nowait()
                except queue.Empty:
                    return
                line = raw.strip()
                if line:
                    recent.append(line)
                    self._log(line)
                if line.startswith("out_time="):
                    try:
                        hours, minutes, seconds = line.split("=", 1)[1].split(":")
                        elapsed = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                        self._push_progress(base + weight * min(1, elapsed / max(0.001, duration)))
                    except ValueError:
                        pass

        while process.poll() is None:
            drain_output()
            if self._cancelled:
                terminate_process_tree(process, self._log, grace_seconds=2.0)
                break
            time.sleep(0.05)

        drain_output()
        try:
            code = process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            terminate_process_tree(process, self._log, grace_seconds=1.0)
            try:
                code = process.wait(timeout=2.0)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("FFmpeg não encerrou após cancelamento forçado.") from exc
        finally:
            try:
                process.stdout.close()
            except (OSError, ValueError):
                pass
            reader_thread.join(timeout=1.0)
            drain_output()

        if self._cancelled:
            raise InterruptedError
        if code:
            raise RuntimeError("A etapa de vídeo falhou.\\n\\n" + "\\n".join(recent))
        self._push_progress(base + weight)
'''
    text = text[:start] + replacement + text[end:]
    path.write_text(text, encoding="utf-8", newline="\n")


patch_process_control()
patch_studio()
print("H4 cancellation patch applied")
