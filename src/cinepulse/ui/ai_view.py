"""Tk construction for the Phase 6 local-AI capability manager."""

from __future__ import annotations

from tkinter import ttk

from .polish_view import register_responsive_split
from .restoration_view import build_restoration_panel


FILTERS = ("Todos", "No render", "Experimentais", "Faltando")


def build_ai_tab(studio, parent) -> None:
    parent.columnconfigure(0, weight=1)

    # --- Overview -----------------------------------------------------
    overview = ttk.Frame(parent, style="Card.TFrame", padding=14)
    overview.grid(row=0, column=0, sticky="ew", pady=(0, 10))
    overview.columnconfigure(0, weight=1)

    title = ttk.Frame(overview, style="Card.TFrame")
    title.grid(row=0, column=0, sticky="ew")
    title.columnconfigure(0, weight=1)
    ttk.Label(title, text="IA local e capacidades", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(
        title,
        text="Veja o que realmente participa do render, o que está faltando e o que é apenas experimental.",
        style="CardMuted.TLabel",
        wraplength=760,
    ).grid(row=1, column=0, sticky="w", pady=(2, 0))
    title_actions = ttk.Frame(title, style="Card.TFrame")
    title_actions.grid(row=0, column=1, rowspan=2, sticky="e", padx=(14, 0))
    ttk.Button(title_actions, text="Reverificar", command=studio._reprobe_ai_inventory).pack(side="left")
    ttk.Button(title_actions, text="Abrir pasta da IA", command=studio._open_ai_folder).pack(side="left", padx=(7, 0))
    ttk.Button(title_actions, text="Documentação", command=studio._open_ai_docs).pack(side="left", padx=(7, 0))

    stats = ttk.Frame(overview, style="Card.TFrame")
    stats.grid(row=1, column=0, sticky="ew", pady=(12, 0))
    for col in range(4):
        stats.columnconfigure(col, weight=1)
    cards = (
        ("NO RENDER", studio.ai_integrated_ready_text, "PanelAltSuccess.TLabel"),
        ("FALTANDO", studio.ai_integrated_missing_text, "PanelAltWarning.TLabel"),
        ("EXPERIMENTAIS", studio.ai_experimental_installed_text, "PanelAltPrimary.TLabel"),
        ("SELEÇÃO", studio.ai_selection_size_text, "PanelAlt.TLabel"),
    )
    for col, (label, variable, value_style) in enumerate(cards):
        card = ttk.Frame(stats, style="PanelAlt.TFrame", padding=(11, 9))
        card.grid(row=0, column=col, sticky="nsew", padx=(0, 6) if col < 3 else 0)
        ttk.Label(card, text=label, style="PanelAltMuted.TLabel", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        ttk.Label(card, textvariable=variable, style=value_style, font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(2, 0))

    truth = ttk.Frame(parent, style="PanelAlt.TFrame", padding=(12, 10))
    truth.grid(row=1, column=0, sticky="ew", pady=(0, 10))
    ttk.Label(truth, text="Instalado ≠ integrado", style="PanelAltPrimary.TLabel").pack(anchor="w")
    ttk.Label(
        truth,
        text=(
            "Real-ESRGAN, RIFE, Demucs e VMAF possuem integração no pipeline atual. "
            "BasicVSR++, CLAP, Depth, SAM 2, CoTracker, CodeFormer e LTX podem ter arquivos no disco sem participar de nenhum render."
        ),
        style="PanelAlt.TLabel",
        wraplength=1030,
        justify="left",
    ).pack(anchor="w", pady=(3, 0))

    # --- Inventory + inspector ---------------------------------------
    body = ttk.Frame(parent)
    body.grid(row=2, column=0, sticky="nsew")
    body.columnconfigure(0, weight=7)
    body.columnconfigure(1, weight=4)

    inventory = ttk.Frame(body, style="Card.TFrame", padding=12)
    inventory.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    inventory.columnconfigure(0, weight=1)

    header = ttk.Frame(inventory, style="Card.TFrame")
    header.grid(row=0, column=0, sticky="ew")
    header.columnconfigure(0, weight=1)
    ttk.Label(header, text="Capacidades disponíveis", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(header, textvariable=studio.ai_inventory_text, style="CardMuted.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))
    filter_row = ttk.Frame(header, style="Card.TFrame")
    filter_row.grid(row=0, column=1, rowspan=2, sticky="e")
    studio._ai_filter_buttons = {}
    for value in FILTERS:
        selected = studio.ai_filter.get() == value
        button = ttk.Button(
            filter_row,
            text=value,
            style="Selected.Ghost.TButton" if selected else "Ghost.TButton",
            command=lambda selected_value=value: studio._set_ai_filter(selected_value),
        )
        button.pack(side="left", padx=(0, 5))
        studio._ai_filter_buttons[value] = button

    table = ttk.Frame(inventory, style="Card.TFrame")
    table.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
    table.rowconfigure(0, weight=1)
    table.columnconfigure(0, weight=1)
    columns = ("selecionar", "modulo", "beneficio", "estado")
    studio.ai_tree = ttk.Treeview(table, columns=columns, show="headings", selectmode="browse", height=12)
    studio.ai_tree.heading("selecionar", text="Baixar")
    studio.ai_tree.heading("modulo", text="Módulo")
    studio.ai_tree.heading("beneficio", text="O que entrega")
    studio.ai_tree.heading("estado", text="Estado real")
    studio.ai_tree.column("selecionar", width=60, minwidth=60, stretch=False, anchor="center")
    studio.ai_tree.column("modulo", width=170, minwidth=145, anchor="w")
    studio.ai_tree.column("beneficio", width=340, minwidth=250, anchor="w")
    studio.ai_tree.column("estado", width=230, minwidth=190, anchor="w")
    scroll = ttk.Scrollbar(table, orient="vertical", command=studio.ai_tree.yview)
    studio.ai_tree.configure(yscrollcommand=scroll.set)
    studio.ai_tree.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns")
    studio.ai_tree.bind("<Button-1>", studio._toggle_ai_component)
    studio.ai_tree.bind("<space>", studio._toggle_focused_ai_component)
    studio.ai_tree.bind("<<TreeviewSelect>>", studio._ai_selection_changed)

    selection = ttk.Frame(inventory, style="PanelAlt.TFrame", padding=(10, 8))
    selection.grid(row=2, column=0, sticky="ew", pady=(10, 0))
    selection.columnconfigure(0, weight=1)
    ttk.Label(selection, textvariable=studio.ai_selection_text, style="PanelAlt.TLabel", wraplength=640).grid(row=0, column=0, sticky="w")
    selection_actions = ttk.Frame(selection, style="PanelAlt.TFrame")
    selection_actions.grid(row=1, column=0, sticky="ew", pady=(8, 0))
    studio.ai_select_missing_button = ttk.Button(selection_actions, text="Selecionar necessários", command=studio._select_missing_ai_components)
    studio.ai_select_missing_button.pack(side="left")
    ttk.Button(selection_actions, text="Limpar seleção", command=studio._clear_ai_selection).pack(side="left", padx=(7, 0))
    studio.ai_install_selected_button = ttk.Button(
        selection_actions, text="Instalar selecionados", style="Primary.TButton", command=studio._install_selected_ai_components,
    )
    studio.ai_install_selected_button.pack(side="right")
    # Kept as an attribute because the install worker historically disables it.
    studio.ai_install_all_button = ttk.Button(selection_actions, text="Instalar necessários", command=studio._install_required_ai_components)
    studio.ai_install_all_button.pack(side="right", padx=(0, 7))

    install_feedback = ttk.Frame(selection, style="PanelAlt.TFrame")
    install_feedback.grid(row=2, column=0, sticky="ew", pady=(9, 0))
    install_feedback.columnconfigure(0, weight=1)
    ttk.Label(install_feedback, textvariable=studio.ai_install_status_text, style="PanelAltMuted.TLabel", wraplength=650).grid(row=0, column=0, sticky="w")
    ttk.Label(install_feedback, textvariable=studio.ai_install_progress_text, style="PanelAltPrimary.TLabel").grid(row=0, column=1, sticky="e", padx=(10, 0))
    studio.ai_install_progressbar = ttk.Progressbar(
        install_feedback, maximum=100, variable=studio.ai_install_progress, style="Studio.Horizontal.TProgressbar"
    )
    studio.ai_install_progressbar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))

    experimental = ttk.Frame(inventory, style="Card.TFrame")
    experimental.grid(row=3, column=0, sticky="ew", pady=(10, 0))
    ttk.Separator(experimental).pack(fill="x", pady=(0, 10))
    ttk.Checkbutton(
        experimental,
        text="Permitir seleção e download de componentes experimentais",
        variable=studio.experimental_downloads,
        command=studio._experimental_download_mode_changed,
    ).pack(anchor="w")
    ttk.Label(
        experimental,
        text=(
            "O aceite libera somente o download. Não ativa integração, não altera o render e não substitui a revisão das licenças. "
            "Componentes com restrição não comercial continuam identificados no inspector."
        ),
        style="CardMuted.TLabel",
        wraplength=760,
        justify="left",
    ).pack(anchor="w", pady=(3, 0))

    # --- Inspector ----------------------------------------------------
    detail = ttk.Frame(body, style="Card.TFrame", padding=14)
    register_responsive_split(studio, "ai", body, inventory, detail, weights=(7, 4), min_sizes=(0, 0), wide_pad=6)
    detail.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
    detail.columnconfigure(0, weight=1)
    ttk.Label(detail, text="Componente selecionado", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
    studio.ai_detail_badge_label = ttk.Label(detail, textvariable=studio.ai_detail_badge, style="StatusMuted.TLabel")
    studio.ai_detail_badge_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
    ttk.Label(detail, textvariable=studio.ai_detail_name, style="Card.TLabel", font=("Segoe UI", 12, "bold"), wraplength=380).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 1))
    ttk.Label(detail, textvariable=studio.ai_detail_category, style="CardMuted.TLabel").grid(row=3, column=0, columnspan=2, sticky="w")

    state = ttk.Frame(detail, style="PanelAlt.TFrame", padding=10)
    state.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(11, 0))
    state.columnconfigure(0, weight=1)
    studio.ai_detail_state_label = ttk.Label(state, textvariable=studio.ai_detail_state, style="PanelAltPrimary.TLabel", font=("Segoe UI", 9, "bold"))
    studio.ai_detail_state_label.grid(row=0, column=0, sticky="w")
    ttk.Label(state, textvariable=studio.ai_detail_state_explanation, style="PanelAlt.TLabel", wraplength=370, justify="left").grid(row=1, column=0, sticky="w", pady=(3, 0))

    def detail_block(row: int, title_text: str, variable) -> None:
        ttk.Label(detail, text=title_text, style="CardMuted.TLabel", font=("Segoe UI", 8, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(11, 0))
        ttk.Label(detail, textvariable=variable, style="Card.TLabel", wraplength=380, justify="left").grid(row=row + 1, column=0, columnspan=2, sticky="w", pady=(2, 0))

    detail_block(5, "O QUE ENTREGA", studio.ai_detail_benefit)
    detail_block(7, "NO CINEPULSE", studio.ai_detail_render_usage)
    detail_block(9, "SE ESTIVER AUSENTE", studio.ai_detail_missing_effect)
    detail_block(11, "ESPAÇO", studio.ai_detail_footprint)
    detail_block(13, "LICENÇA", studio.ai_detail_license)
    ttk.Label(detail, textvariable=studio.ai_detail_license_warning, style="StatusWarning.TLabel", wraplength=380, justify="left").grid(row=15, column=0, columnspan=2, sticky="w", pady=(4, 0))
    detail_block(16, "RECOMENDAÇÃO", studio.ai_detail_recommendation)

    detail_actions = ttk.Frame(detail, style="Card.TFrame")
    detail_actions.grid(row=18, column=0, columnspan=2, sticky="ew", pady=(14, 0))
    studio.ai_detail_toggle_button = ttk.Button(detail_actions, text="Selecionar para instalar", command=studio._toggle_selected_ai_detail)
    studio.ai_detail_toggle_button.pack(side="left")
    ttk.Button(detail_actions, text="Abrir documentação", command=studio._open_ai_docs).pack(side="right")

    build_restoration_panel(studio, parent)
    studio._refresh_ai_tree()
