"""Cross-cutting feedback semantics for CinePulse.

Phase 7 centralises user-facing states without changing render contracts.  The
module deliberately keeps technical errors available while deriving a concise,
actionable summary for the UI.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable
import time

SEVERITIES = ("info", "busy", "success", "warning", "error")

SEVERITY_META = {
    "info": {"badge": "INFO", "icon": "i", "style": "Info"},
    "busy": {"badge": "PROCESSANDO", "icon": "●", "style": "Busy"},
    "success": {"badge": "CONCLUÍDO", "icon": "✓", "style": "Success"},
    "warning": {"badge": "ATENÇÃO", "icon": "!", "style": "Warning"},
    "error": {"badge": "BLOQUEADO", "icon": "×", "style": "Error"},
}


@dataclass(frozen=True)
class FeedbackEntry:
    severity: str
    title: str
    detail: str
    category: str = "Sistema"
    technical_detail: str = ""
    created_at: str = ""


@dataclass(frozen=True)
class FailureSummary:
    title: str
    detail: str
    primary_action: str
    secondary_action: str = "Ver log"


def normalize_severity(value: str) -> str:
    value = str(value or "info").strip().casefold()
    return value if value in SEVERITIES else "info"


def severity_meta(value: str) -> dict[str, str]:
    return SEVERITY_META[normalize_severity(value)]


def compact_detail(value: str, *, limit: int = 220) -> str:
    """Turn a technical/multiline message into a one-line UI-safe summary."""
    text = " ".join(part.strip() for part in str(value or "").splitlines() if part.strip())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def classify_failure(message: str) -> FailureSummary:
    """Map a raw pipeline failure to a stable user-facing explanation.

    The raw message must still be preserved in the log/activity history.  This
    function only decides the summary and the most useful next action.
    """
    raw = str(message or "").strip()
    lower = raw.casefold()
    detail = compact_detail(raw) or "O processamento foi interrompido antes de concluir a saída."

    if any(token in lower for token in ("no space", "espaço", "disk full", "disco")):
        return FailureSummary(
            "Espaço insuficiente para continuar",
            "O armazenamento disponível não atende à etapa atual. Reveja destino, temporários e a reserva mínima antes de tentar novamente.",
            "Rever projeto",
        )
    if any(token in lower for token in ("permission", "permiss", "não consegue gravar", "acesso negado", "access denied")):
        return FailureSummary(
            "O CinePulse não conseguiu gravar os arquivos",
            "O destino ou a pasta temporária recusou escrita. Nenhuma mídia de entrada foi substituída.",
            "Rever destino",
        )
    if "real-esrgan" in lower or "real_esrgan" in lower:
        return FailureSummary(
            "Upscale por IA não pôde continuar",
            "O Real-ESRGAN falhou ou ficou indisponível durante a etapa de melhoria. O detalhe técnico foi preservado no log.",
            "Abrir IA local",
        )
    if "demucs" in lower:
        return FailureSummary(
            "Separação de instrumentos não pôde continuar",
            "O Demucs não concluiu a separação solicitada. Reveja o componente local ou desative stems para a próxima tentativa.",
            "Abrir IA local",
        )
    if "rife" in lower:
        return FailureSummary(
            "Interpolação neural não pôde continuar",
            "A etapa RIFE não concluiu esta execução. Reveja a interpolação; o log mantém a causa técnica completa.",
            "Rever qualidade",
        )
    if "áudio" in lower or "audio" in lower or "loudness" in lower:
        return FailureSummary(
            "A etapa de áudio falhou",
            "O áudio não pôde ser analisado ou processado até o fim. A fonte original permanece intacta.",
            "Rever projeto",
        )
    if "ffmpeg" in lower or "etapa de vídeo" in lower or "video" in lower:
        return FailureSummary(
            "A etapa de vídeo falhou",
            "O pipeline de vídeo foi interrompido antes da validação final. A saída parcial não será promovida como vídeo concluído.",
            "Rever qualidade",
        )
    return FailureSummary(
        "O processamento foi interrompido por um erro",
        detail,
        "Rever projeto",
    )


class FeedbackHistory:
    """Small bounded activity history with consecutive duplicate suppression."""

    def __init__(self, max_items: int = 40) -> None:
        self.max_items = max(1, int(max_items))
        self._items: deque[FeedbackEntry] = deque(maxlen=self.max_items)

    def add(self, entry: FeedbackEntry) -> bool:
        normalized = FeedbackEntry(
            severity=normalize_severity(entry.severity),
            title=str(entry.title).strip(),
            detail=str(entry.detail).strip(),
            category=str(entry.category or "Sistema").strip(),
            technical_detail=str(entry.technical_detail or "").strip(),
            created_at=str(entry.created_at or time.strftime("%H:%M:%S")),
        )
        if self._items:
            previous = self._items[-1]
            same_content = (
                previous.severity, previous.title, previous.detail, previous.category, previous.technical_detail
            ) == (
                normalized.severity, normalized.title, normalized.detail, normalized.category, normalized.technical_detail
            )
            if same_content:
                return False
        self._items.append(normalized)
        return True

    def extend(self, entries: Iterable[FeedbackEntry]) -> None:
        for entry in entries:
            self.add(entry)

    def items(self) -> tuple[FeedbackEntry, ...]:
        return tuple(self._items)

    def newest_first(self) -> tuple[FeedbackEntry, ...]:
        return tuple(reversed(self._items))

    def __len__(self) -> int:
        return len(self._items)
