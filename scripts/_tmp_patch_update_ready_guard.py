from pathlib import Path

path = Path("src/cinepulse/studio.py")
text = path.read_text(encoding="utf-8")

old = (
    "        self._available_update: update_manager.UpdateInfo | None = None\n"
    "        self._update_check_running = False\n"
)
new = (
    "        self._available_update: update_manager.UpdateInfo | None = None\n"
    "        self._prepared_update: tuple[update_manager.UpdateInfo, str] | None = None\n"
    "        self._update_check_running = False\n"
)
if text.count(old) != 1:
    raise SystemExit("prepared update state anchor mismatch")
text = text.replace(old, new, 1)

old = (
    "    def _hide_update_cta(self) -> None:\n"
    "        self._available_update = None\n"
)
new = (
    "    def _hide_update_cta(self) -> None:\n"
    "        self._available_update = None\n"
    "        self._prepared_update = None\n"
)
if text.count(old) != 1:
    raise SystemExit("hide CTA anchor mismatch")
text = text.replace(old, new, 1)

old = (
    "        if hasattr(self, \"header_update_button\"):\n"
    "            self.header_update_button.configure(state=\"disabled\")\n"
    "        if hasattr(self, \"update_button\"):\n"
    "            self.update_button.configure(state=\"disabled\")\n"
    "        self._stage_update(info)\n"
)
new = (
    "        prepared = self._prepared_update\n"
    "        if prepared is not None and prepared[0].version == info.version:\n"
    "            self._launch_prepared_update(prepared[0], prepared[1])\n"
    "            return\n"
    "        if hasattr(self, \"header_update_button\"):\n"
    "            self.header_update_button.configure(state=\"disabled\")\n"
    "        if hasattr(self, \"update_button\"):\n"
    "            self.update_button.configure(state=\"disabled\")\n"
    "        self._stage_update(info)\n"
)
if text.count(old) != 1:
    raise SystemExit("apply updater anchor mismatch")
text = text.replace(old, new, 1)

old = (
    "    def _launch_prepared_update(self, info: update_manager.UpdateInfo, staged: str) -> None:\n"
    "        update_manager.launch_staged(info, Path(staged), APP_DIR, os.getpid())\n"
)
new = (
    "    def _launch_prepared_update(self, info: update_manager.UpdateInfo, staged: str) -> None:\n"
    "        if self._busy or self._queue_running or self._ai_installing:\n"
    "            self._prepared_update = (info, staged)\n"
    "            self._show_update_cta(info)\n"
    "            self._set_feedback(\n"
    "                \"info\", f\"CinePulse {info.version} pronto para instalar\",\n"
    "                \"O pacote já foi verificado. Termine o processamento atual e clique em Atualizar para instalar sem baixar novamente.\",\n"
    "                category=\"Atualização\", primary=(\"Atualizar quando livre\", self._apply_available_update),\n"
    "            )\n"
    "            return\n"
    "        self._prepared_update = None\n"
    "        update_manager.launch_staged(info, Path(staged), APP_DIR, os.getpid())\n"
)
if text.count(old) != 1:
    raise SystemExit("launch prepared anchor mismatch")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("CINEPULSE_UPDATE_READY_RACE_GUARDED")
