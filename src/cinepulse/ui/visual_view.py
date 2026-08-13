"""Tk view construction for the CinePulse Visual Lab.

The view lives outside ``studio.py`` so layout evolution does not keep growing
the render/orchestration class.  Event handlers remain on the studio controller
for now and are passed through explicitly via the ``studio`` object.
"""

from __future__ import annotations

from tkinter import DoubleVar, PhotoImage, StringVar, ttk

from .preview import effect_thumbnail, to_ppm_bytes
from .polish_view import register_responsive_split
from .visual_lab import (
    DIRECTION_BUTTONS,
    EFFECT_DESCRIPTIONS,
    EFFECT_SHORT_NAMES,
    TRANSITION_SHORTLIST,
    VISUAL_VARIANTS,
    transition_thumbnail,
)


def build_visual_tab(studio, parent, *, effect_names, audio_focus_options, transition_options) -> None:
    """Build the Visual Lab controls and preview surface."""
    parent.columnconfigure(0, weight=4, minsize=390)
    parent.columnconfigure(1, weight=7, minsize=560)

    left = ttk.Frame(parent)
    left.grid(row=0, column=0, sticky="new", padx=(0, 7))
    right = ttk.Frame(parent)
    right.grid(row=0, column=1, sticky="new", padx=(7, 0))
    right.columnconfigure(0, weight=1)
    register_responsive_split(studio, "visual", parent, left, right, weights=(4, 7), min_sizes=(390, 560))

    # --- Effects -------------------------------------------------------
    effects = ttk.Frame(left, style="Card.TFrame", padding=12)
    effects.pack(fill="x")
    ttk.Label(effects, text="Efeitos ativos", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
    ttk.Label(
        effects,
        text="Combine VFX e veja o resultado ao lado sem renderizar o projeto inteiro.",
        style="CardMuted.TLabel",
        wraplength=360,
    ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 8))
    for column in range(4):
        effects.columnconfigure(column, weight=1)
    studio._visual_effect_buttons: dict[str, ttk.Button] = {}
    for index, name in enumerate(effect_names):
        rgb = effect_thumbnail(name, studio.color.get(), 112, 63)
        photo = PhotoImage(data=to_ppm_bytes(rgb), format="PPM")
        studio._visual_effect_photos[name] = photo
        active = studio.effect_vars[name].get()
        button = ttk.Button(
            effects,
            text=("✓ " if active else "") + EFFECT_SHORT_NAMES[name],
            image=photo,
            compound="top",
            style="Selected.Ghost.TButton" if active else "Effect.TButton",
            command=lambda effect=name: studio._toggle_effect_from_visual_lab(effect),
        )
        button.grid(row=2 + (index // 4) * 2, column=index % 4, sticky="ew", padx=3, pady=(3, 1))
        ttk.Label(
            effects,
            text=EFFECT_DESCRIPTIONS[name],
            style="CardMuted.TLabel",
            wraplength=88,
            justify="center",
            anchor="center",
        ).grid(row=3 + (index // 4) * 2, column=index % 4, sticky="n", padx=3, pady=(0, 4))
        studio._visual_effect_buttons[name] = button

    # --- Direction -----------------------------------------------------
    direction = ttk.Frame(left, style="Card.TFrame", padding=12)
    direction.pack(fill="x", pady=(10, 0))
    ttk.Label(direction, text="Direção musical", style="CardTitle.TLabel").pack(anchor="w")
    ttk.Label(
        direction,
        text="Atalhos que ajustam foco, suavização, expressão, dinâmica e intensidade em conjunto.",
        style="CardMuted.TLabel",
        wraplength=360,
    ).pack(anchor="w", pady=(2, 8))
    direction_row = ttk.Frame(direction, style="Card.TFrame")
    direction_row.pack(fill="x")
    studio._visual_direction_buttons: dict[str, ttk.Button] = {}
    for short_label, value in DIRECTION_BUTTONS:
        selected = studio.visual_direction.get() == value
        button = ttk.Button(
            direction_row,
            text=("✓ " if selected else "") + short_label,
            style="Selected.Ghost.TButton" if selected else "Ghost.TButton",
            command=lambda selected_value=value: studio._select_visual_direction(selected_value),
        )
        button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        studio._visual_direction_buttons[value] = button

    # --- Appearance ----------------------------------------------------
    controls = ttk.Frame(left, style="Card.TFrame", padding=12)
    controls.pack(fill="x", pady=(10, 0))
    controls.columnconfigure(1, weight=1)
    ttk.Label(controls, text="Aparência dos VFX", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(
        controls,
        text="Esses controles atualizam o preview interativo com debounce para não travar a interface.",
        style="CardMuted.TLabel",
        wraplength=360,
    ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 7))

    ttk.Label(controls, text="Cor principal", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=5)
    color_row = ttk.Frame(controls, style="Card.TFrame")
    color_row.grid(row=2, column=1, columnspan=2, sticky="ew", pady=5)
    studio.color_swatch = ttk.Label(color_row, text="      ", background=studio.color.get(), relief="solid")
    studio.color_swatch.pack(side="left", padx=(0, 7))
    ttk.Button(color_row, text="Escolher cor…", command=studio._choose_color).pack(side="left")

    def slider(row: int, label: str, variable: DoubleVar, textvariable: StringVar, low: float, high: float) -> None:
        ttk.Label(controls, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=5)
        ttk.Scale(controls, from_=low, to=high, variable=variable, command=studio._visual_scale_changed).grid(row=row, column=1, sticky="ew", pady=5)
        ttk.Label(controls, textvariable=textvariable, width=6, anchor="e", style="CardMuted.TLabel").grid(row=row, column=2, padx=(7, 0))

    slider(3, "Intensidade", studio.intensity, studio.intensity_text, 25, 200)
    slider(4, "Área ocupada", studio.occupancy, studio.occupancy_text, 10, 100)
    ttk.Label(controls, text="Reagir a", style="Card.TLabel").grid(row=5, column=0, sticky="w", pady=5)
    focus_box = ttk.Combobox(controls, textvariable=studio.audio_focus, values=audio_focus_options, state="readonly")
    focus_box.grid(row=5, column=1, columnspan=2, sticky="ew", pady=5)
    focus_box.bind("<<ComboboxSelected>>", lambda _e: studio._update_summary())
    slider(6, "Suavização", studio.reaction_smoothing, studio.smoothing_text, 0, 100)
    slider(7, "Expressividade", studio.reaction_expression, studio.expression_text, 25, 200)
    ttk.Checkbutton(
        controls,
        text="Adaptar intensidade a versos, refrões e clímax",
        variable=studio.dynamic_sections,
        command=studio._update_summary,
    ).grid(row=8, column=0, columnspan=3, sticky="w", pady=(7, 2))
    slider(9, "Dinâmica entre seções", studio.section_dynamics, studio.section_dynamics_text, 0, 100)
    ttk.Checkbutton(
        controls,
        text="Separar instrumentos com Demucs para uma reação mais limpa",
        variable=studio.use_stems,
        command=studio._update_summary,
    ).grid(row=10, column=0, columnspan=3, sticky="w", pady=(7, 0))
    ttk.Label(
        controls,
        text="Suavização alta deixa o movimento natural; expressividade alta destaca picos e batidas.",
        style="CardMuted.TLabel",
        wraplength=360,
    ).grid(row=11, column=0, columnspan=3, sticky="w", pady=(7, 0))

    # --- Loop transition ----------------------------------------------
    transitions = ttk.Frame(left, style="Card.TFrame", padding=12)
    transitions.pack(fill="x", pady=(10, 0))
    ttk.Label(transitions, text="Transição do loop", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
    ttk.Label(
        transitions,
        text="Miniaturas explicam a linguagem da emenda. O preview real continua sendo a validação final.",
        style="CardMuted.TLabel",
        wraplength=360,
    ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 8))
    studio._visual_transition_buttons: dict[str, ttk.Button] = {}
    for column in range(4):
        transitions.columnconfigure(column, weight=1)
    short_names = {
        "Corte seco — original": "Corte seco",
        "Dissolver suave": "Dissolver",
        "Fade cinematográfico": "Fade cinema",
        "Radial": "Radial",
    }
    for index, value in enumerate(TRANSITION_SHORTLIST):
        photo = PhotoImage(data=to_ppm_bytes(transition_thumbnail(value, 112, 63)), format="PPM")
        studio._visual_transition_photos[value] = photo
        selected = studio.transition.get() == value
        button = ttk.Button(
            transitions,
            text=("✓ " if selected else "") + short_names[value],
            image=photo,
            compound="top",
            style="Selected.Ghost.TButton" if selected else "Effect.TButton",
            command=lambda selected_value=value: studio._select_visual_transition(selected_value),
        )
        button.grid(row=2, column=index, sticky="ew", padx=3, pady=3)
        studio._visual_transition_buttons[value] = button

    details_row = ttk.Frame(transitions, style="Card.TFrame")
    details_row.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(7, 0))
    ttk.Label(details_row, text="Duração", style="Card.TLabel").pack(side="left")
    ttk.Spinbox(details_row, from_=0.15, to=3.0, increment=0.05, textvariable=studio.transition_duration, width=7, command=studio._update_summary).pack(side="left", padx=(6, 12))
    studio.visual_transition_box = ttk.Combobox(details_row, textvariable=studio.transition, values=tuple(transition_options), state="readonly", width=25)
    studio.visual_transition_box.pack(side="left", fill="x", expand=True)
    studio.visual_transition_box.bind("<<ComboboxSelected>>", lambda _e: studio._update_summary())
    ttk.Checkbutton(
        transitions,
        text="Encontrar automaticamente o melhor ponto de loop",
        variable=studio.auto_loop,
        command=studio._update_summary,
    ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(8, 0))

    # --- Live preview --------------------------------------------------
    preview_card = ttk.Frame(right, style="Card.TFrame", padding=12)
    preview_card.grid(row=0, column=0, sticky="ew")
    preview_header = ttk.Frame(preview_card, style="Card.TFrame")
    preview_header.pack(fill="x")
    preview_copy = ttk.Frame(preview_header, style="Card.TFrame")
    preview_copy.pack(side="left", fill="x", expand=True)
    ttk.Label(preview_copy, text="Preview em tempo real", style="CardTitle.TLabel").pack(anchor="w")
    ttk.Label(
        preview_copy,
        text="VFX reais + reação musical simulada. Use ‘Gerar preview’ para validar música, codec e transição reais.",
        style="CardMuted.TLabel",
        wraplength=520,
    ).pack(anchor="w", pady=(2, 0))
    mode_actions = ttk.Frame(preview_header, style="Card.TFrame")
    mode_actions.pack(side="right")
    studio._visual_preview_mode_buttons: dict[str, ttk.Button] = {}
    for mode in ("Original", "A/B", "Resultado"):
        button = ttk.Button(
            mode_actions,
            text=mode,
            style="Selected.Ghost.TButton" if mode == studio.visual_preview_mode.get() else "Ghost.TButton",
            command=lambda value=mode: studio._set_visual_preview_mode(value),
        )
        button.pack(side="left", padx=(4, 0))
        studio._visual_preview_mode_buttons[mode] = button

    preview_surface = ttk.Frame(preview_card, style="PanelAlt.TFrame", padding=4)
    preview_surface.pack(fill="both", expand=True, pady=(9, 0))
    studio.visual_preview_label = ttk.Label(preview_surface, style="Preview.TLabel", anchor="center")
    studio.visual_preview_label.pack(fill="both", expand=True)

    playback = ttk.Frame(preview_card, style="Card.TFrame")
    playback.pack(fill="x", pady=(8, 0))
    studio.visual_play_button = ttk.Button(playback, text="▶ Animar", command=studio._toggle_visual_preview_playback)
    studio.visual_play_button.pack(side="left")
    studio.visual_timeline = ttk.Scale(
        playback,
        from_=0,
        to=100,
        variable=studio.visual_preview_position,
        command=studio._visual_timeline_changed,
    )
    studio.visual_timeline.pack(side="left", fill="x", expand=True, padx=(8, 8))
    studio.visual_preview_time_text = StringVar(value="Exemplo 00:02.3 / 00:06.0")
    ttk.Label(playback, textvariable=studio.visual_preview_time_text, style="CardMuted.TLabel").pack(side="right")

    source_row = ttk.Frame(preview_card, style="Card.TFrame")
    source_row.pack(fill="x", pady=(5, 0))
    studio.visual_preview_source_text = StringVar(value="Demonstração interna • selecione um vídeo para usar um frame real")
    ttk.Label(source_row, textvariable=studio.visual_preview_source_text, style="CardMuted.TLabel").pack(side="left")
    ttk.Button(source_row, text="Gerar preview real", command=lambda: studio._start(True)).pack(side="right")

    # --- Quick comparisons --------------------------------------------
    variants = ttk.Frame(right, style="Card.TFrame", padding=12)
    variants.grid(row=1, column=0, sticky="ew", pady=(10, 0))
    ttk.Label(variants, text="Comparar efeitos", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
    ttk.Label(
        variants,
        text="Variações rápidas calculadas a partir da configuração atual. Aplicar altera somente os controles indicados.",
        style="CardMuted.TLabel",
        wraplength=650,
    ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 8))
    studio._visual_variant_labels: dict[str, ttk.Label] = {}
    for column in range(4):
        variants.columnconfigure(column, weight=1)
    for index, variant in enumerate(VISUAL_VARIANTS):
        card = ttk.Frame(variants, style="PanelAlt.TFrame", padding=5)
        card.grid(row=2, column=index, sticky="nsew", padx=3)
        label = ttk.Label(card, style="PanelAlt.TLabel", anchor="center")
        label.pack(fill="x")
        studio._visual_variant_labels[variant.key] = label
        ttk.Button(card, text=variant.label, command=lambda key=variant.key: studio._apply_visual_variant(key)).pack(fill="x", pady=(5, 0))
        ttk.Label(card, text=variant.hint, style="PanelAlt.TLabel", anchor="center", justify="center", wraplength=135).pack(fill="x", pady=(3, 0))

    # --- Explanation strip --------------------------------------------
    explanation = ttk.Frame(right, style="Card.TFrame", padding=12)
    explanation.grid(row=2, column=0, sticky="ew", pady=(10, 0))
    ttk.Label(explanation, text="O que este preview representa", style="CardTitle.TLabel").pack(anchor="w")
    ttk.Label(
        explanation,
        text=(
            "O quadro usa o motor VFX real e os controles atuais de cor, intensidade, área, foco, suavização e expressão. "
            "A reação musical interativa usa um sinal demonstrativo; transição, stems, codec, RIFE/Real-ESRGAN e áudio final só são validados no preview renderizado."
        ),
        style="CardMuted.TLabel",
        wraplength=760,
    ).pack(anchor="w", pady=(3, 0))

    studio._refresh_visual_preview_sync()
