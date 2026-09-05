from __future__ import annotations

import json
from pathlib import Path

import cinepulse.render_history as render_history


class FakeTelemetry:
    instances: list["FakeTelemetry"] = []

    def __init__(self, destination: Path, **_kwargs) -> None:
        self.destination = Path(destination)
        self.stages: list[tuple[str, str]] = []
        self.started = False
        FakeTelemetry.instances.append(self)

    def start(self):
        self.started = True
        return self

    def mark_stage(self, stage: str, detail: str = "") -> None:
        self.stages.append((stage, detail))

    def stop(self, *, status: str = "finished"):
        payload = {"schema": 1, "status": status, "summary": {"wall_seconds": 1.25}}
        self.destination.write_text(json.dumps(payload), encoding="utf-8")
        return payload


def test_render_history_records_hardware_evidence(monkeypatch, tmp_path: Path) -> None:
    FakeTelemetry.instances.clear()
    monkeypatch.setattr(render_history, "HardwareTelemetrySession", FakeTelemetry)
    history = render_history.RenderHistory.start(
        tmp_path / "renders",
        {"effects": []},
        preview=False,
        app_version="test",
    )
    history.append_log("[IA 2/3] Real-ESRGAN em lote")
    history.finish("cancelled")

    telemetry = FakeTelemetry.instances[-1]
    assert telemetry.started is True
    assert telemetry.stages[-1] == ("IA 2/3", "Real-ESRGAN em lote")
    assert (history.job_dir / "hardware-telemetry.json").is_file()

    job = json.loads(history.job_path.read_text(encoding="utf-8"))
    assert job["hardware_telemetry"] == "hardware-telemetry.json"
    assert job["hardware_summary"]["wall_seconds"] == 1.25
