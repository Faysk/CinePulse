from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from cinepulse.render_history import RenderHistory, export_redacted_history


@dataclass
class Settings:
    video: str = r"C:\Users\Faysk\Videos\source.mp4"
    audio: str = r"C:\Users\Faysk\Music\song.wav"
    output: str = r"D:\Renders\final.mp4"
    effects: set[str] = None

    def __post_init__(self):
        if self.effects is None:
            self.effects = {"Aurora"}


class RenderHistoryTests(TestCase):
    def test_start_creates_job_and_log(self):
        with TemporaryDirectory() as temp:
            history = RenderHistory.start(Path(temp), Settings(), preview=False, app_version="1.0.0rc5")
            self.assertTrue((history.job_dir / "job.json").is_file())
            self.assertTrue((history.job_dir / "render.log").is_file())
            payload = json.loads((history.job_dir / "job.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "running")
            self.assertEqual(payload["settings"]["effects"], ["Aurora"])

    def test_contract_artifacts_and_finish_are_persisted(self):
        with TemporaryDirectory() as temp:
            history = RenderHistory.start(Path(temp), Settings(), preview=False, app_version="x")
            history.write_plan({"fingerprint": "abc"})
            history.write_contracts(delivery={"container": "MP4"}, storage={"peak": 2.5})
            history.write_verification({"passed": True})
            history.finish("success", output="final.mp4", report="report.txt")
            for name in ("plan.json", "contracts.json", "verification.json"):
                self.assertTrue((history.job_dir / name).is_file())
            job = json.loads((history.job_dir / "job.json").read_text(encoding="utf-8"))
            self.assertEqual(job["status"], "success")
            self.assertTrue(job["finished_at"])
            self.assertEqual(job["report"], "report.txt")

    def test_job_ids_are_unique(self):
        with TemporaryDirectory() as temp:
            a = RenderHistory.start(Path(temp), Settings(), preview=True, app_version="x")
            b = RenderHistory.start(Path(temp), Settings(), preview=True, app_version="x")
            self.assertNotEqual(a.job_id, b.job_id)

    def test_append_log_is_persistent(self):
        with TemporaryDirectory() as temp:
            history = RenderHistory.start(Path(temp), Settings(), preview=False, app_version="x")
            history.append_log("Comando FFmpeg: ffmpeg -i input output")
            text = history.log_path.read_text(encoding="utf-8")
            self.assertIn("Comando FFmpeg", text)

    def test_support_export_redacts_absolute_paths(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            history = RenderHistory.start(root / "history", Settings(), preview=False, app_version="x")
            history.append_log(r"Fonte C:\Users\Faysk\Videos\source.mp4")
            destination = root / "support.zip"
            export_redacted_history(history.job_dir, destination)
            with zipfile.ZipFile(destination) as archive:
                log = archive.read("render.log").decode("utf-8")
                job = archive.read("job.json").decode("utf-8")
            self.assertNotIn(r"C:\Users\Faysk\Videos", log)
            self.assertNotIn(r"C:\Users\Faysk\Videos", job)
            self.assertIn("<PATH>", log)


if __name__ == "__main__":
    import unittest
    unittest.main()
