from __future__ import annotations

from tkinter import ttk
from typing import Callable, Iterable

from ..recovery_service import RecoveryCandidate
from .recovery_lab import card_model


def build_recovery_panel(
    parent,
    candidates: Iterable[RecoveryCandidate],
    *,
    on_action: Callable[[str, str], None],
):
    """Build the recovery activity panel without owning discovery or execution."""
    container = ttk.Frame(parent, padding=12)
    header = ttk.Frame(container)
    header.pack(fill="x", pady=(0, 8))
    ttk.Label(header, text="Recuperação de renders", style="Heading.TLabel").pack(side="left")
    ttk.Label(
        header,
        text="Trabalho preservado após pausas, quedas ou reinicializações.",
    ).pack(side="left", padx=(12, 0))

    models = [card_model(candidate) for candidate in candidates]
    if not models:
        ttk.Label(container, text="Nenhum render interrompido precisa de atenção.").pack(anchor="w", pady=12)
        return container

    for model in models:
        card = ttk.LabelFrame(container, text=model.title, padding=10)
        card.pack(fill="x", pady=6)
        top = ttk.Frame(card)
        top.pack(fill="x")
        ttk.Label(top, text=model.badge).pack(side="left")
        ttk.Label(top, text=model.origin).pack(side="right")
        ttk.Label(card, text=f"Fase: {model.phase} · {model.phase_progress}").pack(anchor="w", pady=(6, 0))
        ttk.Label(card, text=model.reason, wraplength=760).pack(anchor="w", pady=(4, 8))
        actions = ttk.Frame(card)
        actions.pack(fill="x")
        for action, label in model.actions:
            ttk.Button(
                actions,
                text=label,
                command=lambda job_id=model.job_id, selected=action: on_action(job_id, selected),
            ).pack(side="left", padx=(0, 6))
    return container
