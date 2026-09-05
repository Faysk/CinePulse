from pathlib import Path

path = Path("src/cinepulse/composer_export.py")
text = path.read_text(encoding="utf-8")

old_vf = '''    vf = (
        f"zscale=matrixin=bt709:primariesin=bt709:transferin=bt709:rangein={range_in}:"
        "matrix=gbr:primaries=bt709:transfer=bt709:range=full,format=rgba"
    )'''
new_vf = '''    vf = (
        f"zscale=matrixin=709:primariesin=709:transferin=709:rangein={range_in}:"
        "matrix=gbr:primaries=709:transfer=709:range=full,format=rgba"
    )'''
if old_vf not in text:
    raise SystemExit("zscale anchor missing")
text = text.replace(old_vf, new_vf, 1)

old_short = '''                raw = _read_exact(decoder.stdout, frame_bytes)
                if len(raw) != frame_bytes:
                    raise RuntimeError(f"base decoder produced {len(raw)}/{frame_bytes} bytes at frame {index}")'''
new_short = '''                raw = _read_exact(decoder.stdout, frame_bytes)
                if len(raw) != frame_bytes:
                    decode_stderr.flush()
                    code = decoder.poll()
                    details = decoder_log.read_text(encoding="utf-8", errors="replace")[-4000:]
                    suffix = f"; decoder exited with {code}" if code is not None else ""
                    raise RuntimeError(
                        (details.strip() + suffix) if details.strip() else
                        f"base decoder produced {len(raw)}/{frame_bytes} bytes at frame {index}{suffix}"
                    )'''
if old_short not in text:
    raise SystemExit("short-read anchor missing")
text = text.replace(old_short, new_short, 1)

old_finally = '''    finally:
        terminate_process_tree(decoder, logger, grace_seconds=1.5)
        terminate_process_tree(encoder, logger, grace_seconds=1.5)
        shutil.rmtree(temporary_dir, ignore_errors=True)'''
new_finally = '''    finally:
        terminate_process_tree(decoder, logger, grace_seconds=1.5)
        terminate_process_tree(encoder, logger, grace_seconds=1.5)
        for stream in (
            getattr(decoder, "stdout", None),
            getattr(encoder, "stdin", None),
        ):
            try:
                if stream is not None and not stream.closed:
                    stream.close()
            except OSError:
                pass
        shutil.rmtree(temporary_dir, ignore_errors=True)'''
if old_finally not in text:
    raise SystemExit("cleanup anchor missing")
text = text.replace(old_finally, new_finally, 1)

path.write_text(text, encoding="utf-8", newline="\n")
