"""Pure queue presentation helpers for the CinePulse UX MegaPack.

The render queue itself remains owned by :mod:`cinepulse.studio`.  This module
only translates queue state into stable, testable presentation data so the UI
can evolve without changing render semantics or persistence guarantees.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Iterable, Mapping, Any


WAITING_STATUSES = frozenset({"Aguardando"})
ACTIVE_STATUSES = frozenset({"Renderizando"})
DONE_STATUSES = frozenset({"Concluído"})
ATTENTION_STATUSES = frozenset({"Erro", "Interrompido", "Cancelado"})
RETRYABLE_STATUSES = ATTENTION_STATUSES


@dataclass(frozen=True)
class QueueSummary:
    total: int
    waiting: int
    active: int
    done: int
    attention: int

    @property
    def remaining(self) -> int:
        return self.waiting + self.active + self.attention


def normalize_status(status: object) -> str:
    value = str(status or "Aguardando").strip()
    known = WAITING_STATUSES | ACTIVE_STATUSES | DONE_STATUSES | ATTENTION_STATUSES
    return value if value in known else "Aguardando"


def summarize_queue(items: Iterable[Mapping[str, Any]]) -> QueueSummary:
    statuses = [normalize_status(item.get("status")) for item in items]
    return QueueSummary(
        total=len(statuses),
        waiting=sum(status in WAITING_STATUSES for status in statuses),
        active=sum(status in ACTIVE_STATUSES for status in statuses),
        done=sum(status in DONE_STATUSES for status in statuses),
        attention=sum(status in ATTENTION_STATUSES for status in statuses),
    )


def item_progress(item: Mapping[str, Any]) -> float:
    status = normalize_status(item.get("status"))
    if status == "Concluído":
        return 100.0
    if status == "Aguardando":
        return 0.0
    try:
        value = float(item.get("progress", 0.0))
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(100.0, value))


def status_text(item: Mapping[str, Any]) -> str:
    status = normalize_status(item.get("status"))
    if status == "Renderizando":
        return f"Renderizando • {item_progress(item):.0f}%"
    if status in ATTENTION_STATUSES and item.get("error"):
        return f"{status} • atenção necessária"
    return status


def _portable_name(path_value: str) -> str:
    if "\\" in path_value:
        return PureWindowsPath(path_value).name
    return Path(path_value).name


def project_name(settings: Any) -> str:
    video = str(getattr(settings, "video", "") or "").strip()
    if video:
        name = _portable_name(video)
        return Path(name).stem or name
    return "Projeto sem nome"


def output_name(settings: Any) -> str:
    output = str(getattr(settings, "output", "") or "").strip()
    return _portable_name(output) if output else "Saída não definida"


def profile_text(settings: Any) -> str:
    resolution = str(getattr(settings, "resolution", "—") or "—")
    fps = getattr(settings, "fps", "—")
    aspect = str(getattr(settings, "aspect", "—") or "—").split(" — ")[0]
    delivery = str(getattr(settings, "delivery_profile", "") or "").replace("Automático pelo arquivo", "Auto")
    suffix = Path(str(getattr(settings, "output", "") or "")).suffix.upper()
    tail = " • ".join(part for part in (delivery, suffix) if part)
    return f"{resolution} • {fps} fps • {aspect}" + (f" • {tail}" if tail else "")


def processing_text(settings: Any) -> str:
    processor = "Somente CPU" if bool(getattr(settings, "use_cpu", False)) else "Aceleração automática"
    enhancement = str(getattr(settings, "enhancement", "") or "").split(" — ")[0]
    interpolation = str(getattr(settings, "interpolation", "") or "").split(" — ")[0]
    parts = [processor]
    if enhancement:
        parts.append(enhancement)
    if interpolation:
        parts.append(interpolation)
    return " • ".join(parts)


def effects_text(settings: Any) -> str:
    effects = sorted(str(value) for value in (getattr(settings, "effects", set()) or set()))
    return ", ".join(effects) if effects else "Sem VFX"


def can_retry(item: Mapping[str, Any]) -> bool:
    return normalize_status(item.get("status")) in RETRYABLE_STATUSES


def can_move(items: list[Mapping[str, Any]], selected_id: int, direction: int) -> bool:
    if direction not in {-1, 1}:
        return False
    try:
        index = next(index for index, item in enumerate(items) if int(item.get("id", -1)) == int(selected_id))
    except (StopIteration, TypeError, ValueError):
        return False
    target = index + direction
    return 0 <= target < len(items)
