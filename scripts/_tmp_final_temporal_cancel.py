from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"{label}: expected one anchor, got {text.count(old)}")
    return text.replace(old, new, 1)


def patch_temporal() -> None:
    path = Path("src/cinepulse/restoration_temporal_export.py")
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'from .restoration_preview import PreviewRestorationPlan\n',
        'from .restoration_preview import PreviewRestorationPlan\nfrom .process_control import popen_group_kwargs, terminate_process_tree\n',
        "temporal process-control import",
    )

    # The rawvideo bridge has one decoded raw frame in the decoder pipe/client
    # and one encoded raw frame around stdin in addition to the rolling window
    # and reconstruction copy. Account for those bounded bridge slots.
    old_estimate = '''        resident_frames = (2 * int(policy.radius) + 1) + 1
        return self.frame_bytes * resident_frames
'''
    new_estimate = '''        resident_frames = (2 * int(policy.radius) + 1) + 3
        return self.frame_bytes * resident_frames
'''
    text = replace_once(text, old_estimate, new_estimate, "temporal working-set bridge accounting")

    text = replace_once(
        text,
        '''        creationflags=creationflags,
        check=False,
    )
''',
        '''        creationflags=creationflags,
        timeout=15,
        check=False,
    )
''',
        "ffprobe timeout",
    )

    old_locals = '''    cancel = cancel_event or threading.Event()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    decoder: subprocess.Popen | None = None
    encoder: subprocess.Popen | None = None
    frames_written = 0
'''
    new_locals = '''    cancel = cancel_event or threading.Event()
    decoder: subprocess.Popen | None = None
    encoder: subprocess.Popen | None = None
    cancel_watcher_stop = threading.Event()
    cancel_watcher: threading.Thread | None = None
    frames_written = 0
'''
    text = replace_once(text, old_locals, new_locals, "temporal cancellation locals")

    old_spawn = '''            decoder = subprocess.Popen(
                decoder_command,
                stdout=subprocess.PIPE,
                stderr=decoder_log,
                creationflags=creationflags,
            )
            encoder = subprocess.Popen(
                encoder_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=encoder_log,
                creationflags=creationflags,
            )
            if decoder.stdout is None or encoder.stdin is None:
                raise RuntimeError("Não foi possível abrir os pipes do Preview temporal.")

            window: deque[tuple[int, np.ndarray]] = deque()
'''
    new_spawn = '''            if cancel.is_set():
                raise TemporalPreviewCancelled("Exportação temporal Preview cancelada.")
            decoder = subprocess.Popen(
                decoder_command,
                stdout=subprocess.PIPE,
                stderr=decoder_log,
                **popen_group_kwargs(),
            )
            encoder = subprocess.Popen(
                encoder_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=encoder_log,
                **popen_group_kwargs(),
            )
            if decoder.stdout is None or encoder.stdin is None:
                raise RuntimeError("Não foi possível abrir os pipes do Preview temporal.")

            def watch_cancellation() -> None:
                # Rawvideo read/write calls are intentionally blocking to keep
                # memory bounded. This watcher is the escape hatch: cancelling
                # the Preview tears down both process groups, which closes the
                # pipes and unblocks the streaming worker immediately.
                while not cancel_watcher_stop.wait(0.05):
                    if not cancel.is_set():
                        continue
                    for process in (decoder, encoder):
                        if process is not None:
                            terminate_process_tree(process, grace_seconds=1.0)
                    return

            cancel_watcher = threading.Thread(
                target=watch_cancellation,
                name="cinepulse-preview-temporal-cancel",
                daemon=True,
            )
            cancel_watcher.start()

            window: deque[tuple[int, np.ndarray]] = deque()
'''
    text = replace_once(text, old_spawn, new_spawn, "temporal process groups and watcher")

    old_final = '''            return TemporalStreamReport(
                frames_written=frames_written,
                applied_regions=applied_regions,
                fallback_regions=fallback_regions,
            )
        finally:
            for process in (decoder, encoder):
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
'''
    new_final = '''            return TemporalStreamReport(
                frames_written=frames_written,
                applied_regions=applied_regions,
                fallback_regions=fallback_regions,
            )
        except (BrokenPipeError, OSError, ValueError) as exc:
            if cancel.is_set():
                raise TemporalPreviewCancelled("Exportação temporal Preview cancelada.") from exc
            raise
        finally:
            cancel_watcher_stop.set()
            for process in (decoder, encoder):
                if process is not None and process.poll() is None:
                    terminate_process_tree(process, grace_seconds=1.0)
            if cancel_watcher is not None and cancel_watcher is not threading.current_thread():
                cancel_watcher.join(timeout=2.0)
'''
    text = replace_once(text, old_final, new_final, "temporal safe finalization")
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_export() -> None:
    path = Path("src/cinepulse/restoration_export.py")
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'from .restoration_temporal_export import TemporalPreviewCancelled, stream_temporal_preview\n',
        'from .restoration_temporal_export import TemporalPreviewCancelled, stream_temporal_preview\nfrom .process_control import popen_group_kwargs, terminate_process_tree\n',
        "export process-control import",
    )

    old_terminate = '''def _terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
'''
    new_terminate = '''def _terminate_process(process: subprocess.Popen) -> None:
    terminate_process_tree(process, grace_seconds=1.0)
'''
    text = replace_once(text, old_terminate, new_terminate, "export tree termination")

    old_flags = '''    process: subprocess.Popen | None = None
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

    try:
'''
    new_flags = '''    process: subprocess.Popen | None = None

    try:
'''
    text = replace_once(text, old_flags, new_flags, "export process flags")

    old_popen = '''                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )
'''
    new_popen = '''                text=True,
                encoding="utf-8",
                errors="replace",
                **popen_group_kwargs(),
            )
'''
    text = replace_once(text, old_popen, new_popen, "export process group")
    path.write_text(text, encoding="utf-8", newline="\n")


patch_temporal()
patch_export()
print("final-audit temporal cancellation hardening applied")
