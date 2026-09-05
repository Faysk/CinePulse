from pathlib import Path

path = Path("src/cinepulse/restoration_export.py")
text = path.read_text(encoding="utf-8")
old = '''def _terminate_process(process: subprocess.Popen) -> None:
    terminate_process_tree(process, grace_seconds=1.0)
'''
new = '''def _terminate_process(process: subprocess.Popen) -> None:
    # Production Popen objects expose pid and use the shared tree-safe path.
    # Lightweight test/fake process objects keep the historical direct fallback.
    if getattr(process, "pid", None) is not None:
        terminate_process_tree(process, grace_seconds=1.0)
        return
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
'''
if text.count(old) != 1:
    raise SystemExit(f"Preview export termination anchor mismatch: {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
