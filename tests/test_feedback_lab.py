import unittest

from cinepulse.ui.feedback_lab import (
    FeedbackEntry,
    FeedbackHistory,
    classify_failure,
    compact_detail,
    normalize_severity,
    severity_meta,
)


class FeedbackLabTests(unittest.TestCase):
    def test_severity_is_normalized_and_has_meta(self):
        self.assertEqual(normalize_severity("SUCCESS"), "success")
        self.assertEqual(normalize_severity("wat"), "info")
        self.assertEqual(severity_meta("error")["badge"], "BLOQUEADO")

    def test_compact_detail_flattens_and_limits(self):
        self.assertEqual(compact_detail("linha 1\n\nlinha 2"), "linha 1 linha 2")
        compact = compact_detail("x" * 300, limit=20)
        self.assertTrue(compact.endswith("…"))
        self.assertEqual(len(compact), 20)

    def test_failure_classification_prioritizes_actionable_causes(self):
        disk = classify_failure("No space left on device")
        self.assertEqual(disk.title, "Espaço insuficiente para continuar")
        self.assertEqual(disk.primary_action, "Rever projeto")

        ai = classify_failure("Real-ESRGAN falhou ao carregar modelo")
        self.assertEqual(ai.primary_action, "Abrir IA local")

        rife = classify_failure("RIFE falhou")
        self.assertEqual(rife.primary_action, "Rever qualidade")

    def test_history_is_bounded_and_suppresses_consecutive_duplicates(self):
        history = FeedbackHistory(max_items=2)
        first = FeedbackEntry("success", "A", "ok")
        self.assertTrue(history.add(first))
        self.assertFalse(history.add(first))
        history.add(FeedbackEntry("warning", "B", "atenção"))
        history.add(FeedbackEntry("error", "C", "erro"))
        self.assertEqual([entry.title for entry in history.items()], ["B", "C"])


if __name__ == "__main__":
    unittest.main()
