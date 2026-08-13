from __future__ import annotations

import json
import queue
import time
from pathlib import Path
from tkinter import Tk

from cinepulse.paths import PATHS, ensure_runtime_directories
from cinepulse.studio import VideoOptimizerStudio
from tests.integration_smoke import create_fixtures, settings_for


def main() -> None:
    ensure_runtime_directories()
    run_root = PATHS.data / "test-runs" / time.strftime("%Y%m%d_%H%M%S_phase7")
    fixture_root = run_root / "fixtures"
    output_root = run_root / "outputs"
    output_root.mkdir(parents=True, exist_ok=True)
    video, music = create_fixtures(fixture_root)
    output = output_root / "phase7-deep.mp4"

    root = Tk()
    root.withdraw()
    app = VideoOptimizerStudio(root)
    try:
        settings = settings_for("basic", video, music, output)
        settings.deep_verify = True
        app._cancelled = False
        app._worker(settings, preview=False)

        events: list[tuple] = []
        while True:
            try:
                events.append(app._events.get_nowait())
            except queue.Empty:
                break

        errors = [event for event in events if event and event[0] == "error"]
        if errors:
            raise RuntimeError(str(errors[-1]))
        done = next((event for event in events if event and event[0] == "done"), None)
        if done is None:
            raise RuntimeError(f"Worker sem evento done: {events!r}")

        history_dir = Path(str(done[5]))
        required = {"job.json", "render.log", "plan.json", "contracts.json", "verification.json"}
        present = {path.name for path in history_dir.iterdir() if path.is_file()}
        missing = required - present
        if missing:
            raise RuntimeError(f"Histórico incompleto: {sorted(missing)}")

        verification_doc = json.loads((history_dir / "verification.json").read_text(encoding="utf-8"))
        verification = verification_doc.get("verification", verification_doc)
        job = json.loads((history_dir / "job.json").read_text(encoding="utf-8"))
        if verification.get("mode") != "deep" or not verification.get("passed"):
            raise RuntimeError(f"Deep verify não passou: {verification}")
        if verification.get("decoded_to_eof") is not True:
            raise RuntimeError(f"Decode até EOF não confirmado: {verification}")
        if verification.get("cfr") is not True:
            raise RuntimeError(f"CFR não confirmado: {verification}")
        if abs(int(verification.get("frame_count") or 0) - int(verification.get("expected_frame_count") or 0)) > 2:
            raise RuntimeError(f"Contagem de quadros divergente: {verification}")
        if job.get("status") != "success" or job.get("settings", {}).get("deep_verify") is not True:
            raise RuntimeError(f"job.json inconsistente: {job}")

        result = {
            "output": str(output),
            "history": str(history_dir),
            "mode": verification.get("mode"),
            "decoded_to_eof": verification.get("decoded_to_eof"),
            "cfr": verification.get("cfr"),
            "frames": f"{verification.get('frame_count')}/{verification.get('expected_frame_count')}",
            "av_sync_delta": verification.get("av_sync_delta"),
        }
        print("CINEPULSE_PHASE7_VERIFICATION_OK " + json.dumps(result, ensure_ascii=False))
    finally:
        root.destroy()


if __name__ == "__main__":
    main()
