from __future__ import annotations

"""Isolated Tk editor for the Preview Overlay Composer.

The window owns Preview-only state and never writes Stable RenderSettings. It is
intentionally useful even before H6 physical CUDA acceptance: all unsupported or
unproven GPU routes retain the deterministic CPU reference renderer.
"""

from pathlib import Path
from tkinter import BooleanVar, DoubleVar, IntVar, StringVar, Toplevel, filedialog, messagebox, ttk
import uuid

from ..composer_media import probe_composer_media, validate_layer_media
from ..gpu_compositor import OverlayLayer
from ..loop_engine import FFPROBE
from ..overlay_composer import ComposerItem, OverlayComposerState, VisualizerLayer, media_layer_from_path


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


def _state_for(studio) -> OverlayComposerState:
    state = getattr(studio, "_overlay_composer_state", None)
    if not isinstance(state, OverlayComposerState):
        state = OverlayComposerState()
        studio._overlay_composer_state = state
    return state


def _default_project_path(studio) -> Path:
    source = str(getattr(getattr(studio, "source", None), "get", lambda: "")() or "").strip()
    if source:
        candidate = Path(source).expanduser()
        return candidate.with_suffix(candidate.suffix + ".cinepulse-composer.json")
    return Path.home() / "cinepulse-composer.json"


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
    window.geometry("920x620")
    window.minsize(760, 520)

    shell = ttk.Frame(window, padding=12)
    shell.pack(fill="both", expand=True)
    shell.columnconfigure(0, weight=3)
    shell.columnconfigure(1, weight=4)
    shell.rowconfigure(1, weight=1)

    header = ttk.Frame(shell)
    header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
    ttk.Label(header, text="Overlay Composer / Music Visualizer — Preview", font=("Segoe UI", 13, "bold")).pack(side="left")
    status = StringVar(value="Preview isolado • GPU só com evidência física exata")
    ttk.Label(header, textvariable=status).pack(side="right")

    list_card = ttk.LabelFrame(shell, text="Camadas", padding=10)
    list_card.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
    list_card.rowconfigure(0, weight=1)
    list_card.columnconfigure(0, weight=1)
    tree = ttk.Treeview(list_card, columns=("type", "z", "binding"), show="headings", selectmode="browse")
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

    def field(row: int, label: str, variable, *, low: float, high: float, increment: float = 0.05) -> None:
        ttk.Label(editor, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Spinbox(editor, textvariable=variable, from_=low, to=high, increment=increment).grid(row=row, column=1, sticky="ew", pady=4)

    ttk.Checkbutton(editor, text="Camada ativa", variable=enabled).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
    field(1, "X normalizado", x, low=0, high=1, increment=0.01)
    field(2, "Y normalizado", y, low=0, high=1, increment=0.01)
    field(3, "Escala", scale, low=0.01, high=16, increment=0.05)
    field(4, "Opacidade", opacity, low=0, high=1, increment=0.05)
    field(5, "Z-order", z_order, low=-999, high=999, increment=1)
    field(6, "Rotação °", rotation, low=-3600, high=3600, increment=1)
    field(7, "Spin RPM", spin, low=-120, high=120, increment=0.5)
    field(8, "Pulse", pulse, low=0, high=2, increment=0.05)
    field(9, "Beat reaction", beat, low=0, high=2, increment=0.05)
    ttk.Label(editor, text="Binding").grid(row=10, column=0, sticky="w", pady=4)
    binding_box = ttk.Combobox(editor, textvariable=binding, values=BINDINGS, state="readonly")
    binding_box.grid(row=10, column=1, sticky="ew", pady=4)
    field(11, "Suavização", smoothing, low=0, high=1, increment=0.05)
    field(12, "Reação", reaction, low=0, high=2, increment=0.05)
    field(13, "Espessura", thickness, low=0.25, high=8, increment=0.25)
    field(14, "Barras", bars, low=8, high=512, increment=8)

    def item_label(item: ComposerItem) -> tuple[str, str]:
        if item.media is not None:
            return MEDIA_LABELS.get(item.media.kind, item.media.kind), item.media.audio_binding
        assert item.visualizer is not None
        return VISUALIZER_LABELS[item.visualizer.kind], item.visualizer.binding

    def refresh(select: str | None = None) -> None:
        for child in tree.get_children():
            tree.delete(child)
        for item in state.ordered():
            label, audio = item_label(item)
            tree.insert("", "end", iid=item.id, values=(label + ("" if item.enabled else " (off)"), item.z_order, audio))
        if select and tree.exists(select):
            tree.selection_set(select)
            tree.focus(select)
        status.set(f"{len(state.items)} camada(s) • Preview isolado • CUDA somente com evidência aprovada")

    def load_selected(_event=None) -> None:
        selection = tree.selection()
        if not selection:
            return
        item_id = selection[0]
        item = next((candidate for candidate in state.items if candidate.id == item_id), None)
        if item is None:
            return
        selected_id.set(item.id)
        enabled.set(item.enabled)
        layer = item.media or item.visualizer
        assert layer is not None
        x.set(layer.x); y.set(layer.y); scale.set(layer.scale); opacity.set(layer.opacity); z_order.set(layer.z_order)
        rotation.set(getattr(layer, "rotation_degrees", 0.0)); spin.set(getattr(layer, "spin_rpm", 0.0))
        if item.media is not None:
            pulse.set(item.media.pulse); beat.set(item.media.beat_reaction); binding.set(item.media.audio_binding)
            smoothing.set(0.65); reaction.set(1.0); thickness.set(1.0); bars.set(64)
        else:
            assert item.visualizer is not None
            pulse.set(0.0); beat.set(0.0); binding.set(item.visualizer.binding)
            smoothing.set(item.visualizer.smoothing); reaction.set(item.visualizer.reaction)
            thickness.set(item.visualizer.thickness); bars.set(item.visualizer.bars)

    tree.bind("<<TreeviewSelect>>", load_selected)

    def apply_selected() -> None:
        item_id = selected_id.get()
        index = next((idx for idx, candidate in enumerate(state.items) if candidate.id == item_id), None)
        if index is None:
            return
        old = state.items[index]
        try:
            if old.media is not None:
                layer = OverlayLayer(
                    source=old.media.source, kind=old.media.kind, x=x.get(), y=y.get(), scale=scale.get(),
                    opacity=opacity.get(), z_order=z_order.get(), blend=old.media.blend,
                    rotation_degrees=rotation.get(), loop=old.media.loop, spin_rpm=spin.get(),
                    pulse=pulse.get(), beat_reaction=beat.get(), audio_binding=binding.get(),
                )
                replacement = ComposerItem(old.id, media=layer, enabled=enabled.get())
            else:
                assert old.visualizer is not None
                layer = VisualizerLayer(
                    old.visualizer.kind, x=x.get(), y=y.get(), scale=scale.get(), opacity=opacity.get(),
                    z_order=z_order.get(), binding=binding.get(), smoothing=smoothing.get(), reaction=reaction.get(),
                    thickness=thickness.get(), bars=bars.get(), rotation_degrees=rotation.get(), spin_rpm=spin.get(),
                )
                replacement = ComposerItem(old.id, visualizer=layer, enabled=enabled.get())
            state.items[index] = replacement
            refresh(old.id)
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Overlay Composer", str(exc), parent=window)

    ttk.Button(editor, text="Aplicar propriedades", command=apply_selected).grid(row=15, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    actions = ttk.Frame(list_card)
    actions.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))

    def add_media() -> None:
        path = filedialog.askopenfilename(
            parent=window,
            title="Adicionar camada",
            filetypes=(("Mídia visual", "*.png *.gif *.apng *.webp *.mov *.webm *.mkv *.mp4"), ("Todos", "*.*")),
        )
        if not path:
            return
        try:
            layer = media_layer_from_path(path)
            info = probe_composer_media(str(FFPROBE), path)
            problems = validate_layer_media(layer, info)
            if problems:
                raise ValueError("; ".join(problems))
            item = ComposerItem("media-" + uuid.uuid4().hex[:8], media=layer)
            state.add(item)
            refresh(item.id)
            alpha = " • alpha" if info.has_alpha else ""
            status.set(
                f"{Path(path).name}: {info.width}x{info.height} • {info.fps:g} fps • "
                f"{info.duration:.2f}s{alpha}"
            )
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror("Overlay Composer", str(exc), parent=window)

    def add_visualizer(kind: str) -> None:
        item = ComposerItem("viz-" + uuid.uuid4().hex[:8], visualizer=VisualizerLayer(kind))  # type: ignore[arg-type]
        state.add(item); refresh(item.id)

    def remove_selected() -> None:
        selection = tree.selection()
        if selection and state.remove(selection[0]):
            selected_id.set(""); refresh()

    ttk.Button(actions, text="+ Mídia", command=add_media).pack(side="left")
    ttk.Button(actions, text="+ Wave", command=lambda: add_visualizer("waveform")).pack(side="left", padx=(4, 0))
    ttk.Button(actions, text="+ Spectrum", command=lambda: add_visualizer("spectrum")).pack(side="left", padx=(4, 0))
    ttk.Button(actions, text="+ Circular", command=lambda: add_visualizer("circular")).pack(side="left", padx=(4, 0))
    ttk.Button(actions, text="Remover", command=remove_selected).pack(side="right")

    footer = ttk.Frame(shell)
    footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def save_state() -> None:
        default = _default_project_path(studio)
        path = filedialog.asksaveasfilename(parent=window, initialdir=str(default.parent), initialfile=default.name, defaultextension=".json", filetypes=(("CinePulse Composer", "*.json"),))
        if not path:
            return
        try:
            state.save(Path(path)); status.set(f"Salvo: {Path(path).name}")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Overlay Composer", str(exc), parent=window)

    def load_state() -> None:
        path = filedialog.askopenfilename(parent=window, title="Abrir Composer", filetypes=(("CinePulse Composer", "*.json"),))
        if not path:
            return
        try:
            loaded = OverlayComposerState.load(Path(path))
            state.items[:] = loaded.items
            refresh(); status.set(f"Aberto: {Path(path).name}")
        except ValueError as exc:
            messagebox.showerror("Overlay Composer", str(exc), parent=window)

    ttk.Button(footer, text="Abrir…", command=load_state).pack(side="left")
    ttk.Button(footer, text="Salvar…", command=save_state).pack(side="left", padx=(6, 0))
    ttk.Label(footer, text="Stable não é alterado; rotas GPU sem evidência continuam no CPU.").pack(side="right")

    refresh()
