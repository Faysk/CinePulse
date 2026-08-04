from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from tkinter import Tk

from cinepulse.paths import PATHS, ensure_runtime_directories
from cinepulse.process_control import terminate_process_tree
from cinepulse.studio import (
    ASPECT_LANDSCAPE,
    ENHANCE_NONE,
    FIT_COVER,
    MODE_ORIGINAL,
    RenderSettings,
    VideoOptimizerStudio,
)

from integration_smoke import create_fixtures


def main() -> None:
    ensure_runtime_directories()
    root_dir = PATHS.data / "test-runs" / time.strftime("%Y%m%d_%H%M%S_cancel")
    video, _music = create_fixtures(root_dir / "fixtures")
    output = root_dir / "preserve-existing.mp4"
    output.write_bytes(b"ORIGINAL_OUTPUT_MUST_SURVIVE")
    root = Tk()
    root.withdraw()
    app = VideoOptimizerStudio(root)
    settings = RenderSettings(
        mode=MODE_ORIGINAL, video=str(video), audio="", output=str(output), resolution="8K UHD", fps=120,
        aspect=ASPECT_LANDSCAPE, enhancement=ENHANCE_NONE, fit_mode=FIT_COVER, use_cpu=True,
        preserve_audio=True, effects=set(), color="#43D6FF", intensity=0.75, occupancy=0.55,
        audio_focus="Graves", reaction_smoothing=0.8, reaction_expression=0.8, auto_loop=False,
        dynamic_sections=False, section_dynamics=0.7, transition="Corte seco — original",
        transition_duration=0.5, preview_seconds=2, audio_mode="Preservar dinâmica original",
        interpolation="Movimento suave — FFmpeg", cpu_threads=4, minimum_free_gb=1,
        quality_check=False, visual_direction="Personalizada", comparison_preview=False,
    )
    worker = threading.Thread(target=app._worker, args=(settings, False), daemon=True)
    worker.start()
    deadline = time.monotonic() + 15
    while app._process is None and time.monotonic() < deadline:
        time.sleep(0.05)
    if app._process is None:
        raise RuntimeError("Nenhum processo foi iniciado para o teste de cancelamento.")
    app._cancelled = True
    terminate_process_tree(app._process)
    worker.join(timeout=30)
    if worker.is_alive():
        raise RuntimeError("O worker não encerrou após o cancelamento.")
    events = []
    while True:
        try:
            events.append(app._events.get_nowait())
        except queue.Empty:
            break
    root.destroy()
    if not any(event[0] == "cancelled" for event in events):
        raise RuntimeError(f"Evento de cancelamento ausente: {events[-5:]}")
    if output.read_bytes() != b"ORIGINAL_OUTPUT_MUST_SURVIVE":
        raise RuntimeError("O arquivo anterior foi alterado durante o cancelamento.")
    partials = list(output.parent.glob(".*.partial-*.mp4"))
    if partials:
        raise RuntimeError(f"Saídas parciais não foram limpas: {partials}")
    if (PATHS.locks / "render.json").exists():
        raise RuntimeError("O diário de render permaneceu após o cancelamento.")
    print("CINEPULSE_CANCEL_RECOVERY_OK")


if __name__ == "__main__":
    main()

