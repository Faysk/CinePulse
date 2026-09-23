from __future__ import annotations

import json
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest import mock

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
    def test_manifest_source_identity_changes_on_same_size_same_mtime_replacement(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.mp4"
            source.write_bytes(b"video-v1")
            settings = Settings(video=str(source))
            first = RenderHistory.start(root / "history-a", settings, preview=False, app_version="x")
            first_manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
            stat = source.stat()
            source.write_bytes(b"video-v2")
            os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            second = RenderHistory.start(root / "history-b", settings, preview=False, app_version="x")
            second_manifest = json.loads(second.manifest_path.read_text(encoding="utf-8"))
            self.assertNotEqual(
                first_manifest["source"]["content"]["content_sha256"],
                second_manifest["source"]["content"]["content_sha256"],
            )

    def test_start_creates_job_log_and_shadow_manifest(self):
        with TemporaryDirectory() as temp:
            history = RenderHistory.start(Path(temp), Settings(), preview=False, app_version="1.0.0rc5")
            self.assertTrue((history.job_dir / "job.json").is_file())
            self.assertTrue((history.job_dir / "render.log").is_file())
            self.assertTrue((history.job_dir / "manifest.json").is_file())
            payload = json.loads((history.job_dir / "job.json").read_text(encoding="utf-8"))
            manifest = json.loads((history.job_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "running")
            self.assertEqual(payload["settings"]["effects"], ["Aurora"])
            self.assertEqual("preflight", manifest["state"])
            self.assertEqual(history.job_id, manifest["job_id"])

    def test_history_metadata_is_fsynced_and_leaves_no_atomic_temps(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with mock.patch("cinepulse.render_history.os.fsync", wraps=__import__("os").fsync) as fsync:
                history = RenderHistory.start(root, Settings(), preview=False, app_version="x")
                history.write_plan({"fingerprint": "abc"})
                history.write_contracts(verification_expected={"fps": 60})
                history.write_verification({"passed": True})
            self.assertGreaterEqual(fsync.call_count, 4)
            self.assertEqual([], list(history.job_dir.glob("*.tmp-*")))
            self.assertEqual("abc", json.loads((history.job_dir / "plan.json").read_text(encoding="utf-8"))["fingerprint"])

    def test_contract_artifacts_finish_and_manifest_are_persisted(self):
        with TemporaryDirectory() as temp:
            history = RenderHistory.start(Path(temp), Settings(), preview=False, app_version="x")
            history.write_plan({"fingerprint": "abc"})
            history.write_contracts(
                delivery={"container": "MP4"},
                storage={"peak": 2.5},
                verification_expected={"width": 3840, "height": 2160, "fps": 60},
            )
            history.write_verification({"passed": True})
            history.finish("success", output="final.mp4", report="report.txt")
            for name in ("plan.json", "contracts.json", "verification.json"):
                self.assertTrue((history.job_dir / name).is_file())
            job = json.loads((history.job_dir / "job.json").read_text(encoding="utf-8"))
            manifest = json.loads((history.job_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(job["status"], "success")
            self.assertTrue(job["finished_at"])
            self.assertEqual(job["report"], "report.txt")
            self.assertEqual("complete", manifest["state"])
            self.assertEqual("abc", manifest["render_plan"]["fingerprint"])
            self.assertEqual(3840, manifest["expectation"]["width"])

    def test_error_marks_manifest_blocked_and_preserves_error(self):
        with TemporaryDirectory() as temp:
            history = RenderHistory.start(Path(temp), Settings(), preview=False, app_version="x")
            history.write_plan({"fingerprint": "abc"})
            history.finish("error", error="GPU vanished")
            manifest = history.job_store.load()
            self.assertEqual("blocked", manifest.state)
            self.assertEqual("RENDER-ERROR", manifest.last_error["code"])
            self.assertIn("GPU vanished", manifest.last_error["message"])

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

    def test_support_export_redacts_absolute_paths_in_manifest_too(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            history = RenderHistory.start(root / "history", Settings(), preview=False, app_version="x")
            history.append_log(r"Fonte C:\Users\Faysk\Videos\source.mp4")
            destination = root / "support.zip"
            export_redacted_history(history.job_dir, destination)
            with zipfile.ZipFile(destination) as archive:
                log = archive.read("render.log").decode("utf-8")
                job = archive.read("job.json").decode("utf-8")
                manifest = archive.read("manifest.json").decode("utf-8")
            self.assertNotIn(r"C:\Users\Faysk\Videos", log)
            self.assertNotIn(r"C:\Users\Faysk\Videos", job)
            self.assertNotIn(r"C:\Users\Faysk\Videos", manifest)
            self.assertIn("<PATH>", log)


if __name__ == "__main__":
    import unittest
    unittest.main()
