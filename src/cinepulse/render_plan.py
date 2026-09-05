"""Explicit render planning for CinePulse.

Core Integrity Phase 2 turned the Phase 1 observability model into a quality
policy; Phase 3 extends the same contract to VFX geometry/cadence and music-envelope consistency.  The planner is still pure/deterministic, but it now prevents the main
spatial/temporal regressions identified by the 2026-08-13 audit:

* final masters are no longer fixed to 720p/1440p at 60 fps;
* RIFE is attempted at most once and only when the requested cadence exceeds
  the effective source cadence;
* Real-ESRGAN is skipped when the framing can reach the destination without
  spatial upscaling;
* Preserve, Lanczos and Real-ESRGAN represent distinct processing policies.

Phase 3 removes fixed VFX 320x180/60 sampling and unifies full-track music
envelope analysis. Phase 4 adds an explicit color contract: HDR is either
preserved end-to-end or tone-mapped once before SDR-only stages, while SDR
10-bit is no longer collapsed through 8-bit masters.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Iterable, Literal

from .color_pipeline import build_color_pipeline
from .media_profile import ColorProfile
from .delivery import PROFILE_AUTO, build_delivery_plan
from .vfx_policy import choose_vfx_render_spec


StepStatus = Literal["run", "skip", "conditional"]
Severity = Literal["info", "warning", "critical"]
FitMode = Literal["contain", "cover"]


@dataclass(frozen=True)
class FrameSpec:
    width: int
    height: int
    fps: float
    pixel_format: str = "unknown"

    def label(self) -> str:
        fps = f"{self.fps:.3f}".rstrip("0").rstrip(".")
        suffix = "" if self.pixel_format == "unknown" else f" • {self.pixel_format}"
        return f"{self.width}×{self.height} • {fps} fps{suffix}"


@dataclass(frozen=True)
class PlanRisk:
    code: str
    severity: Severity
    title: str
    detail: str


@dataclass(frozen=True)
class RenderStep:
    key: str
    title: str
    status: StepStatus
    reason: str
    device: str
    input_spec: FrameSpec | None = None
    output_spec: FrameSpec | None = None
    internal_spec: FrameSpec | None = None
    cacheable: bool = False
    materializes_frames: bool = False
    lossy_intermediate: bool = False
    notes: tuple[str, ...] = ()

    @property
    def runs(self) -> bool:
        return self.status == "run"

    @property
    def attempts(self) -> bool:
        return self.status in {"run", "conditional"}

    def summary(self) -> str:
        marker = {"run": "✓", "skip": "—", "conditional": "?"}[self.status]
        output = f" → {self.output_spec.label()}" if self.output_spec else ""
        device = "" if self.device in {"", "—"} else f" • dispositivo: {self.device}"
        return f"{marker} {self.title}: {self.reason}{output}{device}"


@dataclass(frozen=True)
class RenderPlan:
    source: FrameSpec
    target: FrameSpec
    project_mode: str
    preview: bool
    enhancement_mode: str
    interpolation_mode: str
    effects_active: bool
    transition_active: bool
    steps: tuple[RenderStep, ...]
    risks: tuple[PlanRisk, ...] = ()
    architecture_version: str = "core-integrity-phase8-runtime-distribution"
    metadata: dict[str, object] = field(default_factory=dict)

    def step(self, key: str) -> RenderStep:
        for item in self.steps:
            if item.key == key:
                return item
        raise KeyError(key)

    @property
    def needs_master(self) -> bool:
        return self.step("master").runs

    @property
    def has_critical_risk(self) -> bool:
        return any(item.severity == "critical" for item in self.risks)

    @property
    def fingerprint(self) -> str:
        raw = json.dumps(self.to_dict(include_fingerprint=False), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return sha256(raw.encode("utf-8")).hexdigest()[:16]

    def to_dict(self, *, include_fingerprint: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "architecture_version": self.architecture_version,
            "source": asdict(self.source),
            "target": asdict(self.target),
            "project_mode": self.project_mode,
            "preview": self.preview,
            "enhancement_mode": self.enhancement_mode,
            "interpolation_mode": self.interpolation_mode,
            "effects_active": self.effects_active,
            "transition_active": self.transition_active,
            "steps": [asdict(step) for step in self.steps],
            "risks": [asdict(risk) for risk in self.risks],
            "metadata": dict(self.metadata),
        }
        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
        return payload

    def user_lines(self, *, max_steps: int | None = None) -> list[str]:
        selected = self.steps if max_steps is None else self.steps[:max_steps]
        return [step.summary() for step in selected]


@dataclass(frozen=True)
class PlanInput:
    source_width: int
    source_height: int
    source_fps: float
    target_width: int
    target_height: int
    target_fps: float
    project_mode: Literal["music", "original"]
    preview: bool
    enhancement_mode: Literal["preserve", "lanczos", "realesrgan"]
    interpolation_mode: Literal["rife", "ffmpeg", "repeat"]
    effects_active: bool
    transition_active: bool
    use_cpu: bool
    fit_mode: FitMode = "contain"
    source_hdr: bool = False
    source_bit_depth: int = 8
    source_pixel_format: str = "unknown"
    source_primaries: str = "unknown"
    source_transfer: str = "unknown"
    source_space: str = "unknown"
    source_range: str = "unknown"
    realesrgan_available: bool = True
    rife_available: bool = True
    auto_loop_may_add_transition: bool = False
    output_suffix: str = ".mp4"
    delivery_profile: str = PROFILE_AUTO


def _risk(code: str, severity: Severity, title: str, detail: str) -> PlanRisk:
    return PlanRisk(code=code, severity=severity, title=title, detail=detail)


def spatial_scale_factor(
    source_width: int,
    source_height: int,
    target_width: int,
    target_height: int,
    fit_mode: FitMode,
) -> float:
    """Return the scale required to frame the source in the requested canvas.

    ``contain`` uses the smaller ratio, while ``cover`` uses the larger ratio.
    This lets the planner answer whether enlarging source pixels is actually
    required instead of comparing canvas edges naively.
    """

    if min(source_width, source_height, target_width, target_height) <= 0:
        raise ValueError("spatial_scale_factor requires positive dimensions.")
    x_ratio = target_width / source_width
    y_ratio = target_height / source_height
    return max(x_ratio, y_ratio) if fit_mode == "cover" else min(x_ratio, y_ratio)


def _master_fps(data: PlanInput) -> float:
    """Cadence used by the target-aware master.

    Music-loop projects interpolate the reusable clip once *before* the master
    and VFX expansion, so the master can already run at target cadence.  This
    avoids repeating the same neural interpolation for every loop iteration.
    Original-video projects keep the previous one-shot final RIFE policy.
    """

    if data.interpolation_mode == "rife" and data.target_fps > data.source_fps + 0.01:
        if data.project_mode == "music":
            return float(data.target_fps)
        return float(data.source_fps)
    return float(data.target_fps)


def build_render_plan(data: PlanInput) -> RenderPlan:
    """Build the cumulative Core Integrity Phase 4 render plan."""

    if min(data.source_width, data.source_height, data.target_width, data.target_height) <= 0:
        raise ValueError("RenderPlan requires positive source and target dimensions.")
    if data.source_fps <= 0 or data.target_fps <= 0:
        raise ValueError("RenderPlan requires positive source and target FPS.")
    if data.fit_mode not in {"contain", "cover"}:
        raise ValueError(f"Unsupported fit mode: {data.fit_mode}")

    source_profile = ColorProfile(
        primaries=data.source_primaries,
        transfer=data.source_transfer,
        space=data.source_space,
        range=data.source_range,
        pixel_format=(data.source_pixel_format or "unknown").split(" ", 1)[0],
        bit_depth=int(data.source_bit_depth),
        hdr=bool(data.source_hdr),
    )
    color_plan = build_color_pipeline(
        source_profile,
        effects_active=data.effects_active,
        transition_active=data.transition_active,
        enhancement_mode=data.enhancement_mode,
        rife_active=(data.interpolation_mode == "rife" and data.target_fps > data.source_fps + 0.01),
    )

    source = FrameSpec(
        data.source_width,
        data.source_height,
        float(data.source_fps),
        data.source_pixel_format or "unknown",
    )
    target = FrameSpec(
        data.target_width,
        data.target_height,
        float(data.target_fps),
        f"{color_plan.output.pixel_format} • {color_plan.output.primaries}/{color_plan.output.transfer}",
    )
    steps: list[RenderStep] = []
    risks: list[PlanRisk] = []
    current = source

    if color_plan.tone_maps_to_sdr or color_plan.precision_reduction:
        color_out = FrameSpec(
            source.width,
            source.height,
            source.fps,
            (
                f"BT.709 SDR {color_plan.working.bit_depth}-bit"
                if color_plan.tone_maps_to_sdr
                else f"{color_plan.working.primaries}/{color_plan.working.transfer} SDR {color_plan.working.bit_depth}-bit"
            ),
        )
        steps.append(
            RenderStep(
                key="color",
                title="Gerenciamento de cor",
                status="run",
                reason=color_plan.reason,
                device="CPU/GPU filter",
                input_spec=current,
                output_spec=color_out,
                notes=(
                    (
                        "Tone mapping usa zscale + linearização + tonemap + gamut/range conversion; setparams sozinho não é conversão."
                        if color_plan.tone_maps_to_sdr
                        else "Redução de profundidade usa zscale + error-diffusion dithering antes do estágio 8-bit."
                    ),
                    "CP-007: um fluxo que entrou em estágio SDR-only nunca volta a ser rotulado como HDR.",
                ),
            )
        )
        if color_plan.tone_maps_to_sdr:
            risks.append(_risk("CI-P4-HDR-SDR", "info", "HDR será convertido para SDR", color_plan.reason))
        elif color_plan.precision_reduction:
            risks.append(_risk("CI-P4-AI-8BIT", "warning", "IA exige redução explícita para 8-bit", color_plan.reason))
        current = color_out
    else:
        label = (
            f"HDR preservado em {color_plan.output.bit_depth}-bit"
            if color_plan.preserves_hdr
            else f"SDR preservado em {color_plan.output.bit_depth}-bit"
        )
        steps.append(
            RenderStep(
                key="color",
                title="Gerenciamento de cor",
                status="skip",
                reason=f"{label}; nenhuma conversão de faixa dinâmica é necessária",
                device="—",
                input_spec=current,
                output_spec=current,
                notes=(color_plan.reason,),
            )
        )
    for assumption in color_plan.assumptions:
        risks.append(_risk("CI-P4-COLOR-UNKNOWN", "warning", "Metadados de cor incompletos", assumption))

    required_scale = spatial_scale_factor(
        source.width,
        source.height,
        target.width,
        target.height,
        data.fit_mode,
    )
    requires_upscale = required_scale > 1.0001

    if data.enhancement_mode == "realesrgan":
        if requires_upscale:
            ai_output = FrameSpec(current.width * 2, current.height * 2, current.fps, "SDR PNG/RGB 8-bit frames")
            status: StepStatus = "run" if data.realesrgan_available else "conditional"
            steps.append(
                RenderStep(
                    key="enhancement",
                    title="Real-ESRGAN x2",
                    status=status,
                    reason=(
                        f"o enquadramento exige ampliar a fonte em {required_scale:.2f}×; IA x2 é target-aware"
                        if data.realesrgan_available
                        else "o destino exige upscale, mas Real-ESRGAN está ausente; a validação deve bloquear/fazer fallback explícito"
                    ),
                    device="GPU",
                    input_spec=current,
                    output_spec=ai_output if data.realesrgan_available else current,
                    cacheable=True,
                    materializes_frames=data.realesrgan_available,
                    notes=("Modelo atual: realesr-animevideov3 x2.",),
                )
            )
            if data.realesrgan_available:
                current = ai_output
        else:
            steps.append(
                RenderStep(
                    key="enhancement",
                    title="Real-ESRGAN x2",
                    status="skip",
                    reason="ignorado: a fonte já atende ou excede a escala espacial necessária para o destino",
                    device="—",
                    input_spec=current,
                    output_spec=current,
                    notes=("CP-004 corrigido: nenhum quadro x2 é criado quando o destino não exige upscale.",),
                )
            )
    elif data.enhancement_mode == "lanczos":
        steps.append(
            RenderStep(
                key="enhancement",
                title="Lanczos",
                status="skip",
                reason=(
                    "redimensionamento espacial explícito será aplicado no master/final"
                    if abs(required_scale - 1.0) > 0.0001
                    else "fonte e destino já possuem escala equivalente; nenhum upscale antecipado é necessário"
                ),
                device="CPU/GPU filter",
                input_spec=current,
                output_spec=current,
                notes=("Lanczos pode ampliar ou reduzir para cumprir o enquadramento solicitado.",),
            )
        )
    else:
        preserve_reason = "sem melhoria neural; pixels da fonte não serão ampliados"
        if requires_upscale:
            preserve_reason += "; o canvas de destino será preenchido sem upscale da imagem"
            risks.append(
                _risk(
                    "CI-P2-PRESERVE",
                    "info",
                    "Preservar impede ampliação da fonte",
                    "O canvas solicitado é maior do que a escala nativa permite. A imagem será mantida sem upscale e centralizada/ajustada no canvas.",
                )
            )
        steps.append(
            RenderStep(
                key="enhancement",
                title="Preservar fonte",
                status="skip",
                reason=preserve_reason,
                device="—",
                input_spec=current,
                output_spec=current,
                notes=("CP-006 corrigido: Preservar possui política espacial distinta de Lanczos.",),
            )
        )

    # Hotfix 1.1.3: music loops interpolate the reusable clip once before the
    # timeline is expanded. Synthetic VFX are then rendered directly at target
    # cadence. Original-video projects retain the one-shot final RIFE policy.
    music_rife_requested = (
        data.project_mode == "music"
        and data.interpolation_mode == "rife"
        and target.fps > current.fps + 0.01
    )
    rife_base_runs = bool(music_rife_requested and data.rife_available)
    if music_rife_requested:
        if data.rife_available:
            rife_base_out = FrameSpec(current.width, current.height, target.fps, current.pixel_format)
            steps.append(
                RenderStep(
                    key="rife_base",
                    title="RIFE do clipe reutilizável",
                    status="run",
                    reason=f"interpola o clipe uma única vez: {current.fps:g} → {target.fps:g} fps antes de expandir o loop",
                    device="CPU" if data.use_cpu else "GPU",
                    input_spec=current,
                    output_spec=rife_base_out,
                    materializes_frames=True,
                    notes=(
                        "Hotfix 1.1.3: a duração da música não multiplica o trabalho neural do clipe repetido.",
                        "CP-002 continua one-shot: não existe segunda chamada RIFE depois dos VFX.",
                    ),
                )
            )
            current = rife_base_out
        else:
            steps.append(
                RenderStep(
                    key="rife_base",
                    title="RIFE do clipe reutilizável",
                    status="conditional",
                    reason="RIFE está ausente; o master atingirá a cadência alvo com fallback FFmpeg explícito",
                    device="—",
                    input_spec=current,
                    output_spec=current,
                    notes=("Nenhum master neural é materializado sem o componente local.",),
                )
            )
    else:
        steps.append(
            RenderStep(
                key="rife_base",
                title="RIFE do clipe reutilizável",
                status="skip",
                reason=(
                    "reservado a loops musicais que realmente precisam elevar o FPS"
                    if data.project_mode != "music"
                    else f"ignorado: {current.fps:g} fps já atendem ao destino de {target.fps:g} fps"
                ),
                device="—",
                input_spec=current,
                output_spec=current,
                notes=("CP-002: no máximo uma chamada RIFE por render.",),
            )
        )

    needs_master = data.project_mode == "music" or data.effects_active or data.transition_active
    if needs_master:
        master_fps = _master_fps(data)
        master = FrameSpec(
            target.width,
            target.height,
            master_fps,
            f"{color_plan.working.pixel_format} • {color_plan.working.primaries}/{color_plan.working.transfer}",
        )
        temporal_note = (
            "mantém a cadência efetiva da fonte para uma única interpolação RIFE posterior"
            if data.interpolation_mode == "rife" and target.fps > source.fps + 0.01
            else "usa diretamente a cadência solicitada; fontes mais rápidas só são reduzidas quando o destino pede menos FPS"
        )
        steps.append(
            RenderStep(
                key="master",
                title="Master de estúdio",
                status="run",
                reason=f"master target-aware em {target.width}×{target.height}; {temporal_note}",
                device="CPU" if data.use_cpu else "GPU/CPU",
                input_spec=current,
                output_spec=master,
                lossy_intermediate=not color_plan.needs_lossless_intermediate,
                notes=(
                    "CP-001 corrigido: o master final não usa mais 720p/1440p fixos.",
                    "CP-002 corrigido: o master não derruba 120 fps para 60 fps quando o destino também pede 120 fps.",
                    (
                        "Phase 4: caminhos color-critical usam FFV1 lossless na profundidade de trabalho planejada."
                        if color_plan.needs_lossless_intermediate
                        else "Fonte SDR 8-bit usa intermediário 8-bit de alta qualidade sem falsa promessa de 10-bit."
                    ),
                ),
            )
        )
        current = master
    else:
        steps.append(
            RenderStep(
                key="master",
                title="Master de estúdio",
                status="skip",
                reason="modo original sem VFX/transição segue direto para a finalização",
                device="—",
                input_spec=current,
                output_spec=current,
            )
        )

    if data.transition_active:
        transition_out = FrameSpec(current.width, current.height, current.fps, current.pixel_format)
        steps.append(
            RenderStep(
                key="transition",
                title="Transição do loop",
                status="run",
                reason="uma transição visual está ativa e herda resolução/FPS do master target-aware",
                device="CPU" if data.use_cpu else "GPU/CPU",
                input_spec=current,
                output_spec=transition_out,
                lossy_intermediate=not color_plan.needs_lossless_intermediate,
                notes=(
                    "HDR é tone-mapped para SDR antes da transição até existir xfade HDR linear-light validado."
                    if data.source_hdr
                    else "A profundidade de bits do master é mantida durante a transição.",
                ),
            )
        )
        current = transition_out
    else:
        reason = "corte seco selecionado"
        status: StepStatus = "skip"
        if data.auto_loop_may_add_transition and data.project_mode == "music":
            reason = "corte seco configurado; o loop automático pode promover para uma dissolução curta após a análise"
            status = "conditional"
        steps.append(
            RenderStep(
                key="transition",
                title="Transição do loop",
                status=status,
                reason=reason,
                device="—" if status == "skip" else "CPU/GPU",
                input_spec=current,
                output_spec=current,
            )
        )

    if data.effects_active:
        vfx_spec = choose_vfx_render_spec(current.width, current.height, current.fps)
        vfx_out = FrameSpec(current.width, current.height, current.fps, current.pixel_format)
        notes = [
            "CP-003 corrigido arquiteturalmente: não existe mais canvas final fixo 320×180/60.",
            "Envelope musical é normalizado sobre a faixa completa e reutilizado por preview/final (CP-013).",
        ]
        if not vfx_spec.native_spatial:
            notes.append("Saídas acima de 4K usam canvas VFX adaptativo 4K e Lanczos na composição para limitar pressão de RAM/pipe.")
            risks.append(
                _risk(
                    "CI-P3-VFX-8K",
                    "warning",
                    "VFX acima de 4K usam canvas adaptativo",
                    "O defeito fixo 320×180 foi removido, mas a validação perceptiva 8K a 100% continua como portão de aceite antes da 1.0.",
                )
            )
        if not vfx_spec.native_temporal:
            notes.append("Cadências acima de 120 fps mantêm a base, mas a reatividade VFX é amostrada a 120 fps.")
            risks.append(
                _risk(
                    "CI-P3-VFX-HFR",
                    "warning",
                    "Reatividade VFX limitada a 120 fps",
                    "A base mantém sua cadência; 240/480 fps ainda aguardam a futura matriz de capacidades/formatos.",
                )
            )
        steps.append(
            RenderStep(
                key="vfx",
                title="VFX reativos",
                status="run",
                reason="layer VFX usa canvas e cadência derivados do RenderPlan, sem retimar a base",
                device="CPU NumPy + encoder",
                input_spec=current,
                output_spec=vfx_out,
                internal_spec=FrameSpec(vfx_spec.width, vfx_spec.height, vfx_spec.fps, "RGBA interno target-aware"),
                lossy_intermediate=not color_plan.needs_lossless_intermediate,
                notes=tuple(notes),
            )
        )
        current = vfx_out
    else:
        steps.append(
            RenderStep(
                key="vfx",
                title="VFX reativos",
                status="skip",
                reason="nenhum VFX selecionado",
                device="—",
                input_spec=current,
                output_spec=current,
            )
        )

    final_rife_runs = data.interpolation_mode == "rife" and target.fps > current.fps + 0.01
    if data.interpolation_mode == "rife":
        if final_rife_runs:
            rife_output = FrameSpec(current.width, current.height, target.fps, current.pixel_format)
            status = "run" if data.rife_available else "conditional"
            steps.append(
                RenderStep(
                    key="rife_final",
                    title="RIFE final",
                    status=status,
                    reason=(
                        f"uma única interpolação é necessária: {current.fps:g} → {target.fps:g} fps"
                        if data.rife_available
                        else f"destino exige {target.fps:g} fps, mas RIFE está ausente; fallback FFmpeg será explícito"
                    ),
                    device="CPU" if data.use_cpu else "GPU",
                    input_spec=current,
                    output_spec=rife_output if data.rife_available else current,
                    materializes_frames=data.rife_available,
                    notes=("CP-002 corrigido: nenhuma interpolação ocorre quando a cadência efetiva já atende ao destino.",),
                )
            )
            if data.rife_available:
                current = rife_output
        else:
            steps.append(
                RenderStep(
                    key="rife_final",
                    title="RIFE final",
                    status="skip",
                    reason=f"ignorado: {current.fps:g} fps efetivos já atendem ao destino de {target.fps:g} fps",
                    device="—",
                    input_spec=current,
                    output_spec=current,
                )
            )
    else:
        steps.append(
            RenderStep(
                key="rife_final",
                title="RIFE final",
                status="skip",
                reason="RIFE não está selecionado",
                device="—",
                input_spec=current,
                output_spec=current,
            )
        )

    final = FrameSpec(target.width, target.height, target.fps, target.pixel_format)
    spatial_note = {
        "preserve": "Preservar: nenhuma ampliação de pixels da fonte; downscale/canvas somente quando necessário.",
        "lanczos": "Lanczos: redimensionamento explícito para o enquadramento solicitado.",
        "realesrgan": "IA: Real-ESRGAN somente quando o destino exige upscale; enquadramento final usa Lanczos.",
    }[data.enhancement_mode]
    steps.append(
        RenderStep(
            key="finalize",
            title="Enquadramento final",
            status="run",
            reason="produz a geometria e cadência solicitadas sem reconstrução após redução intermediária",
            device="CPU" if data.use_cpu else "GPU/CPU",
            input_spec=current,
            output_spec=final,
            notes=(spatial_note,),
        )
    )

    delivery = build_delivery_plan(
        output="preview.mp4" if data.preview else f"output{data.output_suffix or '.mp4'}",
        profile=data.delivery_profile, color_plan=color_plan,
        width=target.width, height=target.height, fps=target.fps, preview=data.preview,
    )
    for issue in delivery.issues:
        risks.append(_risk(
            issue.code, "critical" if issue.severity == "error" else "warning",
            "Perfil de entrega incompatível" if issue.severity == "error" else "Compatibilidade de entrega",
            issue.message,
        ))
    steps.append(
        RenderStep(
            key="delivery",
            title="Codec e contêiner",
            status="run",
            reason=f"{delivery.profile}: {delivery.label}",
            device="CPU" if data.use_cpu or delivery.video_codec in {"VP9", "ProRes 422 HQ"} else "GPU/CPU",
            input_spec=final, output_spec=final,
            notes=(
                "CP-008: contêiner e codecs são resolvidos como um contrato único.",
                "CP-009: o perfil estável bloqueia >8K e >120 fps antes do render.",
                "CP-015: streaming usa AAC; master MOV usa PCM 24-bit; arquivo MKV usa FLAC; WebM usa Opus.",
            ),
        )
    )

    metadata = {
        "needs_master": needs_master,
        "master_fps": _master_fps(data) if needs_master else None,
        "required_spatial_scale": round(required_scale, 6),
        "spatial_upscale_required": requires_upscale,
        "rife_calls_planned": int(rife_base_runs) + (1 if final_rife_runs and data.rife_available else 0),
        "rife_loop_optimized": bool(rife_base_runs),
        "current_pipeline_compatible": True,
        "color_intent": color_plan.intent,
        "color_label": color_plan.label,
        "color_working_pix_fmt": color_plan.working_pix_fmt,
        "color_final_pix_fmt": color_plan.final_pix_fmt,
        "color_preserves_hdr": color_plan.preserves_hdr,
        "color_tone_maps_to_sdr": color_plan.tone_maps_to_sdr,
        "delivery_profile": delivery.profile,
        "delivery_container": delivery.container,
        "delivery_video_codec": delivery.video_codec,
        "delivery_audio_codec": delivery.audio_codec,
        "delivery_blocking": delivery.blocking,
        "resolved_audit_codes": ["CP-001", "CP-002", "CP-003", "CP-004", "CP-005", "CP-006", "CP-007", "CP-008", "CP-009", "CP-010", "CP-011", "CP-012", "CP-013", "CP-014", "CP-015", "CP-016", "CP-017", "CP-018", "CP-019", "CP-020", "CP-021", "CP-022", "CP-023", "CP-029", "CP-030", "CP-031"],
        "pending_audit_codes": ["CP-027", "CP-032", "CP-033"],
        "storage_policy": "bounded-neural-chunks + configurable-scratch + cache-lru",
        "policy_note": "Stable 1.0 uses lossless visual intermediates, signed-or-disabled update trust, hash-locked neural dependencies, managed Python, single-instance protection and Windows distribution gates. Generic recovery remains shadow/Preview by default until physical acceptance.",
    }

    return RenderPlan(
        source=source,
        target=target,
        project_mode=data.project_mode,
        preview=data.preview,
        enhancement_mode=data.enhancement_mode,
        interpolation_mode=data.interpolation_mode,
        effects_active=data.effects_active,
        transition_active=data.transition_active,
        steps=tuple(steps),
        risks=tuple(risks),
        metadata=metadata,
    )


def risks_as_warnings(risks: Iterable[PlanRisk]) -> list[str]:
    """Return concise user-facing warnings without losing audit codes."""

    labels = {"info": "INFO", "warning": "ATENÇÃO", "critical": "CRÍTICO"}
    return [f"[{labels[item.severity]} {item.code}] {item.title}: {item.detail}" for item in risks]
