import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from cinepulse.studio import RenderSettings, VideoOptimizerStudio
from cinepulse.state_store import PRESETS_SCHEMA, QUEUE_SCHEMA
from cinepulse.ui.queue_lab import item_progress


class _StatusSink:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


class QueuePersistenceTests(TestCase):
    def settings(self):
        return RenderSettings(
            mode="Melhorar vídeo original — manter duração e conteúdo",
            video=r"C:\media\clip.mp4",
            audio="",
            output=r"C:\renders\clip.mp4",
            resolution="4K UHD",
            fps=60,
            aspect="16:9 — horizontal",
            enhancement="Upscale simples — Lanczos de alta qualidade",
            fit_mode="Preencher a tela — cortar bordas",
            use_cpu=False,
            preserve_audio=True,
            effects={"Aurora"},
            color="#42D8FF",
            intensity=1.0,
            occupancy=0.65,
            audio_focus="Graves e batidas",
            reaction_smoothing=0.82,
            reaction_expression=0.82,
            auto_loop=True,
            dynamic_sections=True,
            section_dynamics=0.75,
            transition="Corte seco",
            transition_duration=0.75,
            preview_seconds=10,
            audio_mode="Preservar dinâmica original",
            interpolation="Movimento suave — FFmpeg",
            cpu_threads=8,
            minimum_free_gb=20.0,
            quality_check=True,
            visual_direction="Cinematográfica",
            comparison_preview=True,
            use_stems=False,
        )

    def bare_studio(self):
        studio = object.__new__(VideoOptimizerStudio)
        studio._queue_items = []
        studio._queue_serial = 0
        studio._queue_state_read_only = False
        studio._queue_state_error = ""
        studio._presets_state_read_only = False
        studio._presets_state_error = ""
        studio._state_schema_warning_signature = None
        studio.status = _StatusSink()
        studio._refresh_queue_tree = lambda *args, **kwargs: None
        studio._log = lambda *args, **kwargs: None
        studio._show_log = lambda: None
        return studio

    def test_roundtrip_persists_stage_and_recovers_active_item_safely(self):
        with TemporaryDirectory() as temporary:
            config = Path(temporary)
            queue_file = config / "queue.json"
            writer = self.bare_studio()
            writer._queue_items = [{
                "id": 7,
                "settings": self.settings(),
                "status": "Renderizando",
                "error": "",
                "report": "",
                "progress": 52.4,
                "stage": "Interpolando com RIFE",
            }]
            with patch("cinepulse.studio.CONFIG_DIR", config), patch("cinepulse.studio.QUEUE_FILE", queue_file):
                writer._save_queue()
                raw = json.loads(queue_file.read_text(encoding="utf-8"))
                self.assertEqual(raw["schema"], 2)
                self.assertEqual(raw["kind"], "cinepulse.queue")
                self.assertEqual(raw["items"][0]["progress"], 52.4)
                self.assertEqual(raw["items"][0]["stage"], "Interpolando com RIFE")

                reader = self.bare_studio()
                reader._load_queue()

            restored = reader._queue_items[0]
            self.assertEqual(restored["status"], "Aguardando")
            self.assertEqual(restored["progress"], 0.0)
            self.assertEqual(restored["stage"], "Recuperado após encerramento")
            self.assertIn("reiniciado com segurança", restored["error"])
            self.assertIn("Fila restaurada", reader.status.value)

    def test_future_queue_schema_is_read_only_and_never_overwritten_by_studio(self):
        with TemporaryDirectory() as temporary:
            config = Path(temporary)
            queue_file = config / "queue.json"
            original = json.dumps(
                {"schema": QUEUE_SCHEMA + 10, "kind": "cinepulse.queue.vNext", "items": [{"id": 99}]},
                ensure_ascii=False,
            )
            queue_file.write_text(original, encoding="utf-8")

            studio = self.bare_studio()
            with patch("cinepulse.studio.CONFIG_DIR", config), patch("cinepulse.studio.QUEUE_FILE", queue_file):
                studio._load_queue()
                self.assertTrue(studio._queue_state_read_only)
                studio._queue_items = [{
                    "id": 1,
                    "settings": self.settings(),
                    "status": "Aguardando",
                    "error": "",
                    "report": "",
                    "history": "",
                    "progress": 0.0,
                    "stage": "Sessão local",
                }]
                self.assertFalse(studio._save_queue())

            self.assertEqual(original, queue_file.read_text(encoding="utf-8"))
            self.assertIn("somente-leitura", studio.status.value)

    def test_future_presets_schema_is_read_only_and_never_overwritten_by_studio(self):
        with TemporaryDirectory() as temporary:
            config = Path(temporary)
            presets_file = config / "presets.json"
            original = json.dumps(
                {"schema": PRESETS_SCHEMA + 10, "kind": "cinepulse.presets.vNext", "items": {"Future": {"fps": 240}}},
                ensure_ascii=False,
            )
            presets_file.write_text(original, encoding="utf-8")

            studio = self.bare_studio()
            with patch("cinepulse.studio.CONFIG_DIR", config), patch("cinepulse.studio.PRESETS_FILE", presets_file):
                self.assertEqual({}, studio._load_custom_presets())
                self.assertTrue(studio._presets_state_read_only)
                studio._custom_presets = {"Old": {"fps": 60}}
                self.assertFalse(studio._save_custom_presets())

            self.assertEqual(original, presets_file.read_text(encoding="utf-8"))
            self.assertIn("somente-leitura", studio.status.value)

    def test_old_queue_without_phase5_metadata_remains_compatible(self):
        with TemporaryDirectory() as temporary:
            config = Path(temporary)
            queue_file = config / "queue.json"
            settings = self.settings()
            payload = [{
                "id": 1,
                "settings": {
                    **settings.__dict__,
                    "effects": sorted(settings.effects),
                },
                "status": "Concluído",
                "error": "",
                "report": "report.json",
            }]
            queue_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            reader = self.bare_studio()
            with patch("cinepulse.studio.CONFIG_DIR", config), patch("cinepulse.studio.QUEUE_FILE", queue_file):
                reader._load_queue()
            restored = reader._queue_items[0]
            self.assertEqual(restored["status"], "Concluído")
            self.assertEqual(item_progress(restored), 100.0)
            self.assertEqual(restored["stage"], "")


if __name__ == "__main__":
    import unittest
    unittest.main()
