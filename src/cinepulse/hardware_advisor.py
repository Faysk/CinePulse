from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class StageAdvice:
    stage: str
    bottleneck: str
    severity: str
    gpu_expected: bool
    average_gpu_percent: float | None
    average_cpu_percent: float | None
    peak_ram_percent: float | None
    minimum_vram_free_mb: float | None
    peak_gpu_temperature_c: float | None
    action: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HardwareAdvice:
    stages: tuple[StageAdvice, ...]
    # Kept for history-schema compatibility. The summary-only advisor cannot
    # prove a thermal throughput constraint from temperature alone, so it stays
    # false until an explicit throughput-comparison signal is added here.
    thermal_constrained: bool
    memory_constrained: bool
    gpu_starved_stages: tuple[str, ...]
    cpu_bound_stages: tuple[str, ...]
    io_suspected_stages: tuple[str, ...]
    physical_acceptance: str = "pending"

    @property
    def needs_attention(self) -> bool:
        return bool(
            self.thermal_constrained
            or self.memory_constrained
            or self.gpu_starved_stages
            or self.cpu_bound_stages
            or self.io_suspected_stages
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["needs_attention"] = self.needs_attention
        return payload


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _nested(group: dict[str, Any], section: str, key: str) -> float | None:
    payload = group.get(section)
    if not isinstance(payload, dict):
        return None
    return _number(payload.get(key))


def _gpu_expected(stage: str) -> bool:
    """Keep GPU-starvation claims limited to explicitly neural/GPU work."""
    name = str(stage or "").casefold()
    tokens = (
        "ia 2/3",
        "real-esrgan",
        "realesrgan",
        "rife 2/3",
        "rife do clipe",
        "rife final",
        "neural",
    )
    return any(token in name for token in tokens)


def _thermal_note(temperature: float | None) -> str:
    if temperature is None or temperature < 82.0:
        return ""
    return (
        f" GPU atingiu {temperature:.1f} °C; isso é apenas evidência observacional — "
        "não reduza carga sem confirmar perda de throughput sustentado ou instabilidade."
    )


def analyze_stage(stage: str, group: dict[str, Any]) -> StageAdvice:
    sample_count = int(_number(group.get("sample_count")) or 0)
    gpu_expected = _gpu_expected(stage)
    gpu = _nested(group, "gpu", "average_utilization_percent")
    cpu = _nested(group, "cpu", "average_percent")
    ram = _nested(group, "ram", "peak_percent")
    vram_free = _nested(group, "gpu", "minimum_vram_free_mb")
    temperature = _nested(group, "gpu", "peak_temperature_c")
    disk_read = _nested(group, "disk", "average_read_mbps") or 0.0
    disk_write = _nested(group, "disk", "average_write_mbps") or 0.0
    disk_total = disk_read + disk_write
    thermal_note = _thermal_note(temperature)

    if sample_count < 2:
        return StageAdvice(
            stage, "unknown", "info", gpu_expected, gpu, cpu, ram, vram_free, temperature,
            "Colete uma execução mais longa antes de ajustar concorrência.",
            "A amostra é curta demais para classificar utilização de forma responsável." + thermal_note,
        )

    # Temperature is deliberately NOT an early bottleneck. H8 now measures
    # completed neural work/s and only reacts to thermal/power/clock pressure
    # when that pressure coincides with real sustained-throughput regression.
    # This summary advisor has no baseline comparison, so it must not invent one.

    if (ram is not None and ram >= 92.0) or (vram_free is not None and vram_free < 384.0):
        detail = []
        if ram is not None:
            detail.append(f"RAM {ram:.1f}%")
        if vram_free is not None:
            detail.append(f"VRAM livre mínima {vram_free:.0f} MB")
        return StageAdvice(
            stage, "memory-pressure", "warning", gpu_expected, gpu, cpu, ram, vram_free, temperature,
            "Diminua profundidade de fila/tile/concurrency; não promova uma política mais agressiva.",
            "Pressão de memória detectada: " + ", ".join(detail) + "." + thermal_note,
        )

    if gpu_expected and gpu is not None and gpu < 55.0 and (cpu is None or cpu < 82.0):
        if disk_total >= 100.0:
            return StageAdvice(
                stage, "io-suspected", "warning", True, gpu, cpu, ram, vram_free, temperature,
                "Meça o scratch/NVMe e teste overlap de load/process/save; não aumente workers GPU sem evidência.",
                f"GPU média {gpu:.1f}% com CPU não saturada e ~{disk_total:.0f} MB/s de I/O agregado sugere alimentação insuficiente."
                + thermal_note,
            )
        return StageAdvice(
            stage, "gpu-starved", "warning", True, gpu, cpu, ram, vram_free, temperature,
            "Benchmarke candidatos de tile e load:process:save; aplique apenas uma política com integridade aprovada.",
            f"GPU média {gpu:.1f}% durante etapa neural, sem CPU saturada nem pressão de memória evidente."
            + thermal_note,
        )

    if cpu is not None and cpu >= 88.0 and (gpu is None or gpu < 88.0):
        return StageAdvice(
            stage, "cpu-bound", "info", gpu_expected, gpu, cpu, ram, vram_free, temperature,
            "Compare candidatos de threads por etapa e persista somente o vencedor que passar os gates de integridade.",
            f"CPU média {cpu:.1f}% enquanto a GPU não está igualmente saturada." + thermal_note,
        )

    if gpu_expected and gpu is not None and gpu >= 90.0:
        return StageAdvice(
            stage, "gpu-saturated", "ok", True, gpu, cpu, ram, vram_free, temperature,
            "Mantenha a política neural; procure ganhos nas etapas ao redor antes de aumentar pressão na GPU.",
            f"GPU média {gpu:.1f}% indica boa ocupação da etapa neural." + thermal_note,
        )

    return StageAdvice(
        stage, "balanced", "ok", gpu_expected, gpu, cpu, ram, vram_free, temperature,
        "Mantenha a política atual até existir benchmark físico melhor.",
        "Nenhum gargalo forte foi inferido a partir das métricas disponíveis." + thermal_note,
    )


def analyze_hardware_summary(summary: dict[str, Any]) -> HardwareAdvice:
    stages_payload = summary.get("stages") if isinstance(summary, dict) else None
    if not isinstance(stages_payload, dict):
        stages_payload = {}
    stages = tuple(
        analyze_stage(str(name), group if isinstance(group, dict) else {})
        for name, group in sorted(stages_payload.items())
    )
    return HardwareAdvice(
        stages=stages,
        # A peak temperature without a same-run throughput reference is not a
        # proven constraint. Runtime H8 owns that inference using measured work/s.
        thermal_constrained=False,
        memory_constrained=any(item.bottleneck == "memory-pressure" for item in stages),
        gpu_starved_stages=tuple(item.stage for item in stages if item.bottleneck == "gpu-starved"),
        cpu_bound_stages=tuple(item.stage for item in stages if item.bottleneck == "cpu-bound"),
        io_suspected_stages=tuple(item.stage for item in stages if item.bottleneck == "io-suspected"),
    )
