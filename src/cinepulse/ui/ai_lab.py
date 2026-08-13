"""Presentation logic for the Phase 6 local-AI capability manager.

This module intentionally does *not* install or execute any model.  It only
translates the low-level inventory from :mod:`cinepulse.ai_suite` into honest,
user-facing capability states.  In particular, an experimental checkpoint on
disk is never presented as an integrated CinePulse feature.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import re


INTEGRATED_KEYS = ("realesrgan", "rife", "demucs", "vmaf")
EXPERIMENTAL_KEYS = ("basicvsrpp", "clap", "depth", "sam2", "cotracker", "codeformer", "ltx2")


@dataclass(frozen=True)
class CapabilityGuide:
    category: str
    benefit: str
    render_usage: str
    missing_effect: str
    recommendation: str


GUIDES: dict[str, CapabilityGuide] = {
    "realesrgan": CapabilityGuide(
        "Upscale",
        "Recupera textura e aumenta resolução com o motor Real-ESRGAN NCNN.",
        "Integrado ao modo “Upscale por IA — Real-ESRGAN x2”.",
        "Se Real-ESRGAN estiver selecionado, o render final precisa deste componente.",
        "Instale se pretende usar upscale por IA; Lanczos continua disponível sem ele.",
    ),
    "rife": CapabilityGuide(
        "Interpolação",
        "Cria quadros intermediários para movimento mais natural em 60/120 fps.",
        "Integrado à opção “RIFE IA — movimento natural”.",
        "Sem RIFE, o pipeline pode continuar usando interpolação FFmpeg como fallback.",
        "Recomendado para movimento natural; não é obrigatório para concluir um render.",
    ),
    "demucs": CapabilityGuide(
        "Áudio / VFX",
        "Separa voz, bateria, baixo e outros instrumentos para dirigir os VFX com mais precisão.",
        "Integrado à opção de stems do Visual Lab.",
        "Sem Demucs, os VFX continuam funcionando usando a análise do áudio mixado.",
        "Instale se pretende usar reação por stems; é opcional para o fluxo principal.",
    ),
    "vmaf": CapabilityGuide(
        "Validação",
        "Mede qualidade perceptiva em comparações suportadas pelo pipeline.",
        "Integrado às verificações de qualidade quando a build do FFmpeg inclui libvmaf.",
        "Sem VMAF, o render continua; apenas a medição perceptiva fica indisponível.",
        "Útil para validação e comparação, mas não altera a imagem renderizada.",
    ),
    "basicvsrpp": CapabilityGuide(
        "Restauração temporal",
        "Checkpoint para restauração e upscale temporal com consistência entre quadros.",
        "Ainda não integrado ao pipeline CinePulse 1.0.",
        "Se estiver ausente, nenhuma função do render atual é perdida; os arquivos servem apenas à futura integração.",
        "Baixe somente para preparação/testes; aguarde integração, fallback e validação próprios.",
    ),
    "clap": CapabilityGuide(
        "Análise musical",
        "Modelo de áudio para classificação de atmosfera, intenção e direção musical.",
        "Ainda não integrado ao pipeline CinePulse 1.0.",
        "Se estiver ausente, nenhuma função atual é perdida; a direção musical e os VFX usam o sistema já integrado.",
        "Baixe apenas para experimentação futura.",
    ),
    "depth": CapabilityGuide(
        "Profundidade",
        "Checkpoints de profundidade temporal para separar planos e construir VFX em camadas.",
        "Ainda não integrado ao pipeline CinePulse 1.0.",
        "Se estiver ausente, nenhuma função atual é perdida e você evita ocupar espaço com modelos ainda fora do pipeline.",
        "Revise a licença antes de baixar; prefira não instalar se não for testar desenvolvimento.",
    ),
    "sam2": CapabilityGuide(
        "Segmentação",
        "Segmentação e acompanhamento de objetos para futuros VFX guiados por cena.",
        "Ainda não integrado ao pipeline CinePulse 1.0.",
        "Se estiver ausente, nenhuma função atual é perdida; segmentação automática ainda não faz parte do render.",
        "Baixe apenas se estiver preparando a futura integração.",
    ),
    "cotracker": CapabilityGuide(
        "Tracking",
        "Tracking de pontos para prender futuros efeitos a elementos da cena.",
        "Ainda não integrado ao pipeline CinePulse 1.0.",
        "Se estiver ausente, nenhuma função atual é perdida; tracking por CoTracker ainda não é chamado pelo render.",
        "Revise a licença CC-BY-NC-4.0 antes de qualquer download ou uso.",
    ),
    "codeformer": CapabilityGuide(
        "Rostos",
        "Checkpoints para restauração opcional de rostos.",
        "Ainda não integrado ao pipeline CinePulse 1.0.",
        "Se estiver ausente, nenhuma função atual é perdida; restauração facial ainda não está integrada.",
        "Baixe somente para testes compatíveis com a licença S-Lab.",
    ),
    "ltx2": CapabilityGuide(
        "Geração",
        "Stack LTX-2.3 para experimentação local futura de geração de áudio e vídeo.",
        "Ainda não integrado ao pipeline CinePulse 1.0.",
        "Se estiver ausente, nenhuma função atual é perdida e você economiza dezenas de GB de armazenamento.",
        "Só baixe após revisar a licença comunitária, espaço e requisitos de hardware.",
    ),
}


def _guide(item: dict) -> CapabilityGuide:
    return GUIDES.get(
        item.get("key", ""),
        CapabilityGuide(
            "Outro",
            str(item.get("purpose") or "Componente opcional local."),
            str(item.get("activation") or "Estado de integração não documentado."),
            "A ausência deste componente não tem impacto documentado nesta tela.",
            "Consulte a documentação do componente antes de instalar.",
        ),
    )


def human_bytes(value: int | float) -> str:
    amount = float(max(0, value or 0))
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if amount < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(amount)} {unit}"
            if amount >= 100:
                return f"{amount:.0f} {unit}"
            if amount >= 10:
                return f"{amount:.1f} {unit}"
            return f"{amount:.2f} {unit}"
        amount /= 1024.0
    return f"{amount:.2f} TB"


def tier(item: dict) -> str:
    return "experimental" if bool(item.get("experimental")) else "integrated"


def capability_state(item: dict, *, experimental_enabled: bool = False) -> dict[str, str]:
    key = str(item.get("key") or "")
    installed = bool(item.get("installed"))
    installable = bool(item.get("installable"))
    experimental = bool(item.get("experimental"))

    if experimental:
        if installed:
            return {
                "code": "experimental-installed",
                "label": "Arquivos instalados • fora do render",
                "level": "active",
                "explanation": "Os arquivos foram detectados, mas o CinePulse 1.0 não os chama no render principal.",
            }
        if installable and experimental_enabled:
            return {
                "code": "experimental-available",
                "label": "Disponível para baixar • não integrado",
                "level": "muted",
                "explanation": "Pode ser baixado após aceite explícito, sem alterar o render atual.",
            }
        if installable:
            return {
                "code": "experimental-locked",
                "label": "Experimental • aceite necessário",
                "level": "muted",
                "explanation": "Ative o modo experimental somente se quiser baixar arquivos ainda fora do render.",
            }
        return {
            "code": "experimental-unavailable",
            "label": "Experimental • download indisponível",
            "level": "muted",
            "explanation": "O componente está documentado, mas não pode ser instalado por esta versão.",
        }

    if installed:
        return {
            "code": "ready",
            "label": "Pronto no render",
            "level": "ok",
            "explanation": str(item.get("activation") or "Integrado e detectado."),
        }

    labels = {
        "realesrgan": ("Faltando • necessário para upscale por IA", "error"),
        "rife": ("Faltando • fallback FFmpeg disponível", "warning"),
        "demucs": ("Faltando • stems ficam desativados", "warning"),
        "vmaf": ("Faltando • medição VMAF indisponível", "warning"),
    }
    label, level = labels.get(key, ("Faltando • componente opcional", "warning"))
    if not installable:
        label = "Ausente • instalador não disponível"
        level = "error"
    return {
        "code": "missing",
        "label": label,
        "level": level,
        "explanation": _guide(item).missing_effect,
    }


def inventory_summary(items: Iterable[dict]) -> dict[str, int]:
    values = list(items)
    integrated = [item for item in values if not item.get("experimental")]
    experimental = [item for item in values if item.get("experimental")]
    ready = sum(bool(item.get("installed")) for item in integrated)
    exp_installed = sum(bool(item.get("installed")) for item in experimental)
    return {
        "integrated_ready": ready,
        "integrated_total": len(integrated),
        "integrated_missing": len(integrated) - ready,
        "experimental_installed": exp_installed,
        "experimental_total": len(experimental),
    }


def visible_items(items: Iterable[dict], filter_name: str) -> list[dict]:
    values = list(items)
    if filter_name == "No render":
        return [item for item in values if not item.get("experimental")]
    if filter_name == "Experimentais":
        return [item for item in values if item.get("experimental")]
    if filter_name == "Faltando":
        return [item for item in values if not item.get("installed")]
    return values


def selected_download(items: Iterable[dict], selected: set[str]) -> dict[str, int]:
    chosen = [item for item in items if item.get("key") in selected and not item.get("installed") and item.get("installable")]
    return {
        "count": len(chosen),
        "bytes": sum(int(item.get("download_bytes") or 0) for item in chosen),
        "experimental_count": sum(bool(item.get("experimental")) for item in chosen),
    }


def module_detail(item: dict, *, experimental_enabled: bool = False) -> dict[str, str]:
    guide = _guide(item)
    state = capability_state(item, experimental_enabled=experimental_enabled)
    installed_size = int(item.get("size_bytes") or 0)
    download_size = int(item.get("download_bytes") or 0)
    license_text = str(item.get("license") or "Licença gerenciada pelo componente/instalador; consulte a documentação.")
    experimental = bool(item.get("experimental"))

    if item.get("installed"):
        footprint = f"Detectado localmente: {human_bytes(installed_size)}" if installed_size else "Arquivos necessários detectados localmente."
    elif item.get("installable"):
        footprint = f"Download aproximado: {human_bytes(download_size)}"
    else:
        footprint = "Sem pacote instalável nesta versão."

    license_lower = license_text.lower()
    license_warning = ""
    if "non" in license_lower or "não comercial" in license_lower or "cc-by-nc" in license_lower or "restri" in license_lower:
        license_warning = "Atenção: há restrições de uso/licença que precisam ser revisadas antes do download ou uso."
    elif experimental:
        license_warning = "Componente experimental: a licença deve ser revisada antes do uso, mesmo quando permissiva."
    else:
        license_warning = "Componente integrado: consulte os avisos de terceiros para os termos completos da distribuição."

    return {
        "name": str(item.get("name") or item.get("key") or "Componente"),
        "category": guide.category,
        "benefit": guide.benefit,
        "render_usage": guide.render_usage,
        "missing_effect": guide.missing_effect,
        "recommendation": guide.recommendation,
        "state": state["label"],
        "state_level": state["level"],
        "state_explanation": state["explanation"],
        "license": license_text,
        "license_warning": license_warning,
        "footprint": footprint,
        "tier": "Experimental / fora do render" if experimental else "Integrado ao CinePulse",
    }


def progress_from_log(line: str) -> int | None:
    """Extract a trustworthy percentage from one installer log line.

    The value represents only the activity/file that emitted the line.  It is
    intentionally not promoted to a global ETA or overall install percentage.
    """
    matches = re.findall(r"(?<!\d)(100|[1-9]?\d)%", str(line or ""))
    if not matches:
        return None
    value = int(matches[-1])
    return max(0, min(100, value))
