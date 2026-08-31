from __future__ import annotations

from dataclasses import dataclass

from ..recovery_service import RecoveryCandidate


STATUS_META = {
    "active": ("Processando", "primary"),
    "needs_audit": ("Conferindo trabalho preservado", "info"),
    "recoverable": ("Pronto para retomar", "info"),
    "blocked": ("Ação necessária", "danger"),
}

ACTION_LABELS = {
    "acompanhar": "Acompanhar",
    "pausar": "Pausar com segurança",
    "inspecionar": "Inspecionar",
    "auditar": "Conferir integridade",
    "retomar": "Retomar com segurança",
    "preservar": "Preservar por enquanto",
    "reconectar_fonte": "Reconectar fonte",
    "verificar": "Concluir verificação",
}


@dataclass(frozen=True)
class RecoveryCardModel:
    job_id: str
    title: str
    badge: str
    tone: str
    phase: str
    phase_progress: str
    reason: str
    origin: str
    actions: tuple[tuple[str, str], ...]


def progress_text(candidate: RecoveryCandidate) -> str:
    if candidate.units_total is None or candidate.units_total <= 0:
        return f"{candidate.units_committed} unidade(s) confirmada(s)"
    percent = 100.0 * candidate.units_committed / max(1, candidate.units_total)
    return f"{candidate.units_committed}/{candidate.units_total} confirmadas · {percent:.2f}% da fase"


def card_model(candidate: RecoveryCandidate) -> RecoveryCardModel:
    badge, tone = STATUS_META.get(candidate.classification, (candidate.classification, "neutral"))
    if candidate.classification == "active":
        title = "Render em andamento"
    elif candidate.classification == "recoverable":
        title = "Render interrompido encontrado"
    elif candidate.classification == "needs_audit":
        title = "Trabalho preservado encontrado"
    else:
        title = "Não é seguro continuar ainda"
    return RecoveryCardModel(
        job_id=candidate.job_id,
        title=title,
        badge=badge,
        tone=tone,
        phase=candidate.phase,
        phase_progress=progress_text(candidate),
        reason=candidate.reason,
        origin=candidate.origin,
        actions=tuple((action, ACTION_LABELS.get(action, action)) for action in candidate.actions),
    )
