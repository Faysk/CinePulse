from types import SimpleNamespace
import unittest

from cinepulse.ui.queue_lab import (
    can_move,
    can_retry,
    effects_text,
    item_progress,
    processing_text,
    profile_text,
    project_name,
    status_text,
    summarize_queue,
)


class QueueLabTests(unittest.TestCase):
    def settings(self, **overrides):
        data = dict(
            video=r"C:\media\clip.mp4",
            output=r"C:\renders\clip_final.mp4",
            resolution="4K UHD",
            fps=60,
            aspect="16:9 — horizontal",
            use_cpu=False,
            enhancement="Upscale por IA — Real-ESRGAN x2",
            interpolation="RIFE IA — movimento natural",
            effects={"Aurora", "Partículas musicais"},
        )
        data.update(overrides)
        return SimpleNamespace(**data)

    def test_queue_summary_groups_operational_states(self):
        summary = summarize_queue([
            {"status": "Aguardando"}, {"status": "Renderizando"},
            {"status": "Concluído"}, {"status": "Erro"}, {"status": "Cancelado"},
        ])
        self.assertEqual((summary.total, summary.waiting, summary.active, summary.done, summary.attention), (5, 1, 1, 1, 2))
        self.assertEqual(summary.remaining, 4)

    def test_progress_and_status_are_honest(self):
        self.assertEqual(item_progress({"status": "Concluído", "progress": 12}), 100)
        self.assertEqual(item_progress({"status": "Aguardando", "progress": 90}), 0)
        self.assertEqual(status_text({"status": "Renderizando", "progress": 48.7}), "Renderizando • 49%")
        self.assertTrue(can_retry({"status": "Erro"}))
        self.assertFalse(can_retry({"status": "Concluído"}))

    def test_presentation_uses_real_settings(self):
        settings = self.settings()
        self.assertEqual(project_name(settings), "clip")
        self.assertIn("4K UHD", profile_text(settings))
        self.assertIn("60 fps", profile_text(settings))
        self.assertIn("Aceleração automática", processing_text(settings))
        self.assertIn("Aurora", effects_text(settings))

    def test_reorder_boundaries(self):
        items = [{"id": 1}, {"id": 2}, {"id": 3}]
        self.assertFalse(can_move(items, 1, -1))
        self.assertTrue(can_move(items, 1, 1))
        self.assertTrue(can_move(items, 3, -1))
        self.assertFalse(can_move(items, 3, 1))


if __name__ == "__main__":
    unittest.main()
