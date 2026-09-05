from __future__ import annotations

"""Isolated Tk editor for the Preview Overlay Composer.

The window owns Preview-only state and never writes Stable RenderSettings.
Unproven GPU routes retain the deterministic CPU-reference renderer.
"""

from pathlib import Path
import queue
import threading
from tkinter import BooleanVar, DoubleVar, IntVar, PhotoImage, StringVar, Toplevel, filedialog, messagebox, ttk
import uuid

from ..composer_base_probe import probe_composer_base
from ..composer_export import ComposerExportRequest, export_composer_reference
from ..composer_media import probe_composer_media, validate_layer_media
from ..composer_preview import ComposerPreviewResult, render_composer_preview
from ..gpu_compositor import OverlayLayer
from ..loop_engine import FFMPEG, FFPROBE
from ..overlay_composer import ComposerItem, OverlayComposerState, VisualizerLayer, media_layer_from_path
from .preview import to_ppm_bytes


MEDIA_LABELS = {
    "png": "PNG",
    "gif": "GIF",
    "apng": "APNG",
    "webp": "WebP",
    "video-alpha": "Vídeo/alpha",
}
VISUALIZER_LABELS = {
    "waveform": "Waveform",
    "spectrum": "Spectrum",
    "circular": "Circular",
}
BINDINGS = ("master", "vocals", "drums", "bass", "other")
BLEND_MODES = ("normal", "multiply", "screen", "add", "overlay")


def _state_for(studio) -> OverlayComposerState:
    state = getattr(studio, "_overlay_composer_state", None)
    if not isinstance(state, OverlayComposerState):
        state = OverlayComposerState()
        studio._overlay_composer_state = state
    return state


def _studio_source_path(studio) -> Path | None:
    getter = getattr(getattr(studio, "source", None), "get", lambda: "")
    source = str(getter() or "").strip()
    return Path(source).expanduser() if source else None


def _default_project_path(studio) -> Path:
    source = _studio_source_path(studio)
    if source is not None:
        return source.with_suffix(source.suffix + ".cinepulse-composer.json")
    return Path.home() / "cinepulse-composer.json"


def _default_export_path(source: Path) -> Path:
    source = Path(source).expanduser()
    return source.with_name(f"{source.stem}-composer-reference.mkv")


def _snapshot_state(state: OverlayComposerState) -> OverlayComposerState:
    """Detach a running preview/export from subsequent editor mutations."""
    return OverlayComposerState.from_dict(state.as_dict())


def show_overlay_composer(studio) -> None:
    existing = getattr(studio, "_overlay_composer_window", None)
    try:
        if existing is not None and existing.winfo_exists():
            existing.deiconify()
            existing.lift()
            existing.focus_force()
            return
    except Exception:
        pass

    state = _state_for(studio)
    window = Toplevel(studio.root if hasattr(studio, "root") else studio)
    studio._overlay_composer_window = window
    window.title("CinePulse Preview — Overlay Composer")
    window.geometry("1000x730")
    window.minsize(820, 600)

    # Worker threads never call Tk directly. They enqueue UI work and this pump
    # executes it on Tk's owning thread.
    ui_events: queue.Queue[tuple[object, tuple, dict]] = queue.Queue()

    def post(callback, *args, **kwargs) -> None:
        ui_events.put((callback, args, kwargs))

    def pump_ui_events() -> None:
        try:
            while True:
                callback, args, kwargs = ui_events.get_nowait()
                callback(*args, **kwargs)  # type: ignore[operator]
        except queue.Empty:
            pass
        try:
            if window.winfo_exists():
                window.after(40, pump_ui_events)
        except Exception:
            pass

    shell = ttk.Frame(window, padding=12)
    shell.pack(fill="both", expand=True)
    shell.columnconfigure(0, weight=3)
    shell.columnconfigure(1, weight=4)
    shell.rowconfigure(1, weight=1)

    header = ttk.Frame(shell)
    header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
    ttk.Label(
        header,
        text="Overlay Composer / Music Visualizer — Preview",
        font=("Segoe UI", 13, "bold"),
    ).pack(side="left")
    status = StringVar(value="Preview isolado • GPU só com evidência física exata")
    ttk.Label(header, textvariable=status).pack(side="right")

    list_card = ttk.LabelFrame(shell, text="Camadas", padding=10)
    list_card.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
    list_card.rowconfigure(0, weight=1)
    list_card.columnconfigure(0, weight=1)
    tree = ttk.Treeview(
        list_card,
        columns=("type", "z", "binding"),
        show="headings",
        selectmode="browse",
    )
    tree.heading("type", text="Tipo")
    tree.heading("z", text="Z")
    tree.heading("binding", text="Áudio")
    tree.column("type", width=150, anchor="w")
    tree.column("z", width=45, anchor="center")
    tree.column("binding", width=75, anchor="center")
    tree.grid(row=0, column=0, columnspan=3, sticky="nsew")
    scroll = ttk.Scrollbar(list_card, orient="vertical", command=tree.yview)
    scroll.grid(row=0, column=3, sticky="ns")
    tree.configure(yscrollcommand=scroll.set)

    editor = ttk.LabelFrame(shell, text="Propriedades", padding=12)
    editor.grid(row=1, column=1, sticky="nsew", padx=(6, 0))
    editor.columnconfigure(1, weight=1)

    enabled = BooleanVar(value=True)
    x = DoubleVar(value=0.5)
    y = DoubleVar(value=0.5)
    scale = DoubleVar(value=1.0)
    opacity = DoubleVar(value=1.0)
    blend = StringVar(value="normal")
    loop = BooleanVar(value=True)
    z_order = IntVar(value=0)
    rotation = DoubleVar(value=0.0)
    spin = DoubleVar(value=0.0)
    pulse = DoubleVar(value=0.0)
    beat = DoubleVar(value=0.0)
    binding = StringVar(value="master")
    smoothing = DoubleVar(value=0.65)
    reaction = DoubleVar(value=1.0)
    thickness = DoubleVar(value=1.0)
    bars = IntVar(value=64)
    selected_id = StringVar(value="")
    export_progress = DoubleVar(value=0.0)
    preview_time = DoubleVar(value=0.0)
    export_cancel = threading.Event()
    export_state = {"running": False, "close_requested": False}
    preview_state = {"running": False, "close_requested": False}

    def field(
        row: int,
        label: str,
        variable,
        *,
        low: float,
        high: float,
        increment: float = 0.05,
    ) -> None:
        ttk.Label(editor, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Spinbox(
            editor,
            textvariable=variable,
            from_=low,
            to=high,
            increment=increment,
        ).grid(row=row, column=1, sticky="ew", pady=4)

    ttk.Checkbutton(editor, text="Camada ativa", variable=enabled).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 6)
    )
    field(1, "X normalizado", x, low=0, high=1, increment=0.01)
    field(2, "Y normalizado", y, low=0, high=1, increment=0.01)
    field(3, "Escala", scale, low=0.01, high=16, increment=0.05)
    field(4, "Opacidade", opacity, low=0, high=1, increment=0.05)
    ttk.Label(editor, text="Blend").grid(row=5, column=0, sticky="w", pady=4)
    blend_box = ttk.Combobox(
        editor,
        textvariable=blend,
        values=BLEND_MODES,
        state="readonly",
    )
    blend_box.grid(row=5, column=1, sticky="ew", pady=4)
    loop_check = ttk.Checkbutton(editor, text="Loop da mídia", variable=loop)
    loop_check.grid(row=6, column=0, columnspan=2, sticky="w", pady=4)
    field(7, "Z-order", z_order, low=-999, high=999, increment=1)
    field(8, "Rotação °", rotation, low=-3600, high=3600, increment=1)
    field(9, "Spin RPM", spin, low=-120, high=120, increment=0.5)
    field(10, "Pulse", pulse, low=0, high=2, increment=0.05)
    field(11, "Beat reaction", beat, low=0, high=2, increment=0.05)
    ttk.Label(editor, text="Binding").grid(row=12, column=0, sticky="w", pady=4)
    ttk.Combobox(
        editor,
        textvariable=binding,
        values=BINDINGS,
        state="readonly",
    ).grid(row=12, column=1, sticky="ew", pady=4)
    field(13, "Suavização", smoothing, low=0, high=1, increment=0.05)
    field(14, "Reação", reaction, low=0, high=2, increment=0.05)
    field(15, "Espessura", thickness, low=0.25, high=8, increment=0.25)
    field(16, "Barras", bars, low=8, high=512, increment=8)

    def item_label(item: ComposerItem) -> tuple[str, str]:
        if item.media is not None:
            return MEDIA_LABELS.get(item.media.kind, item.media.kind), item.media.audio_binding
        assert item.visualizer is not None
        return VISUALIZER_LABELS[item.visualizer.kind], item.visualizer.binding

    def refresh(select: str | None = None) -> None:
        for child in tree.get_children():
            tree.delete(child)
        # Disabled items must remain editable even though ordered() intentionally
        # omits them from rendering.
        for item in sorted(state.items, key=lambda candidate: (candidate.z_order, candidate.id)):
            label, audio = item_label(item)
            suffix = "" if item.enabled else " (off)"
            tree.insert("", "end", iid=item.id, values=(label + suffix, item.z_order, audio))
        if select and tree.exists(select):
            tree.selection_set(select)
            tree.focus(select)
        if not export_state["running"] and not preview_state["running"]:
            status.set(
                f"{len(state.items)} camada(s), {len(state.ordered())} ativa(s) • "
                "Preview isolado • CUDA só com evidência aprovada"
            )

    def load_selected(_event=None) -> None:
        selection = tree.selection()
        if not selection:
            return
        item = next((candidate for candidate in state.items if candidate.id == selection[0]), None)
        if item is None:
            return
        selected_id.set(item.id)
        enabled.set(item.enabled)
        layer = item.media or item.visualizer
        assert layer is not None
        x.set(layer.x)
        y.set(layer.y)
        scale.set(layer.scale)
        opacity.set(layer.opacity)
        z_order.set(layer.z_order)
        rotation.set(getattr(layer, "rotation_degrees", 0.0))
        spin.set(getattr(layer, "spin_rpm", 0.0))
        if item.media is not None:
            blend.set(item.media.blend)
            loop.set(item.media.loop)
            blend_box.configure(state="readonly")
            loop_check.configure(state="normal")
            pulse.set(item.media.pulse)
            beat.set(item.media.beat_reaction)
            binding.set(item.media.audio_binding)
            smoothing.set(0.65)
            reaction.set(1.0)
            thickness.set(1.0)
            bars.set(64)
        else:
            assert item.visualizer is not None
            blend.set("normal")
            loop.set(False)
            blend_box.configure(state="disabled")
            loop_check.configure(state="disabled")
            pulse.set(0.0)
            beat.set(0.0)
            binding.set(item.visualizer.binding)
            smoothing.set(item.visualizer.smoothing)
            reaction.set(item.visualizer.reaction)
            thickness.set(item.visualizer.thickness)
            bars.set(item.visualizer.bars)

    tree.bind("<<TreeviewSelect>>", load_selected)

    def apply_selected() -> None:
        item_id = selected_id.get()
        index = next(
            (idx for idx, candidate in enumerate(state.items) if candidate.id == item_id),
            None,
        )
        if index is None:
            return
        old = state.items[index]
        try:
            if old.media is not None:
                layer = OverlayLayer(
                    source=old.media.source,
                    kind=old.media.kind,
                    x=x.get(),
                    y=y.get(),
                    scale=scale.get(),
                    opacity=opacity.get(),
                    z_order=z_order.get(),
                    blend=blend.get(),  # type: ignore[arg-type]
                    rotation_degrees=rotation.get(),
                    loop=loop.get(),
                    spin_rpm=spin.get(),
                    pulse=pulse.get(),
                    beat_reaction=beat.get(),
                    audio_binding=binding.get(),
                )
                replacement = ComposerItem(old.id, media=layer, enabled=enabled.get())
            else:
                assert old.visualizer is not None
                layer = VisualizerLayer(
                    old.visualizer.kind,
                    x=x.get(),
                    y=y.get(),
                    scale=scale.get(),
                    opacity=opacity.get(),
                    z_order=z_order.get(),
                    binding=binding.get(),
                    smoothing=smoothing.get(),
                    reaction=reaction.get(),
                    thickness=thickness.get(),
                    bars=bars.get(),
                    rotation_degrees=rotation.get(),
                    spin_rpm=spin.get(),
                )
                replacement = ComposerItem(old.id, visualizer=layer, enabled=enabled.get())
            state.items[index] = replacement
            refresh(old.id)
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Overlay Composer", str(exc), parent=window)

    ttk.Button(editor, text="Aplicar propriedades", command=apply_selected).grid(
        row=17, column=0, columnspan=2, sticky="ew", pady=(10, 0)
    )

    actions = ttk.Frame(list_card)
    actions.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))

    def add_media() -> None:
        path = filedialog.askopenfilename(
            parent=window,
            title="Adicionar camada",
            filetypes=(
                ("Mídia visual", "*.png *.gif *.apng *.webp *.mov *.webm *.mkv *.mp4"),
                ("Todos", "*.*"),
            ),
        )
        if not path:
            return
        if not FFPROBE:
            messagebox.showerror("Overlay Composer", "FFprobe não foi encontrado.", parent=window)
            return
        try:
            layer = media_layer_from_path(path)
            # UI validation is intentionally metadata-only. Exact VFR frame
            # enumeration happens during the off-thread export preflight.
            info = probe_composer_media(
                str(FFPROBE),
                path,
                timeout=15.0,
                exact_timing=False,
            )
            problems = validate_layer_media(layer, info)
            if problems:
                raise ValueError("; ".join(problems))
            item = ComposerItem("media-" + uuid.uuid4().hex[:8], media=layer)
            state.add(item)
            refresh(item.id)
            alpha = " • alpha" if info.has_alpha else ""
            status.set(
                f"{Path(path).name}: {info.width}x{info.height} • "
                f"{info.fps:g} fps • {info.duration:.2f}s{alpha}"
            )
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror("Overlay Composer", str(exc), parent=window)

    def add_visualizer(kind: str) -> None:
        item = ComposerItem(
            "viz-" + uuid.uuid4().hex[:8],
            visualizer=VisualizerLayer(kind),  # type: ignore[arg-type]
        )
        state.add(item)
        refresh(item.id)

    def remove_selected() -> None:
        selection = tree.selection()
        if selection and state.remove(selection[0]):
            selected_id.set("")
            refresh()

    ttk.Button(actions, text="+ Mídia", command=add_media).pack(side="left")
    ttk.Button(actions, text="+ Wave", command=lambda: add_visualizer("waveform")).pack(
        side="left", padx=(4, 0)
    )
    ttk.Button(actions, text="+ Spectrum", command=lambda: add_visualizer("spectrum")).pack(
        side="left", padx=(4, 0)
    )
    ttk.Button(actions, text="+ Circular", command=lambda: add_visualizer("circular")).pack(
        side="left", padx=(4, 0)
    )
    ttk.Button(actions, text="Remover", command=remove_selected).pack(side="right")

    footer = ttk.Frame(shell)
    footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
    footer.columnconfigure(4, weight=1)

    def save_state() -> None:
        default = _default_project_path(studio)
        path = filedialog.asksaveasfilename(
            parent=window,
            initialdir=str(default.parent),
            initialfile=default.name,
            defaultextension=".json",
            filetypes=(("CinePulse Composer", "*.json"),),
        )
        if not path:
            return
        try:
            state.save(Path(path))
            status.set(f"Salvo: {Path(path).name}")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Overlay Composer", str(exc), parent=window)

    def load_state() -> None:
        if export_state["running"] or preview_state["running"]:
            messagebox.showinfo(
                "Overlay Composer",
                "Aguarde o preview ou cancele o export antes de abrir outro projeto.",
                parent=window,
            )
            return
        path = filedialog.askopenfilename(
            parent=window,
            title="Abrir Composer",
            filetypes=(("CinePulse Composer", "*.json"),),
        )
        if not path:
            return
        try:
            loaded = OverlayComposerState.load(Path(path))
            state.items[:] = loaded.items
            selected_id.set("")
            refresh()
            status.set(f"Aberto: {Path(path).name}")
        except ValueError as exc:
            messagebox.showerror("Overlay Composer", str(exc), parent=window)

    ttk.Button(footer, text="Abrir…", command=load_state).grid(row=0, column=0, sticky="w")
    ttk.Button(footer, text="Salvar…", command=save_state).grid(
        row=0, column=1, sticky="w", padx=(6, 10)
    )
    ttk.Label(footer, text="Preview s").grid(row=0, column=2, sticky="e")
    ttk.Spinbox(
        footer,
        textvariable=preview_time,
        from_=0.0,
        to=86400.0,
        increment=0.1,
        width=8,
    ).grid(row=0, column=3, sticky="w", padx=(5, 8))

    preview_button: ttk.Button
    export_button: ttk.Button
    cancel_button: ttk.Button

    def show_preview_result(result: ComposerPreviewResult) -> None:
        preview_state["running"] = False
        preview_button.configure(state="normal")
        if not export_state["running"]:
            export_button.configure(state="normal")
        if preview_state["close_requested"] or export_state["close_requested"]:
            studio._overlay_composer_window = None
            try:
                existing_preview = getattr(studio, "_overlay_composer_preview_window", None)
                if existing_preview is not None and existing_preview.winfo_exists():
                    existing_preview.destroy()
            except Exception:
                pass
            window.destroy()
            return

        existing_preview = getattr(studio, "_overlay_composer_preview_window", None)
        try:
            if existing_preview is not None and existing_preview.winfo_exists():
                existing_preview.destroy()
        except Exception:
            pass
        preview_window = Toplevel(window)
        studio._overlay_composer_preview_window = preview_window
        preview_window.title("CinePulse Preview — Composer frame")
        frame = ttk.Frame(preview_window, padding=8)
        frame.pack(fill="both", expand=True)
        photo = PhotoImage(
            data=to_ppm_bytes(result.rgba[..., :3]),
            format="PPM",
        )
        image = ttk.Label(frame, image=photo, anchor="center")
        image.image = photo  # type: ignore[attr-defined]
        image.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text=(
                f"{result.canvas_width}×{result.canvas_height} • frame {result.frame_index} • "
                f"t={result.project_time:.3f}s • CPU reference"
            ),
        ).pack(anchor="e", pady=(5, 0))
        preview_window.resizable(False, False)
        status.set(
            f"Preview fiel pronto • {result.canvas_width}×{result.canvas_height} • "
            f"{result.media_layers} mídia(s) • {result.visualizers} visualizer(s)"
        )

    def finish_preview_error(message: str) -> None:
        preview_state["running"] = False
        preview_button.configure(state="normal")
        if not export_state["running"]:
            export_button.configure(state="normal")
        if preview_state["close_requested"] or export_state["close_requested"]:
            studio._overlay_composer_window = None
            window.destroy()
            return
        status.set("Falha ao gerar preview do Composer")
        messagebox.showerror("Overlay Composer", message, parent=window)

    def start_preview() -> None:
        if preview_state["running"] or export_state["running"]:
            return
        source = _studio_source_path(studio)
        if source is None or not source.is_file():
            messagebox.showerror(
                "Overlay Composer",
                "Selecione um vídeo fonte válido no CinePulse.",
                parent=window,
            )
            return
        if not FFMPEG or not FFPROBE:
            messagebox.showerror(
                "Overlay Composer",
                "FFmpeg/FFprobe não estão disponíveis.",
                parent=window,
            )
            return
        snapshot = _snapshot_state(state)
        if not snapshot.ordered():
            messagebox.showerror(
                "Overlay Composer",
                "Ative pelo menos uma camada antes de gerar o preview.",
                parent=window,
            )
            return
        try:
            requested_time = max(0.0, float(preview_time.get()))
        except (TypeError, ValueError):
            messagebox.showerror("Overlay Composer", "Tempo de preview inválido.", parent=window)
            return

        preview_state["running"] = True
        preview_state["close_requested"] = False
        preview_button.configure(state="disabled")
        export_button.configure(state="disabled")
        status.set("Gerando preview fiel • canvas limitado a 960×540…")

        def worker() -> None:
            try:
                profile = probe_composer_base(str(FFPROBE), source)
                result = render_composer_preview(
                    source=source,
                    profile=profile,
                    state=snapshot,
                    ffmpeg=str(FFMPEG),
                    ffprobe=str(FFPROBE),
                    project_time=requested_time,
                    audio_sources={"master": source},
                    max_width=960,
                    max_height=540,
                )
                post(show_preview_result, result)
            except Exception as exc:
                post(finish_preview_error, str(exc))

        threading.Thread(
            target=worker,
            name="cinepulse-composer-preview",
            daemon=True,
        ).start()

    preview_button = ttk.Button(
        footer,
        text="Prévia fiel do frame",
        command=start_preview,
    )
    preview_button.grid(row=0, column=4, sticky="w")

    export_buttons = ttk.Frame(footer)
    export_buttons.grid(row=0, column=5, sticky="e", padx=(10, 0))

    ttk.Progressbar(
        footer,
        variable=export_progress,
        maximum=100.0,
        mode="determinate",
        length=260,
    ).grid(row=1, column=2, columnspan=4, sticky="ew", pady=(7, 0))

    def finish_export(
        message: str,
        *,
        error: str | None = None,
        cancelled: bool = False,
    ) -> None:
        export_state["running"] = False
        export_button.configure(state="normal")
        cancel_button.configure(state="disabled")
        if not preview_state["running"]:
            preview_button.configure(state="normal")
        if export_state["close_requested"]:
            studio._overlay_composer_window = None
            try:
                existing_preview = getattr(studio, "_overlay_composer_preview_window", None)
                if existing_preview is not None and existing_preview.winfo_exists():
                    existing_preview.destroy()
            except Exception:
                pass
            window.destroy()
            return
        if cancelled:
            status.set("Export do Composer cancelado • destino anterior preservado")
            return
        if error is not None:
            status.set("Falha no export do Composer • destino anterior preservado")
            messagebox.showerror("Overlay Composer", error, parent=window)
            return
        export_progress.set(100.0)
        status.set(message)
        messagebox.showinfo("Overlay Composer", message, parent=window)

    def request_cancel() -> None:
        if not export_state["running"]:
            return
        export_cancel.set()
        cancel_button.configure(state="disabled")
        status.set("Cancelando export do Composer…")

    def start_export() -> None:
        if export_state["running"] or preview_state["running"]:
            return
        source = _studio_source_path(studio)
        if source is None or not source.is_file():
            messagebox.showerror(
                "Overlay Composer",
                "Selecione um vídeo fonte válido no CinePulse.",
                parent=window,
            )
            return
        if not FFMPEG or not FFPROBE:
            messagebox.showerror(
                "Overlay Composer",
                "FFmpeg/FFprobe não estão disponíveis.",
                parent=window,
            )
            return
        snapshot = _snapshot_state(state)
        if not snapshot.ordered():
            messagebox.showerror(
                "Overlay Composer",
                "Ative pelo menos uma camada antes de exportar.",
                parent=window,
            )
            return

        default = _default_export_path(source)
        chosen = filedialog.asksaveasfilename(
            parent=window,
            title="Exportar Composer lossless",
            initialdir=str(default.parent),
            initialfile=default.name,
            defaultextension=".mkv",
            filetypes=(("Matroska lossless", "*.mkv"),),
        )
        if not chosen:
            return
        output = Path(chosen).expanduser()
        if output.suffix.lower() != ".mkv":
            messagebox.showerror(
                "Overlay Composer",
                "O export de referência lossless usa contêiner MKV.",
                parent=window,
            )
            return
        try:
            if output.resolve() == source.resolve():
                raise ValueError("O Composer nunca sobrescreve o vídeo fonte.")
        except OSError:
            pass
        except ValueError as exc:
            messagebox.showerror("Overlay Composer", str(exc), parent=window)
            return

        export_cancel.clear()
        export_progress.set(0.0)
        export_state["running"] = True
        export_state["close_requested"] = False
        export_button.configure(state="disabled")
        preview_button.configure(state="disabled")
        cancel_button.configure(state="normal")
        status.set("Preparando export lossless • analisando timing exato das camadas…")

        def worker() -> None:
            try:
                profile = probe_composer_base(str(FFPROBE), source)
                request = ComposerExportRequest(
                    source=source,
                    output=output,
                    profile=profile,
                    state=snapshot,
                    ffmpeg=str(FFMPEG),
                    ffprobe=str(FFPROBE),
                    audio_sources={"master": source},
                )

                def update_progress(done: int, total: int) -> None:
                    percent = 100.0 * max(0, done) / max(1, total)
                    post(export_progress.set, min(99.5, percent))
                    post(
                        status.set,
                        f"Exportando Composer lossless… {done}/{total} frame(s) • {percent:.1f}%",
                    )

                result = export_composer_reference(
                    request,
                    cancelled=export_cancel.is_set,
                    progress=update_progress,
                )
                post(
                    finish_export,
                    f"Composer exportado: {result.output.name} • {result.frames} frame(s) • CPU reference lossless",
                )
            except InterruptedError:
                post(finish_export, "", cancelled=True)
            except Exception as exc:
                post(finish_export, "", error=str(exc))

        threading.Thread(
            target=worker,
            name="cinepulse-composer-export",
            daemon=True,
        ).start()

    export_button = ttk.Button(
        export_buttons,
        text="Exportar MKV lossless…",
        command=start_export,
    )
    export_button.pack(side="left")
    cancel_button = ttk.Button(
        export_buttons,
        text="Cancelar",
        command=request_cancel,
        state="disabled",
    )
    cancel_button.pack(side="left", padx=(6, 0))

    ttk.Label(
        shell,
        text=(
            "Prévia fiel limitada a 960×540; export CPU: FFV1 RGB lossless + áudio master. "
            "Blend avançado cai no CPU; Stable intacto."
        ),
    ).grid(row=3, column=0, columnspan=2, sticky="e", pady=(5, 0))

    def close_window() -> None:
        if export_state["running"]:
            export_state["close_requested"] = True
            request_cancel()
            status.set("Fechando após cancelar e limpar o export em andamento…")
            return
        if preview_state["running"]:
            preview_state["close_requested"] = True
            status.set("Fechando após concluir o preview em andamento…")
            return
        studio._overlay_composer_window = None
        try:
            existing_preview = getattr(studio, "_overlay_composer_preview_window", None)
            if existing_preview is not None and existing_preview.winfo_exists():
                existing_preview.destroy()
        except Exception:
            pass
        window.destroy()

    window.protocol("WM_DELETE_WINDOW", close_window)
    window.after(40, pump_ui_events)
    refresh()
