"""Tk view for CinePulse Phase 4 — Quality & output workspace."""

from __future__ import annotations

from tkinter import StringVar, ttk

from ..performance_policy import MACHINE_PROFILES, machine_budget, profile_for_threads
from .polish_view import register_responsive_split


def build_quality_tab(
    studio,
    parent,
    *,
    resolutions: tuple[str, ...],
    fps_options: tuple[int, ...],
    aspects: tuple[str, ...],
    enhancement_options: tuple[str, ...],
    interpolation_options: tuple[str, ...],
    audio_modes: tuple[str, ...],
    delivery_profiles: tuple[str, ...],
) -> None:
    parent.columnconfigure(0, weight=5, minsize=430)
    parent.columnconfigure(1, weight=7, minsize=560)

    left = ttk.Frame(parent)
    left.grid(row=0, column=0, sticky="new", padx=(0, 7))
    right = ttk.Frame(parent)
    right.grid(row=0, column=1, sticky="new", padx=(7, 0))
    right.columnconfigure(0, weight=1)
    register_responsive_split(studio, "quality", parent, left, right, weights=(5, 7), min_sizes=(430, 560))

    # --- Output geometry ---------------------------------------------
    output = ttk.Frame(left, style="Card.TFrame", padding=14)
    output.pack(fill="x")
    output.columnconfigure(1, weight=1)
    ttk.Label(output, text="Imagem de saída", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(
        output,
        text="Resolução, FPS e formato definem o volume de pixels que o CinePulse precisa produzir.",
        style="CardMuted.TLabel",
        wraplength=395,
    ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 9))

    def combo(row: int, label: str, variable, values) -> ttk.Combobox:
        ttk.Label(output, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=5)
        box = ttk.Combobox(output, textvariable=variable, values=values, state="readonly")
        box.grid(row=row, column=1, columnspan=2, sticky="ew", pady=5)
        box.bind("<<ComboboxSelected>>", lambda _event: studio._quality_setting_changed())
        return box

    studio.quality_resolution_box = combo(2, "Resolução", studio.resolution, resolutions)
    studio.quality_fps_box = combo(3, "Quadros por segundo", studio.fps, fps_options)
    studio.quality_aspect_box = combo(4, "Formato da tela", studio.aspect, aspects)
    ttk.Label(
        output,
        text="O enquadramento/corte pode ser conferido visualmente na aba Projeto.",
        style="CardMuted.TLabel",
        wraplength=395,
    ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(5, 0))

    # --- Enhancement --------------------------------------------------
    enhancement = ttk.Frame(left, style="Card.TFrame", padding=14)
    enhancement.pack(fill="x", pady=(10, 0))
    ttk.Label(enhancement, text="Melhoria de imagem", style="CardTitle.TLabel").pack(anchor="w")
    ttk.Label(
        enhancement,
        text="Escolha como o CinePulse trata detalhe espacial. O preview renderizado continua sendo a validação visual real.",
        style="CardMuted.TLabel",
        wraplength=395,
    ).pack(anchor="w", pady=(2, 9))
    enhancement_info = {
        enhancement_options[0]: ("Preservar", "Sem upscale; menor custo e nenhuma tentativa de criar detalhe."),
        enhancement_options[1]: ("Lanczos", "Upscale clássico de alta qualidade; rápido e previsível."),
        enhancement_options[2]: ("Real-ESRGAN IA", "Recuperação de detalhe plausível por IA; exige GPU e aumenta bastante o custo."),
    }
    studio._quality_enhancement_buttons = {}
    for value in enhancement_options:
        title, description = enhancement_info[value]
        installed_note = ""
        if value == enhancement_options[2]:
            installed_note = " • instalado" if studio._quality_real_esrgan_available() else " • componente ausente"
        selected = studio.enhancement.get() == value
        button = ttk.Button(
            enhancement,
            text=("✓ " if selected else "") + title + installed_note + "\n" + description,
            style="Selected.ModeCard.TButton" if selected else "ModeCard.TButton",
            command=lambda selected_value=value: studio._select_quality_enhancement(selected_value),
        )
        button.pack(fill="x", pady=(0, 6))
        studio._quality_enhancement_buttons[value] = button

    # --- Motion -------------------------------------------------------
    motion = ttk.Frame(left, style="Card.TFrame", padding=14)
    motion.pack(fill="x", pady=(10, 0))
    ttk.Label(motion, text="Movimento e interpolação", style="CardTitle.TLabel").pack(anchor="w")
    ttk.Label(
        motion,
        text="Só há geração de quadros extras quando o FPS de destino é maior que o FPS da fonte.",
        style="CardMuted.TLabel",
        wraplength=395,
    ).pack(anchor="w", pady=(2, 9))
    interpolation_info = {
        interpolation_options[0]: ("RIFE IA", "Melhor movimento em cenas adequadas; se faltar o componente, o pipeline usa fallback FFmpeg."),
        interpolation_options[1]: ("FFmpeg suave", "Interpolação por movimento sem modelo neural; equilíbrio entre custo e fluidez."),
        interpolation_options[2]: ("Repetir quadros", "Mais rápido; aumenta FPS sem inventar movimento intermediário."),
    }
    studio._quality_interpolation_buttons = {}
    for value in interpolation_options:
        title, description = interpolation_info[value]
        note = ""
        if value == interpolation_options[0]:
            note = " • instalado" if studio._quality_rife_available() else " • fallback disponível"
        selected = studio.interpolation.get() == value
        button = ttk.Button(
            motion,
            text=("✓ " if selected else "") + title + note + "\n" + description,
            style="Selected.ModeCard.TButton" if selected else "ModeCard.TButton",
            command=lambda selected_value=value: studio._select_quality_interpolation(selected_value),
        )
        button.pack(fill="x", pady=(0, 6))
        studio._quality_interpolation_buttons[value] = button

    # --- Audio --------------------------------------------------------
    audio = ttk.Frame(left, style="Card.TFrame", padding=14)
    audio.pack(fill="x", pady=(10, 0))
    audio.columnconfigure(1, weight=1)
    ttk.Label(audio, text="Áudio e verificação final", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(
        audio,
        text="Tratamento de loudness e checagem perceptiva ficam separados das decisões de imagem.",
        style="CardMuted.TLabel",
        wraplength=395,
    ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 8))
    ttk.Label(audio, text="Perfil de entrega", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=5)
    delivery_box = ttk.Combobox(audio, textvariable=studio.delivery_profile, values=delivery_profiles, state="readonly")
    delivery_box.grid(row=2, column=1, columnspan=2, sticky="ew", pady=5)
    delivery_box.bind("<<ComboboxSelected>>", lambda _event: studio._quality_setting_changed())
    ttk.Label(audio, textvariable=studio.quality_delivery_text, style="CardMuted.TLabel", wraplength=395, justify="left").grid(
        row=3, column=0, columnspan=3, sticky="w", pady=(0, 6)
    )
    ttk.Label(audio, text="Tratamento do áudio", style="Card.TLabel").grid(row=4, column=0, sticky="w", padx=(0, 10), pady=5)
    audio_box = ttk.Combobox(audio, textvariable=studio.audio_mode, values=audio_modes, state="readonly")
    audio_box.grid(row=4, column=1, columnspan=2, sticky="ew", pady=5)
    audio_box.bind("<<ComboboxSelected>>", lambda _event: studio._quality_setting_changed())
    ttk.Checkbutton(
        audio,
        text="Manter o áudio original no modo ‘Melhorar vídeo original’",
        variable=studio.preserve_audio,
        command=studio._quality_setting_changed,
    ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(7, 2))
    ttk.Checkbutton(
        audio,
        text="Executar verificação perceptiva VMAF quando aplicável",
        variable=studio.quality_check,
        command=studio._quality_setting_changed,
    ).grid(row=6, column=0, columnspan=3, sticky="w", pady=2)
    ttk.Checkbutton(
        audio,
        text="Verificação profunda — decodificar o arquivo final até o fim e conferir A/V",
        variable=studio.deep_verify,
        command=studio._quality_setting_changed,
    ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(2, 0))

    # --- Machine ------------------------------------------------------
    machine = ttk.Frame(left, style="Card.TFrame", padding=14)
    machine.pack(fill="x", pady=(10, 0))
    machine.columnconfigure(1, weight=1)
    ttk.Label(machine, text="Uso da máquina", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(
        machine,
        text="Aceleração automática prioriza GPU nas etapas compatíveis; análise musical, VFX NumPy e alguns filtros continuam na CPU. O RenderPlan mostra o dispositivo por etapa.",
        style="CardMuted.TLabel",
        wraplength=395,
    ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 8))
    ttk.Label(machine, text="Processador", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=5)
    proc = ttk.Frame(machine, style="Card.TFrame")
    proc.grid(row=2, column=1, columnspan=2, sticky="ew", pady=5)
    studio._quality_processor_buttons = {}
    for label, cpu_value in (("Aceleração automática", False), ("Somente CPU", True)):
        selected = studio.use_cpu.get() == cpu_value
        button = ttk.Button(
            proc,
            text=("✓ " if selected else "") + label,
            style="Selected.Ghost.TButton" if selected else "Ghost.TButton",
            command=lambda value=cpu_value: studio._select_quality_processor(value),
        )
        button.pack(side="left", fill="x", expand=True, padx=(0, 6))
        studio._quality_processor_buttons[cpu_value] = button
    logical_threads = max(1, int(studio._hardware.cpu_threads))
    profile_value = StringVar(value=profile_for_threads(studio.cpu_threads.get(), logical_threads))
    profile_detail = StringVar(value="")

    def _refresh_machine_profile_detail() -> None:
        selected = profile_for_threads(studio.cpu_threads.get(), logical_threads)
        profile_value.set(selected)
        if selected in MACHINE_PROFILES:
            budget = machine_budget(selected, logical_threads, studio._hardware.vram_mb)
            profile_detail.set(
                f"{budget.cpu_threads}/{budget.logical_threads} threads • reserva {budget.reserved_threads} • Real-ESRGAN {budget.realesrgan_pipeline}"
            )
        else:
            profile_detail.set(f"Manual • {studio.cpu_threads.get()}/{logical_threads} threads lógicas")

    def _sync_machine_profile() -> None:
        _refresh_machine_profile_detail()
        studio._quality_setting_changed()

    def _apply_machine_profile(profile: str) -> None:
        budget = machine_budget(profile, logical_threads, studio._hardware.vram_mb)
        studio.cpu_threads.set(budget.cpu_threads)
        _refresh_machine_profile_detail()
        studio._quality_setting_changed()

    _refresh_machine_profile_detail()

    ttk.Label(machine, text="Threads CPU", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=5)
    threads = ttk.Spinbox(machine, from_=1, to=logical_threads, textvariable=studio.cpu_threads, width=8, command=_sync_machine_profile)
    threads.grid(row=3, column=1, sticky="w", pady=5)
    threads.bind("<FocusOut>", lambda _event: _sync_machine_profile())
    ttk.Label(machine, text="Reserva de disco", style="Card.TLabel").grid(row=4, column=0, sticky="w", pady=5)
    reserve = ttk.Spinbox(machine, from_=1, to=500, increment=1, textvariable=studio.minimum_free_gb, width=8, command=studio._quality_setting_changed)
    reserve.grid(row=4, column=1, sticky="w", pady=5)
    reserve.bind("<FocusOut>", lambda _event: studio._quality_setting_changed())
    ttk.Label(machine, text="GB livres mínimos", style="CardMuted.TLabel").grid(row=4, column=2, sticky="w", padx=(7, 0))

    ttk.Label(machine, text="Disco scratch", style="Card.TLabel").grid(row=5, column=0, sticky="w", pady=5)
    scratch = ttk.Entry(machine, textvariable=studio.scratch_dir, width=30)
    scratch.grid(row=5, column=1, sticky="ew", pady=5)
    scratch.bind("<FocusOut>", lambda _event: studio._quality_setting_changed())
    ttk.Button(machine, text="Escolher…", style="Ghost.TButton", command=studio._choose_scratch_dir).grid(
        row=5, column=2, sticky="e", padx=(7, 0), pady=5
    )

    ttk.Label(machine, text="Limite do cache", style="Card.TLabel").grid(row=6, column=0, sticky="w", pady=5)
    cache_quota = ttk.Spinbox(
        machine, from_=1, to=2000, increment=5, textvariable=studio.cache_quota_gb, width=8,
        command=studio._quality_setting_changed,
    )
    cache_quota.grid(row=6, column=1, sticky="w", pady=5)
    cache_quota.bind("<FocusOut>", lambda _event: studio._quality_setting_changed())
    ttk.Label(machine, text="GB • limpeza LRU automática", style="CardMuted.TLabel").grid(row=6, column=2, sticky="w", padx=(7, 0))


    ttk.Label(machine, text="Perfil de utilização", style="Card.TLabel").grid(row=7, column=0, sticky="w", pady=(10, 5))
    profiles = ttk.Frame(machine, style="Card.TFrame")
    profiles.grid(row=7, column=1, columnspan=2, sticky="ew", pady=(10, 5))
    for profile in MACHINE_PROFILES:
        ttk.Button(
            profiles, text=profile, style="Ghost.TButton",
            command=lambda value=profile: _apply_machine_profile(value),
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
    ttk.Label(
        machine, textvariable=profile_detail, style="CardMuted.TLabel", wraplength=395, justify="left"
    ).grid(row=8, column=0, columnspan=3, sticky="w", pady=(0, 2))

    # --- Impact panel -------------------------------------------------
    impact = ttk.Frame(right, style="Card.TFrame", padding=14)
    impact.grid(row=0, column=0, sticky="ew")
    impact.columnconfigure(0, weight=1)
    header = ttk.Frame(impact, style="Card.TFrame")
    header.grid(row=0, column=0, sticky="ew")
    header.columnconfigure(0, weight=1)
    ttk.Label(header, text="Impacto desta configuração", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
    studio.quality_load_badge_label = ttk.Label(header, textvariable=studio.quality_load_badge, style="CardStatus.TLabel")
    studio.quality_load_badge_label.grid(row=0, column=1, sticky="e")
    ttk.Label(
        impact,
        text="Carga é uma heurística comparativa, não uma promessa de tempo de render.",
        style="CardMuted.TLabel",
    ).grid(row=1, column=0, sticky="w", pady=(2, 10))

    source_target = ttk.Frame(impact, style="PanelAlt.TFrame", padding=12)
    source_target.grid(row=2, column=0, sticky="ew")
    source_target.columnconfigure(0, weight=1)
    source_target.columnconfigure(1, weight=1)
    ttk.Label(source_target, text="FONTE", style="PanelAlt.TLabel", font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(source_target, text="DESTINO", style="PanelAlt.TLabel", font=("Segoe UI", 8, "bold")).grid(row=0, column=1, sticky="w")
    ttk.Label(source_target, textvariable=studio.quality_source_text, style="PanelAlt.TLabel", wraplength=250).grid(row=1, column=0, sticky="nw", padx=(0, 10), pady=(4, 0))
    ttk.Label(source_target, textvariable=studio.quality_target_text, style="PanelAlt.TLabel", wraplength=250).grid(row=1, column=1, sticky="nw", pady=(4, 0))

    metrics = ttk.Frame(impact, style="Card.TFrame")
    metrics.grid(row=3, column=0, sticky="ew", pady=(12, 0))
    for col in range(2):
        metrics.columnconfigure(col, weight=1)

    def metric(row: int, col: int, title: str, variable) -> None:
        card = ttk.Frame(metrics, style="PanelAlt.TFrame", padding=10)
        card.grid(row=row, column=col, sticky="nsew", padx=(0, 6) if col == 0 else (6, 0), pady=(0, 8))
        ttk.Label(card, text=title, style="PanelAlt.TLabel", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        ttk.Label(card, textvariable=variable, style="PanelAlt.TLabel", wraplength=240).pack(anchor="w", pady=(3, 0))

    metric(0, 0, "ESCALA", studio.quality_scale_text)
    metric(0, 1, "MOVIMENTO", studio.quality_motion_text)
    metric(1, 0, "VRAM / IA", studio.quality_vram_text)
    metric(1, 1, "ARQUIVO ESTIMADO", studio.quality_output_text)

    # --- Real render plan ----------------------------------------------
    plan = ttk.Frame(right, style="Card.TFrame", padding=14)
    plan.grid(row=1, column=0, sticky="ew", pady=(10, 0))
    plan.columnconfigure(0, weight=1)
    ttk.Label(plan, text="Plano real de processamento", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
    studio.quality_plan_badge_label = ttk.Label(plan, textvariable=studio.quality_plan_badge, style="StatusMuted.TLabel")
    studio.quality_plan_badge_label.grid(row=0, column=1, sticky="e")
    ttk.Label(
        plan,
        text=(
            "Core Integrity: esta lista vem do mesmo RenderPlan usado pela pré-verificação e pelo worker. "
            "Na Phase 5, codec, contêiner e áudio também fazem parte do contrato real de entrega."
        ),
        style="CardMuted.TLabel",
        wraplength=540,
        justify="left",
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 8))
    plan_body = ttk.Frame(plan, style="PanelAlt.TFrame", padding=10)
    plan_body.grid(row=2, column=0, columnspan=2, sticky="ew")
    ttk.Label(
        plan_body,
        textvariable=studio.quality_plan_text,
        style="PanelAlt.TLabel",
        wraplength=520,
        justify="left",
    ).pack(anchor="w")
    ttk.Label(
        plan,
        textvariable=studio.quality_plan_risk_text,
        style="CardMuted.TLabel",
        wraplength=540,
        justify="left",
    ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

    # --- Compatibility ------------------------------------------------
    warnings = ttk.Frame(right, style="Card.TFrame", padding=14)
    warnings.grid(row=2, column=0, sticky="ew", pady=(10, 0))
    warnings.columnconfigure(0, weight=1)
    ttk.Label(warnings, text="Compatibilidade e avisos", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
    studio.quality_compat_badge_label = ttk.Label(warnings, textvariable=studio.quality_compat_badge, style="StatusMuted.TLabel")
    studio.quality_compat_badge_label.grid(row=0, column=1, sticky="e")
    ttk.Label(warnings, textvariable=studio.quality_warning_text, style="CardMuted.TLabel", wraplength=540, justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=(7, 0))
    action_row = ttk.Frame(warnings, style="Card.TFrame")
    action_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
    ttk.Button(action_row, text="IA local →", command=lambda: studio.notebook.select(5)).pack(side="left")
    ttk.Button(action_row, text="Verificar projeto", command=studio._request_project_preflight).pack(side="left", padx=(7, 0))
    ttk.Button(action_row, text="Gerar preview", style="Primary.TButton", command=lambda: studio._start(True)).pack(side="right")

    # --- Interpretation guide ----------------------------------------
    guide = ttk.Frame(right, style="Card.TFrame", padding=14)
    guide.grid(row=3, column=0, sticky="ew", pady=(10, 0))
    ttk.Label(guide, text="Como interpretar as escolhas", style="CardTitle.TLabel").pack(anchor="w")
    ttk.Label(
        guide,
        text=(
            "Resolução aumenta detalhe de saída e custo por quadro. FPS aumenta o número de quadros. "
            "Real-ESRGAN tenta reconstruir detalhe plausível, mas não recupera informação que nunca existiu. "
            "RIFE tenta criar movimento intermediário; acima de 120 fps o custo cresce muito e a compatibilidade cai."
        ),
        style="CardMuted.TLabel",
        wraplength=540,
        justify="left",
    ).pack(anchor="w", pady=(4, 0))
