"""Tk widgets for Phase 7 global feedback and activity history."""

from __future__ import annotations

from tkinter import Text, Toplevel, ttk

from .tokens import COLORS


def build_feedback_strip(studio, parent) -> None:
    """Build the compact global state strip used in the persistent footer."""
    studio.feedback_frame = ttk.Frame(parent, style="FeedbackInfo.TFrame", padding=(10, 8))
    studio.feedback_frame.pack(fill="x", pady=(6, 0))
    studio.feedback_frame.columnconfigure(1, weight=1)

    studio.feedback_badge_label = ttk.Label(
        studio.feedback_frame,
        textvariable=studio.feedback_badge,
        style="FeedbackInfoBadge.TLabel",
        width=13,
        anchor="center",
    )
    studio.feedback_badge_label.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(0, 10))

    studio.feedback_title_label = ttk.Label(
        studio.feedback_frame,
        textvariable=studio.feedback_title,
        style="FeedbackInfoTitle.TLabel",
    )
    studio.feedback_title_label.grid(row=0, column=1, sticky="w")
    studio.feedback_detail_label = ttk.Label(
        studio.feedback_frame,
        textvariable=studio.feedback_detail,
        style="FeedbackInfoDetail.TLabel",
        wraplength=760,
        justify="left",
    )
    studio.feedback_detail_label.grid(row=1, column=1, sticky="w", pady=(2, 0))

    actions = ttk.Frame(studio.feedback_frame, style="FeedbackInfo.TFrame")
    actions.grid(row=0, column=2, rowspan=2, sticky="e", padx=(12, 0))
    studio.feedback_primary_button = ttk.Button(actions, text="", command=studio._run_feedback_primary)
    studio.feedback_secondary_button = ttk.Button(actions, text="", command=studio._run_feedback_secondary)
    studio.feedback_activity_button = ttk.Button(actions, text="Atividade", command=studio._show_activity_center)
    studio.feedback_activity_button.pack(side="right")


def refresh_feedback_strip(studio, style_key: str) -> None:
    frame_style = f"Feedback{style_key}.TFrame"
    studio.feedback_frame.configure(style=frame_style)
    studio.feedback_badge_label.configure(style=f"Feedback{style_key}Badge.TLabel")
    studio.feedback_title_label.configure(style=f"Feedback{style_key}Title.TLabel")
    studio.feedback_detail_label.configure(style=f"Feedback{style_key}Detail.TLabel")

    # The button container has its own background, so keep it in sync.
    for child in studio.feedback_frame.winfo_children():
        if isinstance(child, ttk.Frame):
            child.configure(style=frame_style)

    for button, label in (
        (studio.feedback_primary_button, studio.feedback_primary_action),
        (studio.feedback_secondary_button, studio.feedback_secondary_action),
    ):
        if button.winfo_manager():
            button.pack_forget()
        text = label.get().strip()
        if text:
            button.configure(text=text)
            button.pack(side="right", padx=(6, 0))

    studio.feedback_activity_button.configure(text=f"Atividade ({studio.feedback_history_count.get()})")
    if not studio.feedback_activity_button.winfo_manager():
        studio.feedback_activity_button.pack(side="right")


def refresh_activity_center(studio) -> None:
    """Refresh an already-open activity center without recreating the window."""
    window = getattr(studio, "_activity_window", None)
    tree = getattr(studio, "_activity_tree", None)
    detail = getattr(studio, "_activity_detail", None)
    if window is None or tree is None or detail is None:
        return
    try:
        if not window.winfo_exists():
            return
    except Exception:
        return

    dark = bool(studio.dark_mode.get())
    detail.configure(
        background=COLORS["dark_field"] if dark else COLORS["light_field"],
        foreground=COLORS["dark_text"] if dark else COLORS["light_text"],
        insertbackground=COLORS["dark_text"] if dark else COLORS["light_text"],
    )

    previous = tree.selection()
    previous_key = ""
    if previous:
        try:
            previous_key = str(tree.item(previous[0], "values")[-1])
        except Exception:
            previous_key = ""

    tree.delete(*tree.get_children())
    entries = studio._feedback_history.newest_first()
    labels = {
        "info": "Info",
        "busy": "Processando",
        "success": "Concluído",
        "warning": "Atenção",
        "error": "Bloqueado",
    }
    selected_iid = ""
    for index, entry in enumerate(entries):
        iid = str(index)
        tree.insert(
            "",
            "end",
            iid=iid,
            values=(entry.created_at or "—", labels.get(entry.severity, entry.severity), entry.category, entry.title),
        )
        if previous_key and entry.title == previous_key and not selected_iid:
            selected_iid = iid

    if not entries:
        detail.configure(state="normal")
        detail.delete("1.0", "end")
        detail.insert("1.0", "Nenhuma atividade relevante registrada nesta sessão.")
        detail.configure(state="disabled")
        return

    studio._activity_entries = entries
    tree.selection_set(selected_iid or "0")
    tree.focus(selected_iid or "0")
    tree.event_generate("<<TreeviewSelect>>")


def show_activity_center(studio) -> None:
    existing = getattr(studio, "_activity_window", None)
    if existing is not None and existing.winfo_exists():
        refresh_activity_center(studio)
        existing.lift()
        existing.focus_force()
        return

    window = Toplevel(studio.root)
    window.title("Atividade do CinePulse")
    window.geometry("920x560")
    window.minsize(720, 420)
    studio._activity_window = window

    outer = ttk.Frame(window, padding=12)
    outer.pack(fill="both", expand=True)
    outer.rowconfigure(1, weight=1)
    outer.columnconfigure(0, weight=1)
    outer.columnconfigure(1, weight=1)

    ttk.Label(outer, text="Atividade recente", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(
        outer,
        text="Resumo humano na lista; detalhes técnicos continuam disponíveis no painel ao lado.",
        style="CardMuted.TLabel",
    ).grid(row=0, column=1, sticky="e")

    body = ttk.Frame(outer)
    body.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
    body.rowconfigure(0, weight=1)
    body.columnconfigure(0, weight=3)
    body.columnconfigure(2, weight=4)

    columns = ("hora", "estado", "categoria", "titulo")
    tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="browse")
    tree.heading("hora", text="Hora")
    tree.heading("estado", text="Estado")
    tree.heading("categoria", text="Área")
    tree.heading("titulo", text="Evento")
    tree.column("hora", width=70, stretch=False)
    tree.column("estado", width=100, stretch=False)
    tree.column("categoria", width=120, stretch=False)
    tree.column("titulo", width=320)
    tree.grid(row=0, column=0, sticky="nsew")
    tree_scroll = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
    tree_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8))
    tree.configure(yscrollcommand=tree_scroll.set)

    detail_holder = ttk.Frame(body)
    detail_holder.grid(row=0, column=2, sticky="nsew")
    detail_holder.rowconfigure(0, weight=1)
    detail_holder.columnconfigure(0, weight=1)

    dark = bool(studio.dark_mode.get())
    detail = Text(
        detail_holder,
        wrap="word",
        font=("Segoe UI", 10),
        padx=10,
        pady=10,
        background=COLORS["dark_field"] if dark else COLORS["light_field"],
        foreground=COLORS["dark_text"] if dark else COLORS["light_text"],
        insertbackground=COLORS["dark_text"] if dark else COLORS["light_text"],
        relief="solid",
        borderwidth=1,
    )
    detail.grid(row=0, column=0, sticky="nsew")
    detail_scroll = ttk.Scrollbar(detail_holder, orient="vertical", command=detail.yview)
    detail_scroll.grid(row=0, column=1, sticky="ns")
    detail.configure(yscrollcommand=detail_scroll.set)

    studio._activity_tree = tree
    studio._activity_detail = detail
    studio._activity_entries = tuple()

    def show_selected(_event=None) -> None:
        selected = tree.selection()
        if not selected:
            return
        entries = getattr(studio, "_activity_entries", tuple())
        try:
            entry = entries[int(selected[0])]
        except (IndexError, TypeError, ValueError):
            return
        chunks = [entry.title, "", entry.detail]
        if entry.technical_detail and entry.technical_detail != entry.detail:
            chunks += ["", "DETALHE TÉCNICO", entry.technical_detail]
        detail.configure(state="normal")
        detail.delete("1.0", "end")
        detail.insert("1.0", "\n".join(chunks))
        detail.configure(state="disabled")

    tree.bind("<<TreeviewSelect>>", show_selected)
    tree.bind("<Return>", show_selected)

    def copy_detail(_event=None):
        try:
            content = detail.get("1.0", "end-1c").strip()
            if content:
                studio.root.clipboard_clear()
                studio.root.clipboard_append(content)
                studio.root.update_idletasks()
        except Exception:
            pass
        return "break"

    footer = ttk.Frame(outer)
    footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
    ttk.Label(
        footer,
        text="Histórico desta sessão • máximo de 40 eventos • ações intermediárias repetidas são consolidadas",
        style="CardMuted.TLabel",
    ).pack(side="left")
    ttk.Button(footer, text="Fechar", command=window.destroy).pack(side="right")
    ttk.Button(footer, text="Copiar detalhe", command=copy_detail).pack(side="right", padx=(0, 7))
    tree.bind("<Control-c>", copy_detail)
    detail.bind("<Control-c>", copy_detail)
    window.bind("<Escape>", lambda _event: (window.destroy(), "break")[1])

    def on_destroy(_event=None) -> None:
        try:
            if window.winfo_exists():
                return
        except Exception:
            pass
        studio._activity_window = None
        studio._activity_tree = None
        studio._activity_detail = None
        studio._activity_entries = tuple()

    window.bind("<Destroy>", on_destroy, add="+")
    refresh_activity_center(studio)
    try:
        window.update_idletasks()
        tree.focus_set()
    except Exception:
        pass
