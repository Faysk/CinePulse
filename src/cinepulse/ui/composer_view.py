from __future__ import annotations

"""Direct-manipulation Preview Overlay Composer.

The default Composer UI intentionally behaves like a small visual editor:
choose a background, add media/visualizers, then drag and resize them directly
on the canvas. Project music is consumed automatically from Studio; stems and
low-level routing remain backend capabilities rather than mandatory UI steps.

Preview-only state stays isolated from Stable RenderSettings. Unproven GPU
routes remain evidence-gated and the deterministic CPU reference is always
available.
"""

from dataclasses import replace
from pathlib import Path
import math
import queue
import subprocess
import threading
from tkinter import BooleanVar, Canvas, DoubleVar, PhotoImage, StringVar, Toplevel, filedialog, messagebox, ttk
import uuid

from ..composer_auto_export import export_composer_auto
from ..composer_base_probe import STILL_IMAGE_SUFFIXES, probe_composer_base
from ..composer_export import ComposerExportRequest
from ..composer_media import ComposerMediaInfo, probe_composer_media, validate_layer_media
from ..composer_preview import (
    ComposerPreviewResult,
    _decode_base_frame,
    fit_preview_canvas,
    render_composer_preview,
)
from ..loop_engine import FFMPEG, FFPROBE
from ..overlay_composer import ComposerItem, OverlayComposerState, VisualizerLayer, media_layer_from_path
from .preview import to_ppm_bytes


MEDIA_LABELS = {
    "png": "Imagem",
    "gif": "GIF",
    "apng": "APNG",
    "webp": "WebP",
    "video-alpha": "Vídeo / alpha",
}
VISUALIZER_LABELS = {
    "waveform": "Onda",
    "spectrum": "Gráfico",
    "circular": "Circular",
}
BLEND_MODES = ("normal", "multiply", "screen", "add", "overlay")
OUTPUT_RESOLUTIONS = {
    "720p HD": (1280, 720),
    "1080p Full HD": (1920, 1080),
    "1440p QHD": (2560, 1440),
    "4K UHD": (3840, 2160),
    "5K": (5120, 2880),
    "6K": (5760, 3240),
    "8K UHD": (7680, 4320),
    "10K": (10240, 5760),
    "12K": (11520, 6480),
}


def _var_value(studio, name: str) -> str:
    variable = getattr(studio, name, None)
    getter = getattr(variable, "get", None)
    if getter is None:
        return ""
    try:
        return str(getter() or "").strip()
    except Exception:
        return ""


def _studio_source_path(studio) -> Path | None:
    # Compatibility: older tests/helpers used source while real Studio owns video.
    for name in ("source", "video"):
        raw = _var_value(studio, name)
        if raw:
            return Path(raw).expanduser()
    return None


def _studio_audio_path(studio) -> Path | None:
    raw = _var_value(studio, "audio")
    return Path(raw).expanduser() if raw else None


def _studio_fps(studio) -> float:
    variable = getattr(studio, "fps", None)
    getter = getattr(variable, "get", None)
    try:
        value = float(getter()) if getter is not None else 30.0
    except Exception:
        value = 30.0
    return value if value > 0 else 30.0


def _studio_output_size(studio) -> tuple[int, int]:
    return OUTPUT_RESOLUTIONS.get(_var_value(studio, "resolution"), (1920, 1080))


def _probe_duration(path: Path) -> float:
    if not FFPROBE or not path.is_file():
        return 0.0
    try:
        result = subprocess.run(
            [
                str(FFPROBE), "-v", "error", "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1", str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
        if result.returncode:
            return 0.0
        value = float((result.stdout or "").strip() or 0.0)
        return value if math.isfinite(value) and value > 0 else 0.0
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def _state_for(studio) -> OverlayComposerState:
    state = getattr(studio, "_overlay_composer_state", None)
    if not isinstance(state, OverlayComposerState):
        state = OverlayComposerState()
        studio._overlay_composer_state = state
    return state


def _composer_base_source(studio, state: OverlayComposerState) -> Path | None:
    if state.background_source:
        candidate = Path(state.background_source).expanduser()
        if candidate.is_file():
            return candidate
    candidate = _studio_source_path(studio)
    return candidate if candidate is not None and candidate.is_file() else None


def _default_project_path(studio) -> Path:
    state = _state_for(studio)
    source = _composer_base_source(studio, state) or _studio_source_path(studio)
    if source is not None:
        return source.with_suffix(source.suffix + ".cinepulse-composer.json")
    return Path.home() / "cinepulse-composer.json"


def _default_export_path(source: Path) -> Path:
    source = Path(source).expanduser()
    return source.with_name(f"{source.stem}-composer-reference.mkv")


def _snapshot_state(state: OverlayComposerState) -> OverlayComposerState:
    """Detach a running preview/export from subsequent editor mutations."""
    return OverlayComposerState.from_dict(state.as_dict())


def _profile_for(studio, state: OverlayComposerState):
    if not FFPROBE:
        raise RuntimeError("FFprobe não foi encontrado.")
    source = _composer_base_source(studio, state)
    if source is None:
        raise ValueError("Escolha um fundo para começar.")

    if source.suffix.lower() in STILL_IMAGE_SUFFIXES:
        audio = _studio_audio_path(studio)
        duration = _probe_duration(audio) if audio is not None else 0.0
        if duration <= 0:
            duration = 10.0
        width, height = _studio_output_size(studio)
        return source, probe_composer_base(
            str(FFPROBE),
            source,
            duration_override=duration,
            fps_override=_studio_fps(studio),
            width_override=width,
            height_override=height,
        )

    return source, probe_composer_base(str(FFPROBE), source)


def _project_master_source(studio, base: Path) -> Path:
    audio = _studio_audio_path(studio)
    if audio is not None and audio.is_file():
        return audio
    return base


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
    window.title("CinePulse Preview — Composer visual")
    window.geometry("1380x820")
    window.minsize(1050, 680)

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
    shell.columnconfigure(0, weight=1)
    shell.columnconfigure(1, weight=0)
    shell.rowconfigure(1, weight=1)

    title_row = ttk.Frame(shell)
    title_row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
    ttk.Label(title_row, text="Composer visual", font=("Segoe UI", 15, "bold")).pack(side="left")
    ttk.Label(title_row, text="Arraste para mover • puxe os cantos para redimensionar").pack(side="left", padx=(14, 0))
    audio_status = StringVar()
    ttk.Label(title_row, textvariable=audio_status).pack(side="right")

    left = ttk.Frame(shell)
    left.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
    left.columnconfigure(0, weight=1)
    left.rowconfigure(1, weight=1)

    toolbar = ttk.Frame(left)
    toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))

    background_text = StringVar(value="Escolher fundo…")
    ttk.Button(toolbar, textvariable=background_text, command=lambda: choose_background()).pack(side="left")
    ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
    ttk.Button(toolbar, text="+ GIF / imagem", command=lambda: add_media()).pack(side="left")
    ttk.Button(toolbar, text="+ Gráfico", command=lambda: add_visualizer("spectrum")).pack(side="left", padx=(5, 0))
    ttk.Button(toolbar, text="+ Onda", command=lambda: add_visualizer("waveform")).pack(side="left", padx=(5, 0))
    ttk.Button(toolbar, text="+ Circular", command=lambda: add_visualizer("circular")).pack(side="left", padx=(5, 0))

    stage_card = ttk.LabelFrame(left, text="Prévia do vídeo", padding=8)
    stage_card.grid(row=1, column=0, sticky="nsew")
    stage_card.columnconfigure(0, weight=1)
    stage_card.rowconfigure(0, weight=1)

    canvas = Canvas(stage_card, width=960, height=540, background="#06090f", highlightthickness=0)
    canvas.grid(row=0, column=0, sticky="nsew")

    footer = ttk.Frame(left)
    footer.grid(row=2, column=0, sticky="ew", pady=(8, 0))
    footer.columnconfigure(2, weight=1)
    preview_time = DoubleVar(value=0.0)
    ttk.Label(footer, text="Tempo").grid(row=0, column=0, sticky="w")
    ttk.Spinbox(footer, textvariable=preview_time, from_=0.0, to=86400.0, increment=0.5, width=8).grid(row=0, column=1, sticky="w", padx=(5, 10))
    status = StringVar(value="Escolha um fundo. A música do projeto será usada automaticamente.")
    ttk.Label(footer, textvariable=status).grid(row=0, column=2, sticky="ew")
    preview_button = ttk.Button(footer, text="Atualizar prévia", command=lambda: request_render("manual"))
    preview_button.grid(row=0, column=3, padx=(8, 0))
    export_button = ttk.Button(footer, text="Exportar vídeo…", command=lambda: start_export())
    export_button.grid(row=0, column=4, padx=(6, 0))
    cancel_button = ttk.Button(footer, text="Cancelar", command=lambda: request_cancel(), state="disabled")
    cancel_button.grid(row=0, column=5, padx=(6, 0))

    sidebar = ttk.Frame(shell, width=330)
    sidebar.grid(row=1, column=1, sticky="ns")
    sidebar.grid_propagate(False)
    sidebar.columnconfigure(0, weight=1)
    sidebar.rowconfigure(1, weight=1)

    ttk.Label(sidebar, text="Camadas", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
    layers = ttk.Treeview(sidebar, columns=("name",), show="headings", height=10, selectmode="browse")
    layers.heading("name", text="Clique para selecionar")
    layers.column("name", width=310, anchor="w")
    layers.grid(row=1, column=0, sticky="nsew", pady=(5, 8))

    selected_title = StringVar(value="Nenhuma camada selecionada")
    properties = ttk.LabelFrame(sidebar, text="Ajustes rápidos", padding=10)
    properties.grid(row=2, column=0, sticky="ew")
    properties.columnconfigure(0, weight=1)
    ttk.Label(properties, textvariable=selected_title, font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))

    opacity_var = DoubleVar(value=100.0)
    reaction_var = DoubleVar(value=100.0)
    opacity_text = StringVar(value="100%")
    reaction_text = StringVar(value="100%")
    loop_var = BooleanVar(value=True)

    def slider_row(row: int, title: str, variable: DoubleVar, value_text: StringVar) -> ttk.Scale:
        head = ttk.Frame(properties)
        head.grid(row=row, column=0, sticky="ew", pady=(2, 0))
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text=title).grid(row=0, column=0, sticky="w")
        ttk.Label(head, textvariable=value_text).grid(row=0, column=1, sticky="e")
        scale_widget = ttk.Scale(properties, from_=0, to=200 if title == "Reação à música" else 100, variable=variable)
        scale_widget.grid(row=row + 1, column=0, sticky="ew", pady=(0, 7))
        scale_widget.bind("<ButtonRelease-1>", lambda _event: apply_quick_properties())
        return scale_widget

    slider_row(1, "Opacidade", opacity_var, opacity_text)
    slider_row(3, "Reação à música", reaction_var, reaction_text)
    loop_check = ttk.Checkbutton(properties, text="Repetir GIF / vídeo", variable=loop_var, command=lambda: apply_quick_properties())
    loop_check.grid(row=5, column=0, sticky="w", pady=(2, 8))

    order_row = ttk.Frame(properties)
    order_row.grid(row=6, column=0, sticky="ew")
    ttk.Button(order_row, text="Para frente", command=lambda: move_z(1)).pack(side="left")
    ttk.Button(order_row, text="Para trás", command=lambda: move_z(-1)).pack(side="left", padx=(5, 0))
    ttk.Button(order_row, text="Remover", command=lambda: remove_selected()).pack(side="right")

    advanced_open = BooleanVar(value=False)
    advanced = ttk.Frame(properties)
    advanced.columnconfigure(1, weight=1)
    rotation_var = DoubleVar(value=0.0)
    spin_var = DoubleVar(value=0.0)
    blend_var = StringVar(value="normal")
    ttk.Label(advanced, text="Rotação").grid(row=0, column=0, sticky="w", pady=3)
    ttk.Spinbox(advanced, textvariable=rotation_var, from_=-3600, to=3600, increment=1).grid(row=0, column=1, sticky="ew", pady=3)
    ttk.Label(advanced, text="Spin RPM").grid(row=1, column=0, sticky="w", pady=3)
    ttk.Spinbox(advanced, textvariable=spin_var, from_=-120, to=120, increment=0.5).grid(row=1, column=1, sticky="ew", pady=3)
    ttk.Label(advanced, text="Blend").grid(row=2, column=0, sticky="w", pady=3)
    blend_box = ttk.Combobox(advanced, textvariable=blend_var, values=BLEND_MODES, state="readonly")
    blend_box.grid(row=2, column=1, sticky="ew", pady=3)
    ttk.Button(advanced, text="Aplicar avançado", command=lambda: apply_advanced()).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(7, 0))

    def toggle_advanced() -> None:
        if advanced_open.get():
            advanced_open.set(False)
            advanced.grid_remove()
            advanced_button.configure(text="Mais opções…")
        else:
            advanced_open.set(True)
            advanced.grid(row=8, column=0, sticky="ew", pady=(8, 0))
            advanced_button.configure(text="Menos opções")

    advanced_button = ttk.Button(properties, text="Mais opções…", command=toggle_advanced)
    advanced_button.grid(row=7, column=0, sticky="ew", pady=(4, 0))

    project_row = ttk.LabelFrame(sidebar, text="Projeto", padding=8)
    project_row.grid(row=3, column=0, sticky="ew", pady=(8, 0))
    project_row.columnconfigure(0, weight=1)
    ttk.Button(project_row, text="Abrir projeto…", command=lambda: load_state()).grid(row=0, column=0, sticky="ew")
    ttk.Button(project_row, text="Salvar projeto…", command=lambda: save_state()).grid(row=1, column=0, sticky="ew", pady=(5, 0))

    selected_id = StringVar(value="")
    media_info: dict[str, ComposerMediaInfo] = {}
    stage = {
        "photo": None,
        "preview_w": 960,
        "preview_h": 540,
        "origin_x": 0,
        "origin_y": 0,
        "profile": None,
        "rendering": False,
        "dirty": False,
        "closing": False,
    }
    drag = {
        "mode": "",
        "start_x": 0.0,
        "start_y": 0.0,
        "start_layer_x": 0.5,
        "start_layer_y": 0.5,
        "start_scale": 1.0,
        "start_distance": 1.0,
    }
    export_cancel = threading.Event()
    export_running = {"value": False}

    def update_audio_status() -> None:
        audio = _studio_audio_path(studio)
        if audio is not None and audio.is_file():
            audio_status.set(f"Música automática: {audio.name}")
        else:
            audio_status.set("Música: nenhuma selecionada")

    def update_background_text() -> None:
        base = _composer_base_source(studio, state)
        background_text.set(f"Fundo: {base.name}" if base is not None else "Escolher fundo…")

    def item_text(item: ComposerItem) -> str:
        if item.media is not None:
            return f"{MEDIA_LABELS.get(item.media.kind, item.media.kind)} • {Path(item.media.source).name}"
        assert item.visualizer is not None
        return VISUALIZER_LABELS.get(item.visualizer.kind, item.visualizer.kind)

    def refresh_layers(select: str | None = None) -> None:
        for child in layers.get_children():
            layers.delete(child)
        for item in sorted(state.items, key=lambda candidate: (candidate.z_order, candidate.id), reverse=True):
            suffix = "" if item.enabled else " (oculta)"
            layers.insert("", "end", iid=item.id, values=(item_text(item) + suffix,))
        candidate = select or selected_id.get()
        if candidate and layers.exists(candidate):
            layers.selection_set(candidate)
            layers.focus(candidate)
        draw_selection()

    def selected_item() -> ComposerItem | None:
        item_id = selected_id.get()
        return next((item for item in state.items if item.id == item_id), None)

    def item_index(item_id: str) -> int | None:
        return next((index for index, item in enumerate(state.items) if item.id == item_id), None)

    def cached_media_info(item: ComposerItem) -> ComposerMediaInfo | None:
        if item.media is None or not FFPROBE:
            return None
        existing_info = media_info.get(item.id)
        if existing_info is not None:
            return existing_info
        try:
            info = probe_composer_media(str(FFPROBE), item.media.source, timeout=10.0, exact_timing=False)
        except Exception:
            return None
        media_info[item.id] = info
        return info

    def item_bbox(item: ComposerItem) -> tuple[float, float, float, float] | None:
        profile = stage.get("profile")
        if profile is None:
            return None
        w = float(stage["preview_w"])
        h = float(stage["preview_h"])
        ox = float(stage["origin_x"])
        oy = float(stage["origin_y"])
        layer = item.media or item.visualizer
        if layer is None:
            return None
        cx = ox + float(layer.x) * max(1.0, w - 1.0)
        cy = oy + float(layer.y) * max(1.0, h - 1.0)
        if item.media is not None:
            info = cached_media_info(item)
            if info is not None:
                ratio = w / max(1.0, float(profile.width))
                bw = max(24.0, info.width * float(layer.scale) * ratio)
                bh = max(24.0, info.height * float(layer.scale) * ratio)
            else:
                bw, bh = 180.0, 100.0
        else:
            assert item.visualizer is not None
            if item.visualizer.kind == "circular":
                bw = bh = max(50.0, min(w, h) * 0.34 * item.visualizer.scale)
            else:
                bw = max(70.0, w * 0.42 * item.visualizer.scale)
                bh = max(45.0, h * 0.20 * item.visualizer.scale)
        return (cx - bw / 2.0, cy - bh / 2.0, cx + bw / 2.0, cy + bh / 2.0)

    def draw_selection() -> None:
        canvas.delete("selection")
        item = selected_item()
        if item is None:
            return
        bbox = item_bbox(item)
        if bbox is None:
            return
        x0, y0, x1, y1 = bbox
        canvas.create_rectangle(x0, y0, x1, y1, outline="#35a7ff", width=2, tags="selection")
        size = 7
        for px, py in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            canvas.create_rectangle(px - size, py - size, px + size, py + size, fill="#35a7ff", outline="#dff3ff", tags="selection")

    def sync_properties() -> None:
        item = selected_item()
        if item is None:
            selected_title.set("Nenhuma camada selecionada")
            return
        layer = item.media or item.visualizer
        assert layer is not None
        selected_title.set(item_text(item))
        opacity_var.set(float(layer.opacity) * 100.0)
        opacity_text.set(f"{round(opacity_var.get())}%")
        rotation_var.set(float(getattr(layer, "rotation_degrees", 0.0)))
        spin_var.set(float(getattr(layer, "spin_rpm", 0.0)))
        if item.media is not None:
            reaction_var.set(float(item.media.beat_reaction) * 100.0)
            loop_var.set(bool(item.media.loop))
            blend_var.set(item.media.blend)
            loop_check.configure(state="normal")
            blend_box.configure(state="readonly")
        else:
            assert item.visualizer is not None
            reaction_var.set(float(item.visualizer.reaction) * 100.0)
            loop_var.set(False)
            blend_var.set("normal")
            loop_check.configure(state="disabled")
            blend_box.configure(state="disabled")
        reaction_text.set(f"{round(reaction_var.get())}%")
        draw_selection()

    def select_item(item_id: str) -> None:
        if item_index(item_id) is None:
            return
        selected_id.set(item_id)
        if layers.exists(item_id):
            layers.selection_set(item_id)
            layers.focus(item_id)
        sync_properties()

    def replace_selected_layer(**changes) -> bool:
        index = item_index(selected_id.get())
        if index is None:
            return False
        item = state.items[index]
        if item.media is not None:
            state.items[index] = replace(item, media=replace(item.media, **changes))
        else:
            assert item.visualizer is not None
            state.items[index] = replace(item, visualizer=replace(item.visualizer, **changes))
        return True

    def apply_quick_properties() -> None:
        item = selected_item()
        if item is None:
            return
        opacity = max(0.0, min(1.0, float(opacity_var.get()) / 100.0))
        reaction = max(0.0, min(2.0, float(reaction_var.get()) / 100.0))
        opacity_text.set(f"{round(opacity * 100)}%")
        reaction_text.set(f"{round(reaction * 100)}%")
        if item.media is not None:
            replace_selected_layer(opacity=opacity, beat_reaction=reaction, loop=bool(loop_var.get()))
        else:
            replace_selected_layer(opacity=opacity, reaction=reaction)
        request_render("property")

    def apply_advanced() -> None:
        item = selected_item()
        if item is None:
            return
        try:
            changes = {"rotation_degrees": float(rotation_var.get()), "spin_rpm": float(spin_var.get())}
            if item.media is not None:
                changes["blend"] = blend_var.get()
            replace_selected_layer(**changes)
            request_render("advanced")
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Composer", str(exc), parent=window)

    def move_z(direction: int) -> None:
        item = selected_item()
        if item is None:
            return
        replace_selected_layer(z_order=item.z_order + (1 if direction > 0 else -1))
        refresh_layers(item.id)
        request_render("z")

    def remove_selected() -> None:
        item = selected_item()
        if item is None:
            return
        if state.remove(item.id):
            selected_id.set("")
            media_info.pop(item.id, None)
            refresh_layers()
            sync_properties()
            request_render("remove")

    def choose_background() -> None:
        path = filedialog.askopenfilename(
            parent=window,
            title="Escolher fundo",
            filetypes=(
                ("Imagem ou vídeo", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.mp4 *.mov *.mkv *.webm"),
                ("Imagens", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                ("Vídeos", "*.mp4 *.mov *.mkv *.webm"),
                ("Todos", "*.*"),
            ),
        )
        if not path:
            return
        state.background_source = str(Path(path).expanduser())
        update_background_text()
        status.set(f"Fundo selecionado: {Path(path).name}")
        request_render("background")

    def add_media() -> None:
        path = filedialog.askopenfilename(
            parent=window,
            title="Adicionar GIF, imagem ou vídeo",
            filetypes=(("Mídia visual", "*.png *.gif *.apng *.webp *.mov *.webm *.mkv *.mp4"), ("Todos", "*.*")),
        )
        if not path:
            return
        if not FFPROBE:
            messagebox.showerror("Composer", "FFprobe não foi encontrado.", parent=window)
            return
        try:
            layer = media_layer_from_path(path)
            info = probe_composer_media(str(FFPROBE), path, timeout=15.0, exact_timing=False)
            problems = validate_layer_media(layer, info)
            if problems:
                raise ValueError("; ".join(problems))
            target_w, _target_h = _studio_output_size(studio)
            default_scale = max(0.01, min(16.0, (target_w * 0.24) / max(1, info.width)))
            top_z = max((item.z_order for item in state.items), default=0) + 1
            layer = replace(layer, x=0.78, y=0.20, scale=default_scale, z_order=top_z, loop=True)
            item = ComposerItem("media-" + uuid.uuid4().hex[:8], media=layer)
            state.add(item)
            media_info[item.id] = info
            refresh_layers(item.id)
            select_item(item.id)
            status.set(f"{Path(path).name} adicionado • arraste no quadro para posicionar")
            request_render("add-media")
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror("Composer", str(exc), parent=window)

    def add_visualizer(kind: str) -> None:
        top_z = max((item.z_order for item in state.items), default=0) + 1
        x, y, scale = (0.84, 0.78, 0.55) if kind == "circular" else (0.78, 0.82, 0.55)
        item = ComposerItem(
            "viz-" + uuid.uuid4().hex[:8],
            visualizer=VisualizerLayer(
                kind, x=x, y=y, scale=scale, z_order=top_z,
                binding="master", reaction=1.0, bars=48 if kind == "spectrum" else 64,
            ),
        )
        state.add(item)
        refresh_layers(item.id)
        select_item(item.id)
        status.set(f"{VISUALIZER_LABELS[kind]} adicionado • já usa a música do projeto")
        request_render("add-visualizer")

    def on_layer_select(_event=None) -> None:
        selection = layers.selection()
        if selection:
            select_item(selection[0])

    layers.bind("<<TreeviewSelect>>", on_layer_select)

    def hit_handle(x: float, y: float, bbox: tuple[float, float, float, float]) -> bool:
        x0, y0, x1, y1 = bbox
        radius = 14.0
        return any(abs(x - px) <= radius and abs(y - py) <= radius for px, py in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)))

    def item_at(x: float, y: float) -> ComposerItem | None:
        for item in sorted(state.items, key=lambda candidate: (candidate.z_order, candidate.id), reverse=True):
            if not item.enabled:
                continue
            bbox = item_bbox(item)
            if bbox is None:
                continue
            x0, y0, x1, y1 = bbox
            if x0 <= x <= x1 and y0 <= y <= y1:
                return item
        return None

    def on_canvas_press(event) -> None:
        item = selected_item()
        if item is not None:
            bbox = item_bbox(item)
            if bbox is not None and hit_handle(event.x, event.y, bbox):
                x0, y0, x1, y1 = bbox
                cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
                layer = item.media or item.visualizer
                assert layer is not None
                drag.update(
                    mode="resize", start_x=float(event.x), start_y=float(event.y),
                    start_scale=float(layer.scale),
                    start_distance=max(1.0, math.hypot(event.x - cx, event.y - cy)),
                )
                return
        hit = item_at(event.x, event.y)
        if hit is None:
            return
        select_item(hit.id)
        layer = hit.media or hit.visualizer
        assert layer is not None
        drag.update(
            mode="move", start_x=float(event.x), start_y=float(event.y),
            start_layer_x=float(layer.x), start_layer_y=float(layer.y), start_scale=float(layer.scale),
        )

    def on_canvas_drag(event) -> None:
        item = selected_item()
        if item is None or not drag["mode"]:
            return
        preview_w = max(1.0, float(stage["preview_w"]))
        preview_h = max(1.0, float(stage["preview_h"]))
        if drag["mode"] == "move":
            nx = max(0.0, min(1.0, float(drag["start_layer_x"]) + (event.x - float(drag["start_x"])) / preview_w))
            ny = max(0.0, min(1.0, float(drag["start_layer_y"]) + (event.y - float(drag["start_y"])) / preview_h))
            replace_selected_layer(x=nx, y=ny)
            draw_selection()
            return
        bbox = item_bbox(item)
        if bbox is None:
            return
        x0, y0, x1, y1 = bbox
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        distance = max(1.0, math.hypot(event.x - cx, event.y - cy))
        factor = distance / max(1.0, float(drag["start_distance"]))
        replace_selected_layer(scale=max(0.01, min(16.0, float(drag["start_scale"]) * factor)))
        draw_selection()

    def on_canvas_release(_event) -> None:
        if drag["mode"]:
            drag["mode"] = ""
            request_render("drag")

    canvas.bind("<ButtonPress-1>", on_canvas_press)
    canvas.bind("<B1-Motion>", on_canvas_drag)
    canvas.bind("<ButtonRelease-1>", on_canvas_release)

    def show_stage(ppm: bytes, width: int, height: int, profile, message: str) -> None:
        stage["rendering"] = False
        photo = PhotoImage(data=ppm, format="PPM")
        stage["photo"] = photo
        stage["preview_w"] = width
        stage["preview_h"] = height
        stage["profile"] = profile
        canvas.delete("preview")
        canvas.update_idletasks()
        cw = max(width, canvas.winfo_width())
        ch = max(height, canvas.winfo_height())
        ox = max(0, int((cw - width) / 2))
        oy = max(0, int((ch - height) / 2))
        stage["origin_x"] = ox
        stage["origin_y"] = oy
        canvas.create_image(ox, oy, image=photo, anchor="nw", tags="preview")
        canvas.tag_lower("preview")
        draw_selection()
        status.set(message)
        preview_button.configure(state="normal")
        if not export_running["value"]:
            export_button.configure(state="normal")
        if stage["dirty"] and not stage["closing"]:
            stage["dirty"] = False
            request_render("queued")

    def show_render_error(message: str) -> None:
        stage["rendering"] = False
        preview_button.configure(state="normal")
        if not export_running["value"]:
            export_button.configure(state="normal")
        status.set(message)
        if stage["dirty"] and not stage["closing"]:
            stage["dirty"] = False
            request_render("queued")

    def request_render(_reason: str = "") -> None:
        if stage["closing"]:
            return
        if stage["rendering"]:
            stage["dirty"] = True
            return
        if not FFMPEG or not FFPROBE:
            status.set("FFmpeg/FFprobe não estão disponíveis.")
            return
        try:
            base, profile = _profile_for(studio, state)
            requested_time = max(0.0, float(preview_time.get()))
        except Exception as exc:
            status.set(str(exc))
            return
        snapshot = _snapshot_state(state)
        master = _project_master_source(studio, base)
        sources = snapshot.resolved_audio_sources(master)
        stage["rendering"] = True
        preview_button.configure(state="disabled")
        export_button.configure(state="disabled")
        status.set("Atualizando prévia…")

        def worker() -> None:
            try:
                if snapshot.ordered():
                    result: ComposerPreviewResult = render_composer_preview(
                        source=base, profile=profile, state=snapshot,
                        ffmpeg=str(FFMPEG), ffprobe=str(FFPROBE),
                        project_time=requested_time, audio_sources=sources,
                        max_width=960, max_height=540,
                    )
                    post(
                        show_stage,
                        to_ppm_bytes(result.rgba[..., :3]),
                        result.canvas_width,
                        result.canvas_height,
                        profile,
                        f"Prévia pronta • {result.media_layers} mídia(s) • {result.visualizers} visualizador(es)",
                    )
                    return
                width, height, _scale = fit_preview_canvas(profile.width, profile.height, max_width=960, max_height=540)
                frame_count = max(1, int(round(profile.duration * profile.fps)))
                frame_index = 0 if profile.still_image else min(
                    frame_count - 1,
                    max(0, int(math.floor(min(requested_time, profile.duration - 1e-9) * profile.fps))),
                )
                rgba = _decode_base_frame(
                    str(FFMPEG), base, profile, frame_index,
                    target_width=width, target_height=height,
                )
                post(show_stage, to_ppm_bytes(rgba[..., :3]), width, height, profile, "Fundo pronto • adicione GIF, imagem ou gráfico")
            except Exception as exc:
                post(show_render_error, f"Prévia: {exc}")

        threading.Thread(target=worker, name="cinepulse-composer-stage", daemon=True).start()

    def request_cancel() -> None:
        if not export_running["value"]:
            return
        export_cancel.set()
        cancel_button.configure(state="disabled")
        status.set("Cancelando export…")

    def finish_export(message: str, error: str | None = None, cancelled: bool = False) -> None:
        export_running["value"] = False
        export_button.configure(state="normal")
        preview_button.configure(state="normal")
        cancel_button.configure(state="disabled")
        if cancelled:
            status.set("Export cancelado • arquivo anterior preservado")
        elif error is not None:
            status.set("Falha no export • arquivo anterior preservado")
            messagebox.showerror("Composer", error, parent=window)
        else:
            status.set(message)
            messagebox.showinfo("Composer", message, parent=window)

    def start_export() -> None:
        if export_running["value"] or stage["rendering"]:
            return
        if not FFMPEG or not FFPROBE:
            messagebox.showerror("Composer", "FFmpeg/FFprobe não estão disponíveis.", parent=window)
            return
        snapshot = _snapshot_state(state)
        if not snapshot.ordered():
            messagebox.showinfo("Composer", "Adicione pelo menos um GIF, imagem ou visualizador.", parent=window)
            return
        try:
            base, profile = _profile_for(studio, snapshot)
        except Exception as exc:
            messagebox.showerror("Composer", str(exc), parent=window)
            return
        default = _default_export_path(base)
        output = filedialog.asksaveasfilename(
            parent=window,
            title="Exportar Composer",
            initialdir=str(default.parent),
            initialfile=default.name,
            defaultextension=".mkv",
            filetypes=(("Matroska lossless", "*.mkv"),),
        )
        if not output:
            return
        master = _project_master_source(studio, base)
        output_audio = _studio_audio_path(studio)
        if output_audio is not None and not output_audio.is_file():
            output_audio = None
        request = ComposerExportRequest(
            source=base, output=Path(output), profile=profile, state=snapshot,
            ffmpeg=str(FFMPEG), ffprobe=str(FFPROBE),
            audio_sources=snapshot.resolved_audio_sources(master),
            output_audio=output_audio,
        )
        export_cancel.clear()
        export_running["value"] = True
        export_button.configure(state="disabled")
        preview_button.configure(state="disabled")
        cancel_button.configure(state="normal")
        status.set("Exportando… a música do projeto será usada automaticamente")

        def worker() -> None:
            try:
                result = export_composer_auto(
                    request,
                    cancelled=export_cancel.is_set,
                    log=lambda message: post(status.set, message),
                )
                post(finish_export, f"Vídeo pronto: {Path(result.output).name} • backend {result.backend}")
            except InterruptedError:
                post(finish_export, "", None, True)
            except Exception as exc:
                post(finish_export, "", str(exc), False)

        threading.Thread(target=worker, name="cinepulse-composer-export", daemon=True).start()

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
            status.set(f"Projeto salvo: {Path(path).name}")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Composer", str(exc), parent=window)

    def load_state() -> None:
        if export_running["value"]:
            return
        path = filedialog.askopenfilename(parent=window, title="Abrir Composer", filetypes=(("CinePulse Composer", "*.json"),))
        if not path:
            return
        try:
            loaded = OverlayComposerState.load(Path(path))
            state.items[:] = loaded.items
            state.audio_sources.clear()
            state.audio_sources.update(loaded.audio_sources)
            state.background_source = loaded.background_source
            media_info.clear()
            selected_id.set("")
            update_background_text()
            refresh_layers()
            sync_properties()
            status.set(f"Projeto aberto: {Path(path).name}")
            request_render("load")
        except ValueError as exc:
            messagebox.showerror("Composer", str(exc), parent=window)

    def close_window() -> None:
        if export_running["value"]:
            if not messagebox.askyesno("Composer", "Cancelar o export e fechar?", parent=window):
                return
            export_cancel.set()
        stage["closing"] = True
        studio._overlay_composer_window = None
        try:
            window.destroy()
        except Exception:
            pass

    window.protocol("WM_DELETE_WINDOW", close_window)
    update_audio_status()
    update_background_text()
    refresh_layers()
    pump_ui_events()
    window.after(120, request_render)
