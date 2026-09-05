from pathlib import Path
import re

path = Path("src/cinepulse/studio.py")
text = path.read_text(encoding="utf-8")

old = (
    "        self._process: subprocess.Popen | None = None\n"
    "        self._cancelled = False\n"
    "        self._busy = False\n"
    "        self._started_at: float | None = None\n"
)
new = (
    "        self._process: subprocess.Popen | None = None\n"
    "        self._cancelled = False\n"
    "        self._busy = False\n"
    "        self._available_update: update_manager.UpdateInfo | None = None\n"
    "        self._update_check_running = False\n"
    "        self._started_at: float | None = None\n"
)
if text.count(old) != 1:
    raise SystemExit("Studio init state anchor mismatch")
text = text.replace(old, new, 1)

old = "        self._schedule(350, self._recover_interrupted_render)\n"
new = old + "        self._schedule(1200, self._startup_update_check)\n"
if text.count(old) != 1:
    raise SystemExit("startup schedule anchor mismatch")
text = text.replace(old, new, 1)

old = (
    '        ttk.Label(header_tools, text=f"v{__version__}", style="Muted.TLabel").pack(side="left", padx=(0, 8), pady=(7, 0))\n'
    '        ttk.Button(header_tools, text="Ajuda  F1", command=self._show_quick_guide).pack(side="left")\n'
)
new = (
    '        ttk.Label(header_tools, text=f"v{__version__}", style="Muted.TLabel").pack(side="left", padx=(0, 8), pady=(7, 0))\n'
    '        self.header_update_button = ttk.Button(\n'
    '            header_tools, text="", style="Primary.TButton", command=self._apply_available_update,\n'
    '        )\n'
    '        self.header_help_button = ttk.Button(header_tools, text="Ajuda  F1", command=self._show_quick_guide)\n'
    '        self.header_help_button.pack(side="left")\n'
)
if text.count(old) != 1:
    raise SystemExit("header tools anchor mismatch")
text = text.replace(old, new, 1)

method_pattern = re.compile(
    r'\n    def _check_updates\(self\) -> None:\n.*?\n    def _recover_interrupted_render\(self\) -> None:\n',
    re.S,
)
replacement = '''
    def _startup_update_check(self) -> None:
        # Startup discovery is deliberately silent and asynchronous: network
        # latency must never delay the editor or produce a modal error dialog.
        self._check_updates(silent=True)

    def _hide_update_cta(self) -> None:
        self._available_update = None
        if hasattr(self, "update_button"):
            self.update_button.configure(text="Atualizações", command=self._check_updates, state="normal")
        if hasattr(self, "header_update_button") and self.header_update_button.winfo_manager():
            self.header_update_button.pack_forget()

    def _show_update_cta(self, info: update_manager.UpdateInfo) -> None:
        self._available_update = info
        label = f"Atualizar v{info.version}"
        if hasattr(self, "update_button"):
            self.update_button.configure(text=label, command=self._apply_available_update, state="normal")
        if hasattr(self, "header_update_button"):
            self.header_update_button.configure(text=label, state="normal")
            if not self.header_update_button.winfo_manager():
                self.header_update_button.pack(side="left", padx=(0, 8), before=self.header_help_button)

    def _check_updates(self, *, silent: bool = False) -> None:
        if self._update_check_running:
            return
        self._update_check_running = True
        if hasattr(self, "update_button"):
            self.update_button.configure(state="disabled")
        if not silent:
            self._set_feedback(
                "busy", "Verificando atualizações",
                "Consultando a última release Stable do GitHub sem alterar a instalação atual.",
                category="Atualização",
            )
        install_mode = installation_mode(APP_DIR)

        def worker() -> None:
            try:
                info = update_manager.check_available(
                    __version__, installation=install_mode, timeout=5,
                )
                self._events.put(("update_checked", info, silent))
            except Exception as exc:
                self._events.put(("update_error", "check", str(exc), silent))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_available_update(self) -> None:
        info = self._available_update
        if info is None:
            self._check_updates(silent=False)
            return
        if self._busy or self._queue_running or self._ai_installing:
            self._set_feedback(
                "warning", "Atualização aguardando",
                "Conclua ou cancele o processamento atual; o CinePulse não fecha um render para instalar uma atualização.",
                category="Atualização",
            )
            return
        if hasattr(self, "header_update_button"):
            self.header_update_button.configure(state="disabled")
        if hasattr(self, "update_button"):
            self.update_button.configure(state="disabled")
        self._stage_update(info)

    def _stage_update(self, info: update_manager.UpdateInfo) -> None:
        package = "MSI" if info.package_kind == "msi" else "pacote portátil"
        self._set_feedback(
            "busy", f"Baixando CinePulse {info.version}",
            f"Baixando o {package} da release oficial e verificando SHA-256 antes de fechar o programa.",
            category="Atualização",
        )

        def worker() -> None:
            try:
                staged = update_manager.stage(info)
                self._events.put(("update_ready", info, str(staged)))
            except Exception as exc:
                self._events.put(("update_error", "stage", str(exc), False))

        threading.Thread(target=worker, daemon=True).start()

    def _launch_prepared_update(self, info: update_manager.UpdateInfo, staged: str) -> None:
        update_manager.launch_staged(info, Path(staged), APP_DIR, os.getpid())
        self._set_feedback(
            "success", f"CinePulse {info.version} verificado",
            "A atualização será aplicada assim que esta janela fechar e o CinePulse abrirá novamente automaticamente.",
            category="Atualização",
        )
        self._on_close()

    def _recover_interrupted_render(self) -> None:
'''
text, count = method_pattern.subn("\n" + replacement.lstrip("\n"), text, count=1)
if count != 1:
    raise SystemExit(f"updater method block mismatch: {count}")

event_pattern = re.compile(
    r'                elif kind == "update_checked":\n.*?                elif kind == "ai_install_done":\n',
    re.S,
)
event_replacement = '''                elif kind == "update_checked":
                    info = event[1]
                    silent = bool(event[2]) if len(event) > 2 else False
                    self._update_check_running = False
                    if info is None:
                        self._hide_update_cta()
                        if not silent:
                            self._set_feedback(
                                "success", "CinePulse atualizado",
                                "Você já está usando a versão Stable mais recente publicada no GitHub.",
                                category="Atualização",
                            )
                    else:
                        self._show_update_cta(info)
                        self._set_feedback(
                            "info", f"CinePulse {info.version} disponível",
                            "Nova versão verificada. Clique em Atualizar; o download, a verificação e o reinício são automáticos.",
                            category="Atualização", primary=("Atualizar agora", self._apply_available_update),
                        )
                elif kind == "update_ready":
                    info = event[1]
                    staged = str(event[2])
                    try:
                        self._launch_prepared_update(info, staged)
                    except Exception as exc:
                        self._events.put(("update_error", "launch", str(exc), False))
                elif kind == "update_error":
                    phase = str(event[1]) if len(event) > 1 else "check"
                    detail = str(event[2]) if len(event) > 2 else "Falha desconhecida."
                    silent = bool(event[3]) if len(event) > 3 else False
                    self._update_check_running = False
                    if self._available_update is not None:
                        self._show_update_cta(self._available_update)
                    elif hasattr(self, "update_button"):
                        self.update_button.configure(text="Atualizações", command=self._check_updates, state="normal")
                    if silent and phase == "check":
                        self._log("Verificação automática de atualização indisponível: " + detail)
                    else:
                        self._set_feedback(
                            "error", "Não foi possível concluir a atualização",
                            "A versão atual foi preservada; nenhuma substituição incompleta foi promovida.",
                            category="Atualização", secondary=("Ver log", self._show_log), technical_detail=detail,
                        )
                elif kind == "ai_install_done":
'''
text, count = event_pattern.subn(event_replacement, text, count=1)
if count != 1:
    raise SystemExit(f"update event block mismatch: {count}")

path.write_text(text, encoding="utf-8")
print("CINEPULSE_ONE_CLICK_UPDATER_UI_PATCHED")
