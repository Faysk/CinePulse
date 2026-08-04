from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


VIDEO_OUTPUT_SUFFIXES = {".mp4", ".mkv", ".mov", ".webm"}


@dataclass(frozen=True)
class StoragePlan:
    output_gb: float
    temporary_gb: float
    output_free_gb: float
    temporary_free_gb: float
    same_volume: bool
    reserve_gb: float

    @property
    def blocking_reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if self.same_volume:
            needed = self.output_gb + self.temporary_gb + self.reserve_gb
            if self.output_free_gb < needed:
                reasons.append(
                    f"O disco compartilhado precisa de aproximadamente {needed:.2f} GB; "
                    f"há {self.output_free_gb:.2f} GB livres."
                )
        else:
            output_needed = self.output_gb + self.reserve_gb
            temp_needed = self.temporary_gb + self.reserve_gb
            if self.output_free_gb < output_needed:
                reasons.append(
                    f"O disco de saída precisa de aproximadamente {output_needed:.2f} GB; "
                    f"há {self.output_free_gb:.2f} GB livres."
                )
            if self.temporary_free_gb < temp_needed:
                reasons.append(
                    f"O disco temporário precisa de aproximadamente {temp_needed:.2f} GB; "
                    f"há {self.temporary_free_gb:.2f} GB livres."
                )
        return tuple(reasons)


def nearest_existing_parent(path: Path) -> Path:
    candidate = path.expanduser().resolve(strict=False)
    if candidate.suffix:
        candidate = candidate.parent
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    if not candidate.exists():
        raise OSError(f"Nenhuma pasta existente foi encontrada para {path}.")
    return candidate


def volume_identity(path: Path) -> str:
    resolved = nearest_existing_parent(path)
    if os.name == "nt":
        return (resolved.drive or resolved.anchor).casefold()
    return str(resolved.stat().st_dev)


def free_gb(path: Path) -> float:
    return os.statvfs(path).f_bavail * os.statvfs(path).f_frsize / 1024**3 if os.name != "nt" else __import__("shutil").disk_usage(path).free / 1024**3


def build_storage_plan(
    output: Path,
    temporary: Path,
    output_gb: float,
    temporary_gb: float,
    reserve_gb: float,
) -> StoragePlan:
    output_parent = nearest_existing_parent(output)
    temporary_parent = nearest_existing_parent(temporary)
    same_volume = volume_identity(output_parent) == volume_identity(temporary_parent)
    return StoragePlan(
        output_gb=max(0.0, float(output_gb)),
        temporary_gb=max(0.0, float(temporary_gb)),
        output_free_gb=free_gb(output_parent),
        temporary_free_gb=free_gb(temporary_parent),
        same_volume=same_volume,
        reserve_gb=max(0.0, float(reserve_gb)),
    )


def validate_output_path(output: Path, inputs: tuple[Path, ...]) -> tuple[str, ...]:
    errors: list[str] = []
    if output.suffix.lower() not in VIDEO_OUTPUT_SUFFIXES:
        errors.append("A saída deve usar MP4, MKV, MOV ou WebM.")
    output_resolved = output.expanduser().resolve(strict=False)
    for source in inputs:
        if source and output_resolved == source.expanduser().resolve(strict=False):
            errors.append("O arquivo de saída não pode substituir diretamente uma mídia de entrada.")
            break
    return tuple(errors)


def check_directory_writable(path: Path) -> None:
    parent = nearest_existing_parent(path)
    handle, probe = tempfile.mkstemp(prefix=".cinepulse-write-", dir=parent)
    os.close(handle)
    Path(probe).unlink(missing_ok=True)


def quality_warnings(
    source_width: int,
    source_height: int,
    source_fps: float,
    target_width: int,
    target_height: int,
    target_fps: int,
    vram_mb: int | None,
    neural_upscale: bool,
    neural_interpolation: bool,
) -> tuple[str, ...]:
    warnings: list[str] = []
    fps_ratio = target_fps / max(1.0, source_fps)
    scale_ratio = max(target_width / max(1, source_width), target_height / max(1, source_height))
    if fps_ratio > 4.0:
        warnings.append(
            f"O destino tem {fps_ratio:.1f}x o FPS da fonte; acima de 4x o ganho visual costuma ser pequeno."
        )
    if scale_ratio > 4.0:
        warnings.append(
            f"A ampliação é de {scale_ratio:.1f}x; a IA pode criar detalhe plausível, mas não recuperar informação ausente."
        )
    if target_fps >= 240:
        warnings.append("240/480 fps tem compatibilidade limitada e produz arquivos muito grandes.")
    megapixels = target_width * target_height / 1_000_000
    if neural_upscale and vram_mb is not None:
        suggested = math.ceil(2048 + megapixels * 420)
        if vram_mb < suggested:
            warnings.append(
                f"A resolução escolhida pode exigir mais de {suggested / 1024:.1f} GB de VRAM; "
                "o processamento usará tiles e poderá ficar bem mais lento."
            )
    if neural_interpolation and target_fps > 120:
        warnings.append("RIFE acima de 120 fps exige muitas etapas; 60 ou 120 fps costuma ser o melhor equilíbrio.")
    return tuple(warnings)
