from __future__ import annotations

import unittest

from cinepulse.ui.ai_lab import (
    capability_state,
    human_bytes,
    inventory_summary,
    module_detail,
    progress_from_log,
    selected_download,
    visible_items,
)


class AiLabTests(unittest.TestCase):
    def _item(self, key: str, *, installed: bool = False, experimental: bool = False, license: str = "") -> dict:
        return {
            "key": key,
            "name": key,
            "purpose": "purpose",
            "installed": installed,
            "activation": "Integrado e validado",
            "size_bytes": 1234 if installed else 0,
            "installable": True,
            "installer_component": key,
            "experimental": experimental,
            "license": license,
            "download_bytes": 1024**3,
        }

    def test_integrated_ready_is_presented_as_render_capability(self) -> None:
        state = capability_state(self._item("rife", installed=True))
        self.assertEqual(state["code"], "ready")
        self.assertEqual(state["label"], "Pronto no render")
        self.assertEqual(state["level"], "ok")

    def test_rife_missing_exposes_real_ffmpeg_fallback(self) -> None:
        state = capability_state(self._item("rife", installed=False))
        self.assertIn("fallback FFmpeg", state["label"])
        detail = module_detail(self._item("rife", installed=False))
        self.assertIn("FFmpeg", detail["missing_effect"])
        self.assertNotIn("bloque", detail["missing_effect"].lower())

    def test_experimental_installed_never_becomes_render_ready(self) -> None:
        item = self._item("ltx2", installed=True, experimental=True, license="LTX-2 Community License; restrições")
        state = capability_state(item, experimental_enabled=True)
        self.assertEqual(state["code"], "experimental-installed")
        self.assertIn("fora do render", state["label"])
        detail = module_detail(item, experimental_enabled=True)
        self.assertIn("Ainda não integrado", detail["render_usage"])
        self.assertIn("restrições", detail["license_warning"].lower())

    def test_experimental_download_requires_explicit_mode(self) -> None:
        item = self._item("sam2", experimental=True)
        locked = capability_state(item, experimental_enabled=False)
        enabled = capability_state(item, experimental_enabled=True)
        self.assertEqual(locked["code"], "experimental-locked")
        self.assertEqual(enabled["code"], "experimental-available")

    def test_summary_filters_and_selection_are_deterministic(self) -> None:
        items = [
            self._item("realesrgan", installed=True),
            self._item("rife"),
            self._item("basicvsrpp", experimental=True),
            self._item("sam2", installed=True, experimental=True),
        ]
        summary = inventory_summary(items)
        self.assertEqual(summary["integrated_ready"], 1)
        self.assertEqual(summary["integrated_missing"], 1)
        self.assertEqual(summary["experimental_installed"], 1)
        self.assertEqual([item["key"] for item in visible_items(items, "No render")], ["realesrgan", "rife"])
        self.assertEqual([item["key"] for item in visible_items(items, "Experimentais")], ["basicvsrpp", "sam2"])
        download = selected_download(items, {"rife", "basicvsrpp", "sam2"})
        self.assertEqual(download["count"], 2)  # installed SAM 2 does not re-download
        self.assertEqual(download["experimental_count"], 1)
        self.assertEqual(download["bytes"], 2 * 1024**3)

    def test_installer_progress_parser_is_local_and_conservative(self) -> None:
        self.assertEqual(progress_from_log("checkpoint.bin: 40%"), 40)
        self.assertEqual(progress_from_log("etapa 2/3 • arquivo 100%"), 100)
        self.assertIsNone(progress_from_log("baixando e verificando…"))
        self.assertIsNone(progress_from_log("erro 140% impossível"))

    def test_human_bytes_keeps_large_model_sizes_readable(self) -> None:
        self.assertEqual(human_bytes(0), "0 B")
        self.assertEqual(human_bytes(1024**3), "1.00 GB")
        self.assertEqual(human_bytes(47 * 1024**3), "47.0 GB")


if __name__ == "__main__":
    unittest.main()
