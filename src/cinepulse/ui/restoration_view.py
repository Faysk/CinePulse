"""Desktop surface for the Preview-only restoration lab.

The panel intentionally lives under the experimental/local-AI workspace and
keeps all state outside ``RenderSettings``.  Stable render/export ownership is
therefore unchanged while Preview restoration can be reviewed interactively.
"""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import BooleanVar, DoubleVar, PhotoImage, StringVar, TclError, ttk

from ..loop_engine import FFMPEG, first_video_size
from ..restoration_preview import PreviewRestorationPlan, inspect_and_plan_preview_restoration
from .preview import demo_background, extract_video_frame, to_ppm_bytes
from .restoration_lab import RESTORATION_PRESETS, RestorationUiState, analysis_summary, color_preview, overlay_boxes_preview


_PRESET_LABELS = {key: label for key, label, _description in RESTORATION_PRESETS}
_LABEL_PRESETS = {label: key for key, label, _description in RESTORATION_PRESETS}


def _safe_size(path: str) -> tuple[int, int] | None:
    try:
        size = first_video_size(path)
    except Exception:
        return None
    if not size or len(size) != 2:
        return None
    try:
        width, height = int(size[0]), int(size[1])
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def build_restoration_panel(studio, parent) -> None:
    """Attach the Preview restoration controls to the desktop workspace.

    The function owns only UI state and Preview analysis.  It deliberately does
    not mutate Studio's production render settings or final-render callbacks.
    """

    studio.restoration_remove_overlays = BooleanVar(value=False)
    studio.restoration_preset = StringVar(value=_PRESET_LABELS["neutral"])
    studio.restoration_brightness = DoubleVar(value=0.0)
    studio.restoration_contrast = DoubleVar(value=1.0)
    studio.restoration_saturation = DoubleVar(value=1.0)
    studio.restoration_gamma = DoubleVar(value=1.0)
    studio.restoration_temperature = DoubleVar(value=0.0)
    studio.restoration_tint = DoubleVar(value=0.0)
    studio.restoration_analysis_text = StringVar(value=analysis_summary(None))
    studio.restoration_preview_note = StringVar(
        value="Preview isolado: nada desta seção entra no render Stable automaticamente."
    )
    studio._restoration_plan: PreviewRestorationPlan | None = None
    studio._restoration_plan_source = ""
    studio._restoration_analysis_token = 0
    studio._restoration_preview_photo = None

    shell = ttk.Frame(parent, style="Card.TFrame", padding=14)
    shell.grid(row=3, column=0, sticky="ew", pady=(12, 0))
    shell.columnconfigure(0, weight=4, minsize=360)
    shell.columnconfigure(1, weight=6, minsize=520)

    header = ttk.Frame(shell, style="Card.TFrame")
    header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 11))
    header.columnconfigure(0, weight=1)
    ttk.Label(header, text="Restauração Preview", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(
        header,
        text="Remove overlays persistentes e recupera cor em um caminho experimental, separado do Stable.",
        style="CardMuted.TLabel",
        wraplength=790,
    ).grid(row=1, column=0, sticky="w", pady=(2, 0))
    ttk.Label(header, text="PREVIEW / EXPERIMENTAL", style="StatusWarning.TLabel").grid(
        row=0, column=1, rowspan=2, sticky="e", padx=(12, 0)
    )

    controls = ttk.Frame(shell, style="PanelAlt.TFrame", padding=12)
    controls.grid(row=1, column=0, sticky="nsew", padx=(0, 7))
    controls.columnconfigure(1, weight=1)

    ttk.Checkbutton(
        controls,
        text="Detectar e remover textos, QR codes e overlays persistentes",
        variable=studio.restoration_remove_overlays,
        command=lambda: _refresh_preview(studio),
    ).grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(
        controls,
        text="A remoção só usa regiões aprovadas pelos guardrails do detector; regiões ambíguas são preservadas.",
        style="PanelAltMuted.TLabel",
        wraplength=420,
    ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(3, 10))

    ttk.Label(controls, text="Preset de cor", style="PanelAlt.TLabel").grid(row=2, column=0, sticky="w", pady=4)
    preset = ttk.Combobox(
        controls,
        textvariable=studio.restoration_preset,
        values=[label for _key, label, _description in RESTORATION_PRESETS],
        state="readonly",
        width=22,
    )
    preset.grid(row=2, column=1, columnspan=2, sticky="ew", pady=4)

    def _preset_changed(_event=None) -> None:
        key = _LABEL_PRESETS.get(studio.restoration_preset.get(), "neutral")
        state = RestorationUiState(preset=key)
        values = state.controls()
        studio.restoration_brightness.set(values.brightness)
        studio.restoration_contrast.set(values.contrast)
        studio.restoration_saturation.set(values.saturation)
        studio.restoration_gamma.set(values.gamma)
        studio.restoration_temperature.set(values.temperature)
        studio.restoration_tint.set(values.tint)
        _refresh_preview(studio)

    preset.bind("<<ComboboxSelected>>", _preset_changed)

    def slider(row: int, label: str, variable: DoubleVar, low: float, high: float, resolution_hint: str) -> None:
        ttk.Label(controls, text=label, style="PanelAlt.TLabel").grid(row=row, column=0, sticky="w", pady=4)
        scale = ttk.Scale(controls, from_=low, to=high, variable=variable, command=lambda _v: _refresh_preview(studio))
        scale.grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 6))
        value = ttk.Label(controls, text=resolution_hint, style="PanelAltMuted.TLabel", width=8, anchor="e")
        value.grid(row=row, column=2, sticky="e")

    slider(3, "Brilho", studio.restoration_brightness, -0.18, 0.18, "±18%")
    slider(4, "Contraste", studio.restoration_contrast, 0.70, 1.35, "70–135%")
    slider(5, "Saturação", studio.restoration_saturation, 0.65, 1.40, "65–140%")
    slider(6, "Gamma", studio.restoration_gamma, 0.75, 1.30, "0.75–1.30")
    slider(7, "Temperatura", studio.restoration_temperature, -1.0, 1.0, "frio↔quente")
    slider(8, "Tint", studio.restoration_tint, -1.0, 1.0, "verde↔magenta")

    actions = ttk.Frame(controls, style="PanelAlt.TFrame")
    actions.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(11, 0))
    studio.restoration_analyze_button = ttk.Button(
        actions, text="Analisar overlays", style="Primary.TButton", command=lambda: _start_analysis(studio)
    )
    studio.restoration_analyze_button.pack(side="left")
    ttk.Button(actions, text="Atualizar preview", command=lambda: _refresh_preview(studio)).pack(side="left", padx=(7, 0))
    ttk.Button(actions, text="Resetar", command=lambda: _reset(studio)).pack(side="right")

    ttk.Label(
        controls,
        textvariable=studio.restoration_analysis_text,
        style="PanelAltMuted.TLabel",
        wraplength=430,
        justify="left",
    ).grid(row=10, column=0, columnspan=3, sticky="w", pady=(9, 0))

    preview = ttk.Frame(shell, style="PanelAlt.TFrame", padding=12)
    preview.grid(row=1, column=1, sticky="nsew", padx=(7, 0))
    preview.columnconfigure(0, weight=1)
    ttk.Label(preview, text="Revisão visual", style="PanelAlt.TLabel", font=("Segoe UI", 10, "bold")).grid(
        row=0, column=0, sticky="w"
    )
    ttk.Label(
        preview,
        text="Amarelo marca regiões que o detector considera seguras para remoção.",
        style="PanelAltMuted.TLabel",
        wraplength=620,
    ).grid(row=1, column=0, sticky="w", pady=(2, 8))
    studio.restoration_preview_label = ttk.Label(preview, anchor="center")
    studio.restoration_preview_label.grid(row=2, column=0, sticky="nsew")
    ttk.Label(
        preview,
        textvariable=studio.restoration_preview_note,
        style="PanelAltMuted.TLabel",
        wraplength=620,
        justify="left",
    ).grid(row=3, column=0, sticky="w", pady=(8, 0))

    _refresh_preview(studio)


def _state(studio) -> RestorationUiState:
    preset = _LABEL_PRESETS.get(studio.restoration_preset.get(), "neutral")
    return RestorationUiState(
        remove_overlays=bool(studio.restoration_remove_overlays.get()),
        preset=preset,
        brightness=float(studio.restoration_brightness.get()),
        contrast=float(studio.restoration_contrast.get()),
        saturation=float(studio.restoration_saturation.get()),
        gamma=float(studio.restoration_gamma.get()),
        temperature=float(studio.restoration_temperature.get()),
        tint=float(studio.restoration_tint.get()),
    )


def _reset(studio) -> None:
    studio.restoration_remove_overlays.set(False)
    studio.restoration_preset.set(_PRESET_LABELS["neutral"])
    studio.restoration_brightness.set(0.0)
    studio.restoration_contrast.set(1.0)
    studio.restoration_saturation.set(1.0)
    studio.restoration_gamma.set(1.0)
    studio.restoration_temperature.set(0.0)
    studio.restoration_tint.set(0.0)
    studio._restoration_plan = None
    studio._restoration_plan_source = ""
    studio.restoration_analysis_text.set(analysis_summary(None))
    _refresh_preview(studio)


def _refresh_preview(studio) -> None:
    if not hasattr(studio, "restoration_preview_label"):
        return
    source = str(studio.video.get()).strip()
    frame = extract_video_frame(FFMPEG, source, width=640, height=360, position=1.0) if source else None
    if frame is None:
        frame = demo_background(640, 360)
        studio.restoration_preview_note.set(
            "Selecione um vídeo para usar um frame real. Por enquanto, os controles usam a imagem de demonstração."
        )
    else:
        studio.restoration_preview_note.set(
            "Preview rápido em frame real. A exportação Stable continua intocada; este laboratório é Preview-only."
        )
    try:
        frame = color_preview(frame, _state(studio).controls())
        plan = studio._restoration_plan if studio._restoration_plan_source == source else None
        if studio.restoration_remove_overlays.get():
            frame = overlay_boxes_preview(frame, plan)
        photo = PhotoImage(data=to_ppm_bytes(frame), format="PPM")
        studio._restoration_preview_photo = photo
        studio.restoration_preview_label.configure(image=photo)
    except (ValueError, TclError):
        return


def _start_analysis(studio) -> None:
    source = str(studio.video.get()).strip()
    if not source or not Path(source).is_file():
        studio.restoration_analysis_text.set("Selecione um vídeo válido antes de analisar overlays.")
        return
    size = _safe_size(source)
    if size is None:
        studio.restoration_analysis_text.set("Não foi possível identificar a resolução da fonte com segurança.")
        return

    studio._restoration_analysis_token += 1
    token = studio._restoration_analysis_token
    studio.restoration_analysis_text.set(analysis_summary(None, analyzing=True))
    try:
        studio.restoration_analyze_button.configure(state="disabled")
    except TclError:
        pass
    controls = _state(studio).controls()

    def worker() -> None:
        plan = None
        error = None
        try:
            plan = inspect_and_plan_preview_restoration(
                FFMPEG,
                Path(source),
                frame_width=size[0],
                frame_height=size[1],
                color=controls,
            )
        except Exception as exc:  # Preview must fail closed, never break Stable UI.
            error = str(exc).strip() or exc.__class__.__name__

        def finish() -> None:
            if token != getattr(studio, "_restoration_analysis_token", -1):
                return
            if error is None and plan is not None:
                studio._restoration_plan = plan
                studio._restoration_plan_source = source
            else:
                studio._restoration_plan = None
                studio._restoration_plan_source = ""
            studio.restoration_analysis_text.set(analysis_summary(plan, error=error))
            try:
                studio.restoration_analyze_button.configure(state="normal")
            except TclError:
                pass
            _refresh_preview(studio)

        try:
            studio.root.after(0, finish)
        except TclError:
            return

    threading.Thread(target=worker, name="cinepulse-restoration-analysis", daemon=True).start()
