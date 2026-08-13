"""Tk view helpers for Phase 8 final polish and first-run guidance."""

from __future__ import annotations

from tkinter import Text, Toplevel, ttk

from .polish_lab import SHORTCUTS
from .tokens import COLORS


def register_responsive_split(
    studio,
    key: str,
    parent,
    left,
    right,
    *,
    weights: tuple[int, int] = (5, 7),
    min_sizes: tuple[int, int] = (0, 0),
    wide_pad: int = 7,
    base_row: int = 0,
) -> None:
    registry = getattr(studio, "_responsive_splits", None)
    if registry is None:
        studio._responsive_splits = {}
        registry = studio._responsive_splits
    registry[key] = {
        "parent": parent,
        "left": left,
        "right": right,
        "weights": weights,
        "min_sizes": min_sizes,
        "wide_pad": wide_pad,
        "base_row": base_row,
    }


def apply_responsive_splits(studio, compact: bool) -> None:
    """Stack registered two-column workspaces on compact windows."""
    for spec in getattr(studio, "_responsive_splits", {}).values():
        parent = spec["parent"]
        left = spec["left"]
        right = spec["right"]
        left_weight, right_weight = spec["weights"]
        left_min, right_min = spec["min_sizes"]
        pad = spec["wide_pad"]
        base_row = spec.get("base_row", 0)
        if compact:
            parent.columnconfigure(0, weight=1, minsize=0)
            parent.columnconfigure(1, weight=0, minsize=0)
            left.grid_configure(row=base_row, column=0, sticky="nsew", padx=0, pady=(0, pad))
            right.grid_configure(row=base_row + 1, column=0, sticky="nsew", padx=0, pady=(pad, 0))
        else:
            parent.columnconfigure(0, weight=left_weight, minsize=left_min)
            parent.columnconfigure(1, weight=right_weight, minsize=right_min)
            left.grid_configure(row=base_row, column=0, sticky="nsew", padx=(0, pad), pady=0)
            right.grid_configure(row=base_row, column=1, sticky="nsew", padx=(pad, 0), pady=0)


def build_welcome_card(studio, parent) -> None:
    """Build a non-modal first-run card that never blocks the editor."""
    card = ttk.Frame(parent, style="Welcome.TFrame", padding=(14, 12))
    studio.welcome_card = card
    card.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
    card.columnconfigure(0, weight=1)

    copy = ttk.Frame(card, style="Welcome.TFrame")
    copy.grid(row=0, column=0, sticky="ew")
    ttk.Label(copy, text="Primeiros passos", style="WelcomeTitle.TLabel").pack(anchor="w")
    ttk.Label(
        copy,
        text=(
            "1. Escolha vídeo e música  •  2. Confira o visual sem custo pesado  •  "
            "3. Gere um preview renderizado antes do vídeo final"
        ),
        style="WelcomeDetail.TLabel",
        wraplength=900,
        justify="left",
    ).pack(anchor="w", pady=(3, 0))

    actions = ttk.Frame(card, style="Welcome.TFrame")
    actions.grid(row=0, column=1, sticky="e", padx=(14, 0))
    ttk.Button(actions, text="Abrir Projeto", command=lambda: studio._open_tab(1)).pack(side="left")
    ttk.Button(actions, text="Ver Visual Lab", command=lambda: studio._open_tab(3)).pack(side="left", padx=(6, 0))
    ttk.Button(actions, text="Entendi", style="Primary.TButton", command=studio._dismiss_welcome).pack(side="left", padx=(6, 0))


def refresh_welcome_visibility(studio) -> None:
    card = getattr(studio, "welcome_card", None)
    if card is None:
        return
    if bool(getattr(studio, "_welcome_completed", False)):
        card.grid_remove()
    else:
        card.grid()


def refresh_quick_guide_theme(studio) -> None:
    text = getattr(studio, "_quick_guide_text", None)
    window = getattr(studio, "_quick_guide_window", None)
    if text is None or window is None:
        return
    try:
        if not window.winfo_exists():
            return
    except Exception:
        return
    dark = bool(studio.dark_mode.get())
    text.configure(
        background=COLORS["dark_field"] if dark else COLORS["light_field"],
        foreground=COLORS["dark_text"] if dark else COLORS["light_text"],
        insertbackground=COLORS["dark_text"] if dark else COLORS["light_text"],
    )


def show_quick_guide(studio) -> None:
    existing = getattr(studio, "_quick_guide_window", None)
    if existing is not None:
        try:
            if existing.winfo_exists():
                refresh_quick_guide_theme(studio)
                existing.lift()
                existing.focus_force()
                return
        except Exception:
            pass

    window = Toplevel(studio.root)
    window.title("Primeiros passos — CinePulse")
    window.geometry("820x610")
    window.minsize(680, 480)
    studio._quick_guide_window = window

    outer = ttk.Frame(window, padding=16)
    outer.pack(fill="both", expand=True)
    outer.rowconfigure(1, weight=1)
    outer.columnconfigure(0, weight=1)

    ttk.Label(outer, text="Primeiros passos", style="Title.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(
        outer,
        text="Um mapa curto do fluxo — sem esconder as opções avançadas.",
        style="Subtitle.TLabel",
    ).grid(row=0, column=1, sticky="e")

    holder = ttk.Frame(outer)
    holder.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
    holder.rowconfigure(0, weight=1)
    holder.columnconfigure(0, weight=1)
    text = Text(holder, wrap="word", font=("Segoe UI", 10), padx=14, pady=14, relief="solid", borderwidth=1)
    text.grid(row=0, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(holder, orient="vertical", command=text.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    text.configure(yscrollcommand=scrollbar.set)
    studio._quick_guide_text = text

    sections = [
        ("1 — PROJETO", "Escolha o tipo de projeto, vídeo, música e destino. A aba Projeto mostra metadados, enquadramento e saúde do projeto sem modificar a mídia."),
        ("2 — VISUAL", "Use Início ou Visual e transições para experimentar VFX imediatamente. Esse preview visual é leve e representativo; não substitui a validação do render real."),
        ("3 — QUALIDADE", "Defina resolução, FPS, upscale e interpolação. O CinePulse mostra carga relativa, pressão de VRAM e avisos sem inventar uma ETA que a máquina ainda não mediu."),
        ("4 — PREVIEW RENDERIZADO", "Antes do vídeo final, gere um preview curto. É aqui que FFmpeg, áudio, transição temporal, IA e codec são validados de verdade."),
        ("5 — FILA", "Adicione variações à fila para executar em sequência. A fila persiste no disco e itens interrompidos são recuperados para reinício seguro, não para uma continuação fictícia."),
        ("6 — IA LOCAL", "‘Instalado’ não significa ‘integrado’. A aba IA local separa componentes usados pelo render dos experimentais e mostra licença, tamanho e efeito real de cada ausência."),
    ]
    for title, body in sections:
        text.insert("end", title + "\n", ("heading",))
        text.insert("end", body + "\n\n")

    text.insert("end", "ATALHOS DE TECLADO\n", ("heading",))
    for shortcut, action in SHORTCUTS:
        text.insert("end", f"{shortcut:<20} {action}\n")
    text.tag_configure("heading", font=("Segoe UI", 10, "bold"), spacing1=4, spacing3=3)
    text.configure(state="disabled")
    refresh_quick_guide_theme(studio)

    footer = ttk.Frame(outer)
    footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))

    def go_to_tab(index: int) -> None:
        studio._open_tab(index)
        window.destroy()

    ttk.Button(footer, text="Abrir Projeto", command=lambda: go_to_tab(1)).pack(side="left")
    ttk.Button(footer, text="Visual e transições", command=lambda: go_to_tab(3)).pack(side="left", padx=(6, 0))
    ttk.Button(footer, text="Fechar", style="Primary.TButton", command=window.destroy).pack(side="right")

    def close_from_escape(_event=None):
        window.destroy()
        return "break"

    window.bind("<Escape>", close_from_escape)
    window.protocol("WM_DELETE_WINDOW", window.destroy)

    def on_destroy(_event=None) -> None:
        try:
            if window.winfo_exists():
                return
        except Exception:
            pass
        studio._quick_guide_window = None
        studio._quick_guide_text = None

    window.bind("<Destroy>", on_destroy, add="+")
    try:
        window.update_idletasks()
        window.focus_force()
    except Exception:
        pass
