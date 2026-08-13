"""Tk view for CinePulse Phase 3 — Project workspace."""

from __future__ import annotations

from tkinter import PhotoImage, ttk

from .preview import demo_background, to_ppm_bytes
from .project_lab import framing_preview
from .polish_view import register_responsive_split


def build_project_tab(
    studio,
    parent,
    *,
    mode_music: str,
    mode_original: str,
    aspects: tuple[str, ...],
    fit_modes: tuple[str, ...],
) -> None:
    """Build the project workspace without changing render contracts."""
    parent.columnconfigure(0, weight=5, minsize=430)
    parent.columnconfigure(1, weight=7, minsize=560)

    left = ttk.Frame(parent)
    left.grid(row=0, column=0, sticky="new", padx=(0, 7))
    right = ttk.Frame(parent)
    right.grid(row=0, column=1, sticky="new", padx=(7, 0))
    right.columnconfigure(0, weight=1)
    register_responsive_split(studio, "project", parent, left, right, weights=(5, 7), min_sizes=(430, 560))

    # --- Mode ---------------------------------------------------------
    mode_card = ttk.Frame(left, style="Card.TFrame", padding=14)
    mode_card.pack(fill="x")
    ttk.Label(mode_card, text="Que projeto você quer criar?", style="CardTitle.TLabel").pack(anchor="w")
    ttk.Label(
        mode_card,
        text="A escolha muda duração, áudio usado e o comportamento do loop — não é só um nome de preset.",
        style="CardMuted.TLabel",
        wraplength=395,
    ).pack(anchor="w", pady=(2, 10))
    studio._project_mode_buttons = {}
    for label, value, description in (
        (
            "Loop musical",
            mode_music,
            "Repete o clipe durante toda a música e usa a música como duração do projeto.",
        ),
        (
            "Melhorar vídeo original",
            mode_original,
            "Mantém a duração e o conteúdo do vídeo; o áudio original pode ser preservado.",
        ),
    ):
        selected = studio.mode.get() == value
        button = ttk.Button(
            mode_card,
            text=("✓ " if selected else "") + label + "\n" + description,
            style="Selected.ModeCard.TButton" if selected else "ModeCard.TButton",
            command=lambda selected_value=value: studio._set_project_mode(selected_value),
        )
        button.pack(fill="x", pady=(0, 7))
        studio._project_mode_buttons[value] = button

    # --- Files --------------------------------------------------------
    files = ttk.Frame(left, style="Card.TFrame", padding=14)
    files.pack(fill="x", pady=(10, 0))
    files.columnconfigure(1, weight=1)
    ttk.Label(files, text="Arquivos do projeto", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(
        files,
        text="Depois da seleção, o CinePulse analisa a mídia em segundo plano e mostra o que encontrou aqui mesmo.",
        style="CardMuted.TLabel",
        wraplength=395,
    ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 10))

    def file_block(row: int, label: str, variable, command, prefix: str):
        ttk.Label(files, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=(6, 2))
        entry = ttk.Entry(files, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=(6, 2))
        ttk.Button(files, text="Selecionar…", command=command).grid(row=row, column=2, padx=(7, 0), pady=(6, 2))
        entry.bind("<FocusOut>", lambda _event: studio._project_paths_edited())
        entry.bind("<Return>", lambda _event: studio._project_paths_edited())
        badge = ttk.Label(files, textvariable=getattr(studio, f"project_{prefix}_badge"), style="StatusMuted.TLabel")
        badge.grid(row=row + 1, column=1, columnspan=2, sticky="w", pady=(0, 1))
        setattr(studio, f"project_{prefix}_badge_label", badge)
        headline = ttk.Label(files, textvariable=getattr(studio, f"project_{prefix}_headline"), style="Card.TLabel", wraplength=320)
        headline.grid(row=row + 2, column=1, columnspan=2, sticky="w")
        detail = ttk.Label(files, textvariable=getattr(studio, f"project_{prefix}_detail"), style="CardMuted.TLabel", wraplength=320)
        detail.grid(row=row + 3, column=1, columnspan=2, sticky="w", pady=(0, 6))
        return entry

    studio.project_video_entry = file_block(2, "Vídeo", studio.video, studio._choose_video, "video")
    studio.audio_label = ttk.Label(files, text="Música", style="Card.TLabel")
    studio.audio_label.grid(row=6, column=0, sticky="w", padx=(0, 10), pady=(6, 2))
    studio.audio_entry = ttk.Entry(files, textvariable=studio.audio)
    studio.audio_entry.grid(row=6, column=1, sticky="ew", pady=(6, 2))
    studio.audio_button = ttk.Button(files, text="Selecionar…", command=studio._choose_audio)
    studio.audio_button.grid(row=6, column=2, padx=(7, 0), pady=(6, 2))
    studio.audio_entry.bind("<FocusOut>", lambda _event: studio._project_paths_edited())
    studio.audio_entry.bind("<Return>", lambda _event: studio._project_paths_edited())
    studio.project_audio_badge_label = ttk.Label(files, textvariable=studio.project_audio_badge, style="StatusMuted.TLabel")
    studio.project_audio_badge_label.grid(row=7, column=1, columnspan=2, sticky="w")
    ttk.Label(files, textvariable=studio.project_audio_headline, style="Card.TLabel", wraplength=320).grid(row=8, column=1, columnspan=2, sticky="w")
    ttk.Label(files, textvariable=studio.project_audio_detail, style="CardMuted.TLabel", wraplength=320).grid(row=9, column=1, columnspan=2, sticky="w", pady=(0, 6))

    ttk.Separator(files).grid(row=10, column=0, columnspan=3, sticky="ew", pady=7)
    ttk.Label(files, text="Salvar como", style="Card.TLabel").grid(row=11, column=0, sticky="w", padx=(0, 10), pady=(6, 2))
    studio.project_output_entry = ttk.Entry(files, textvariable=studio.output)
    studio.project_output_entry.grid(row=11, column=1, sticky="ew", pady=(6, 2))
    studio.project_output_entry.bind("<FocusOut>", lambda _event: studio._project_paths_edited())
    studio.project_output_entry.bind("<Return>", lambda _event: studio._project_paths_edited())
    ttk.Button(files, text="Escolher…", command=studio._choose_output).grid(row=11, column=2, padx=(7, 0), pady=(6, 2))
    studio.project_output_badge_label = ttk.Label(files, textvariable=studio.project_output_badge, style="StatusMuted.TLabel")
    studio.project_output_badge_label.grid(row=12, column=1, columnspan=2, sticky="w")
    ttk.Label(files, textvariable=studio.project_output_detail, style="CardMuted.TLabel", wraplength=320).grid(row=13, column=1, columnspan=2, sticky="w", pady=(0, 4))

    # --- Rendered preview options ------------------------------------
    preview_card = ttk.Frame(left, style="Card.TFrame", padding=14)
    preview_card.pack(fill="x", pady=(10, 0))
    preview_card.columnconfigure(1, weight=1)
    ttk.Label(preview_card, text="Preview renderizado", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(
        preview_card,
        text="É a validação real do pipeline. Diferente da prévia instantânea, ele processa vídeo, áudio, VFX e transição.",
        style="CardMuted.TLabel",
        wraplength=395,
    ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 9))
    ttk.Label(preview_card, text="Duração", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=5)
    ttk.Spinbox(preview_card, from_=1, to=30, textvariable=studio.preview_seconds, width=6).grid(row=2, column=1, sticky="w", pady=5)
    ttk.Label(preview_card, text="segundos (1–30)", style="CardMuted.TLabel").grid(row=2, column=2, sticky="w", padx=(7, 0))
    ttk.Checkbutton(
        preview_card,
        text="Criar comparação lado a lado — original à esquerda, resultado à direita",
        variable=studio.comparison_preview,
        command=studio._update_summary,
    ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(7, 4))
    actions = ttk.Frame(preview_card, style="Card.TFrame")
    actions.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(7, 0))
    ttk.Button(actions, text="Abrir pasta de previews", command=studio._open_preview_folder).pack(side="left")
    ttk.Button(actions, text="Gerar preview agora", style="Primary.TButton", command=lambda: studio._start(True)).pack(side="right")

    # --- Framing preview ---------------------------------------------
    framing = ttk.Frame(right, style="Card.TFrame", padding=14)
    framing.grid(row=0, column=0, sticky="ew")
    framing.columnconfigure(0, weight=1)
    header = ttk.Frame(framing, style="Card.TFrame")
    header.grid(row=0, column=0, sticky="ew")
    header.columnconfigure(0, weight=1)
    ttk.Label(header, text="Enquadramento do projeto", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
    studio.project_framing_badge_label = ttk.Label(header, textvariable=studio.project_framing_badge, style="CardStatus.TLabel")
    studio.project_framing_badge_label.grid(row=0, column=1, sticky="e")
    ttk.Label(
        framing,
        text="Guia instantâneo de proporção e corte. Não executa upscale, RIFE, VFX ou encode.",
        style="CardMuted.TLabel",
    ).grid(row=1, column=0, sticky="w", pady=(2, 9))

    surface = ttk.Frame(framing, style="PanelAlt.TFrame", padding=8)
    surface.grid(row=2, column=0, sticky="ew")
    studio.project_framing_label = ttk.Label(surface, style="Preview.TLabel", anchor="center")
    studio.project_framing_label.pack(fill="both", expand=True)

    controls = ttk.Frame(framing, style="Card.TFrame")
    controls.grid(row=3, column=0, sticky="ew", pady=(10, 0))
    controls.columnconfigure(1, weight=1)
    ttk.Label(controls, text="Formato", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
    aspect_box = ttk.Combobox(controls, textvariable=studio.aspect, values=aspects, state="readonly")
    aspect_box.grid(row=0, column=1, columnspan=2, sticky="ew", pady=4)
    aspect_box.bind("<<ComboboxSelected>>", lambda _event: studio._project_framing_changed())
    ttk.Label(controls, text="Enquadrar", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
    studio._project_fit_buttons = {}
    fit_row = ttk.Frame(controls, style="Card.TFrame")
    fit_row.grid(row=1, column=1, columnspan=2, sticky="ew", pady=4)
    short_fit = (("Preencher / cortar", fit_modes[0]), ("Encaixar / barras", fit_modes[1]))
    for label, value in short_fit:
        selected = studio.fit_mode.get() == value
        button = ttk.Button(
            fit_row,
            text=("✓ " if selected else "") + label,
            style="Selected.Ghost.TButton" if selected else "Ghost.TButton",
            command=lambda selected_value=value: studio._set_project_fit_mode(selected_value),
        )
        button.pack(side="left", fill="x", expand=True, padx=(0, 6))
        studio._project_fit_buttons[value] = button
    ttk.Label(framing, textvariable=studio.project_framing_info, style="CardMuted.TLabel", wraplength=540).grid(row=4, column=0, sticky="w", pady=(8, 0))

    # --- Inline preflight --------------------------------------------
    preflight = ttk.Frame(right, style="Card.TFrame", padding=14)
    preflight.grid(row=1, column=0, sticky="ew", pady=(10, 0))
    preflight.columnconfigure(0, weight=1)
    preflight_header = ttk.Frame(preflight, style="Card.TFrame")
    preflight_header.grid(row=0, column=0, columnspan=2, sticky="ew")
    preflight_header.columnconfigure(0, weight=1)
    ttk.Label(preflight_header, text="Saúde do projeto", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
    studio.project_preflight_badge_label = ttk.Label(preflight_header, textvariable=studio.project_preflight_badge, style="StatusMuted.TLabel")
    studio.project_preflight_badge_label.grid(row=0, column=1, sticky="e")
    ttk.Label(preflight, textvariable=studio.project_preflight_title, style="Card.TLabel", wraplength=520).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 2))
    ttk.Label(preflight, textvariable=studio.project_preflight_detail, style="CardMuted.TLabel", wraplength=520, justify="left").grid(row=2, column=0, columnspan=2, sticky="w")
    preflight_actions = ttk.Frame(preflight, style="Card.TFrame")
    preflight_actions.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
    studio.project_preflight_button = ttk.Button(preflight_actions, text="Verificar agora", command=studio._request_project_preflight)
    studio.project_preflight_button.pack(side="left")
    ttk.Button(preflight_actions, text="Abrir relatório detalhado…", command=studio._show_preflight).pack(side="left", padx=(7, 0))
    ttk.Button(preflight_actions, text="Qualidade e saída →", command=lambda: studio.notebook.select(2)).pack(side="right")

    # --- Explanation --------------------------------------------------
    guide = ttk.Frame(right, style="Card.TFrame", padding=14)
    guide.grid(row=2, column=0, sticky="ew", pady=(10, 0))
    guide.columnconfigure(0, weight=1)
    ttk.Label(guide, text="O que está sendo validado", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(
        guide,
        text=(
            "A seleção de mídia valida formato e metadados imediatamente. A verificação completa acrescenta espaço em disco, "
            "VRAM, HDR/faixa de cor, FPS extremo, tamanho estimado e compatibilidade do processamento."
        ),
        style="CardMuted.TLabel",
        wraplength=540,
        justify="left",
    ).grid(row=1, column=0, sticky="w", pady=(4, 0))

    # Seed a real widget image immediately; async scan can replace the source.
    demo = demo_background(640, 360)
    initial = framing_preview(demo, studio.aspect.get(), studio.fit_mode.get(), source_width=640, source_height=360)
    studio._project_framing_photo = PhotoImage(data=to_ppm_bytes(initial), format="PPM")
    studio.project_framing_label.configure(image=studio._project_framing_photo)
