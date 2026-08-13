"""Tk construction for the Phase 5 queue workspace."""

from __future__ import annotations

from tkinter import ttk

from .polish_view import register_responsive_split



def build_queue_tab(studio, parent) -> None:
    parent.rowconfigure(1, weight=1)
    parent.columnconfigure(0, weight=1)

    # --- Queue overview -------------------------------------------------
    overview = ttk.Frame(parent, style="Card.TFrame", padding=14)
    overview.grid(row=0, column=0, sticky="ew", pady=(0, 10))
    overview.columnconfigure(0, weight=1)
    ttk.Label(overview, text="Fila de render", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(
        overview,
        text="Cada item preserva seus próprios arquivos, qualidade, VFX e opções de áudio. A ordem só pode ser alterada com a fila parada.",
        style="CardMuted.TLabel",
        wraplength=930,
        justify="left",
    ).grid(row=1, column=0, sticky="w", pady=(2, 10))

    actions = ttk.Frame(overview, style="Card.TFrame")
    actions.grid(row=0, column=1, rowspan=2, sticky="e", padx=(14, 0))
    studio.start_queue_button = ttk.Button(actions, text="Iniciar fila", style="Primary.TButton", command=studio._start_queue)
    studio.start_queue_button.pack(side="left")
    studio.queue_stop_button = ttk.Button(actions, text="Cancelar execução", command=studio._cancel)
    studio.queue_stop_button.pack(side="left", padx=(8, 0))

    stats = ttk.Frame(overview, style="Card.TFrame")
    stats.grid(row=2, column=0, columnspan=2, sticky="ew")
    for col in range(4):
        stats.columnconfigure(col, weight=1)

    cards = (
        ("NA FILA", studio.queue_waiting_text, "PanelAltMuted.TLabel"),
        ("EM PROCESSAMENTO", studio.queue_active_text, "PanelAltPrimary.TLabel"),
        ("CONCLUÍDOS", studio.queue_done_text, "PanelAltSuccess.TLabel"),
        ("ATENÇÃO", studio.queue_attention_text, "PanelAltWarning.TLabel"),
    )
    for col, (title, variable, style) in enumerate(cards):
        card = ttk.Frame(stats, style="PanelAlt.TFrame", padding=(11, 9))
        card.grid(row=0, column=col, sticky="nsew", padx=(0, 6) if col < 3 else 0)
        ttk.Label(card, text=title, style="PanelAlt.TLabel", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        ttk.Label(card, textvariable=variable, style=style, font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(2, 0))

    # --- Main queue / inspector ----------------------------------------
    body = ttk.Frame(parent)
    body.grid(row=1, column=0, sticky="nsew")
    body.rowconfigure(0, weight=1)
    body.columnconfigure(0, weight=7)
    body.columnconfigure(1, weight=4)

    list_card = ttk.Frame(body, style="Card.TFrame", padding=12)
    list_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    list_card.rowconfigure(2, weight=1)
    list_card.columnconfigure(0, weight=1)

    list_header = ttk.Frame(list_card, style="Card.TFrame")
    list_header.grid(row=0, column=0, sticky="ew")
    list_header.columnconfigure(0, weight=1)
    ttk.Label(list_header, text="Projetos", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(list_header, textvariable=studio.queue_overview_text, style="CardMuted.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))
    reorder = ttk.Frame(list_header, style="Card.TFrame")
    reorder.grid(row=0, column=1, rowspan=2, sticky="e")
    ttk.Button(reorder, text="↑", width=3, command=lambda: studio._move_queue_item(-1)).pack(side="left")
    ttk.Button(reorder, text="↓", width=3, command=lambda: studio._move_queue_item(1)).pack(side="left", padx=(5, 0))

    ttk.Label(
        list_card,
        textvariable=studio.queue_empty_text,
        style="CardMuted.TLabel",
        wraplength=680,
        justify="left",
    ).grid(row=1, column=0, sticky="w", pady=(8, 6))

    table = ttk.Frame(list_card, style="Card.TFrame")
    table.grid(row=2, column=0, sticky="nsew")
    table.rowconfigure(0, weight=1)
    table.columnconfigure(0, weight=1)
    columns = ("ordem", "projeto", "perfil", "progresso", "status")
    studio.queue_tree = ttk.Treeview(table, columns=columns, show="headings", selectmode="browse")
    studio.queue_tree.heading("ordem", text="#")
    studio.queue_tree.heading("projeto", text="Projeto")
    studio.queue_tree.heading("perfil", text="Qualidade")
    studio.queue_tree.heading("progresso", text="Progresso")
    studio.queue_tree.heading("status", text="Estado")
    studio.queue_tree.column("ordem", width=42, minwidth=42, stretch=False, anchor="center")
    studio.queue_tree.column("projeto", width=220, anchor="w")
    studio.queue_tree.column("perfil", width=240, anchor="w")
    studio.queue_tree.column("progresso", width=90, minwidth=80, stretch=False, anchor="center")
    studio.queue_tree.column("status", width=125, minwidth=110, stretch=False, anchor="center")
    scroll = ttk.Scrollbar(table, orient="vertical", command=studio.queue_tree.yview)
    studio.queue_tree.configure(yscrollcommand=scroll.set)
    studio.queue_tree.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns")
    studio.queue_tree.bind("<<TreeviewSelect>>", studio._queue_selection_changed)
    studio.queue_tree.bind("<Double-1>", lambda _event: studio._open_selected_queue_output())

    list_actions = ttk.Frame(list_card, style="Card.TFrame")
    list_actions.grid(row=3, column=0, sticky="ew", pady=(10, 0))
    ttk.Button(list_actions, text="Tentar novamente", command=studio._retry_queue_item).pack(side="left")
    ttk.Button(list_actions, text="Remover", command=studio._remove_queue_item).pack(side="left", padx=(7, 0))
    ttk.Button(list_actions, text="Limpar concluídos", command=studio._clear_completed_queue).pack(side="left", padx=(7, 0))
    ttk.Button(list_actions, text="Limpar fila", style="Danger.TButton", command=studio._clear_queue).pack(side="right")

    # --- Selected item inspector ---------------------------------------
    detail = ttk.Frame(body, style="Card.TFrame", padding=14)
    register_responsive_split(studio, "queue", body, list_card, detail, weights=(7, 4), min_sizes=(0, 0), wide_pad=6)
    detail.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
    detail.columnconfigure(0, weight=1)
    ttk.Label(detail, text="Item selecionado", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
    studio.queue_selected_badge_label = ttk.Label(detail, textvariable=studio.queue_selected_badge, style="StatusMuted.TLabel")
    studio.queue_selected_badge_label.grid(row=0, column=1, sticky="e")
    ttk.Label(detail, textvariable=studio.queue_selected_title, style="Card.TLabel", font=("Segoe UI", 12, "bold"), wraplength=390).grid(row=1, column=0, columnspan=2, sticky="w", pady=(7, 1))
    ttk.Label(detail, textvariable=studio.queue_selected_profile, style="CardMuted.TLabel", wraplength=390).grid(row=2, column=0, columnspan=2, sticky="w")

    progress_box = ttk.Frame(detail, style="PanelAlt.TFrame", padding=10)
    progress_box.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(11, 0))
    progress_box.columnconfigure(0, weight=1)
    ttk.Label(progress_box, textvariable=studio.queue_selected_stage, style="PanelAlt.TLabel", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(progress_box, textvariable=studio.queue_selected_progress_text, style="PanelAlt.TLabel").grid(row=0, column=1, sticky="e")
    studio.queue_selected_progressbar = ttk.Progressbar(progress_box, maximum=100, variable=studio.queue_selected_progress, style="Studio.Horizontal.TProgressbar")
    studio.queue_selected_progressbar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))

    def detail_row(row: int, title: str, variable) -> None:
        ttk.Label(detail, text=title, style="CardMuted.TLabel", font=("Segoe UI", 8, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(11, 0))
        ttk.Label(detail, textvariable=variable, style="Card.TLabel", wraplength=390, justify="left").grid(row=row + 1, column=0, columnspan=2, sticky="w", pady=(2, 0))

    detail_row(4, "ENTRADA", studio.queue_selected_input)
    detail_row(6, "SAÍDA", studio.queue_selected_output)
    detail_row(8, "PROCESSAMENTO", studio.queue_selected_processing)
    detail_row(10, "VFX", studio.queue_selected_effects)
    detail_row(12, "ÚLTIMO DETALHE", studio.queue_selected_note)

    selected_actions = ttk.Frame(detail, style="Card.TFrame")
    selected_actions.grid(row=14, column=0, columnspan=2, sticky="ew", pady=(14, 0))
    ttk.Button(selected_actions, text="Abrir saída", command=studio._open_selected_queue_output).pack(side="left")
    ttk.Button(selected_actions, text="Abrir relatório", command=studio._open_selected_queue_report).pack(side="left", padx=(7, 0))
    ttk.Button(selected_actions, text="Histórico técnico", command=studio._open_selected_queue_history).pack(side="left", padx=(7, 0))
    ttk.Button(selected_actions, text="Carregar no editor", command=studio._load_selected_queue_item).pack(side="right")
