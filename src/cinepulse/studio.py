from __future__ import annotations

import json
import hashlib
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from tkinter import (
    BooleanVar,
    Canvas,
    DoubleVar,
    IntVar,
    StringVar,
    PhotoImage,
    TclError,
    Text,
    Tk,
    Toplevel,
    colorchooser,
    filedialog,
    messagebox,
    simpledialog,
)
from tkinter import ttk

import numpy as np
from . import ai_suite
from . import experimental_components
from . import vfx
from .loop_engine import (
    CREATE_NO_WINDOW,
    FFMPEG,
    FFPROBE,
    REAL_ESRGAN,
    REAL_ESRGAN_DIR,
    REAL_ESRGAN_MODELS,
    first_video_fps,
    first_video_size,
    format_time,
    has_audio,
    media_duration,
    nvenc_available,
    probe_media,
)


from .paths import PATHS
from .runtime_distribution import find_powershell, installation_mode
from .hardware import detect_hardware
from .media_profile import ColorProfile
from .delivery import (
    DELIVERY_PROFILES, PROFILE_AUTO, DeliveryPlan, build_delivery_plan, suggested_extension, detect_ffmpeg_encoders,
)
from .color_pipeline import ColorPipeline, build_color_pipeline
from .render_plan import FrameSpec, PlanInput, RenderPlan, build_render_plan, risks_as_warnings, spatial_scale_factor
from .process_control import popen_group_kwargs, terminate_process_tree
from .safe_output import AtomicOutput, RenderJournal, process_alive
from .rife_engine import RifePaths, build_command as build_rife_command, target_frame_count
from .audio_mastering import analyze_loudness, build_audio_filter
from . import __version__
from .quality_metrics import measure_vmaf
from .stem_engine import build_demucs_command, stem_cache_key, stems_for_focus
from . import update_manager
from .ui.tokens import COLORS
from .ui.preview import extract_video_frame, effect_thumbnail, to_ppm_bytes, visual_preview
from .ui.visual_lab import DIRECTION_BUTTONS, EFFECT_SHORT_NAMES, VISUAL_VARIANTS, variant_preview
from .ui.visual_view import build_visual_tab
from .ui.project_lab import (
    framing_explanation,
    framing_preview,
    output_state as project_output_state,
    summarize_audio_probe,
    summarize_video_probe,
)
from .ui.project_view import build_project_tab
from .ui.quality_lab import estimate_quality_impact, motion_description, scale_description
from .ui.quality_view import build_quality_tab
from .ui.queue_lab import (
    ATTENTION_STATUSES,
    can_move as queue_can_move,
    can_retry as queue_can_retry,
    effects_text as queue_effects_text,
    item_progress as queue_item_progress,
    normalize_status as queue_normalize_status,
    processing_text as queue_processing_text,
    profile_text as queue_profile_text,
    project_name as queue_project_name,
    status_text as queue_status_text,
    summarize_queue,
)
from .ui.queue_view import build_queue_tab
from .ui.ai_lab import capability_state, human_bytes, inventory_summary, module_detail, progress_from_log, selected_download, visible_items
from .ui.ai_view import build_ai_tab
from .ui.feedback_lab import FeedbackEntry, FeedbackHistory, classify_failure, severity_meta
from .ui.feedback_view import build_feedback_strip, refresh_activity_center, refresh_feedback_strip, show_activity_center
from .ui.polish_lab import compact_layout, safe_window_geometry, sanitize_ui_state, tab_for_shortcut
from .ui.platform_support import enable_windows_dpi_awareness
from .ui.polish_view import (
    apply_responsive_splits,
    build_welcome_card,
    refresh_quick_guide_theme,
    refresh_welcome_visibility,
    register_responsive_split,
    show_quick_guide,
)
from .preflight import (
    build_storage_plan,
    check_directory_writable,
    quality_warnings as preflight_quality_warnings,
    validate_output_path,
)
from .verification import VerifyExpectation, deep_verify, quick_verify
from .render_history import RenderHistory
from .state_store import load_presets_state, load_queue_state, save_presets_state, save_queue_state
from .storage_engine import (
    cache_usage_bytes,
    choose_chunk_frames,
    enforce_cache_quota,
    estimate_storage,
    probe_scratch,
    resolve_scratch_dir,
    safe_rmtree,
    touch_cache_entry,
)


APP_TITLE = "CinePulse"
APP_DIR = PATHS.root
APP_TEMP = PATHS.temp
PREVIEW_DIR = PATHS.previews
WORK_DIR = PATHS.work
CONFIG_DIR = PATHS.config
PRESETS_FILE = CONFIG_DIR / "presets.json"
QUEUE_FILE = CONFIG_DIR / "queue.json"
UI_STATE_FILE = CONFIG_DIR / "ui_state.json"
CACHE_DIR = PATHS.cache / "ai"
REPORT_DIR = PATHS.reports
RIFE_EXE = ai_suite.RIFE_EXE
RIFE_MODEL = ai_suite.RIFE_DIR / "rife-v4.6"
RIFE_OPTION = "RIFE IA — movimento natural"
MODE_MUSIC = "Loop musical — repetir vídeo durante a música"
MODE_ORIGINAL = "Melhorar vídeo original — manter duração e conteúdo"
ENHANCE_NONE = "Sem melhoria — preservar a fonte"
ENHANCE_SIMPLE = "Upscale simples — Lanczos de alta qualidade"
ENHANCE_AI = "Upscale por IA — Real-ESRGAN x2"
ASPECT_ORIGINAL = "Original — sem cortar"
ASPECT_LANDSCAPE = "16:9 — horizontal"
ASPECT_PORTRAIT = "9:16 — vertical"
ASPECT_IMAX = "IMAX digital — 1.90:1"
ASPECT_WIDE = "Cinema Wide — 2.39:1"
FIT_COVER = "Preencher a tela — cortar bordas"
FIT_CONTAIN = "Encaixar inteiro — usar barras"
AUDIO_FOCUS_OPTIONS = (
    "Todos equilibrados",
    "Graves",
    "Graves e batidas",
    "Médios",
    "Agudos",
    "Batidas e ataques",
)
AUDIO_MODES = (
    "Preservar dinâmica original",
    "Normalizar para YouTube — -14 LUFS",
    "Masterização leve e segura",
)
INTERPOLATION_OPTIONS = (
    "RIFE IA — movimento natural",
    "Movimento suave — FFmpeg",
    "Quadros repetidos — rápido",
)
VISUAL_DIRECTIONS = {
    "Personalizada": None,
    "Suave e atmosférica": ("Graves", 94, 58, 88, 72),
    "Cinematográfica": ("Graves e batidas", 86, 78, 82, 92),
    "Energética": ("Batidas e ataques", 65, 125, 95, 125),
    "Minimalista": ("Graves", 96, 48, 62, 55),
    "Crescente até o refrão": ("Graves e batidas", 90, 72, 100, 82),
}

RESOLUTIONS = {
    "720p HD": (1280, 720),
    "1080p Full HD": (1920, 1080),
    "1440p QHD": (2560, 1440),
    "4K UHD": (3840, 2160),
    "5K": (5120, 2880),
    "6K": (5760, 3240),
    "8K UHD": (7680, 4320),
    "10K": (10240, 5760),
    "12K": (11520, 6480),
}
FPS_OPTIONS = (24, 25, 30, 48, 50, 60, 90, 120, 144, 240, 480)
EFFECT_NAMES = (
    "Aurora",
    "Espectro",
    "Barras arredondadas",
    "Onda líquida",
    "Círculo mágico",
    "Partículas musicais",
    "Pulso cinematográfico",
    "Energia mágica",
)
TRANSITIONS = {
    "Corte seco — original": None,
    "Dissolver suave": "dissolve",
    "Fade cinematográfico": "fade",
    "Fade para preto": "fadeblack",
    "Fade para branco": "fadewhite",
    "Deslizar para esquerda": "slideleft",
    "Deslizar para direita": "slideright",
    "Círculo abrindo": "circleopen",
    "Círculo fechando": "circleclose",
    "Radial": "radial",
    "Pixelizar": "pixelize",
    "Suave horizontal": "smoothleft",
}

BUILTIN_PRESETS = {
    "Meu padrão — 8K 120 fps Aurora": {
        "mode": MODE_MUSIC,
        "resolution": "8K UHD",
        "fps": 120,
        "aspect": ASPECT_LANDSCAPE,
        "enhancement": ENHANCE_AI,
        "fit_mode": FIT_COVER,
        "use_cpu": False,
        "preserve_audio": True,
        "effects": ["Aurora", "Pulso cinematográfico", "Energia mágica"],
        "color": "#43D6FF",
        "intensity": 100,
        "occupancy": 65,
        "transition": "Corte seco — original",
        "transition_duration": 0.75,
        "audio_focus": "Graves e batidas",
        "reaction_smoothing": 82,
        "reaction_expression": 82,
        "auto_loop": True,
        "dynamic_sections": True,
        "section_dynamics": 75,
        "audio_mode": "Preservar dinâmica original",
        "interpolation": "Movimento suave — FFmpeg",
        "cpu_threads": max(1, min(8, os.cpu_count() or 4)),
        "minimum_free_gb": 20,
        "quality_check": True,
        "deep_verify": False,
        "visual_direction": "Cinematográfica",
    },
    "YouTube — 8K 60 fps natural": {
        "mode": MODE_MUSIC,
        "resolution": "8K UHD",
        "fps": 60,
        "aspect": ASPECT_LANDSCAPE,
        "enhancement": ENHANCE_AI,
        "fit_mode": FIT_COVER,
        "use_cpu": False,
        "preserve_audio": True,
        "effects": ["Aurora", "Pulso cinematográfico"],
        "color": "#43D6FF",
        "intensity": 80,
        "occupancy": 55,
        "transition": "Dissolver suave",
        "transition_duration": 0.75,
        "audio_focus": "Graves e batidas",
        "reaction_smoothing": 88,
        "reaction_expression": 70,
        "auto_loop": True,
        "dynamic_sections": True,
        "section_dynamics": 85,
        "audio_mode": "Normalizar para YouTube — -14 LUFS",
        "interpolation": "Movimento suave — FFmpeg",
        "cpu_threads": max(1, min(8, os.cpu_count() or 4)),
        "minimum_free_gb": 20,
        "quality_check": True,
        "deep_verify": False,
        "visual_direction": "Suave e atmosférica",
    },
    "Shorts/Reels — 4K vertical": {
        "mode": MODE_MUSIC,
        "resolution": "4K UHD",
        "fps": 60,
        "aspect": ASPECT_PORTRAIT,
        "enhancement": ENHANCE_AI,
        "fit_mode": FIT_COVER,
        "use_cpu": False,
        "preserve_audio": True,
        "effects": ["Partículas musicais", "Pulso cinematográfico"],
        "color": "#43D6FF",
        "intensity": 75,
        "occupancy": 60,
        "transition": "Dissolver suave",
        "transition_duration": 0.55,
        "audio_focus": "Graves e batidas",
        "reaction_smoothing": 84,
        "reaction_expression": 76,
        "auto_loop": True,
        "dynamic_sections": True,
        "section_dynamics": 80,
        "audio_mode": "Normalizar para YouTube — -14 LUFS",
        "interpolation": "Movimento suave — FFmpeg",
        "cpu_threads": max(1, min(8, os.cpu_count() or 4)),
        "minimum_free_gb": 15,
        "quality_check": True,
        "deep_verify": False,
        "visual_direction": "Energética",
    },
    "Vídeo original — 4K 60 fps IA": {
        "mode": MODE_ORIGINAL,
        "resolution": "4K UHD",
        "fps": 60,
        "aspect": ASPECT_ORIGINAL,
        "enhancement": ENHANCE_AI,
        "fit_mode": FIT_CONTAIN,
        "use_cpu": False,
        "preserve_audio": True,
        "effects": [],
        "color": "#43D6FF",
        "intensity": 75,
        "occupancy": 55,
        "transition": "Corte seco — original",
        "transition_duration": 0.75,
        "audio_focus": "Todos equilibrados",
        "reaction_smoothing": 85,
        "reaction_expression": 75,
        "auto_loop": False,
        "dynamic_sections": False,
        "section_dynamics": 70,
        "audio_mode": "Preservar dinâmica original",
        "interpolation": "Movimento suave — FFmpeg",
        "cpu_threads": max(1, min(8, os.cpu_count() or 4)),
        "minimum_free_gb": 20,
        "quality_check": True,
        "deep_verify": False,
        "visual_direction": "Personalizada",
    },
}


@dataclass
class RenderSettings:
    mode: str
    video: str
    audio: str
    output: str
    resolution: str
    fps: int
    aspect: str
    enhancement: str
    fit_mode: str
    use_cpu: bool
    preserve_audio: bool
    effects: set[str]
    color: str
    intensity: float
    occupancy: float
    audio_focus: str
    reaction_smoothing: float
    reaction_expression: float
    auto_loop: bool
    dynamic_sections: bool
    section_dynamics: float
    transition: str
    transition_duration: float
    preview_seconds: int
    audio_mode: str
    interpolation: str
    cpu_threads: int
    minimum_free_gb: float
    quality_check: bool
    deep_verify: bool = False
    visual_direction: str = "Personalizada"
    comparison_preview: bool = True
    use_stems: bool = False
    delivery_profile: str = PROFILE_AUTO
    scratch_dir: str = ""
    cache_quota_gb: float = 50.0


class ScrollableTab(ttk.Frame):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.canvas = Canvas(self, highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas, padding=18)
        self.window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.content.bind("<Configure>", self._content_changed)
        self.canvas.bind("<Configure>", self._canvas_changed)
        # Bind globally so scrolling also works while the pointer is over a
        # card/label inside the canvas.  Only the visible tab under the pointer
        # reacts; native scrollable widgets keep their own wheel behaviour.
        self.bind_all("<MouseWheel>", self._mousewheel, add="+")
        self.bind_all("<Button-4>", self._mousewheel, add="+")
        self.bind_all("<Button-5>", self._mousewheel, add="+")

    def _content_changed(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _canvas_changed(self, event) -> None:
        self.canvas.itemconfigure(self.window, width=event.width)

    def _mousewheel(self, event) -> None:
        try:
            if not self.winfo_ismapped():
                return
            x, y = self.winfo_pointerxy()
            left, top = self.winfo_rootx(), self.winfo_rooty()
            if not (left <= x < left + self.winfo_width() and top <= y < top + self.winfo_height()):
                return
            widget_class = str(event.widget.winfo_class()) if getattr(event, "widget", None) is not None else ""
            if widget_class in {"Treeview", "Text", "Listbox"}:
                return
            if getattr(event, "num", None) == 4:
                step = -1
            elif getattr(event, "num", None) == 5:
                step = 1
            else:
                delta = int(getattr(event, "delta", 0) or 0)
                if not delta:
                    return
                step = -1 if delta > 0 else 1
            self.canvas.yview_scroll(step * 3, "units")
        except Exception:
            return


class VideoOptimizerStudio:
    def __init__(self, root: Tk) -> None:
        self.root = root
        # Every Tk ``after`` callback registered by Studio is tracked so a
        # clean shutdown cannot leave Tcl commands behind in a reused Python
        # process (important for tests, relaunches and installer hand-offs).
        self._closing = False
        self._after_ids: set[str] = set()
        self.root.title(APP_TITLE)
        self._ui_state = self._load_ui_state()
        screen_width = max(1024, self.root.winfo_screenwidth())
        screen_height = max(720, self.root.winfo_screenheight())
        initial_width = min(1440, max(1080, screen_width - 80))
        initial_height = min(900, max(720, screen_height - 100))
        geometry = safe_window_geometry(
            self._ui_state.get("geometry", ""),
            screen_width=screen_width,
            screen_height=screen_height,
            fallback_width=initial_width,
            fallback_height=initial_height,
        )
        self.root.geometry(geometry)
        self.root.minsize(1024, 700)

        self.mode = StringVar(value=MODE_MUSIC)
        self.video = StringVar()
        self.audio = StringVar()
        self.output = StringVar()
        self.resolution = StringVar(value="8K UHD")
        self.fps = IntVar(value=60)
        self.aspect = StringVar(value=ASPECT_LANDSCAPE)
        self.enhancement = StringVar(value=ENHANCE_AI)
        self.fit_mode = StringVar(value=FIT_COVER)
        self.use_cpu = BooleanVar(value=False)
        self.dark_mode = BooleanVar(value=bool(self._ui_state.get("dark_mode", False)))
        self.preserve_audio = BooleanVar(value=True)
        self.effect_vars = {name: BooleanVar(value=name in {"Aurora", "Pulso cinematográfico"}) for name in EFFECT_NAMES}
        self.color = StringVar(value="#43D6FF")
        self.intensity = DoubleVar(value=100.0)
        self.occupancy = DoubleVar(value=65.0)
        self.intensity_text = StringVar(value="100%")
        self.occupancy_text = StringVar(value="65%")
        self.audio_focus = StringVar(value="Graves e batidas")
        self.reaction_smoothing = DoubleVar(value=82.0)
        self.reaction_expression = DoubleVar(value=82.0)
        self.smoothing_text = StringVar(value="82%")
        self.expression_text = StringVar(value="82%")
        self.auto_loop = BooleanVar(value=True)
        self.dynamic_sections = BooleanVar(value=True)
        self.section_dynamics = DoubleVar(value=75.0)
        self.section_dynamics_text = StringVar(value="75%")
        self.transition = StringVar(value="Corte seco — original")
        self.transition_duration = DoubleVar(value=0.75)
        self.preview_seconds = IntVar(value=10)
        self.audio_mode = StringVar(value="Preservar dinâmica original")
        self.interpolation = StringVar(value="Movimento suave — FFmpeg")
        self.cpu_threads = IntVar(value=max(1, min(8, os.cpu_count() or 4)))
        self.minimum_free_gb = DoubleVar(value=20.0)
        self.scratch_dir = StringVar(value=str(WORK_DIR))
        self.cache_quota_gb = DoubleVar(value=50.0)
        self.quality_check = BooleanVar(value=True)
        self.deep_verify = BooleanVar(value=False)
        self.visual_direction = StringVar(value="Cinematográfica")
        self.comparison_preview = BooleanVar(value=True)
        self.use_stems = BooleanVar(value=False)
        self.delivery_profile = StringVar(value=PROFILE_AUTO)
        self.status = StringVar(value="Configure o projeto e gere um preview antes do vídeo final.")
        self.stage = StringVar(value="Pronto")
        self.progress_text = StringVar(value="0%")
        self.time_text = StringVar(value="Decorrido 00:00:00  •  Restante --:--:--")
        self.summary = StringVar()
        self.preset_name = StringVar(value="Meu padrão — 8K 120 fps Aurora")
        self.preset_state_text = StringVar(value="Selecione um preset e clique em Aplicar.")
        self.experimental_downloads = BooleanVar(value=False)
        self.home_preview_mode = StringVar(value="Resultado")
        self.visual_preview_mode = StringVar(value="Resultado")
        self.visual_preview_position = DoubleVar(value=38.0)

        # Phase 3 — Project workspace state.  These variables are UI-only and
        # intentionally do not alter RenderSettings or the render pipeline.
        self.project_video_badge = StringVar(value="Aguardando vídeo")
        self.project_video_headline = StringVar(value="Selecione um vídeo para analisar resolução, FPS, duração e cor.")
        self.project_video_detail = StringVar(value="A análise usa FFprobe em segundo plano e não modifica o arquivo.")
        self.project_audio_badge = StringVar(value="Aguardando música")
        self.project_audio_headline = StringVar(value="Selecione uma música no modo Loop musical.")
        self.project_audio_detail = StringVar(value="WAV ou FLAC são recomendados para preservar melhor a fonte.")
        self.project_output_badge = StringVar(value="Destino pendente")
        self.project_output_detail = StringVar(value="Escolha o arquivo final; previews continuam isolados na pasta interna.")
        self.project_framing_badge = StringVar(value="Guia instantâneo")
        self.project_framing_info = StringVar(value="Selecione um vídeo para visualizar o enquadramento usando um frame real.")
        self.project_preflight_badge = StringVar(value="Não verificado")
        self.project_preflight_title = StringVar(value="Complete os arquivos do projeto para executar a pré-verificação detalhada.")
        self.project_preflight_detail = StringVar(value="A validação inline de cada caminho aparece assim que ele é informado.")

        # Phase 4 — Quality & output impact state.
        self.quality_load_badge = StringVar(value="Aguardando fonte")
        self.quality_source_text = StringVar(value="Selecione um vídeo para medir escala e movimento.")
        self.quality_target_text = StringVar(value="Destino calculado a partir da configuração atual.")
        self.quality_scale_text = StringVar(value="—")
        self.quality_motion_text = StringVar(value="—")
        self.quality_vram_text = StringVar(value="—")
        self.quality_output_text = StringVar(value="—")
        self.quality_compat_badge = StringVar(value="Ainda não calculado")
        self.quality_warning_text = StringVar(value="O CinePulse mostrará avisos de resolução, FPS, VRAM, IA e compatibilidade aqui.")
        self.quality_plan_badge = StringVar(value="Aguardando fonte")
        self.quality_plan_text = StringVar(value="O plano real de processamento aparecerá depois que a fonte for analisada.")
        self.quality_plan_risk_text = StringVar(value="Phase 1: o RenderPlan descreve honestamente o pipeline atual; as correções de política entram nas próximas fases.")
        self.quality_delivery_text = StringVar(value="O perfil de entrega será resolvido pelo arquivo final.")

        # Phase 5 — Queue workspace state.  Queue execution remains owned by
        # Studio; these variables only expose recoverable state clearly.
        self.queue_waiting_text = StringVar(value="0")
        self.queue_active_text = StringVar(value="0")
        self.queue_done_text = StringVar(value="0")
        self.queue_attention_text = StringVar(value="0")
        self.queue_overview_text = StringVar(value="Nenhum projeto aguardando processamento.")
        self.queue_empty_text = StringVar(value="Adicione um projeto usando ‘Adicionar à fila’ no rodapé. A fila é salva automaticamente.")
        self.queue_selected_badge = StringVar(value="Nenhum item")
        self.queue_selected_title = StringVar(value="Selecione um projeto para ver os detalhes.")
        self.queue_selected_profile = StringVar(value="Arquivos, perfil, VFX e último estado aparecem aqui.")
        self.queue_selected_input = StringVar(value="—")
        self.queue_selected_output = StringVar(value="—")
        self.queue_selected_processing = StringVar(value="—")
        self.queue_selected_effects = StringVar(value="—")
        self.queue_selected_note = StringVar(value="Nenhum detalhe registrado.")
        self.queue_selected_stage = StringVar(value="Aguardando seleção")
        self.queue_selected_progress = DoubleVar(value=0.0)
        self.queue_selected_progress_text = StringVar(value="0%")

        # Phase 6 — Local AI capability manager.  These variables describe
        # what the pipeline can actually use; an experimental file on disk is
        # deliberately never presented as an integrated render feature.
        self.ai_filter = StringVar(value="Todos")
        self.ai_integrated_ready_text = StringVar(value="0/4")
        self.ai_integrated_missing_text = StringVar(value="4")
        self.ai_experimental_installed_text = StringVar(value="0/7")
        self.ai_selection_size_text = StringVar(value="0 B")
        self.ai_inventory_text = StringVar(value="Lendo inventário local…")
        self.ai_selection_text = StringVar(value="Nenhum componente selecionado para download.")
        self.ai_install_status_text = StringVar(value="Nenhuma instalação em andamento.")
        self.ai_install_progress = DoubleVar(value=0.0)
        self.ai_install_progress_text = StringVar(value="")
        self.ai_detail_badge = StringVar(value="Nenhum módulo")
        self.ai_detail_name = StringVar(value="Selecione um componente para entender seu papel.")
        self.ai_detail_category = StringVar(value="Integração, impacto, espaço e licença aparecem aqui.")
        self.ai_detail_state = StringVar(value="Aguardando seleção")
        self.ai_detail_state_explanation = StringVar(value="")
        self.ai_detail_benefit = StringVar(value="—")
        self.ai_detail_render_usage = StringVar(value="—")
        self.ai_detail_missing_effect = StringVar(value="—")
        self.ai_detail_footprint = StringVar(value="—")
        self.ai_detail_license = StringVar(value="—")
        self.ai_detail_license_warning = StringVar(value="")
        self.ai_detail_recommendation = StringVar(value="—")

        # Phase 7 — global feedback language.  Existing status/stage variables
        # remain for compatibility, while this strip provides consistent
        # severity, explanation and next actions across the whole application.
        self.feedback_severity = StringVar(value="info")
        self.feedback_badge = StringVar(value="INFO")
        self.feedback_title = StringVar(value="Pronto para configurar")
        self.feedback_detail = StringVar(value=self.status.get())
        self.feedback_primary_action = StringVar(value="")
        self.feedback_secondary_action = StringVar(value="")
        self.feedback_history_count = IntVar(value=0)

        self._events: queue.Queue = queue.Queue()
        self._process: subprocess.Popen | None = None
        self._cancelled = False
        self._busy = False
        self._available_update: update_manager.UpdateInfo | None = None
        self._update_check_running = False
        self._started_at: float | None = None
        self._progress_value = 0.0
        self._logs: list[str] = []
        self._log_window: Toplevel | None = None
        self._log_text: Text | None = None
        self._scrollable_tabs: list[ScrollableTab] = []
        self._nvenc = nvenc_available()
        self._hardware = detect_hardware()
        self._render_journal = RenderJournal(PATHS.locks / "render.json")
        self._active_render_history: RenderHistory | None = None
        self._custom_presets: dict[str, dict] = self._load_custom_presets()
        self._presets: dict[str, dict] = {**BUILTIN_PRESETS, **self._custom_presets}
        self._queue_items: list[dict] = []
        self._queue_serial = 0
        self._queue_running = False
        self._active_queue_id: int | None = None
        self._ai_selected: set[str] = set()
        self._ai_installing = False
        self._ai_detail_key = ""
        self._ai_filter_buttons: dict[str, ttk.Button] = {}
        self._ai_inventory_snapshot: list[dict] = []
        self._feedback_history = FeedbackHistory(max_items=40)
        self._feedback_primary_callback = None
        self._feedback_secondary_callback = None
        self._feedback_status_guard = False
        self._active_preset_name = ""
        self._applied_preset_snapshot: dict | None = None
        self._activity_window: Toplevel | None = None
        self._quick_guide_window: Toplevel | None = None
        self._quick_guide_text: Text | None = None
        self._welcome_completed = bool(self._ui_state.get("welcome_completed", False))
        self._responsive_splits: dict[str, dict] = {}
        self._layout_compact: bool | None = None
        self._layout_after: str | None = None
        self._home_preview_after: str | None = None
        self._home_preview_serial = 0
        self._home_preview_source: np.ndarray | None = None
        self._home_preview_source_path = ""
        self._home_preview_photo: PhotoImage | None = None
        self._home_effect_photos: dict[str, PhotoImage] = {}
        self._visual_preview_after: str | None = None
        self._visual_preview_serial = 0
        self._visual_preview_source: np.ndarray | None = None
        self._visual_preview_source_path = ""
        self._visual_preview_photo: PhotoImage | None = None
        self._visual_preview_playing = False
        self._visual_playback_after: str | None = None
        self._visual_effect_photos: dict[str, PhotoImage] = {}
        self._visual_transition_photos: dict[str, PhotoImage] = {}
        self._visual_variant_photos: dict[str, PhotoImage] = {}
        self._project_video_serial = 0
        self._project_audio_serial = 0
        self._project_preflight_serial = 0
        self._project_source_rgb: np.ndarray | None = None
        self._project_source_path = ""
        self._project_video_size: tuple[int, int] | None = None
        self._project_video_probe: dict | None = None
        self._project_video_probe_path = ""
        self._project_audio_probe: dict | None = None
        self._project_audio_probe_path = ""
        self._project_framing_photo: PhotoImage | None = None

        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        self._prune_previews()
        self._prune_work()

        self._configure_style()
        self.status.trace_add("write", self._status_feedback_changed)
        self._build_ui()
        self._apply_selected_preset()
        self._load_queue()
        try:
            self.notebook.select(int(self._ui_state.get("last_tab", 0)))
        except Exception:
            self.notebook.select(0)
        refresh_welcome_visibility(self)
        self._install_shortcuts()
        self.root.bind("<Configure>", self._on_root_configure, add="+")
        self._schedule(0, self._apply_responsive_layout)
        self._schedule(100, self._poll_events)
        self._schedule(500, self._tick_clock)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._schedule(350, self._recover_interrupted_render)
        self._schedule(1200, self._startup_update_check)

    # ------------------------------------------------------------------
    # Phase 8 — release UX, persistence, keyboard and responsive layout
    # ------------------------------------------------------------------
    def _schedule(self, delay_ms: int, callback) -> str | None:
        """Schedule one Studio-owned Tk callback and make it shutdown-safe."""
        if self._closing:
            return None
        holder: dict[str, str | None] = {"token": None}

        def invoke() -> None:
            token = holder["token"]
            if token is not None:
                self._after_ids.discard(token)
            if self._closing:
                return
            callback()

        try:
            token = self.root.after(max(0, int(delay_ms)), invoke)
        except Exception:
            return None
        holder["token"] = token
        self._after_ids.add(token)
        return token

    def _cancel_after(self, token: str | None) -> None:
        if token is None:
            return
        self._after_ids.discard(token)
        try:
            self.root.after_cancel(token)
        except Exception:
            pass

    def _cancel_scheduled_callbacks(self) -> None:
        for token in tuple(self._after_ids):
            self._cancel_after(token)
        self._after_ids.clear()
        self._layout_after = None
        self._home_preview_after = None
        self._visual_preview_after = None
        self._visual_playback_after = None

    def _load_ui_state(self) -> dict:
        try:
            payload = json.loads(UI_STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            payload = {}
        return sanitize_ui_state(payload)

    def _save_ui_state(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            last_tab = 0
            if hasattr(self, "notebook"):
                try:
                    last_tab = int(self.notebook.index(self.notebook.select()))
                except Exception:
                    last_tab = 0
            payload = sanitize_ui_state(
                {
                    "dark_mode": bool(self.dark_mode.get()),
                    "welcome_completed": bool(self._welcome_completed),
                    "last_tab": last_tab,
                    "geometry": self.root.geometry(),
                }
            )
            temporary = UI_STATE_FILE.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, UI_STATE_FILE)
            self._ui_state = payload
        except OSError:
            # UI preferences are convenience state and may never block render.
            pass

    def _dismiss_welcome(self) -> None:
        self._welcome_completed = True
        refresh_welcome_visibility(self)
        self._save_ui_state()
        self._set_feedback(
            "info",
            "Primeiros passos concluídos",
            "O guia continua disponível em Ajuda ou pela tecla F1.",
            category="Interface",
            record=False,
        )

    def _show_quick_guide(self) -> None:
        show_quick_guide(self)

    def _install_shortcuts(self) -> None:
        self.root.bind("<F1>", lambda _event: (self._show_quick_guide(), "break")[1])
        for number in range(1, 7):
            self.root.bind(
                f"<Control-Key-{number}>",
                lambda _event, n=number: self._shortcut_tab(n),
            )
        self.root.bind("<Control-Tab>", lambda _event: self._cycle_tab(1))
        self.root.bind("<Control-Shift-Tab>", lambda _event: self._cycle_tab(-1))
        try:
            self.root.bind("<Control-ISO_Left_Tab>", lambda _event: self._cycle_tab(-1))
        except TclError:
            # ISO_Left_Tab is available on X11 but is not a valid Tk keysym on Windows.
            pass
        self.root.bind("<Control-o>", lambda _event: self._run_shortcut(self._choose_video))
        self.root.bind("<Control-Shift-O>", lambda _event: self._run_shortcut(self._choose_audio))
        self.root.bind("<Control-Shift-S>", lambda _event: self._run_shortcut(self._choose_output))
        self.root.bind("<Control-p>", lambda _event: self._run_shortcut(lambda: self._start(True)))
        self.root.bind("<Control-l>", lambda _event: self._run_shortcut(self._show_log))
        self.root.bind("<Control-Shift-A>", lambda _event: self._run_shortcut(self._show_activity_center))

    def _run_shortcut(self, callback) -> str:
        if callable(callback):
            callback()
        return "break"

    def _shortcut_tab(self, number: int) -> str:
        index = tab_for_shortcut(number)
        if index is not None:
            self._open_tab(index)
        return "break"

    def _cycle_tab(self, delta: int) -> str:
        try:
            current = int(self.notebook.index(self.notebook.select()))
            count = int(self.notebook.index("end"))
            if count:
                self.notebook.select((current + int(delta)) % count)
        except Exception:
            pass
        return "break"

    def _on_root_configure(self, event=None) -> None:
        if event is not None and getattr(event, "widget", None) is not self.root:
            return
        if self._layout_after is not None:
            self._cancel_after(self._layout_after)
        self._layout_after = self._schedule(120, self._apply_responsive_layout)

    def _apply_responsive_layout(self) -> None:
        self._layout_after = None
        try:
            compact = compact_layout(self.root.winfo_width(), self.root.winfo_height())
        except Exception:
            compact = False
        if compact == self._layout_compact:
            return
        self._layout_compact = compact
        apply_responsive_splits(self, compact)
        if hasattr(self, "footer_summary_label"):
            self.footer_summary_label.configure(wraplength=600 if compact else 980)
        if hasattr(self, "header_subtitle_label"):
            self.header_subtitle_label.configure(wraplength=650 if compact else 980)
        if hasattr(self, "outer"):
            self.outer.configure(padding=(16, 12, 16, 12) if compact else (24, 18, 24, 16))
        if hasattr(self, "footer"):
            self.footer.configure(padding=(10, 6) if compact else (14, 10))
        # Cancel is contextual and hidden while idle, so even the minimum
        # window can keep summary and primary actions on one predictable row.
        self._refresh_footer_density()
        # Keep focus/navigation readable at the minimum supported size.
        self.style.configure("TNotebook.Tab", padding=(9, 7) if compact else (14, 8))

    def _refresh_footer_density(self) -> None:
        """Keep the global footer useful instead of clipped at 1024×700."""
        if not hasattr(self, "footer_summary_left"):
            return
        compact = bool(self._layout_compact)
        active = bool(self._busy or self._ai_installing)

        def show_packed(widget, **options) -> None:
            if widget.winfo_manager() != "pack":
                widget.pack(**options)

        if compact and active:
            # During work, progress and cancellation matter more than the long
            # configuration sentence or utility shortcuts.
            self.footer_summary_left.pack_forget()
            self.footer_utility_row.pack_forget()
            self.add_queue_compact_button.pack_forget()
            show_packed(self.bar, fill="x", pady=(9, 0), before=self.feedback_frame)
            show_packed(self.footer_progress_row, fill="x", pady=(4, 0), before=self.feedback_frame)
            self.footer_time_label.pack_forget()
            return

        # Summary is always visible while idle and on every wide layout.
        if self.footer_summary_left.winfo_manager() != "pack":
            self.footer_summary_left.pack(
                side="left", fill="x", expand=True, before=self.footer_action_row
            )

        if compact:
            # Idle progress at 0% conveys nothing and stole enough vertical
            # space to clip the activity state. Keep queueing available beside
            # the primary actions and move utilities out of the minimum shell.
            self.bar.pack_forget()
            self.footer_progress_row.pack_forget()
            self.footer_time_label.pack_forget()
            self.footer_utility_row.pack_forget()
            if self.add_queue_compact_button.winfo_manager() != "pack":
                self.add_queue_compact_button.pack(side="left", padx=(8, 0))
        else:
            self.add_queue_compact_button.pack_forget()
            show_packed(self.bar, fill="x", pady=(9, 0), before=self.feedback_frame)
            show_packed(self.footer_progress_row, fill="x", pady=(4, 0), before=self.feedback_frame)
            show_packed(self.footer_time_label, anchor="w", pady=(2, 0), before=self.feedback_frame)
            if self.footer_utility_row.winfo_manager() != "pack":
                self.footer_utility_row.pack(fill="x", pady=(7, 0), after=self.feedback_frame)

    def _configure_style(self) -> None:
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass
        self._configure_shell_styles(bool(self.dark_mode.get()))

    def _configure_shell_styles(self, dark: bool) -> None:
        bg = COLORS["dark_bg"] if dark else COLORS["light_bg"]
        panel = COLORS["dark_panel"] if dark else COLORS["light_panel"]
        panel_alt = COLORS["dark_panel_alt"] if dark else COLORS["light_panel_alt"]
        field = COLORS["dark_field"] if dark else COLORS["light_field"]
        border = COLORS["dark_border"] if dark else COLORS["light_border"]
        text = COLORS["dark_text"] if dark else COLORS["light_text"]
        muted = COLORS["dark_muted"] if dark else COLORS["light_muted"]
        muted2 = COLORS["dark_muted_2"] if dark else COLORS["light_muted_2"]

        self.root.configure(background=bg)
        self.style.configure(".", background=bg, foreground=text, font=("Segoe UI", 10))
        self.style.configure("TFrame", background=bg)
        self.style.configure("TLabel", background=bg, foreground=text)
        self.style.configure("Title.TLabel", background=bg, foreground=text, font=("Segoe UI", 21, "bold"))
        self.style.configure("Subtitle.TLabel", background=bg, foreground=muted, font=("Segoe UI", 10))
        self.style.configure("Muted.TLabel", background=bg, foreground=muted, font=("Segoe UI", 9))
        self.style.configure("Card.TFrame", background=panel, relief="solid", borderwidth=1)
        self.style.configure("Card.TLabel", background=panel, foreground=text)
        self.style.configure("CardTitle.TLabel", background=panel, foreground=text, font=("Segoe UI", 11, "bold"))
        self.style.configure("CardMuted.TLabel", background=panel, foreground=muted, font=("Segoe UI", 9))
        self.style.configure("CardStatus.TLabel", background=panel, foreground=COLORS["primary"], font=("Segoe UI", 9, "bold"))
        self.style.configure("StatusOk.TLabel", background=panel, foreground=COLORS["success"], font=("Segoe UI", 9, "bold"))
        self.style.configure("StatusWarning.TLabel", background=panel, foreground=COLORS["warning"], font=("Segoe UI", 9, "bold"))
        self.style.configure("StatusError.TLabel", background=panel, foreground=COLORS["danger"], font=("Segoe UI", 9, "bold"))
        self.style.configure("StatusMuted.TLabel", background=panel, foreground=muted, font=("Segoe UI", 9, "bold"))
        self.style.configure("PanelAlt.TFrame", background=panel_alt, relief="solid", borderwidth=1)
        self.style.configure("PanelAlt.TLabel", background=panel_alt, foreground=text)
        self.style.configure("PanelAltMuted.TLabel", background=panel_alt, foreground=muted, font=("Segoe UI", 9, "bold"))
        self.style.configure("PanelAltPrimary.TLabel", background=panel_alt, foreground=COLORS["primary"], font=("Segoe UI", 9, "bold"))
        self.style.configure("PanelAltSuccess.TLabel", background=panel_alt, foreground=COLORS["success"], font=("Segoe UI", 9, "bold"))
        self.style.configure("PanelAltWarning.TLabel", background=panel_alt, foreground=COLORS["warning"], font=("Segoe UI", 9, "bold"))
        self.style.configure("PanelAltError.TLabel", background=panel_alt, foreground=COLORS["danger"], font=("Segoe UI", 9, "bold"))
        self.style.configure("Preview.TLabel", background=COLORS["cinema"], foreground="#FFFFFF")
        self.style.configure("Section.TLabelframe", background=bg, bordercolor=border)
        self.style.configure("Section.TLabelframe.Label", background=bg, foreground=text, font=("Segoe UI", 10, "bold"))
        self.style.configure("TEntry", fieldbackground=field, foreground=text, bordercolor=border, padding=6)
        self.style.configure("TCombobox", fieldbackground=field, foreground=text, bordercolor=border, padding=5)
        self.style.map("TCombobox", fieldbackground=[("readonly", field)], foreground=[("readonly", text)])
        self.style.configure("TSpinbox", fieldbackground=field, foreground=text, bordercolor=border, padding=5)
        self.style.configure("TButton", padding=(11, 7), background=panel_alt, foreground=text, bordercolor=border, focuscolor=COLORS["primary"], focusthickness=2)
        self.style.configure("TCheckbutton", background=bg, foreground=text, focuscolor=COLORS["primary"])
        self.style.map("TCheckbutton", background=[("active", bg)], foreground=[("disabled", muted2)])
        self.style.configure("ModeCard.TButton", padding=(12, 10), anchor="w", justify="left", background=panel_alt, foreground=text, bordercolor=border)
        self.style.configure("Selected.ModeCard.TButton", padding=(12, 10), anchor="w", justify="left", background="#E9F2FF" if not dark else "#173457", foreground=COLORS["primary"], bordercolor=COLORS["primary"])
        self.style.map("TButton", background=[("active", border)])
        self.style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(16, 9), background=COLORS["primary"], foreground="#FFFFFF", bordercolor=COLORS["primary"])
        self.style.map("Primary.TButton", background=[("active", COLORS["primary_hover"]), ("pressed", COLORS["primary_pressed"])], foreground=[("disabled", muted2)])
        self.style.configure("Danger.TButton", padding=(13, 8), background=panel, foreground=COLORS["danger"], bordercolor=border)
        self.style.map("Danger.TButton", background=[("active", COLORS["danger_hover"])], foreground=[("active", "#FFFFFF")])
        self.style.configure("Ghost.TButton", padding=(10, 7), background=panel, foreground=text, bordercolor=border)
        self.style.configure("Selected.Ghost.TButton", padding=(10, 7), background="#E9F2FF" if not dark else "#173457", foreground=COLORS["primary"], bordercolor=COLORS["primary"])
        self.style.configure("Effect.TButton", padding=4, background=panel, foreground=text, bordercolor=border)
        self.style.configure("TNotebook", background=bg, bordercolor=border, tabmargins=(0, 4, 0, 0))
        self.style.configure("TNotebook.Tab", background=bg, foreground=muted, padding=(14, 8), font=("Segoe UI", 10))
        self.style.map("TNotebook.Tab", background=[("selected", panel)], foreground=[("selected", COLORS["primary"])])
        self.style.configure("Treeview", background=panel, fieldbackground=panel, foreground=text, rowheight=30, bordercolor=border)
        self.style.map("Treeview", background=[("selected", "#DDEBFF" if not dark else "#173457")], foreground=[("selected", text)])
        self.style.configure("Treeview.Heading", background=panel_alt, foreground=text, padding=7)
        self.style.configure("Studio.Horizontal.TProgressbar", background=COLORS["primary"], troughcolor=panel_alt, thickness=12)

        welcome_surface = "#EAF3FF" if not dark else "#12243A"
        self.style.configure("Welcome.TFrame", background=welcome_surface, relief="solid", borderwidth=1, bordercolor=COLORS["primary"])
        self.style.configure("WelcomeTitle.TLabel", background=welcome_surface, foreground=text, font=("Segoe UI", 11, "bold"))
        self.style.configure("WelcomeDetail.TLabel", background=welcome_surface, foreground=muted, font=("Segoe UI", 9))

        # Phase 7 global feedback surfaces.  Colour supports meaning but never
        # carries it alone: badge/title text remains explicit in every state.
        feedback_surfaces = {
            "Info": ("#EAF3FF", "#173457") if not dark else ("#12243A", "#DCEBFF"),
            "Busy": ("#EAF3FF", COLORS["primary"]) if not dark else ("#132A45", "#79B8FF"),
            "Success": ("#EAF8F2", COLORS["success"]) if not dark else ("#102A22", "#5AD6AC"),
            "Warning": ("#FFF6E2", COLORS["warning"]) if not dark else ("#33270F", "#F4BF59"),
            "Error": ("#FDECEC", COLORS["danger"]) if not dark else ("#351719", "#FF827A"),
        }
        for key, (surface, accent_color) in feedback_surfaces.items():
            self.style.configure(f"Feedback{key}.TFrame", background=surface, relief="solid", borderwidth=1, bordercolor=accent_color)
            self.style.configure(f"Feedback{key}Badge.TLabel", background=surface, foreground=accent_color, font=("Segoe UI", 8, "bold"))
            self.style.configure(f"Feedback{key}Title.TLabel", background=surface, foreground=text, font=("Segoe UI", 10, "bold"))
            self.style.configure(f"Feedback{key}Detail.TLabel", background=surface, foreground=muted, font=("Segoe UI", 9))

    def _apply_theme(self) -> None:
        dark = bool(self.dark_mode.get())
        try:
            self.style.theme_use("clam")
        except Exception:
            pass
        self._configure_shell_styles(dark)
        canvas_color = COLORS["dark_bg"] if dark else COLORS["light_bg"]
        for tab in self._scrollable_tabs:
            tab.canvas.configure(background=canvas_color)
        if hasattr(self, "feedback_frame"):
            self._refresh_feedback_view()
        refresh_activity_center(self)
        refresh_quick_guide_theme(self)
        self._save_ui_state()
        # Theme configuration resets notebook metrics; re-apply density once.
        self._layout_compact = None
        if self._layout_after is not None:
            self._cancel_after(self._layout_after)
        self._layout_after = self._schedule(0, self._apply_responsive_layout)

    # ------------------------------------------------------------------
    # Phase 7 — global feedback / activity semantics
    # ------------------------------------------------------------------
    def _status_feedback_changed(self, *_args) -> None:
        """Mirror legacy ``status.set`` calls into the new global strip.

        The render pipeline and older UI code still write to ``self.status``.
        Instead of forcing a risky bulk rewrite, direct status updates are
        treated as informational (or as the current busy-stage detail).
        Explicit success/warning/error states use ``_set_feedback`` below.
        """
        if self._feedback_status_guard:
            return
        detail = self.status.get().strip()
        self.feedback_detail.set(detail)
        if self._busy:
            self.feedback_severity.set("busy")
            self.feedback_title.set(self.stage.get().strip() or "Processando")
        else:
            self.feedback_severity.set("info")
            self.feedback_title.set("Estado atualizado")
            self._feedback_primary_callback = None
            self._feedback_secondary_callback = None
            self.feedback_primary_action.set("")
            self.feedback_secondary_action.set("")
        meta = severity_meta(self.feedback_severity.get())
        self.feedback_badge.set(meta["badge"])
        if hasattr(self, "feedback_frame"):
            self._refresh_feedback_view()

    def _set_feedback(
        self,
        severity: str,
        title: str,
        detail: str,
        *,
        category: str = "Sistema",
        primary: tuple[str, object] | None = None,
        secondary: tuple[str, object] | None = None,
        technical_detail: str = "",
        record: bool = True,
        sync_status: bool = True,
    ) -> None:
        # Some persistence tests intentionally construct a lightweight Studio
        # via ``__new__``. Keep the state layer optional in that scenario so
        # queue compatibility remains testable without a Tk interpreter.
        if not hasattr(self, "feedback_severity"):
            if sync_status and hasattr(self, "status"):
                summary = f"{str(title).strip()}: {str(detail).strip()}" if title else str(detail).strip()
                self.status.set(summary)
            return
        severity = severity if severity in {"info", "busy", "success", "warning", "error"} else "info"
        meta = severity_meta(severity)
        self.feedback_severity.set(severity)
        self.feedback_badge.set(meta["badge"])
        self.feedback_title.set(str(title).strip())
        self.feedback_detail.set(str(detail).strip())
        self._feedback_primary_callback = primary[1] if primary else None
        self._feedback_secondary_callback = secondary[1] if secondary else None
        self.feedback_primary_action.set(primary[0] if primary else "")
        self.feedback_secondary_action.set(secondary[0] if secondary else "")
        if sync_status:
            self._feedback_status_guard = True
            try:
                self.status.set(str(detail).strip())
            finally:
                self._feedback_status_guard = False
        if record:
            added = self._feedback_history.add(
                FeedbackEntry(
                    severity=severity,
                    title=str(title).strip(),
                    detail=str(detail).strip(),
                    category=category,
                    technical_detail=str(technical_detail or "").strip(),
                )
            )
            if added:
                self.feedback_history_count.set(len(self._feedback_history))
        if hasattr(self, "feedback_frame"):
            self._refresh_feedback_view()
        if record and added:
            refresh_activity_center(self)

    def _refresh_feedback_view(self) -> None:
        if not hasattr(self, "feedback_frame"):
            return
        refresh_feedback_strip(self, severity_meta(self.feedback_severity.get())["style"])

    def _run_feedback_primary(self) -> None:
        callback = self._feedback_primary_callback
        if callable(callback):
            callback()

    def _run_feedback_secondary(self) -> None:
        callback = self._feedback_secondary_callback
        if callable(callback):
            callback()

    def _show_activity_center(self) -> None:
        show_activity_center(self)

    def _open_tab(self, index: int) -> None:
        try:
            self.notebook.select(index)
        except Exception:
            pass

    def _open_external_path(self, value: str | Path) -> None:
        path = Path(value)
        try:
            if os.name == "nt" and hasattr(os, "startfile"):
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            self._set_feedback(
                "warning", "O arquivo foi criado, mas não abriu automaticamente",
                f"Use o Explorador de Arquivos para abrir: {path}",
                category="Sistema", technical_detail=str(exc),
            )

    def _failure_action(self, label: str):
        actions = {
            "Rever projeto": lambda: self._open_tab(1),
            "Rever destino": lambda: self._open_tab(1),
            "Rever qualidade": lambda: self._open_tab(2),
            "Abrir IA local": lambda: self._open_tab(5),
            "Abrir fila": lambda: self._open_tab(4),
            "Ver log": self._show_log,
        }
        return actions.get(label, lambda: None)

    def _announce_failure(self, raw_error: str, *, category: str = "Render") -> None:
        summary = classify_failure(raw_error)
        self._set_feedback(
            "error",
            summary.title,
            summary.detail,
            category=category,
            primary=(summary.primary_action, self._failure_action(summary.primary_action)),
            secondary=(summary.secondary_action, self._failure_action(summary.secondary_action)),
            technical_detail=raw_error,
        )

    def _processor_changed(self) -> None:
        if self.use_cpu.get() and self.enhancement.get() == ENHANCE_AI and self._ai_upscale_required(self._settings()):
            self.enhancement.set(ENHANCE_SIMPLE)
            self.status.set("Modo CPU ativado: melhoria alterada para Lanczos porque este destino realmente exige Real-ESRGAN.")
        self._update_summary()

    def _enhancement_changed(self) -> None:
        if self.use_cpu.get() and self.enhancement.get() == ENHANCE_AI and self._ai_upscale_required(self._settings()):
            self.use_cpu.set(False)
            self.status.set("Real-ESRGAN necessário para este destino: Aceleração automática reativada; a GPU será usada apenas nas etapas compatíveis.")
        self._update_summary()

    def _ensure_available_features(self) -> None:
        missing: list[str] = []
        if (
            self.enhancement.get() == ENHANCE_AI
            and not REAL_ESRGAN.is_file()
            and self._ai_upscale_required(self._settings())
        ):
            self.enhancement.set(ENHANCE_SIMPLE)
            missing.append("Real-ESRGAN")
        if self.interpolation.get() == RIFE_OPTION and not RIFE_EXE.is_file():
            self.interpolation.set("Movimento suave — FFmpeg")
            missing.append("RIFE")
        demucs_ready = ai_suite.VENV_PYTHON.is_file() and (
            ai_suite.MODELS / "demucs" / "local_repo" / "htdemucs_ft.yaml"
        ).is_file()
        if self.use_stems.get() and not demucs_ready:
            self.use_stems.set(False)
            missing.append("Demucs")
        if missing:
            self.status.set(
                "Preset adaptado porque faltam componentes: " + ", ".join(missing) + ". Use ‘Instalar componentes’."
            )
        self._update_summary()

    def _visual_scale_changed(self, _value=None) -> None:
        self.intensity_text.set(f"{self.intensity.get():.0f}%")
        self.occupancy_text.set(f"{self.occupancy.get():.0f}%")
        self.smoothing_text.set(f"{self.reaction_smoothing.get():.0f}%")
        self.expression_text.set(f"{self.reaction_expression.get():.0f}%")
        self.section_dynamics_text.set(f"{self.section_dynamics.get():.0f}%")
        self._update_summary()

    @staticmethod
    def _prune_previews(max_files: int = 20) -> None:
        try:
            previews = sorted(PREVIEW_DIR.glob("*.mp4"), key=lambda path: path.stat().st_mtime, reverse=True)
            for old in previews[max_files:]:
                old.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _prune_work(root: Path = WORK_DIR) -> None:
        cutoff = time.time() - 24 * 60 * 60
        try:
            for directory in root.glob("job_*"):
                if directory.is_dir() and directory.stat().st_mtime < cutoff:
                    shutil.rmtree(directory, ignore_errors=True)
        except OSError:
            pass

    @staticmethod
    def _load_custom_presets() -> dict[str, dict]:
        if not PRESETS_FILE.is_file():
            return {}
        try:
            data, migrated = load_presets_state(PRESETS_FILE)
            if migrated:
                save_presets_state(PRESETS_FILE, data)
            return data
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def _save_custom_presets(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        save_presets_state(PRESETS_FILE, self._custom_presets)

    @staticmethod
    def _settings_from_dict(data: dict) -> RenderSettings:
        defaults = {
            "audio_mode": "Preservar dinâmica original",
            "interpolation": "Movimento suave — FFmpeg",
            "cpu_threads": max(1, min(8, os.cpu_count() or 4)),
            "minimum_free_gb": 20.0,
            "scratch_dir": str(WORK_DIR),
            "cache_quota_gb": 50.0,
            "quality_check": True,
            "deep_verify": False,
            "visual_direction": "Personalizada",
            "comparison_preview": True,
            "use_stems": False,
            "delivery_profile": PROFILE_AUTO,
        }
        accepted = {field.name for field in fields(RenderSettings)}
        clean = {key: value for key, value in {**defaults, **data}.items() if key in accepted}
        clean["effects"] = set(clean.get("effects", []))
        return RenderSettings(**clean)

    def _save_queue(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        payload = []
        for item in self._queue_items:
            settings = asdict(item["settings"])
            settings["effects"] = sorted(settings["effects"])
            payload.append({
                "id": item["id"],
                "settings": settings,
                "status": item["status"],
                "error": item.get("error", ""),
                "report": item.get("report", ""),
                "history": item.get("history", ""),
                "progress": round(queue_item_progress(item), 1),
                "stage": item.get("stage", ""),
            })
        save_queue_state(QUEUE_FILE, payload)

    def _load_queue(self) -> None:
        if not QUEUE_FILE.is_file():
            return
        try:
            payload, migrated = load_queue_state(QUEUE_FILE)
            restored = []
            recovered_active = 0
            for saved in payload:
                settings = self._settings_from_dict(saved["settings"])
                status = saved.get("status", "Aguardando")
                progress = float(saved.get("progress", 0.0) or 0.0)
                stage = str(saved.get("stage", "") or "")
                if status == "Renderizando":
                    recovered_active += 1
                    status = "Aguardando"
                    progress = 0.0
                    stage = "Recuperado após encerramento"
                    saved["error"] = "Recuperado após encerramento; o item será reiniciado com segurança."
                restored.append({
                    "id": int(saved["id"]), "settings": settings, "status": queue_normalize_status(status),
                    "error": saved.get("error", ""), "report": saved.get("report", ""),
                    "history": saved.get("history", ""), "progress": progress, "stage": stage,
                })
            self._queue_items = restored
            self._queue_serial = max((item["id"] for item in restored), default=0)
            self._refresh_queue_tree()
            if migrated:
                self._save_queue()
            if restored:
                if recovered_active:
                    self._set_feedback(
                        "warning", "Fila restaurada após encerramento",
                        f"{len(restored)} projeto(s) restaurados; {recovered_active} item(ns) que estavam renderizando voltaram para Aguardando em 0%.",
                        category="Recuperação", primary=("Abrir fila", lambda: self._open_tab(4)),
                    )
                else:
                    self._set_feedback(
                        "info", "Fila restaurada", f"{len(restored)} projeto(s) recuperados da sessão anterior.",
                        category="Fila", primary=("Abrir fila", lambda: self._open_tab(4)), record=False,
                    )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self._log(f"Não foi possível restaurar a fila: {exc}")
            self._set_feedback(
                "warning", "Fila salva não pôde ser restaurada",
                "O editor continua disponível, mas a lista persistida precisa de revisão antes de ser reutilizada.",
                category="Recuperação", secondary=("Ver log", self._show_log), technical_detail=str(exc),
            )

    def _capture_preset(self) -> dict:
        return {
            "mode": self.mode.get(),
            "resolution": self.resolution.get(),
            "fps": int(self.fps.get()),
            "aspect": self.aspect.get(),
            "enhancement": self.enhancement.get(),
            "fit_mode": self.fit_mode.get(),
            "use_cpu": self.use_cpu.get(),
            "preserve_audio": self.preserve_audio.get(),
            "effects": sorted(self._selected_effects()),
            "color": self.color.get(),
            "intensity": round(self.intensity.get()),
            "occupancy": round(self.occupancy.get()),
            "transition": self.transition.get(),
            "transition_duration": float(self.transition_duration.get()),
            "audio_focus": self.audio_focus.get(),
            "reaction_smoothing": round(self.reaction_smoothing.get()),
            "reaction_expression": round(self.reaction_expression.get()),
            "auto_loop": self.auto_loop.get(),
            "dynamic_sections": self.dynamic_sections.get(),
            "section_dynamics": round(self.section_dynamics.get()),
            "audio_mode": self.audio_mode.get(),
            "interpolation": self.interpolation.get(),
            "cpu_threads": int(self.cpu_threads.get()),
            "minimum_free_gb": float(self.minimum_free_gb.get()),
            "scratch_dir": self.scratch_dir.get().strip(),
            "cache_quota_gb": float(self.cache_quota_gb.get()),
            "quality_check": self.quality_check.get(),
            "deep_verify": self.deep_verify.get(),
            "visual_direction": self.visual_direction.get(),
            "comparison_preview": self.comparison_preview.get(),
            "use_stems": self.use_stems.get(),
            "delivery_profile": self.delivery_profile.get(),
        }

    def _apply_selected_preset(self) -> None:
        data = self._presets.get(self.preset_name.get())
        if not data:
            return
        mapping = (
            (self.mode, "mode"),
            (self.resolution, "resolution"),
            (self.fps, "fps"),
            (self.aspect, "aspect"),
            (self.enhancement, "enhancement"),
            (self.fit_mode, "fit_mode"),
            (self.use_cpu, "use_cpu"),
            (self.preserve_audio, "preserve_audio"),
            (self.color, "color"),
            (self.intensity, "intensity"),
            (self.occupancy, "occupancy"),
            (self.transition, "transition"),
            (self.transition_duration, "transition_duration"),
            (self.audio_focus, "audio_focus"),
            (self.reaction_smoothing, "reaction_smoothing"),
            (self.reaction_expression, "reaction_expression"),
            (self.auto_loop, "auto_loop"),
            (self.dynamic_sections, "dynamic_sections"),
            (self.section_dynamics, "section_dynamics"),
            (self.audio_mode, "audio_mode"),
            (self.interpolation, "interpolation"),
            (self.cpu_threads, "cpu_threads"),
            (self.minimum_free_gb, "minimum_free_gb"),
            (self.scratch_dir, "scratch_dir"),
            (self.cache_quota_gb, "cache_quota_gb"),
            (self.quality_check, "quality_check"),
            (self.deep_verify, "deep_verify"),
            (self.visual_direction, "visual_direction"),
            (self.comparison_preview, "comparison_preview"),
            (self.use_stems, "use_stems"),
            (self.delivery_profile, "delivery_profile"),
        )
        for variable, key in mapping:
            if key in data:
                variable.set(data[key])
        selected = set(data.get("effects", []))
        for name, variable in self.effect_vars.items():
            variable.set(name in selected)
        selected_name = self.preset_name.get()
        self.color_swatch.configure(background=self.color.get())
        self._visual_scale_changed()
        self._update_mode()
        self._ensure_available_features()
        self._active_preset_name = selected_name
        self._applied_preset_snapshot = self._capture_preset()
        self._refresh_preset_state()
        self.status.set(f"Preset aplicado: {selected_name}")

    def _preset_selection_changed(self, _event=None) -> None:
        self._refresh_preset_state()
        selected = self.preset_name.get().strip()
        if selected and selected != self._active_preset_name:
            self.status.set(f"Preset selecionado: {selected}. Clique em Aplicar para alterar o projeto.")

    def _refresh_preset_state(self) -> None:
        selected = self.preset_name.get().strip()
        active = self._active_preset_name.strip()
        if not active:
            self.preset_state_text.set("Nenhum preset aplicado nesta sessão.")
            return
        if selected != active:
            self.preset_state_text.set(f"Selecionado: {selected} • ainda não aplicado  |  Ativo: {active}")
            return
        if self._applied_preset_snapshot is not None and self._capture_preset() != self._applied_preset_snapshot:
            self.preset_state_text.set(f"Ativo: {active} • ajustes manuais")
        else:
            self.preset_state_text.set(f"Ativo: {active}")

    def _save_new_preset(self) -> None:
        name = simpledialog.askstring(APP_TITLE, "Nome do novo preset:", parent=self.root)
        if not name or not name.strip():
            return
        name = name.strip()
        if name in BUILTIN_PRESETS:
            messagebox.showwarning(APP_TITLE, "Esse nome pertence a um preset interno e não pode ser substituído.")
            return
        if name in self._custom_presets and not messagebox.askyesno(APP_TITLE, "Esse preset já existe. Deseja atualizá-lo?"):
            return
        self._custom_presets[name] = self._capture_preset()
        self._save_custom_presets()
        self._presets = {**BUILTIN_PRESETS, **self._custom_presets}
        self.preset_box.configure(values=tuple(self._presets))
        self.preset_name.set(name)
        self._active_preset_name = name
        self._applied_preset_snapshot = self._capture_preset()
        self._refresh_preset_state()
        self.status.set(f"Preset salvo e ativo: {name}")

    def _delete_preset(self) -> None:
        name = self.preset_name.get()
        if name in BUILTIN_PRESETS:
            messagebox.showinfo(APP_TITLE, "Os presets internos são protegidos. Crie uma variação com outro nome.")
            return
        if name not in self._custom_presets:
            return
        if not messagebox.askyesno(APP_TITLE, f"Excluir o preset ‘{name}’?"):
            return
        del self._custom_presets[name]
        if self._active_preset_name == name:
            self._active_preset_name = ""
            self._applied_preset_snapshot = None
        self._save_custom_presets()
        self._presets = {**BUILTIN_PRESETS, **self._custom_presets}
        self.preset_box.configure(values=tuple(self._presets))
        self.preset_name.set(next(iter(BUILTIN_PRESETS)))
        self._refresh_preset_state()
        self.status.set("Preset personalizado excluído. Escolha e aplique outro preset quando quiser.")

    def _clear_ai_cache(self) -> None:
        if self._busy:
            messagebox.showinfo(APP_TITLE, "Aguarde o processamento atual terminar antes de limpar o cache.")
            return
        files = [path for path in CACHE_DIR.glob("*") if path.is_file()]
        total = sum(path.stat().st_size for path in files)
        if not files:
            messagebox.showinfo(APP_TITLE, "O cache da IA está vazio.")
            return
        if not messagebox.askyesno(
            APP_TITLE,
            f"Remover {len(files)} arquivo(s) do cache ({total / (1024**3):.2f} GB)?",
        ):
            return
        for path in files:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        self.status.set("Cache da IA limpo.")

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=(24, 18, 24, 16))
        outer.pack(fill="both", expand=True)
        self.outer = outer

        header = ttk.Frame(outer)
        header.pack(fill="x")
        title_block = ttk.Frame(header)
        title_block.pack(side="left", fill="x", expand=True)
        ttk.Label(title_block, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        self.header_subtitle_label = ttk.Label(
            title_block,
            text="Upscale, interpolação, loops musicais, transições e VFX dinâmicos com processamento local.",
            style="Subtitle.TLabel",
            wraplength=980,
            justify="left",
        )
        self.header_subtitle_label.pack(anchor="w", pady=(1, 0))
        header_tools = ttk.Frame(header)
        header_tools.pack(side="right", padx=(16, 0), anchor="n")
        ttk.Label(header_tools, text=f"v{__version__}", style="Muted.TLabel").pack(side="left", padx=(0, 8), pady=(7, 0))
        self.header_update_button = ttk.Button(
            header_tools, text="", style="Primary.TButton", command=self._apply_available_update,
        )
        self.header_help_button = ttk.Button(header_tools, text="Ajuda  F1", command=self._show_quick_guide)
        self.header_help_button.pack(side="left")
        ttk.Checkbutton(
            header_tools,
            text="Modo escuro",
            variable=self.dark_mode,
            command=self._apply_theme,
        ).pack(side="left", padx=(10, 0), pady=(5, 0))

        preset_area = ttk.Frame(outer)
        preset_area.pack(fill="x", pady=(14, 12))
        preset_left = ttk.Frame(preset_area)
        preset_left.pack(side="left", fill="x", expand=True)
        ttk.Label(preset_left, text="Preset", style="Muted.TLabel").pack(anchor="w", pady=(0, 3))
        self.preset_box = ttk.Combobox(
            preset_left,
            textvariable=self.preset_name,
            values=tuple(self._presets),
            state="readonly",
        )
        self.preset_box.pack(fill="x")
        self.preset_box.bind("<<ComboboxSelected>>", self._preset_selection_changed)
        ttk.Label(preset_left, textvariable=self.preset_state_text, style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
        preset_actions = ttk.Frame(preset_area)
        preset_actions.pack(side="right", padx=(10, 0), pady=(18, 0))
        ttk.Button(preset_actions, text="Aplicar", style="Primary.TButton", command=self._apply_selected_preset).pack(side="left")
        ttk.Button(preset_actions, text="Salvar como novo…", command=self._save_new_preset).pack(side="left", padx=(8, 0))
        ttk.Button(preset_actions, text="Excluir", style="Danger.TButton", command=self._delete_preset).pack(side="left", padx=(8, 0))

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True)
        home_tab = ScrollableTab(self.notebook)
        project = ScrollableTab(self.notebook)
        output = ScrollableTab(self.notebook)
        visual = ScrollableTab(self.notebook)
        queue_tab = ScrollableTab(self.notebook)
        ai_tab = ScrollableTab(self.notebook)
        self._scrollable_tabs = [home_tab, project, output, visual, queue_tab, ai_tab]
        canvas_bg = COLORS["dark_bg"] if self.dark_mode.get() else COLORS["light_bg"]
        for tab in self._scrollable_tabs:
            tab.canvas.configure(background=canvas_bg)
        self.notebook.add(home_tab, text="Início")
        self.notebook.add(project, text="Projeto")
        self.notebook.add(output, text="Qualidade e saída")
        self.notebook.add(visual, text="Visual e transições")
        self.notebook.add(queue_tab, text="Fila")
        self.notebook.add(ai_tab, text="IA local")
        self._build_home_tab(home_tab.content)
        self._build_project_tab(project.content)
        self._build_output_tab(output.content)
        self._build_visual_tab(visual.content)
        self._build_queue_tab(queue_tab.content)
        self._build_ai_tab(ai_tab.content)
        self.notebook.bind("<<NotebookTabChanged>>", self._notebook_changed)

        footer = ttk.Frame(outer, style="Card.TFrame", padding=(14, 10))
        self.footer = footer
        footer.pack(fill="x", pady=(12, 0))
        summary_row = ttk.Frame(footer, style="Card.TFrame")
        summary_row.pack(fill="x")
        summary_left = ttk.Frame(summary_row, style="Card.TFrame")
        self.footer_summary_left = summary_left
        summary_left.pack(side="left", fill="x", expand=True)
        ttk.Label(summary_left, text="Resumo da configuração atual", style="CardTitle.TLabel").pack(anchor="w")
        self.footer_summary_label = ttk.Label(summary_left, textvariable=self.summary, wraplength=980, style="CardMuted.TLabel", justify="left")
        self.footer_summary_label.pack(anchor="w", pady=(2, 0))
        action_row = ttk.Frame(summary_row, style="Card.TFrame")
        self.footer_action_row = action_row
        action_row.pack(side="right", padx=(16, 0))
        self.preview_button = ttk.Button(action_row, text="Gerar preview", command=lambda: self._start(True))
        self.preview_button.pack(side="left")
        self.render_button = ttk.Button(action_row, text="Criar vídeo final", style="Primary.TButton", command=lambda: self._start(False))
        self.render_button.pack(side="left", padx=(8, 0))
        self.add_queue_compact_button = ttk.Button(action_row, text="Fila +", command=self._add_to_queue)
        self.add_queue_compact_button.pack(side="left", padx=(8, 0))
        self.add_queue_compact_button.pack_forget()
        self.cancel_button = ttk.Button(action_row, text="Cancelar", command=self._cancel, state="disabled")
        # Cancel is contextual: reserve no permanent width while idle.
        self.cancel_button.pack(side="left", padx=(8, 0))
        self.cancel_button.pack_forget()

        self.bar = ttk.Progressbar(footer, maximum=100, style="Studio.Horizontal.TProgressbar")
        self.bar.pack(fill="x", pady=(9, 0))
        progress_row = ttk.Frame(footer, style="Card.TFrame")
        self.footer_progress_row = progress_row
        progress_row.pack(fill="x", pady=(4, 0))
        ttk.Label(progress_row, textvariable=self.stage, style="Card.TLabel").pack(side="left")
        ttk.Label(progress_row, textvariable=self.progress_text, style="Card.TLabel", font=("Segoe UI", 9, "bold")).pack(side="right")
        self.footer_time_label = ttk.Label(footer, textvariable=self.time_text, style="CardMuted.TLabel")
        self.footer_time_label.pack(anchor="w", pady=(2, 0))
        build_feedback_strip(self, footer)
        self._refresh_feedback_view()

        utility_row = ttk.Frame(footer, style="Card.TFrame")
        self.footer_utility_row = utility_row
        utility_row.pack(fill="x", pady=(7, 0))
        self.log_button = ttk.Button(utility_row, text="Ver log", command=self._show_log)
        self.log_button.pack(side="left")
        ttk.Button(utility_row, text="Diagnóstico", command=self._create_diagnostics).pack(side="left", padx=(8, 0))
        self.add_queue_button = ttk.Button(utility_row, text="Adicionar à fila", command=self._add_to_queue)
        self.add_queue_button.pack(side="left", padx=(8, 0))

    def _build_home_tab(self, parent) -> None:
        parent.columnconfigure(0, weight=4)
        parent.columnconfigure(1, weight=7)
        parent.rowconfigure(1, weight=1)

        build_welcome_card(self, parent)

        left = ttk.Frame(parent)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 7))
        right = ttk.Frame(parent)
        right.grid(row=1, column=1, sticky="nsew", padx=(7, 0))
        right.columnconfigure(0, weight=1)
        register_responsive_split(self, "home", parent, left, right, weights=(4, 7), min_sizes=(0, 0), base_row=1)

        quick = ttk.Frame(left, style="Card.TFrame", padding=14)
        quick.pack(fill="x")
        ttk.Label(quick, text="Comece rápido", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(quick, text="Escolha um nível e refine depois. Nada é renderizado até você confirmar.", style="CardMuted.TLabel").pack(anchor="w", pady=(2, 9))
        profile_rows = (
            ("Rápido", "1080p/60 • Lanczos • preview e máquinas mais simples"),
            ("Recomendado", "4K/60 • Real-ESRGAN • melhor equilíbrio para este computador"),
            ("Máximo", "8K/120 • Real-ESRGAN + RIFE • qualidade máxima e render longo"),
        )
        for label, description in profile_rows:
            row = ttk.Frame(quick, style="PanelAlt.TFrame", padding=(10, 8))
            row.pack(fill="x", pady=4)
            text = f"★  {label}" if label == "Recomendado" else label
            style = "Primary.TButton" if label == "Recomendado" else "Ghost.TButton"
            ttk.Button(row, text=text, width=16, style=style, command=lambda value=label: self._apply_quality_level(value)).pack(side="left")
            copy = ttk.Frame(row, style="PanelAlt.TFrame")
            copy.pack(side="left", fill="x", expand=True, padx=(10, 0))
            ttk.Label(copy, text=label, style="PanelAlt.TLabel", font=("Segoe UI", 10, "bold")).pack(anchor="w")
            ttk.Label(copy, text=description, style="PanelAlt.TLabel", foreground=COLORS["light_muted"], wraplength=360).pack(anchor="w")

        project = ttk.Frame(left, style="Card.TFrame", padding=14)
        project.pack(fill="x", pady=(12, 0))
        ttk.Label(project, text="Projeto atual", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(project, text="Troque os arquivos aqui sem sair da tela inicial.", style="CardMuted.TLabel").grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 8))
        project.columnconfigure(1, weight=1)

        ttk.Label(project, text="Vídeo", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 8))
        self.home_video_entry = ttk.Entry(project, textvariable=self.video)
        self.home_video_entry.grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Button(project, text="…", width=3, command=self._choose_video).grid(row=2, column=2, padx=(6, 0), pady=4)

        ttk.Label(project, text="Música", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=4, padx=(0, 8))
        self.home_audio_entry = ttk.Entry(project, textvariable=self.audio)
        self.home_audio_entry.grid(row=3, column=1, sticky="ew", pady=4)
        self.home_audio_button = ttk.Button(project, text="…", width=3, command=self._choose_audio)
        self.home_audio_button.grid(row=3, column=2, padx=(6, 0), pady=4)

        ttk.Label(project, text="Salvar como", style="Card.TLabel").grid(row=4, column=0, sticky="w", pady=4, padx=(0, 8))
        ttk.Entry(project, textvariable=self.output).grid(row=4, column=1, sticky="ew", pady=4)
        ttk.Button(project, text="…", width=3, command=self._choose_output).grid(row=4, column=2, padx=(6, 0), pady=4)

        hardware = ttk.Frame(left, style="Card.TFrame", padding=14)
        hardware.pack(fill="x", pady=(12, 0))
        gpu_text = self._hardware.gpu or "Nenhuma GPU NVIDIA detectada"
        vram_text = f"{self._hardware.vram_mb / 1024:.1f} GB de VRAM" if self._hardware.vram_mb else "VRAM não detectada"
        title_row = ttk.Frame(hardware, style="Card.TFrame")
        title_row.pack(fill="x")
        ttk.Label(title_row, text="Este computador", style="CardTitle.TLabel").pack(side="left")
        ttk.Label(title_row, text="● Pronto" if FFMPEG else "● Atenção", style="Card.TLabel", foreground=COLORS["success"] if FFMPEG else COLORS["warning"]).pack(side="right")
        ttk.Label(hardware, text=f"GPU  •  {gpu_text}  •  {vram_text}", style="Card.TLabel", wraplength=430).pack(anchor="w", pady=(9, 0))
        ttk.Label(hardware, text=f"CPU  •  {self._hardware.cpu_threads} threads  •  perfil sugerido: {self._hardware.quality_tier}", style="CardMuted.TLabel").pack(anchor="w", pady=(4, 0))
        ttk.Label(hardware, text=f"FFmpeg {'pronto' if FFMPEG else 'não encontrado'}  •  NVIDIA {'pronta' if self._nvenc else 'fallback por CPU'}", style="CardMuted.TLabel").pack(anchor="w", pady=(4, 0))
        util = ttk.Frame(hardware, style="Card.TFrame")
        util.pack(fill="x", pady=(10, 0))
        ttk.Button(util, text="Diagnóstico", command=self._create_diagnostics).pack(side="left")
        self.update_button = ttk.Button(util, text="Atualizações", command=self._check_updates)
        self.update_button.pack(side="left", padx=(6, 0))
        ttk.Button(util, text="Componentes", command=self._install_components).pack(side="left", padx=(6, 0))

        preview_card = ttk.Frame(right, style="Card.TFrame", padding=14)
        preview_card.grid(row=0, column=0, sticky="ew")
        preview_header = ttk.Frame(preview_card, style="Card.TFrame")
        preview_header.pack(fill="x")
        header_copy = ttk.Frame(preview_header, style="Card.TFrame")
        header_copy.pack(side="left", fill="x", expand=True)
        ttk.Label(header_copy, text="Como isso vai ficar", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(header_copy, text="Exemplo visual imediato usando o mesmo motor de VFX do render final.", style="CardMuted.TLabel").pack(anchor="w", pady=(2, 0))
        mode_actions = ttk.Frame(preview_header, style="Card.TFrame")
        mode_actions.pack(side="right")
        self._home_preview_mode_buttons: dict[str, ttk.Button] = {}
        for mode in ("Original", "A/B", "Resultado"):
            button = ttk.Button(mode_actions, text=mode, style="Selected.Ghost.TButton" if mode == "Resultado" else "Ghost.TButton", command=lambda value=mode: self._set_home_preview_mode(value))
            button.pack(side="left", padx=(5, 0))
            self._home_preview_mode_buttons[mode] = button

        preview_surface = ttk.Frame(preview_card, style="PanelAlt.TFrame", padding=4)
        preview_surface.pack(fill="both", expand=True, pady=(10, 0))
        self.home_preview_label = ttk.Label(preview_surface, style="Preview.TLabel", anchor="center")
        self.home_preview_label.pack(fill="both", expand=True)
        preview_tools = ttk.Frame(preview_card, style="Card.TFrame")
        preview_tools.pack(fill="x", pady=(8, 0))
        self.home_preview_source_text = StringVar(value="Demonstração interna • selecione um vídeo para usar um frame real")
        ttk.Label(preview_tools, textvariable=self.home_preview_source_text, style="CardMuted.TLabel").pack(side="left")
        ttk.Button(preview_tools, text="Gerar preview real", command=lambda: self._start(True)).pack(side="right")

        effects = ttk.Frame(right, style="Card.TFrame", padding=14)
        effects.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        ttk.Label(effects, text="Exemplos visuais dos VFX", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(effects, text="Clique em um efeito para ativar ou desativar. As miniaturas vêm do motor VFX real.", style="CardMuted.TLabel").grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 9))
        self._home_effect_buttons: dict[str, ttk.Button] = {}
        for column in range(4):
            effects.columnconfigure(column, weight=1)
        effect_descriptions = {
            "Aurora": "Faixas fluidas",
            "Espectro": "Barras reativas",
            "Barras arredondadas": "Barras suaves",
            "Onda líquida": "Ondulações",
            "Círculo mágico": "Anel e glifos",
            "Partículas musicais": "Partículas",
            "Pulso cinematográfico": "Batidas e flashes",
            "Energia mágica": "Glow e raios",
        }
        for index, name in enumerate(EFFECT_NAMES):
            rgb = effect_thumbnail(name, self.color.get(), 160, 90)
            photo = PhotoImage(data=to_ppm_bytes(rgb), format="PPM")
            self._home_effect_photos[name] = photo
            active = self.effect_vars[name].get()
            text = f"✓ {name}\n{effect_descriptions[name]}" if active else f"{name}\n{effect_descriptions[name]}"
            button = ttk.Button(
                effects,
                text=text,
                image=photo,
                compound="top",
                style="Selected.Ghost.TButton" if active else "Effect.TButton",
                command=lambda effect=name: self._toggle_effect_from_home(effect),
            )
            button.grid(row=2 + index // 4, column=index % 4, sticky="ew", padx=4, pady=4)
            self._home_effect_buttons[name] = button

        transitions = ttk.Frame(right, style="Card.TFrame", padding=14)
        transitions.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ttk.Label(transitions, text="Transição do loop", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(transitions, text="Atalhos para as transições mais usadas; o editor completo fica em Visual e transições.", style="CardMuted.TLabel").pack(anchor="w", pady=(2, 8))
        trans_row = ttk.Frame(transitions, style="Card.TFrame")
        trans_row.pack(fill="x")
        self._home_transition_buttons: dict[str, ttk.Button] = {}
        for label, value in (("Corte seco", "Corte seco — original"), ("Dissolver", "Dissolver suave"), ("Fade cinema", "Fade cinematográfico")):
            selected = self.transition.get() == value
            button = ttk.Button(trans_row, text=("✓ " if selected else "") + label, style="Selected.Ghost.TButton" if selected else "Ghost.TButton", command=lambda selected_value=value: self._select_home_transition(selected_value))
            button.pack(side="left", fill="x", expand=True, padx=(0, 6))
            self._home_transition_buttons[value] = button
        ttk.Button(trans_row, text="Editar detalhes →", command=lambda: self.notebook.select(3)).pack(side="right")

        self._refresh_home_preview_sync()

    def _notebook_changed(self, _event=None) -> None:
        try:
            current = self.notebook.index(self.notebook.select())
        except Exception:
            return
        if current == 0:
            self._schedule_home_preview()
        elif current == 1:
            video = self.video.get().strip()
            if video and Path(video).is_file() and video != self._project_source_path:
                self._inspect_project_video(video)
            self._refresh_project_framing_sync()
            self._refresh_project_output_state()
        elif current == 2:
            video = self.video.get().strip()
            if video and Path(video).is_file() and self._project_video_probe_path != video:
                self._inspect_project_video(video)
            if self.mode.get() == MODE_MUSIC:
                audio = self.audio.get().strip()
                if audio and Path(audio).is_file() and self._project_audio_probe_path != audio:
                    self._inspect_project_audio(audio)
            self._refresh_quality_controls()
            self._refresh_quality_impact()
        elif current == 3:
            self._schedule_visual_preview()

    def _set_home_preview_mode(self, mode: str) -> None:
        self.home_preview_mode.set(mode)
        for name, button in getattr(self, "_home_preview_mode_buttons", {}).items():
            button.configure(style="Selected.Ghost.TButton" if name == mode else "Ghost.TButton")
        self._schedule_home_preview()

    def _toggle_effect_from_home(self, effect: str) -> None:
        variable = self.effect_vars[effect]
        variable.set(not variable.get())
        self._update_summary()

    def _select_home_transition(self, value: str) -> None:
        self.transition.set(value)
        self._update_summary()
        for key, button in getattr(self, "_home_transition_buttons", {}).items():
            label = {
                "Corte seco — original": "Corte seco",
                "Dissolver suave": "Dissolver",
                "Fade cinematográfico": "Fade cinema",
            }.get(key, key)
            selected = key == value
            button.configure(text=("✓ " if selected else "") + label, style="Selected.Ghost.TButton" if selected else "Ghost.TButton")

    def _refresh_home_effect_button_states(self) -> None:
        descriptions = {
            "Aurora": "Faixas fluidas",
            "Espectro": "Barras reativas",
            "Barras arredondadas": "Barras suaves",
            "Onda líquida": "Ondulações",
            "Círculo mágico": "Anel e glifos",
            "Partículas musicais": "Partículas",
            "Pulso cinematográfico": "Batidas e flashes",
            "Energia mágica": "Glow e raios",
        }
        for name, button in getattr(self, "_home_effect_buttons", {}).items():
            active = self.effect_vars[name].get()
            button.configure(
                text=("✓ " if active else "") + name + "\n" + descriptions[name],
                style="Selected.Ghost.TButton" if active else "Effect.TButton",
            )

    def _schedule_home_preview(self, *, source_changed: bool = False) -> None:
        if not hasattr(self, "home_preview_label"):
            return
        if source_changed:
            self._home_preview_source = None
            self._home_preview_source_path = ""
        if self._home_preview_after is not None:
            self._cancel_after(self._home_preview_after)
        self._home_preview_after = self._schedule(160, self._request_home_preview)

    def _preview_composite_for_mode(self, base: np.ndarray, result: np.ndarray, mode: str) -> np.ndarray:
        if mode == "Original":
            return base.copy()
        if mode == "A/B":
            out = base.copy()
            split = out.shape[1] // 2
            out[:, split:] = result[:, split:]
            out[:, max(0, split - 1) : min(out.shape[1], split + 2)] = np.asarray((235, 240, 248), dtype=np.uint8)
            return out
        return result

    def _request_home_preview(self) -> None:
        self._home_preview_after = None
        self._home_preview_serial += 1
        serial = self._home_preview_serial
        path = self.video.get().strip()
        effects = self._selected_effects()
        color = self.color.get()
        intensity = max(0.05, min(2.0, float(self.intensity.get()) / 100.0))
        occupancy = max(0.10, min(1.0, float(self.occupancy.get()) / 100.0))
        mode = self.home_preview_mode.get()
        cached = self._home_preview_source.copy() if self._home_preview_source is not None and self._home_preview_source_path == path else None

        self._refresh_home_effect_button_states()
        if path and cached is None:
            self.home_preview_source_text.set("Carregando um frame real do vídeo…")

        def worker() -> None:
            base = cached
            used_video = bool(base is not None)
            if base is None and path:
                base = extract_video_frame(FFMPEG, path, width=640, height=360, position=1.0)
                used_video = base is not None
            if base is None:
                from .ui.preview import demo_background
                base = demo_background(640, 360)
            result = visual_preview(effects, color, intensity, occupancy, base_rgb=base, width=640, height=360)
            composed = self._preview_composite_for_mode(base, result, mode)
            self._events.put(("home_preview", serial, composed, base if used_video else None, path if used_video else "", used_video))

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_home_preview_sync(self) -> None:
        if not hasattr(self, "home_preview_label"):
            return
        from .ui.preview import demo_background
        base = demo_background(640, 360)
        result = visual_preview(
            self._selected_effects(),
            self.color.get(),
            max(0.05, min(2.0, float(self.intensity.get()) / 100.0)),
            max(0.10, min(1.0, float(self.occupancy.get()) / 100.0)),
            base_rgb=base,
            width=640,
            height=360,
        )
        image = self._preview_composite_for_mode(base, result, self.home_preview_mode.get())
        self._home_preview_photo = PhotoImage(data=to_ppm_bytes(image), format="PPM")
        self.home_preview_label.configure(image=self._home_preview_photo)

    def _apply_quality_level(self, level: str) -> None:
        if level == "Rápido":
            self.resolution.set("1080p Full HD")
            self.fps.set(60)
            self.enhancement.set(ENHANCE_SIMPLE)
            self.interpolation.set("Quadros repetidos — rápido")
            self.use_cpu.set(not self._nvenc)
            for variable in self.effect_vars.values():
                variable.set(False)
        elif level == "Máximo":
            self.resolution.set("8K UHD")
            self.fps.set(120)
            self.enhancement.set(ENHANCE_AI)
            self.interpolation.set(RIFE_OPTION)
            self.use_cpu.set(False)
            for name, variable in self.effect_vars.items():
                variable.set(name in {"Aurora", "Pulso cinematográfico", "Energia mágica"})
        else:
            self.resolution.set("4K UHD")
            self.fps.set(60)
            self.enhancement.set(ENHANCE_AI if REAL_ESRGAN.is_file() else ENHANCE_SIMPLE)
            self.interpolation.set(RIFE_OPTION if RIFE_EXE.is_file() else "Movimento suave — FFmpeg")
            self.use_cpu.set(False if self._nvenc else True)
            for name, variable in self.effect_vars.items():
                variable.set(name in {"Aurora", "Pulso cinematográfico"})
        self._update_summary()
        self.status.set(f"Nível {level} aplicado. Revise os detalhes ou veja o resultado na prévia visual.")

    def _build_project_tab(self, parent) -> None:
        build_project_tab(
            self,
            parent,
            mode_music=MODE_MUSIC,
            mode_original=MODE_ORIGINAL,
            aspects=(ASPECT_ORIGINAL, ASPECT_LANDSCAPE, ASPECT_PORTRAIT, ASPECT_IMAX, ASPECT_WIDE),
            fit_modes=(FIT_COVER, FIT_CONTAIN),
        )

    def _build_output_tab(self, parent) -> None:
        build_quality_tab(
            self,
            parent,
            resolutions=tuple(RESOLUTIONS),
            fps_options=FPS_OPTIONS,
            aspects=(ASPECT_ORIGINAL, ASPECT_LANDSCAPE, ASPECT_PORTRAIT, ASPECT_IMAX, ASPECT_WIDE),
            enhancement_options=(ENHANCE_NONE, ENHANCE_SIMPLE, ENHANCE_AI),
            interpolation_options=INTERPOLATION_OPTIONS,
            audio_modes=AUDIO_MODES,
            delivery_profiles=DELIVERY_PROFILES,
        )
        self._refresh_quality_controls()
        self._refresh_quality_impact()

    def _build_visual_tab(self, parent) -> None:
        build_visual_tab(
            self,
            parent,
            effect_names=EFFECT_NAMES,
            audio_focus_options=AUDIO_FOCUS_OPTIONS,
            transition_options=TRANSITIONS,
        )

    def _toggle_effect_from_visual_lab(self, effect: str) -> None:
        variable = self.effect_vars[effect]
        variable.set(not variable.get())
        self._update_summary()

    def _refresh_visual_effect_button_states(self) -> None:
        for name, button in getattr(self, "_visual_effect_buttons", {}).items():
            active = self.effect_vars[name].get()
            button.configure(
                text=("✓ " if active else "") + EFFECT_SHORT_NAMES[name],
                style="Selected.Ghost.TButton" if active else "Effect.TButton",
            )

    def _select_visual_direction(self, value: str) -> None:
        self.visual_direction.set(value)
        self._apply_visual_direction()

    def _refresh_visual_direction_buttons(self) -> None:
        short_by_value = {value: short for short, value in DIRECTION_BUTTONS}
        for value, button in getattr(self, "_visual_direction_buttons", {}).items():
            selected = self.visual_direction.get() == value
            button.configure(
                text=("✓ " if selected else "") + short_by_value[value],
                style="Selected.Ghost.TButton" if selected else "Ghost.TButton",
            )

    def _select_visual_transition(self, value: str) -> None:
        self.transition.set(value)
        self._update_summary()

    def _refresh_visual_transition_buttons(self) -> None:
        labels = {
            "Corte seco — original": "Corte seco",
            "Dissolver suave": "Dissolver",
            "Fade cinematográfico": "Fade cinema",
            "Radial": "Radial",
        }
        for value, button in getattr(self, "_visual_transition_buttons", {}).items():
            selected = self.transition.get() == value
            button.configure(
                text=("✓ " if selected else "") + labels[value],
                style="Selected.Ghost.TButton" if selected else "Effect.TButton",
            )

    def _set_visual_preview_mode(self, mode: str) -> None:
        self.visual_preview_mode.set(mode)
        for name, button in getattr(self, "_visual_preview_mode_buttons", {}).items():
            button.configure(style="Selected.Ghost.TButton" if name == mode else "Ghost.TButton")
        self._schedule_visual_preview(refresh_variants=False)

    def _visual_timeline_changed(self, _value=None) -> None:
        seconds = float(self.visual_preview_position.get()) / 100.0 * 6.0
        if hasattr(self, "visual_preview_time_text"):
            self.visual_preview_time_text.set(f"Exemplo 00:{seconds:04.1f} / 00:06.0")
        self._schedule_visual_preview(refresh_variants=not self._visual_preview_playing)

    def _toggle_visual_preview_playback(self) -> None:
        self._visual_preview_playing = not self._visual_preview_playing
        if hasattr(self, "visual_play_button"):
            self.visual_play_button.configure(text="❚❚ Pausar" if self._visual_preview_playing else "▶ Animar")
        if self._visual_playback_after is not None:
            self._cancel_after(self._visual_playback_after)
            self._visual_playback_after = None
        if self._visual_preview_playing:
            self._advance_visual_preview()

    def _advance_visual_preview(self) -> None:
        self._visual_playback_after = None
        if not self._visual_preview_playing or self._closing:
            return
        self.visual_preview_position.set((float(self.visual_preview_position.get()) + 3.2) % 100.0)
        self._visual_timeline_changed()
        self._visual_playback_after = self._schedule(190, self._advance_visual_preview)

    def _schedule_visual_preview(self, *, source_changed: bool = False, refresh_variants: bool = True) -> None:
        if not hasattr(self, "visual_preview_label"):
            return
        if source_changed:
            self._visual_preview_source = None
            self._visual_preview_source_path = ""
        if self._visual_preview_after is not None:
            self._cancel_after(self._visual_preview_after)
        delay = 80 if self._visual_preview_playing else 170
        self._visual_preview_after = self._schedule(
            delay, lambda: self._request_visual_preview(refresh_variants=refresh_variants)
        )

    def _visual_preview_frame_number(self) -> int:
        return int(round(float(self.visual_preview_position.get()) / 100.0 * 359))

    def _request_visual_preview(self, *, refresh_variants: bool = True) -> None:
        self._visual_preview_after = None
        self._visual_preview_serial += 1
        serial = self._visual_preview_serial
        effects = self._selected_effects()
        color = self.color.get()
        intensity = float(self.intensity.get()) / 100.0
        occupancy = float(self.occupancy.get()) / 100.0
        focus = self.audio_focus.get()
        smoothing = float(self.reaction_smoothing.get()) / 100.0
        expression = float(self.reaction_expression.get()) / 100.0
        frame_number = self._visual_preview_frame_number()
        mode = self.visual_preview_mode.get()
        path = self.video.get().strip()
        cached = self._visual_preview_source.copy() if self._visual_preview_source is not None and self._visual_preview_source_path == path else None
        if cached is None and self._home_preview_source is not None and self._home_preview_source_path == path:
            cached = self._home_preview_source.copy()
        if cached is None and path:
            self.visual_preview_source_text.set("Carregando um frame real do vídeo…")

        dynamic_sections = self.dynamic_sections.get()
        section_strength = float(self.section_dynamics.get()) / 100.0

        def worker() -> None:
            from .ui.preview import demo_background

            base = cached
            used_video = base is not None
            if base is None:
                base = extract_video_frame(FFMPEG, path, width=640, height=360) if path else None
                used_video = base is not None
            if base is None:
                base = demo_background(640, 360)
            effective_intensity = intensity
            if dynamic_sections:
                phase = (frame_number % 360) / 359.0
                envelope = 0.88 + 0.22 * section_strength * (0.5 + 0.5 * np.sin(np.pi * (phase * 2.0 - 0.5)))
                effective_intensity = min(2.0, max(0.05, intensity * float(envelope)))
            result = visual_preview(
                effects,
                color,
                effective_intensity,
                occupancy,
                base_rgb=base,
                width=640,
                height=360,
                frame_number=frame_number,
                focus=focus,
                smoothing=smoothing,
                expression=expression,
            )
            composed = self._preview_composite_for_mode(base, result, mode)
            variant_images: dict[str, np.ndarray] = {}
            if refresh_variants:
                for variant in VISUAL_VARIANTS:
                    variant_images[variant.key] = variant_preview(
                        variant.key,
                        effects,
                        color,
                        effective_intensity,
                        occupancy,
                        base_rgb=base,
                        frame_number=frame_number,
                        focus=focus,
                        smoothing=smoothing,
                        expression=expression,
                    )
            self._events.put(("visual_preview", serial, composed, variant_images, base if used_video else None, path if used_video else "", used_video))

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_visual_preview_sync(self) -> None:
        if not hasattr(self, "visual_preview_label"):
            return
        from .ui.preview import demo_background

        base = demo_background(640, 360)
        frame_number = self._visual_preview_frame_number()
        effects = self._selected_effects()
        result = visual_preview(
            effects,
            self.color.get(),
            float(self.intensity.get()) / 100.0,
            float(self.occupancy.get()) / 100.0,
            base_rgb=base,
            width=640,
            height=360,
            frame_number=frame_number,
            focus=self.audio_focus.get(),
            smoothing=float(self.reaction_smoothing.get()) / 100.0,
            expression=float(self.reaction_expression.get()) / 100.0,
        )
        image = self._preview_composite_for_mode(base, result, self.visual_preview_mode.get())
        self._visual_preview_photo = PhotoImage(data=to_ppm_bytes(image), format="PPM")
        self.visual_preview_label.configure(image=self._visual_preview_photo)
        for variant in VISUAL_VARIANTS:
            variant_image = variant_preview(
                variant.key,
                effects,
                self.color.get(),
                float(self.intensity.get()) / 100.0,
                float(self.occupancy.get()) / 100.0,
                base_rgb=base,
                frame_number=frame_number,
                focus=self.audio_focus.get(),
                smoothing=float(self.reaction_smoothing.get()) / 100.0,
                expression=float(self.reaction_expression.get()) / 100.0,
            )
            photo = PhotoImage(data=to_ppm_bytes(variant_image), format="PPM")
            self._visual_variant_photos[variant.key] = photo
            self._visual_variant_labels[variant.key].configure(image=photo)

    def _apply_visual_variant(self, key: str) -> None:
        if key == "soft":
            self.intensity.set(max(25.0, float(self.intensity.get()) * 0.78))
            self.reaction_expression.set(max(25.0, float(self.reaction_expression.get()) * 0.78))
            self.reaction_smoothing.set(min(100.0, float(self.reaction_smoothing.get()) + 8.0))
            self.visual_direction.set("Personalizada")
        elif key == "energy":
            self.intensity.set(min(200.0, float(self.intensity.get()) * 1.20))
            self.reaction_expression.set(min(200.0, float(self.reaction_expression.get()) * 1.25))
            self.reaction_smoothing.set(max(0.0, float(self.reaction_smoothing.get()) - 10.0))
            self.audio_focus.set("Batidas e ataques")
            self.visual_direction.set("Personalizada")
        elif key == "clean":
            if "Partículas musicais" in self.effect_vars:
                self.effect_vars["Partículas musicais"].set(False)
            self.occupancy.set(max(10.0, float(self.occupancy.get()) * 0.92))
            self.visual_direction.set("Personalizada")
        elif key == "epic":
            self.effect_vars["Energia mágica"].set(True)
            self.effect_vars["Pulso cinematográfico"].set(True)
            self.visual_direction.set("Energética")
            self._apply_visual_direction()
            return
        self._visual_scale_changed()
        self.status.set("Variação visual aplicada. Você ainda pode ajustar cada controle manualmente.")

    def _build_queue_tab(self, parent) -> None:
        build_queue_tab(self, parent)

    def _build_ai_tab(self, parent) -> None:
        build_ai_tab(self, parent)

    def _open_ai_folder(self) -> None:
        self._open_queue_path(str(ai_suite.AI_ROOT), prefer_parent=False)

    def _open_ai_docs(self) -> None:
        self._open_queue_path(str(APP_DIR / "docs" / "AI_COMPONENTS.md"), prefer_parent=False)

    def _set_ai_filter(self, value: str) -> None:
        if value not in {"Todos", "No render", "Experimentais", "Faltando"}:
            return
        self.ai_filter.set(value)
        self._refresh_ai_tree()

    def _reprobe_ai_inventory(self) -> None:
        self._refresh_ai_tree(reprobe=True)
        self.status.set("Inventário de IA local verificado novamente.")

    def _set_ai_detail_styles(self, level: str) -> None:
        card_style = {
            "ok": "StatusOk.TLabel",
            "warning": "StatusWarning.TLabel",
            "error": "StatusError.TLabel",
            "active": "CardStatus.TLabel",
            "muted": "StatusMuted.TLabel",
        }.get(level, "StatusMuted.TLabel")
        panel_style = {
            "ok": "PanelAltSuccess.TLabel",
            "warning": "PanelAltWarning.TLabel",
            "error": "PanelAltError.TLabel",
            "active": "PanelAltPrimary.TLabel",
            "muted": "PanelAltMuted.TLabel",
        }.get(level, "PanelAltMuted.TLabel")
        if hasattr(self, "ai_detail_badge_label"):
            self.ai_detail_badge_label.configure(style=card_style)
        if hasattr(self, "ai_detail_state_label"):
            self.ai_detail_state_label.configure(style=panel_style)

    def _refresh_ai_detail(self, items: list[dict] | None = None) -> None:
        if not hasattr(self, "ai_detail_name"):
            return
        items = items if items is not None else (self._ai_inventory_snapshot or ai_suite.inventory())
        visible = visible_items(items, self.ai_filter.get())
        known = {item["key"]: item for item in items}
        if self._ai_detail_key not in known:
            self._ai_detail_key = visible[0]["key"] if visible else ""
        if self._ai_detail_key and self._ai_detail_key not in {item["key"] for item in visible}:
            self._ai_detail_key = visible[0]["key"] if visible else ""
        item = known.get(self._ai_detail_key)
        if item is None:
            self.ai_detail_badge.set("Nenhum módulo")
            self.ai_detail_name.set("Nenhum componente neste filtro.")
            self.ai_detail_category.set("Troque o filtro para consultar o restante do catálogo.")
            self.ai_detail_state.set("Sem seleção")
            self.ai_detail_state_explanation.set("")
            for variable in (
                self.ai_detail_benefit, self.ai_detail_render_usage, self.ai_detail_missing_effect,
                self.ai_detail_footprint, self.ai_detail_license, self.ai_detail_recommendation,
            ):
                variable.set("—")
            self.ai_detail_license_warning.set("")
            self._set_ai_detail_styles("muted")
            if hasattr(self, "ai_detail_toggle_button"):
                self.ai_detail_toggle_button.configure(state="disabled", text="Selecionar para instalar")
            return

        detail = module_detail(item, experimental_enabled=self.experimental_downloads.get())
        state = capability_state(item, experimental_enabled=self.experimental_downloads.get())
        self.ai_detail_badge.set(detail["tier"])
        self.ai_detail_name.set(detail["name"])
        self.ai_detail_category.set(detail["category"])
        self.ai_detail_state.set(detail["state"])
        self.ai_detail_state_explanation.set(detail["state_explanation"])
        self.ai_detail_benefit.set(detail["benefit"])
        self.ai_detail_render_usage.set(detail["render_usage"])
        self.ai_detail_missing_effect.set(detail["missing_effect"])
        self.ai_detail_footprint.set(detail["footprint"])
        self.ai_detail_license.set(detail["license"])
        self.ai_detail_license_warning.set(detail["license_warning"])
        self.ai_detail_recommendation.set(detail["recommendation"])
        self._set_ai_detail_styles(state["level"])

        allowed = bool(item["installable"] and not item["installed"] and (not item["experimental"] or self.experimental_downloads.get()))
        selected = item["key"] in self._ai_selected
        if hasattr(self, "ai_detail_toggle_button"):
            if item["installed"]:
                text = "Já instalado"
            elif item["experimental"] and not self.experimental_downloads.get():
                text = "Ative o modo experimental"
            elif not item["installable"]:
                text = "Sem instalador nesta versão"
            else:
                text = "Remover da seleção" if selected else "Selecionar para instalar"
            self.ai_detail_toggle_button.configure(text=text, state="normal" if allowed and not self._ai_installing else "disabled")

    def _refresh_ai_tree(self, *, reprobe: bool = False) -> None:
        if not hasattr(self, "ai_tree"):
            return
        if reprobe or not self._ai_inventory_snapshot:
            self._ai_inventory_snapshot = ai_suite.inventory()
        items = self._ai_inventory_snapshot
        known = {item["key"] for item in items}
        self._ai_selected.intersection_update(known)
        visible = visible_items(items, self.ai_filter.get())

        for row in self.ai_tree.get_children():
            self.ai_tree.delete(row)
        self.ai_tree.tag_configure("ok", foreground=COLORS["success"])
        self.ai_tree.tag_configure("warning", foreground=COLORS["warning"])
        self.ai_tree.tag_configure("error", foreground=COLORS["danger"])
        self.ai_tree.tag_configure("active", foreground=COLORS["primary"])

        for item in visible:
            state = capability_state(item, experimental_enabled=self.experimental_downloads.get())
            detail = module_detail(item, experimental_enabled=self.experimental_downloads.get())
            allowed = item["installable"] and not item["installed"] and (not item["experimental"] or self.experimental_downloads.get())
            marker = "☑" if item["key"] in self._ai_selected else ("☐" if allowed else "—")
            self.ai_tree.insert(
                "", "end", iid=item["key"],
                values=(marker, item["name"], item["purpose"], state["label"]),
                tags=(state["level"],),
            )

        summary = inventory_summary(items)
        self.ai_integrated_ready_text.set(f"{summary['integrated_ready']}/{summary['integrated_total']}")
        self.ai_integrated_missing_text.set(str(summary["integrated_missing"]))
        self.ai_experimental_installed_text.set(f"{summary['experimental_installed']}/{summary['experimental_total']}")
        self.ai_inventory_text.set(
            f"{len(items)} módulos catalogados • {summary['integrated_total']} integrados ao render • "
            f"{summary['experimental_total']} experimentais fora do render"
        )

        selection = selected_download(items, self._ai_selected)
        self.ai_selection_size_text.set(human_bytes(selection["bytes"]) if selection["count"] else "0 B")
        if selection["count"]:
            extra = f" • {selection['experimental_count']} experimental(is)" if selection["experimental_count"] else " • somente componentes integrados"
            self.ai_selection_text.set(
                f"{selection['count']} componente(s) selecionado(s) • download aproximado {human_bytes(selection['bytes'])}{extra}."
            )
        else:
            self.ai_selection_text.set("Nenhum componente selecionado. ‘Selecionar necessários’ escolhe somente recursos integrados que estão faltando.")

        for value, button in getattr(self, "_ai_filter_buttons", {}).items():
            button.configure(style="Selected.Ghost.TButton" if value == self.ai_filter.get() else "Ghost.TButton")

        self._refresh_ai_detail(items)
        if self._ai_detail_key and self.ai_tree.exists(self._ai_detail_key):
            self.ai_tree.selection_set(self._ai_detail_key)
            self.ai_tree.focus(self._ai_detail_key)
            self.ai_tree.see(self._ai_detail_key)

        if not self._ai_installing:
            self.ai_install_selected_button.configure(state="normal" if selection["count"] else "disabled")
            missing_required = any(item["installable"] and not item["installed"] and not item["experimental"] for item in items)
            self.ai_select_missing_button.configure(state="normal" if missing_required else "disabled")
            self.ai_install_all_button.configure(state="normal" if missing_required else "disabled")

    def _ai_selection_changed(self, _event=None) -> None:
        if not hasattr(self, "ai_tree"):
            return
        selected = self.ai_tree.selection()
        if selected:
            self._ai_detail_key = selected[0]
            self._refresh_ai_detail()

    def _toggle_ai_key(self, key: str) -> None:
        item = next((entry for entry in (self._ai_inventory_snapshot or ai_suite.inventory()) if entry["key"] == key), None)
        if not item or item["installed"] or not item["installable"] or self._ai_installing:
            return
        if item["experimental"] and not self.experimental_downloads.get():
            messagebox.showinfo(
                APP_TITLE,
                "Este componente está fora do render atual. Ative o modo experimental abaixo para liberar apenas o download.",
            )
            return
        self._ai_detail_key = key
        if key in self._ai_selected:
            self._ai_selected.remove(key)
        else:
            self._ai_selected.add(key)
        self._refresh_ai_tree()

    def _toggle_ai_component(self, event) -> None:
        if self.ai_tree.identify_column(event.x) != "#1":
            return
        key = self.ai_tree.identify_row(event.y)
        if key:
            self._toggle_ai_key(key)

    def _toggle_focused_ai_component(self, _event=None) -> str:
        key = self.ai_tree.focus()
        if key:
            self._toggle_ai_key(key)
        return "break"

    def _toggle_selected_ai_detail(self) -> None:
        if self._ai_detail_key:
            self._toggle_ai_key(self._ai_detail_key)

    def _clear_ai_selection(self) -> None:
        self._ai_selected.clear()
        self._refresh_ai_tree()

    def _select_missing_ai_components(self) -> None:
        # Safe default: this button never sweeps experimental downloads into
        # the selection, even when advanced mode is enabled.
        self._ai_selected = {
            item["key"] for item in ai_suite.inventory()
            if item["installable"] and not item["installed"] and not item["experimental"]
        }
        self._refresh_ai_tree()

    def _install_required_ai_components(self) -> None:
        keys = {
            item["key"] for item in ai_suite.inventory()
            if item["installable"] and not item["installed"] and not item["experimental"]
        }
        self._start_ai_component_install(keys)

    def _experimental_download_mode_changed(self) -> None:
        if not self.experimental_downloads.get():
            self._ai_selected = {
                key for key in self._ai_selected
                if not next((item["experimental"] for item in ai_suite.inventory() if item["key"] == key), False)
            }
        self._refresh_ai_tree()

    def _install_selected_ai_components(self) -> None:
        self._start_ai_component_install(set(self._ai_selected))

    def _install_all_ai_components(self) -> None:
        # Legacy entry point kept for compatibility with older callers.  The
        # Phase 6 UI uses the safer “Instalar necessários” action instead.
        keys = {
            item["key"] for item in ai_suite.inventory()
            if item["installable"] and not item["installed"] and (not item["experimental"] or self.experimental_downloads.get())
        }
        self._start_ai_component_install(keys)

    def _start_ai_component_install(self, keys: set[str]) -> None:
        if self._busy or self._ai_installing:
            messagebox.showinfo(APP_TITLE, "Aguarde o processamento atual terminar antes de instalar componentes.")
            return
        items = {item["key"]: item for item in ai_suite.inventory()}
        selected = [
            items[key] for key in sorted(keys)
            if key in items and items[key]["installable"] and not items[key]["installed"]
            and (not items[key]["experimental"] or self.experimental_downloads.get())
        ]
        if not selected:
            messagebox.showinfo(APP_TITLE, "Não há componentes instaláveis faltando nessa seleção.")
            return
        total_bytes = sum(item["download_bytes"] for item in selected)
        names = "\n".join(
            f"• {item['name']}" + (f" — EXPERIMENTAL — {item['license']}" if item["experimental"] else "")
            for item in selected
        )
        warning = ""
        if any(item["experimental"] for item in selected):
            warning = (
                "\n\nATENÇÃO: os itens experimentais não participam do render atual. "
                "Ao continuar, você declara que revisará e cumprirá as licenças e assume espaço, compatibilidade e uso."
            )
        if not messagebox.askyesno(APP_TITLE, f"Baixar, verificar e instalar estes componentes?\n\n{names}\n\nDownload aproximado: {total_bytes / (1024**3):.2f} GB.{warning}"):
            return
        installer = APP_DIR / "installer" / "Start-CinePulse.ps1"
        if not installer.is_file():
            messagebox.showerror(APP_TITLE, "O instalador de componentes não foi encontrado.")
            return
        components = sorted({item["installer_component"] for item in selected if not item["experimental"]})
        experimental_keys = sorted({item["installer_component"] for item in selected if item["experimental"]})
        self._ai_installing = True
        self._refresh_footer_density()
        self._ai_selected.clear()
        self.ai_install_status_text.set("Preparando downloads e verificações…")
        self.ai_install_progress.set(0.0)
        self.ai_install_progress_text.set("")
        if hasattr(self, "ai_install_progressbar"):
            self.ai_install_progressbar.configure(mode="indeterminate")
            self.ai_install_progressbar.start(12)
        for button in (self.ai_select_missing_button, self.ai_install_selected_button, self.ai_install_all_button):
            button.configure(state="disabled")
        for button in (self.render_button, self.preview_button, self.add_queue_button, self.add_queue_compact_button):
            button.configure(state="disabled")
        self.bar.configure(mode="indeterminate")
        self.bar.start(12)
        self.stage.set("Instalando IA local")
        self._set_feedback(
            "busy", "Instalando componentes locais",
            "Baixando, verificando hashes e preparando os componentes selecionados. O log técnico continua disponível.",
            category="IA local", primary=("Abrir IA local", lambda: self._open_tab(5)), secondary=("Ver log", self._show_log),
        )

        def worker() -> None:
            recent: deque[str] = deque(maxlen=30)

            def report_activity(line: str) -> None:
                clean_line = str(line).strip()
                if not clean_line:
                    return
                recent.append(clean_line)
                self._log(clean_line)
                self._events.put(("ai_install_status", clean_line))

            try:
                shell = find_powershell().executable
                if components:
                    command = [
                        shell, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(installer),
                    ]
                    if installation_mode(APP_DIR) == "installed":
                        command.append("-NonPortable")
                    command.extend(["-InstallOnly", "-ComponentsCsv", ",".join(components)])
                    process = subprocess.Popen(
                        command, cwd=str(APP_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW,
                    )
                    assert process.stdout is not None
                    for line in process.stdout:
                        report_activity(line)
                    code = process.wait()
                    if code:
                        raise RuntimeError("\n".join(recent) or f"O instalador terminou com o código {code}.")
                if experimental_keys:
                    experimental_components.install(experimental_keys, report_activity)
                self._events.put(("ai_install_done", [item["name"] for item in selected]))
            except Exception as exc:
                self._events.put(("ai_install_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_ai_component_install(self) -> None:
        self._ai_installing = False
        self._refresh_footer_density()
        if hasattr(self, "ai_install_progressbar"):
            self.ai_install_progressbar.stop()
            self.ai_install_progressbar.configure(mode="determinate")
        self.bar.stop()
        self.bar.configure(mode="determinate")
        self.bar["value"] = 0
        self.progress_text.set("0%")
        for button in (self.ai_select_missing_button, self.ai_install_selected_button, self.ai_install_all_button):
            button.configure(state="normal")
        if not self._busy:
            for button in (self.render_button, self.preview_button, self.add_queue_button, self.add_queue_compact_button):
                button.configure(state="normal")
        self._refresh_ai_tree(reprobe=True)

    def _file_row(self, parent, row: int, label: str, variable: StringVar, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=7)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=7)
        ttk.Button(parent, text="Selecionar…", command=command).grid(row=row, column=2, padx=(8, 0), pady=7)

    def _combo_row(self, parent, row, label, variable, values, changed) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=7)
        box = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly")
        box.grid(row=row, column=1, columnspan=2, sticky="ew", pady=7)
        box.bind("<<ComboboxSelected>>", lambda _e: changed())

    def _quality_real_esrgan_available(self) -> bool:
        return REAL_ESRGAN.is_file()

    def _quality_rife_available(self) -> bool:
        return RIFE_EXE.is_file()

    def _set_quality_status_style(self, target: str, level: str) -> None:
        label = getattr(self, f"quality_{target}_badge_label", None)
        if label is None:
            return
        style = {
            "ok": "StatusOk.TLabel",
            "warning": "StatusWarning.TLabel",
            "error": "StatusError.TLabel",
            "active": "CardStatus.TLabel",
            "muted": "StatusMuted.TLabel",
        }.get(level, "StatusMuted.TLabel")
        label.configure(style=style)

    def _select_quality_enhancement(self, value: str) -> None:
        if value not in {ENHANCE_NONE, ENHANCE_SIMPLE, ENHANCE_AI}:
            return
        self.enhancement.set(value)
        self._enhancement_changed()
        self._refresh_quality_controls()
        self._refresh_quality_impact()

    def _select_quality_interpolation(self, value: str) -> None:
        if value not in INTERPOLATION_OPTIONS:
            return
        self.interpolation.set(value)
        self._quality_setting_changed()

    def _select_quality_processor(self, use_cpu: bool) -> None:
        self.use_cpu.set(bool(use_cpu))
        self._processor_changed()
        self._refresh_quality_controls()
        self._refresh_quality_impact()

    def _quality_setting_changed(self, _event=None) -> None:
        self._update_summary()

    def _refresh_quality_controls(self) -> None:
        enhancement_info = {
            ENHANCE_NONE: ("Preservar", "Sem upscale; menor custo e nenhuma tentativa de criar detalhe."),
            ENHANCE_SIMPLE: ("Lanczos", "Upscale clássico de alta qualidade; rápido e previsível."),
            ENHANCE_AI: ("Real-ESRGAN IA", "Recuperação de detalhe plausível por IA; exige GPU e aumenta bastante o custo."),
        }
        for value, button in getattr(self, "_quality_enhancement_buttons", {}).items():
            title, description = enhancement_info[value]
            note = ""
            if value == ENHANCE_AI:
                note = " • instalado" if self._quality_real_esrgan_available() else " • componente ausente"
            selected = self.enhancement.get() == value
            button.configure(
                text=("✓ " if selected else "") + title + note + "\n" + description,
                style="Selected.ModeCard.TButton" if selected else "ModeCard.TButton",
            )

        interpolation_info = {
            RIFE_OPTION: ("RIFE IA", "Melhor movimento em cenas adequadas; se faltar o componente, o pipeline usa fallback FFmpeg."),
            "Movimento suave — FFmpeg": ("FFmpeg suave", "Interpolação por movimento sem modelo neural; equilíbrio entre custo e fluidez."),
            "Quadros repetidos — rápido": ("Repetir quadros", "Mais rápido; aumenta FPS sem inventar movimento intermediário."),
        }
        for value, button in getattr(self, "_quality_interpolation_buttons", {}).items():
            title, description = interpolation_info[value]
            note = ""
            if value == RIFE_OPTION:
                note = " • instalado" if self._quality_rife_available() else " • fallback disponível"
            selected = self.interpolation.get() == value
            button.configure(
                text=("✓ " if selected else "") + title + note + "\n" + description,
                style="Selected.ModeCard.TButton" if selected else "ModeCard.TButton",
            )

        for cpu_value, button in getattr(self, "_quality_processor_buttons", {}).items():
            selected = self.use_cpu.get() == cpu_value
            button.configure(
                text=("✓ " if selected else "") + ("Somente CPU" if cpu_value else "Aceleração automática"),
                style="Selected.Ghost.TButton" if selected else "Ghost.TButton",
            )

    def _refresh_quality_impact(self) -> None:
        if not hasattr(self, "quality_load_badge_label"):
            return

        video_path = self.video.get().strip()
        probe = self._project_video_probe if self._project_video_probe_path == video_path else None
        source_size = self._project_video_size if probe is not None else None
        if probe is None or source_size is None:
            target_w, target_h = self._target_size(self.resolution.get(), self.aspect.get(), None)
            self.quality_load_badge.set("Aguardando fonte")
            self._set_quality_status_style("load", "muted")
            self.quality_source_text.set("Selecione um vídeo para medir escala, FPS e duração.")
            self.quality_target_text.set(f"{target_w}×{target_h} • {self.fps.get()} fps • {self.aspect.get()}")
            self.quality_scale_text.set("A escala depende da resolução da fonte.")
            self.quality_motion_text.set("O custo de interpolação depende do FPS da fonte.")
            if self.enhancement.get() == ENHANCE_AI:
                self.quality_vram_text.set("Real-ESRGAN selecionado • carregue a fonte para calcular a referência de VRAM.")
            else:
                self.quality_vram_text.set("Sem cálculo neural específico nesta configuração.")
            self.quality_output_text.set("Carregue a fonte (e a música, no modo loop) para estimar tamanho.")
            suffix = Path(self.output.get().strip()).suffix.lower() or suggested_extension(self.delivery_profile.get(), ".mp4")
            self.quality_delivery_text.set(f"{self.delivery_profile.get()} • destino {suffix.upper()} • codecs serão confirmados após analisar a cor da fonte.")
            self.quality_plan_badge.set("Aguardando fonte")
            self._set_quality_status_style("plan", "muted")
            self.quality_plan_text.set("O RenderPlan precisa da resolução e do FPS reais da fonte para declarar cada etapa.")
            self.quality_plan_risk_text.set("Nenhuma decisão estrutural é inferida sem a mídia; isso evita apresentar um plano fictício.")
            component_notes: list[str] = []
            if self.enhancement.get() == ENHANCE_AI and not self._quality_real_esrgan_available():
                component_notes.append("Real-ESRGAN não está instalado; o render final será bloqueado até instalar ou trocar a melhoria.")
            if self.interpolation.get() == RIFE_OPTION and not self._quality_rife_available():
                component_notes.append("RIFE não está instalado; o pipeline pode continuar com fallback FFmpeg.")
            if component_notes:
                self.quality_compat_badge.set(f"{len(component_notes)} observação(ões)")
                self._set_quality_status_style("compat", "warning" if self._quality_real_esrgan_available() or self.enhancement.get() != ENHANCE_AI else "error")
                self.quality_warning_text.set(" • ".join(component_notes))
            else:
                self.quality_compat_badge.set("Aguardando mídia")
                self._set_quality_status_style("compat", "muted")
                self.quality_warning_text.set("Sem a fonte não dá para avaliar escala, movimento, HDR e pressão real de VRAM.")
            return

        source_w, source_h = source_size
        try:
            source_fps = first_video_fps(probe)
            video_duration = media_duration(probe)
        except Exception:
            source_fps = 30.0
            video_duration = None

        duration: float | None
        if self.mode.get() == MODE_MUSIC:
            audio_path = self.audio.get().strip()
            audio_probe = self._project_audio_probe if self._project_audio_probe_path == audio_path else None
            try:
                duration = media_duration(audio_probe) if audio_probe is not None else None
            except Exception:
                duration = None
        else:
            duration = video_duration

        target_w, target_h = self._target_size(self.resolution.get(), self.aspect.get(), (source_w, source_h))
        try:
            color = ColorProfile.from_probe(probe)
            color_label = color.label
        except Exception:
            color = ColorProfile("unknown", "unknown", "unknown", "unknown", "unknown", 8, False)
            color_label = "cor não identificada"

        plan = self._build_render_plan(
            self._settings(),
            preview=False,
            source_w=source_w,
            source_h=source_h,
            source_fps=source_fps,
            target_w=target_w,
            target_h=target_h,
            target_fps=int(self.fps.get()),
            color_profile=color,
        )
        delivery = self._build_delivery_contract(
            self._settings(), preview=False, source_color=color, target_w=target_w, target_h=target_h,
            target_fps=int(self.fps.get()), render_plan=plan,
        )
        self.quality_delivery_text.set(f"{delivery.label} • perfil {delivery.profile}")
        color_warnings = [
            f"{risk.title}: {risk.detail}"
            for risk in plan.risks
            if risk.code.startswith("CI-P4-")
        ]
        # Phase 2: workload/VRAM follows what the RenderPlan will actually execute,
        # not merely the option selected in the combobox.
        impact = estimate_quality_impact(
            source_width=source_w,
            source_height=source_h,
            source_fps=source_fps,
            duration_seconds=duration,
            target_width=target_w,
            target_height=target_h,
            target_fps=int(self.fps.get()),
            vram_mb=self._hardware.vram_mb,
            neural_upscale=plan.step("enhancement").attempts,
            interpolation=self.interpolation.get(),
        )
        critical_risks = [risk for risk in plan.risks if risk.severity == "critical"]
        if critical_risks:
            self.quality_plan_badge.set(f"{plan.fingerprint[:8]} • {len(critical_risks)} risco(s) crítico(s)")
            self._set_quality_status_style("plan", "error")
        elif plan.risks:
            self.quality_plan_badge.set(f"{plan.fingerprint[:8]} • {len(plan.risks)} atenção(ões)")
            self._set_quality_status_style("plan", "warning")
        else:
            self.quality_plan_badge.set(f"{plan.fingerprint[:8]} • sem risco estrutural detectado")
            self._set_quality_status_style("plan", "ok")
        self.quality_plan_text.set("\n".join(plan.user_lines()))
        if plan.risks:
            self.quality_plan_risk_text.set(" • ".join(f"{risk.code}: {risk.title}" for risk in plan.risks[:4]))
        else:
            self.quality_plan_risk_text.set("O plano atual não detectou redução estrutural conhecida nesta combinação.")

        self.quality_source_text.set(f"{source_w}×{source_h} • {source_fps:.2f} fps • {color_label}")
        duration_text = f" • {format_time(duration)}" if duration is not None else " • duração pendente"
        self.quality_target_text.set(f"{target_w}×{target_h} • {self.fps.get()} fps • {self.aspect.get()}{duration_text}")
        self.quality_scale_text.set(scale_description(impact.scale_ratio))
        self.quality_motion_text.set(motion_description(source_fps, int(self.fps.get()), self.interpolation.get()))

        if impact.vram_reference_gb is not None:
            available = self._hardware.vram_mb / 1024 if self._hardware.vram_mb else None
            if available is None:
                self.quality_vram_text.set(f"Referência do Real-ESRGAN ~{impact.vram_reference_gb:.1f} GB • VRAM disponível não detectada")
            else:
                self.quality_vram_text.set(f"Referência ~{impact.vram_reference_gb:.1f} GB • detectado ~{available:.1f} GB")
        else:
            self.quality_vram_text.set("Sem referência adicional de VRAM para upscale neural")

        if impact.output_gb is None:
            self.quality_output_text.set(f"Bitrate de referência ~{impact.bitrate_mbps} Mb/s • duração da música pendente")
        else:
            self.quality_output_text.set(f"~{impact.output_gb:.2f} GB • bitrate de referência ~{impact.bitrate_mbps} Mb/s")

        self.quality_load_badge.set(f"Carga relativa: {impact.workload_label}")
        load_level = "warning" if impact.workload_label in {"Muito alta", "Extrema"} else "active"
        self._set_quality_status_style("load", load_level)

        warnings = list(color_warnings) + list(impact.warnings) + list(delivery.warnings)
        hard_error = delivery.blocking
        if delivery.errors:
            warnings = list(delivery.errors) + warnings
        if plan.step("enhancement").attempts and self.enhancement.get() == ENHANCE_AI and not self._quality_real_esrgan_available():
            warnings.insert(0, "Real-ESRGAN é necessário para ampliar esta fonte, mas o componente local não está instalado; o render final ficará bloqueado.")
            hard_error = True
        if plan.step("rife_final").attempts and self.interpolation.get() == RIFE_OPTION and not self._quality_rife_available():
            warnings.append("RIFE é necessário para atingir o FPS solicitado e não está instalado; o pipeline usará fallback FFmpeg.")
        if not self.use_cpu.get() and not self._nvenc and max(target_w, target_h) <= 8192:
            warnings.append("NVENC não foi detectado; a codificação poderá usar CPU e ficar mais lenta.")

        if hard_error:
            self.quality_compat_badge.set("Ação necessária")
            self._set_quality_status_style("compat", "error")
        elif warnings:
            self.quality_compat_badge.set(f"{len(warnings)} aviso(s)")
            self._set_quality_status_style("compat", "warning")
        else:
            self.quality_compat_badge.set("✓ Compatível")
            self._set_quality_status_style("compat", "ok")

        if warnings:
            self.quality_warning_text.set(" • ".join(warnings[:5]))
        else:
            self.quality_warning_text.set("Nenhum aviso de escala, FPS, VRAM, HDR ou componente para a configuração analisada.")

    def _open_preview_folder(self) -> None:
        """Open the preview directory without making non-Windows smoke tests fail."""
        try:
            if hasattr(os, "startfile"):
                os.startfile(PREVIEW_DIR)  # type: ignore[attr-defined]
            elif shutil.which("xdg-open"):
                subprocess.Popen(["xdg-open", str(PREVIEW_DIR)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                self.status.set(f"Previews: {PREVIEW_DIR}")
        except OSError as exc:
            self.status.set(f"Não foi possível abrir a pasta de previews: {exc}")

    def _set_project_status_style(self, target: str, level: str) -> None:
        label = getattr(self, f"project_{target}_badge_label", None)
        if label is None:
            return
        style = {
            "ok": "StatusOk.TLabel",
            "warning": "StatusWarning.TLabel",
            "error": "StatusError.TLabel",
            "active": "CardStatus.TLabel",
            "muted": "StatusMuted.TLabel",
        }.get(level, "StatusMuted.TLabel")
        label.configure(style=style)

    def _set_project_mode(self, value: str) -> None:
        if value not in {MODE_MUSIC, MODE_ORIGINAL}:
            return
        self.mode.set(value)
        self._update_mode()
        self._mark_project_preflight_stale("Modo do projeto alterado; verifique novamente antes do render final.")

    def _refresh_project_mode_buttons(self) -> None:
        descriptions = {
            MODE_MUSIC: (
                "Loop musical",
                "Repete o clipe durante toda a música e usa a música como duração do projeto.",
            ),
            MODE_ORIGINAL: (
                "Melhorar vídeo original",
                "Mantém a duração e o conteúdo do vídeo; o áudio original pode ser preservado.",
            ),
        }
        for value, button in getattr(self, "_project_mode_buttons", {}).items():
            label, description = descriptions[value]
            selected = self.mode.get() == value
            button.configure(
                text=("✓ " if selected else "") + label + "\n" + description,
                style="Selected.ModeCard.TButton" if selected else "ModeCard.TButton",
            )

    def _refresh_project_fit_buttons(self) -> None:
        labels = {FIT_COVER: "Preencher / cortar", FIT_CONTAIN: "Encaixar / barras"}
        for value, button in getattr(self, "_project_fit_buttons", {}).items():
            selected = self.fit_mode.get() == value
            button.configure(
                text=("✓ " if selected else "") + labels.get(value, value),
                style="Selected.Ghost.TButton" if selected else "Ghost.TButton",
            )

    def _set_project_fit_mode(self, value: str) -> None:
        if value not in {FIT_COVER, FIT_CONTAIN}:
            return
        self.fit_mode.set(value)
        self._project_framing_changed()

    def _project_framing_changed(self) -> None:
        self._refresh_project_fit_buttons()
        self._refresh_project_framing_sync()
        self._update_summary()

    def _refresh_project_framing_sync(self) -> None:
        if not hasattr(self, "project_framing_label"):
            return
        from .ui.preview import demo_background

        current_path = self.video.get().strip()
        used_real = bool(
            self._project_source_rgb is not None
            and current_path
            and self._project_source_path == current_path
        )
        source = self._project_source_rgb if used_real else demo_background(640, 360)
        logical_size = self._project_video_size if used_real and self._project_video_size else (source.shape[1], source.shape[0])
        source_w, source_h = logical_size
        image = framing_preview(
            source,
            self.aspect.get(),
            self.fit_mode.get(),
            source_width=source_w,
            source_height=source_h,
            canvas_width=640,
            canvas_height=360,
        )
        self._project_framing_photo = PhotoImage(data=to_ppm_bytes(image), format="PPM")
        self.project_framing_label.configure(image=self._project_framing_photo)
        explanation = framing_explanation(source_w, source_h, self.aspect.get(), self.fit_mode.get())
        self.project_framing_badge.set("Frame real do vídeo" if used_real else "Demonstração")
        prefix = f"Fonte {source_w}×{source_h} • " if used_real else "Guia demonstrativo • "
        self.project_framing_info.set(prefix + explanation)

    def _project_paths_edited(self) -> None:
        """Refresh inline validation after manual path edits without modal dialogs."""
        video = self.video.get().strip()
        audio = self.audio.get().strip()
        if video and Path(video).is_file() and video != self._project_source_path:
            self._inspect_project_video(video)
        elif not video:
            self.project_video_badge.set("Aguardando vídeo")
            self._set_project_status_style("video", "muted")
            self.project_video_headline.set("Selecione um vídeo para analisar resolução, FPS, duração e cor.")
            self.project_video_detail.set("A análise usa FFprobe em segundo plano e não modifica o arquivo.")
            self._project_source_rgb = None
            self._project_source_path = ""
            self._project_video_size = None
            self._project_video_probe = None
            self._project_video_probe_path = ""
            self._refresh_project_framing_sync()
        elif not Path(video).is_file():
            self.project_video_badge.set("⚠ Vídeo não encontrado")
            self._set_project_status_style("video", "error")
            self.project_video_headline.set("O caminho informado não aponta para um arquivo existente.")
            self.project_video_detail.set("Escolha novamente o vídeo antes de executar preview ou render.")
            self._project_video_probe = None
            self._project_video_probe_path = ""

        if self.mode.get() == MODE_MUSIC:
            if audio and Path(audio).is_file():
                self._inspect_project_audio(audio)
            elif not audio:
                self.project_audio_badge.set("Aguardando música")
                self._set_project_status_style("audio", "muted")
                self.project_audio_headline.set("Selecione a música que define a duração do projeto.")
                self.project_audio_detail.set("WAV ou FLAC são recomendados para preservar melhor a fonte.")
                self._project_audio_probe = None
                self._project_audio_probe_path = ""
            else:
                self.project_audio_badge.set("⚠ Áudio não encontrado")
                self._set_project_status_style("audio", "error")
                self.project_audio_headline.set("O caminho informado não aponta para um arquivo existente.")
                self.project_audio_detail.set("Escolha novamente a música antes de gerar o loop musical.")
                self._project_audio_probe = None
                self._project_audio_probe_path = ""
        else:
            self.project_audio_badge.set("Não usado neste modo")
            self._set_project_status_style("audio", "muted")
            self.project_audio_headline.set("O modo Melhorar vídeo original não exige uma música separada.")
            self.project_audio_detail.set("A opção de preservar o áudio original continua disponível em Qualidade e saída.")

        self._refresh_project_output_state()
        self._mark_project_preflight_stale("Arquivos ou destino alterados; a verificação detalhada precisa ser atualizada.")

    def _inspect_project_video(self, path: str | None = None) -> None:
        path = (path if path is not None else self.video.get()).strip()
        self._project_video_serial += 1
        serial = self._project_video_serial
        if not path or not Path(path).is_file():
            self.project_video_badge.set("⚠ Vídeo inválido" if path else "Aguardando vídeo")
            self._set_project_status_style("video", "error" if path else "muted")
            return
        if self._project_video_probe_path != path:
            self._project_video_probe = None
            self._project_video_probe_path = ""
        self.project_video_badge.set("Analisando vídeo…")
        self._set_project_status_style("video", "active")
        self.project_video_headline.set(Path(path).name)
        self.project_video_detail.set("Lendo metadados com FFprobe sem bloquear a interface…")

        def worker() -> None:
            try:
                info = probe_media(path)
                summary = summarize_video_probe(info)
                size = first_video_size(info)
                source_w, source_h = size
                scale = min(640 / max(1, source_w), 360 / max(1, source_h))
                frame_w = max(2, round(source_w * scale))
                frame_h = max(2, round(source_h * scale))
                frame = extract_video_frame(FFMPEG, path, width=frame_w, height=frame_h, position=1.0)
                self._events.put(("project_video", serial, path, summary, size, frame, info, ""))
            except Exception as exc:
                self._events.put(("project_video", serial, path, None, None, None, None, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _inspect_project_audio(self, path: str | None = None) -> None:
        path = (path if path is not None else self.audio.get()).strip()
        self._project_audio_serial += 1
        serial = self._project_audio_serial
        if self.mode.get() != MODE_MUSIC:
            return
        if not path or not Path(path).is_file():
            self.project_audio_badge.set("⚠ Áudio inválido" if path else "Aguardando música")
            self._set_project_status_style("audio", "error" if path else "muted")
            return
        if self._project_audio_probe_path != path:
            self._project_audio_probe = None
            self._project_audio_probe_path = ""
        self.project_audio_badge.set("Analisando música…")
        self._set_project_status_style("audio", "active")
        self.project_audio_headline.set(Path(path).name)
        self.project_audio_detail.set("Lendo duração, codec, canais e sample rate…")

        def worker() -> None:
            try:
                info = probe_media(path)
                summary = summarize_audio_probe(info)
                self._events.put(("project_audio", serial, path, summary, info, ""))
            except Exception as exc:
                self._events.put(("project_audio", serial, path, None, None, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_project_output_state(self) -> None:
        state, title, detail = project_output_state(
            self.output.get().strip(),
            self.video.get().strip(),
            self.audio.get().strip() if self.mode.get() == MODE_MUSIC else "",
        )
        icon = {"ok": "✓", "warning": "⚠", "error": "⚠", "pending": "○"}.get(state, "○")
        self.project_output_badge.set(f"{icon} {title}")
        self._set_project_status_style("output", {"ok": "ok", "warning": "warning", "error": "error", "pending": "muted"}.get(state, "muted"))
        self.project_output_detail.set(detail)

    def _project_missing_requirements(self) -> list[str]:
        missing: list[str] = []
        if not FFMPEG or not FFPROBE:
            missing.append("FFmpeg/FFprobe não estão disponíveis")
        video = self.video.get().strip()
        if not video or not Path(video).is_file():
            missing.append("selecione um vídeo válido")
        if self.mode.get() == MODE_MUSIC:
            audio = self.audio.get().strip()
            if not audio or not Path(audio).is_file():
                missing.append("selecione a música do loop")
        output = self.output.get().strip()
        if not output:
            missing.append("escolha o destino do vídeo final")
        else:
            state, title, _detail = project_output_state(
                output,
                video,
                self.audio.get().strip() if self.mode.get() == MODE_MUSIC else "",
            )
            if state == "error":
                missing.append(title.casefold())
        if (
            self.enhancement.get() == ENHANCE_AI
            and not REAL_ESRGAN.is_file()
            and self._ai_upscale_required(self._settings())
        ):
            missing.append("Real-ESRGAN é necessário para ampliar esta fonte, mas o componente local não está instalado")
        return missing

    def _mark_project_preflight_stale(self, reason: str = "A configuração mudou desde a última verificação.") -> None:
        if not hasattr(self, "project_preflight_title"):
            return
        missing = self._project_missing_requirements()
        if missing:
            self.project_preflight_badge.set("Precisa de atenção")
            self._set_project_status_style("preflight", "warning")
            self.project_preflight_title.set("Ainda não dá para validar o projeto completo.")
            self.project_preflight_detail.set(" • ".join(missing))
        else:
            self.project_preflight_badge.set("Pronto para verificar")
            self._set_project_status_style("preflight", "active")
            self.project_preflight_title.set("Os requisitos básicos estão presentes.")
            self.project_preflight_detail.set(reason + " Clique em ‘Verificar agora’ para recalcular espaço, VRAM e avisos de qualidade.")
        if hasattr(self, "project_preflight_button"):
            self.project_preflight_button.configure(state="normal")

    def _request_project_preflight(self) -> None:
        missing = self._project_missing_requirements()
        if missing:
            self.project_preflight_badge.set("Bloqueado")
            self._set_project_status_style("preflight", "error")
            self.project_preflight_title.set("Corrija os itens básicos antes da verificação detalhada.")
            detail = " • ".join(missing)
            self.project_preflight_detail.set(detail)
            self._set_feedback(
                "error", "Projeto ainda não pode ser verificado", detail,
                category="Projeto", primary=("Rever projeto", lambda: self._open_tab(1)),
            )
            return
        self._project_preflight_serial += 1
        serial = self._project_preflight_serial
        settings = self._settings()
        self.project_preflight_badge.set("Verificando…")
        self._set_project_status_style("preflight", "active")
        self.project_preflight_title.set("Analisando mídia, espaço, VRAM e compatibilidade da saída…")
        self.project_preflight_detail.set("Isso acontece em segundo plano; você pode continuar navegando pelo CinePulse.")
        self._set_feedback(
            "busy", "Verificando a saúde do projeto",
            "Analisando mídia, espaço em disco, VRAM e compatibilidade sem iniciar o render.",
            category="Projeto", record=False,
        )
        if hasattr(self, "project_preflight_button"):
            self.project_preflight_button.configure(state="disabled")

        def worker() -> None:
            try:
                report = self._preflight_report(settings, False)
                self._events.put(("project_preflight", serial, report, ""))
            except Exception as exc:
                self._events.put(("project_preflight", serial, None, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_project_preflight_report(self, report: dict | None, error: str = "") -> None:
        if hasattr(self, "project_preflight_button"):
            self.project_preflight_button.configure(state="normal")
        if error or report is None:
            self.project_preflight_badge.set("Falha na verificação")
            self._set_project_status_style("preflight", "error")
            self.project_preflight_title.set("Não foi possível concluir a pré-verificação.")
            detail = error or "O relatório não retornou dados válidos."
            self.project_preflight_detail.set(detail)
            self._set_feedback(
                "error", "Pré-verificação não concluída",
                "O projeto não foi liberado por esta tentativa de verificação. Os arquivos de entrada não foram alterados.",
                category="Projeto", primary=("Rever projeto", lambda: self._open_tab(1)),
                secondary=("Ver log", self._show_log), technical_detail=detail,
            )
            return
        warnings = list(report.get("warnings") or [])
        blocking = bool(report.get("blocking"))
        output_gb = float(report.get("output_gb") or 0.0)
        temp_gb = float(report.get("temp_gb") or 0.0)
        if blocking:
            self.project_preflight_badge.set("Bloqueado")
            self._set_project_status_style("preflight", "error")
            self.project_preflight_title.set("O render final está bloqueado pela verificação de armazenamento.")
            reasons = list(report.get("blocking_reasons") or [])
            detail = " • ".join(reasons[:3]) or "Há um bloqueio de armazenamento."
            self.project_preflight_detail.set(detail)
            self._set_feedback(
                "error", "Render bloqueado pela pré-verificação", detail,
                category="Projeto", primary=("Rever projeto", lambda: self._open_tab(1)),
            )
        elif warnings:
            self.project_preflight_badge.set(f"Pronto com {len(warnings)} aviso(s)")
            self._set_project_status_style("preflight", "warning")
            self.project_preflight_title.set(f"Projeto processável • saída ~{output_gb:.2f} GB • temporários ~{temp_gb:.2f} GB")
            detail = "Avisos principais: " + " • ".join(warnings[:3])
            self.project_preflight_detail.set(detail)
            self._set_feedback(
                "warning", f"Projeto pronto com {len(warnings)} aviso(s)", detail,
                category="Projeto", primary=("Rever qualidade", lambda: self._open_tab(2)),
            )
        else:
            self.project_preflight_badge.set("✓ Projeto pronto")
            self._set_project_status_style("preflight", "ok")
            self.project_preflight_title.set(f"Sem bloqueios ou avisos • saída ~{output_gb:.2f} GB • temporários ~{temp_gb:.2f} GB")
            detail = "A configuração atual passou pela verificação detalhada. Gere um preview renderizado antes do vídeo final."
            self.project_preflight_detail.set(detail)
            self._set_feedback(
                "success", "Projeto passou pela pré-verificação", detail,
                category="Projeto", primary=("Gerar preview", lambda: self._start(True)),
            )

    def _choose_video(self) -> None:
        path = filedialog.askopenfilename(title="Selecione o vídeo", filetypes=[("Vídeos", "*.mp4 *.mov *.mkv *.webm *.avi"), ("Todos", "*.*")])
        if path:
            self.video.set(path)
            self._suggest_output()
            self._schedule_home_preview(source_changed=True)
            self._schedule_visual_preview(source_changed=True)
            self._inspect_project_video(path)
            self._refresh_project_output_state()
            self._mark_project_preflight_stale("Vídeo alterado; atualize a verificação detalhada.")

    def _choose_audio(self) -> None:
        path = filedialog.askopenfilename(title="Selecione a música", filetypes=[("Áudio", "*.wav *.flac *.mp3 *.m4a *.aac *.ogg"), ("Todos", "*.*")])
        if path:
            self.audio.set(path)
            self._suggest_output()
            self._inspect_project_audio(path)
            self._refresh_project_output_state()
            self._update_summary()

    def _choose_output(self) -> None:
        current = self.output.get() or "video_otimizado.mp4"
        preferred_ext = suggested_extension(self.delivery_profile.get(), Path(current).suffix or ".mp4")
        path = filedialog.asksaveasfilename(
            title="Salvar vídeo final", defaultextension=preferred_ext, initialdir=str(Path(current).parent),
            initialfile=Path(current).name, filetypes=[
                ("MP4 — streaming", "*.mp4"), ("MOV — master", "*.mov"),
                ("MKV — arquivo", "*.mkv"), ("WebM — web", "*.webm"), ("Todos", "*.*"),
            ],
        )
        if path:
            self.output.set(path)
            self._refresh_project_output_state()
            self._mark_project_preflight_stale("Destino alterado; atualize a verificação detalhada.")
            self._refresh_quality_impact()

    def _choose_scratch_dir(self) -> None:
        current = resolve_scratch_dir(self.scratch_dir.get(), WORK_DIR)
        path = filedialog.askdirectory(title="Escolha o disco/pasta de temporários", initialdir=str(current))
        if path:
            self.scratch_dir.set(path)
            self._mark_project_preflight_stale("Disco scratch alterado; atualize a verificação detalhada.")
            self._quality_setting_changed()

    def _choose_color(self) -> None:
        _rgb, value = colorchooser.askcolor(color=self.color.get(), title="Cor principal dos VFX")
        if value:
            self.color.set(value.upper())
            self.color_swatch.configure(background=value)
            self._refresh_effect_thumbnail_colors()
            self._update_summary()

    def _refresh_effect_thumbnail_colors(self) -> None:
        """Keep discovery cards consistent with the selected VFX color."""
        color = self.color.get()
        for name, button in getattr(self, "_home_effect_buttons", {}).items():
            photo = PhotoImage(data=to_ppm_bytes(effect_thumbnail(name, color, 160, 90)), format="PPM")
            self._home_effect_photos[name] = photo
            button.configure(image=photo)
        for name, button in getattr(self, "_visual_effect_buttons", {}).items():
            photo = PhotoImage(data=to_ppm_bytes(effect_thumbnail(name, color, 112, 63)), format="PPM")
            self._visual_effect_photos[name] = photo
            button.configure(image=photo)

    def _suggest_output(self) -> None:
        if self.output.get() or not self.video.get():
            return
        source = Path(self.video.get())
        suffix = "musical" if self.mode.get() == MODE_MUSIC else "otimizado"
        self.output.set(str(source.with_name(f"{source.stem}_{suffix}.mp4")))

    def _update_mode(self) -> None:
        music = self.mode.get() == MODE_MUSIC
        state = "normal" if music else "disabled"
        self.audio_entry.configure(state=state)
        self.audio_button.configure(state=state)
        if hasattr(self, "home_audio_entry"):
            self.home_audio_entry.configure(state=state)
        if hasattr(self, "home_audio_button"):
            self.home_audio_button.configure(state=state)
        # Keep the label legible in both themes; disabled widgets already convey state.
        if hasattr(self, "audio_label"):
            self.audio_label.configure(style="Card.TLabel" if hasattr(self, "project_video_entry") else "TLabel")
        self._refresh_project_mode_buttons()
        if music:
            audio = self.audio.get().strip()
            if audio and Path(audio).is_file():
                self._inspect_project_audio(audio)
            else:
                self.project_audio_badge.set("Aguardando música")
                self._set_project_status_style("audio", "muted")
                self.project_audio_headline.set("Selecione a música que define a duração do projeto.")
                self.project_audio_detail.set("WAV ou FLAC são recomendados para preservar melhor a fonte.")
        else:
            self.project_audio_badge.set("Não usado neste modo")
            self._set_project_status_style("audio", "muted")
            self.project_audio_headline.set("O modo Melhorar vídeo original não exige uma música separada.")
            self.project_audio_detail.set("A opção de preservar o áudio original continua disponível em Qualidade e saída.")
        self._refresh_project_output_state()
        self._update_summary()

    def _selected_effects(self) -> set[str]:
        return {name for name, variable in self.effect_vars.items() if variable.get()}

    def _apply_visual_direction(self) -> None:
        values = VISUAL_DIRECTIONS.get(self.visual_direction.get())
        if values is None:
            self.status.set("Direção personalizada: os controles permanecem livres.")
            return
        focus, smoothing, expression, sections, intensity = values
        self.audio_focus.set(focus)
        self.reaction_smoothing.set(smoothing)
        self.reaction_expression.set(expression)
        self.section_dynamics.set(sections)
        self.intensity.set(intensity)
        self.dynamic_sections.set(True)
        self._visual_scale_changed()
        self.status.set(f"Direção musical aplicada: {self.visual_direction.get()}")

    def _target_size(self, resolution: str, aspect: str, source_size: tuple[int, int] | None = None) -> tuple[int, int]:
        width, height = RESOLUTIONS[resolution]
        if aspect == ASPECT_PORTRAIT:
            return height, width
        if aspect == ASPECT_IMAX:
            return width, max(2, round((width / 1.90) / 2) * 2)
        if aspect == ASPECT_WIDE:
            return width, max(2, round((width / 2.39) / 2) * 2)
        if aspect == ASPECT_ORIGINAL and source_size:
            source_w, source_h = source_size
            long_edge = max(width, height)
            if source_w >= source_h:
                out_w = long_edge
                out_h = max(2, round(out_w * source_h / source_w / 2) * 2)
            else:
                out_h = long_edge
                out_w = max(2, round(out_h * source_w / source_h / 2) * 2)
            return out_w, out_h
        return width, height

    def _update_summary(self) -> None:
        effects = self._selected_effects()
        effect_text = ", ".join(sorted(effects)) if effects else "sem VFX"
        self.summary.set(
            f"{self.resolution.get()} • {self.fps.get()} fps • {self.aspect.get()} • "
            f"{self.enhancement.get()} • {self.fit_mode.get()} • {effect_text} • "
            f"intensidade {self.intensity.get():.0f}% • área {self.occupancy.get():.0f}% • "
            f"reação: {self.audio_focus.get()}, suavização {self.reaction_smoothing.get():.0f}%, "
            f"expressividade {self.reaction_expression.get():.0f}% • "
            f"seções {self.section_dynamics.get():.0f}% • "
            f"stems {'Demucs' if self.use_stems.get() else 'desativados'} • "
            f"loop {'automático' if self.auto_loop.get() else 'manual'} • "
            f"entrega: {self.delivery_profile.get()} • verificação {'profunda' if self.deep_verify.get() else 'rápida'} • áudio: {self.audio_mode.get()} • {self.interpolation.get()} • "
            f"{'Somente CPU' if self.use_cpu.get() else 'Aceleração automática'}"
        )
        self._refresh_preset_state()
        self._refresh_home_effect_button_states() if hasattr(self, "_home_effect_buttons") else None
        self._refresh_visual_effect_button_states() if hasattr(self, "_visual_effect_buttons") else None
        self._refresh_visual_direction_buttons() if hasattr(self, "_visual_direction_buttons") else None
        self._refresh_visual_transition_buttons() if hasattr(self, "_visual_transition_buttons") else None
        if hasattr(self, "_home_transition_buttons"):
            labels = {
                "Corte seco — original": "Corte seco",
                "Dissolver suave": "Dissolver",
                "Fade cinematográfico": "Fade cinema",
            }
            for key, button in self._home_transition_buttons.items():
                selected = self.transition.get() == key
                button.configure(
                    text=("✓ " if selected else "") + labels.get(key, key),
                    style="Selected.Ghost.TButton" if selected else "Ghost.TButton",
                )
        self._schedule_home_preview()
        self._schedule_visual_preview()
        if hasattr(self, "project_framing_label"):
            self._refresh_project_fit_buttons()
            self._refresh_project_framing_sync()
            self._refresh_project_output_state()
            self._mark_project_preflight_stale()
        if hasattr(self, "quality_load_badge_label"):
            self._refresh_quality_controls()
            self._refresh_quality_impact()

    def _settings(self) -> RenderSettings:
        return RenderSettings(
            mode=self.mode.get(), video=self.video.get().strip(), audio=self.audio.get().strip(),
            output=self.output.get().strip(), resolution=self.resolution.get(), fps=int(self.fps.get()),
            aspect=self.aspect.get(), enhancement=self.enhancement.get(), fit_mode=self.fit_mode.get(),
            use_cpu=self.use_cpu.get(), preserve_audio=self.preserve_audio.get(),
            effects=self._selected_effects(), color=self.color.get(), intensity=float(self.intensity.get()) / 100.0,
            occupancy=float(self.occupancy.get()) / 100.0, audio_focus=self.audio_focus.get(),
            reaction_smoothing=float(self.reaction_smoothing.get()) / 100.0,
            reaction_expression=float(self.reaction_expression.get()) / 100.0,
            auto_loop=self.auto_loop.get(), dynamic_sections=self.dynamic_sections.get(),
            section_dynamics=float(self.section_dynamics.get()) / 100.0,
            transition=self.transition.get(),
            transition_duration=float(self.transition_duration.get()), preview_seconds=max(1, min(30, int(self.preview_seconds.get()))),
            audio_mode=self.audio_mode.get(), interpolation=self.interpolation.get(),
            cpu_threads=max(1, int(self.cpu_threads.get())), minimum_free_gb=max(1.0, float(self.minimum_free_gb.get())),
            scratch_dir=self.scratch_dir.get().strip(), cache_quota_gb=max(1.0, float(self.cache_quota_gb.get())),
            quality_check=self.quality_check.get(), deep_verify=self.deep_verify.get(), visual_direction=self.visual_direction.get(),
            comparison_preview=self.comparison_preview.get(),
            use_stems=self.use_stems.get(),
            delivery_profile=self.delivery_profile.get(),
        )

    @staticmethod
    def _normalized_enhancement_mode(value: str) -> str:
        if value == ENHANCE_AI:
            return "realesrgan"
        if value == ENHANCE_SIMPLE:
            return "lanczos"
        return "preserve"

    @staticmethod
    def _normalized_interpolation_mode(value: str) -> str:
        if value == RIFE_OPTION:
            return "rife"
        if value == "Quadros repetidos — rápido":
            return "repeat"
        return "ffmpeg"

    def _ai_upscale_required(self, settings: RenderSettings, preview: bool = False) -> bool:
        """Return whether the requested framing actually needs neural upscale.

        Missing/unreadable media returns ``True`` conservatively so validation
        never hides a required component merely because probing failed.
        """

        try:
            info = probe_media(settings.video)
            source_w, source_h = first_video_size(info)
            target_w, target_h = self._target_size(settings.resolution, settings.aspect, (source_w, source_h))
            if preview:
                target_w, target_h = self._target_size("720p HD", settings.aspect, (source_w, source_h))
            fit_mode = "cover" if settings.fit_mode == FIT_COVER else "contain"
            return spatial_scale_factor(source_w, source_h, target_w, target_h, fit_mode) > 1.0001
        except Exception:
            return True

    def _build_render_plan(
        self,
        settings: RenderSettings,
        *,
        preview: bool,
        source_w: int,
        source_h: int,
        source_fps: float,
        target_w: int,
        target_h: int,
        target_fps: float,
        color_profile: ColorProfile,
        transition_active: bool | None = None,
        auto_loop_may_add_transition: bool | None = None,
    ) -> RenderPlan:
        """Build the single render decision model used by UI, preflight and worker.

        Core Integrity Phase 2 makes the policy target-aware: the final master
        preserves requested spatial/temporal fidelity, AI only runs when an
        upscale is actually needed, and RIFE is never used to rebuild FPS that
        the source already contained.
        """

        if transition_active is None:
            transition_active = settings.mode == MODE_MUSIC and TRANSITIONS.get(settings.transition) is not None
        if auto_loop_may_add_transition is None:
            auto_loop_may_add_transition = (
                settings.mode == MODE_MUSIC
                and settings.auto_loop
                and TRANSITIONS.get(settings.transition) is None
            )
        return build_render_plan(
            PlanInput(
                source_width=source_w,
                source_height=source_h,
                source_fps=float(source_fps),
                target_width=target_w,
                target_height=target_h,
                target_fps=float(target_fps),
                project_mode="music" if settings.mode == MODE_MUSIC else "original",
                preview=preview,
                enhancement_mode=self._normalized_enhancement_mode(settings.enhancement),
                interpolation_mode=self._normalized_interpolation_mode(settings.interpolation),
                effects_active=bool(settings.effects),
                transition_active=bool(transition_active),
                use_cpu=settings.use_cpu,
                fit_mode="cover" if settings.fit_mode == FIT_COVER else "contain",
                source_hdr=color_profile.hdr,
                source_bit_depth=color_profile.bit_depth,
                source_pixel_format=f"{color_profile.pixel_format} {color_profile.bit_depth}-bit",
                source_primaries=color_profile.primaries,
                source_transfer=color_profile.transfer,
                source_space=color_profile.space,
                source_range=color_profile.range,
                realesrgan_available=REAL_ESRGAN.is_file(),
                rife_available=RIFE_EXE.is_file(),
                auto_loop_may_add_transition=bool(auto_loop_may_add_transition),
                output_suffix=(".mp4" if preview else (Path(settings.output).suffix.lower() or ".mp4")),
                delivery_profile=settings.delivery_profile,
            )
        )

    def _build_delivery_contract(
        self,
        settings: RenderSettings,
        *,
        preview: bool,
        source_color: ColorProfile,
        target_w: int,
        target_h: int,
        target_fps: float,
        render_plan: RenderPlan,
        transition_active: bool | None = None,
    ) -> DeliveryPlan:
        if transition_active is None:
            transition_active = settings.mode == MODE_MUSIC and TRANSITIONS.get(settings.transition) is not None
        color_plan = build_color_pipeline(
            source_color,
            effects_active=bool(settings.effects),
            transition_active=bool(transition_active),
            enhancement_mode=self._normalized_enhancement_mode(settings.enhancement),
            rife_active=(
                render_plan.step("rife_base").attempts or render_plan.step("rife_final").attempts
            ) and settings.interpolation == RIFE_OPTION,
        )
        return build_delivery_plan(
            output="preview.mp4" if preview else settings.output,
            profile=settings.delivery_profile,
            color_plan=color_plan,
            width=target_w, height=target_h, fps=target_fps, preview=preview,
            use_cpu=settings.use_cpu, nvenc_available=self._nvenc,
            available_encoders=detect_ffmpeg_encoders(FFMPEG),
        )

    @staticmethod
    def _estimated_bitrate_mbps(width: int, height: int, fps: int) -> int:
        pixels_ratio = width * height / (1920 * 1080)
        return max(8, min(600, round(12 * pixels_ratio * max(1, fps / 60))))

    def _preflight_report(self, settings: RenderSettings, preview: bool) -> dict:
        video_info = probe_media(settings.video)
        color_profile = ColorProfile.from_probe(video_info)
        source_w, source_h = first_video_size(video_info)
        source_fps = first_video_fps(video_info)
        source_duration = media_duration(video_info)
        if settings.mode == MODE_MUSIC:
            project_duration = media_duration(probe_media(settings.audio))
        else:
            project_duration = source_duration
        if preview:
            project_duration = min(project_duration, settings.preview_seconds)
        target_w, target_h = self._target_size(settings.resolution, settings.aspect, (source_w, source_h))
        target_fps = settings.fps
        if preview:
            target_w, target_h = self._target_size("720p HD", settings.aspect, (source_w, source_h))
            target_fps = min(60, target_fps)
        render_plan = self._build_render_plan(
            settings,
            preview=preview,
            source_w=source_w,
            source_h=source_h,
            source_fps=source_fps,
            target_w=target_w,
            target_h=target_h,
            target_fps=target_fps,
            color_profile=color_profile,
        )
        delivery_plan = self._build_delivery_contract(
            settings, preview=preview, source_color=color_profile,
            target_w=target_w, target_h=target_h, target_fps=target_fps, render_plan=render_plan,
        )
        bitrate = self._estimated_bitrate_mbps(target_w, target_h, target_fps)
        output_gb = bitrate * project_duration / 8 / 1024 * 1.08
        scratch_path = resolve_scratch_dir(settings.scratch_dir, WORK_DIR)
        cache_current_gb = cache_usage_bytes(PATHS.cache) / (1024 ** 3)
        storage_estimate = estimate_storage(
            render_plan,
            clip_duration=source_duration,
            project_duration=project_duration,
            output_gb=output_gb,
            cache_current_gb=cache_current_gb,
            cache_quota_gb=settings.cache_quota_gb,
        )
        temp_gb = storage_estimate.peak_scratch_gb
        output_path = Path(settings.output).expanduser() if settings.output else PREVIEW_DIR / "preview.mp4"
        storage = build_storage_plan(
            output_path,
            scratch_path,
            output_gb,
            temp_gb,
            settings.minimum_free_gb,
            cache=PATHS.cache,
            cache_growth_gb=storage_estimate.cache_growth_gb,
        )
        scratch_probe = probe_scratch(scratch_path)
        warnings: list[str] = []
        if cache_current_gb > settings.cache_quota_gb:
            warnings.append(
                f"O cache atual ({cache_current_gb:.2f} GB) excede a quota de {settings.cache_quota_gb:.0f} GB; "
                "a política LRU removerá entradas antigas antes do render."
            )
        if scratch_probe.write_mbps is not None and scratch_probe.write_mbps < 80:
            warnings.append(
                f"O scratch respondeu a ~{scratch_probe.write_mbps:.0f} MB/s na amostra rápida; "
                "IA/RIFE podem ficar limitados pelo disco."
            )
        warnings.extend(preflight_quality_warnings(
            source_w, source_h, source_fps, target_w, target_h, target_fps,
            self._hardware.vram_mb,
            render_plan.step("enhancement").attempts and settings.enhancement == ENHANCE_AI,
            render_plan.step("rife_final").attempts and settings.interpolation == RIFE_OPTION,
        ))
        warnings.extend(risks_as_warnings(render_plan.risks))
        warnings.extend(delivery_plan.warnings)
        if not settings.use_cpu and not self._nvenc and max(target_w, target_h) <= 8192:
            warnings.append("A aceleração NVIDIA não foi detectada; a codificação usará CPU e será mais lenta.")
        if settings.mode == MODE_MUSIC and Path(settings.audio).suffix.lower() not in {".wav", ".flac"}:
            warnings.append("Para preservar melhor a música, prefira WAV ou FLAC como fonte.")
        if render_plan.step("rife_final").attempts and settings.interpolation == RIFE_OPTION and not RIFE_EXE.is_file():
            warnings.append("RIFE é necessário para atingir o FPS solicitado, mas não foi encontrado; o render usará fallback FFmpeg.")
        blocking_reasons = list(storage.blocking_reasons)
        blocking_reasons.extend(delivery_plan.errors)
        blocking = bool(blocking_reasons)
        lines = [
            "PRÉ-VERIFICAÇÃO DO PROJETO",
            "",
            f"Fonte: {source_w}×{source_h} • {source_fps:.2f} fps • {format_time(source_duration)}",
            f"Cor da fonte: {color_profile.label}",
            f"Destino: {target_w}×{target_h} • {target_fps} fps • {format_time(project_duration)}",
            f"Entrega: {delivery_plan.label} • perfil {delivery_plan.profile}",
            f"Saída estimada: {output_gb:.2f} GB",
            f"Pico scratch estimado: {temp_gb:.2f} GB",
            f"Duração materializada do clipe: {format_time(storage_estimate.clip_duration_seconds)}",
            f"Duração do projeto final: {format_time(storage_estimate.project_duration_seconds)}",
            f"Scratch: {scratch_path}",
            f"Volume scratch: {scratch_probe.volume} • {scratch_probe.free_gb:.1f}/{scratch_probe.total_gb:.1f} GB livres"
            + (f" • escrita ~{scratch_probe.write_mbps:.0f} MB/s (amostra rápida)" if scratch_probe.write_mbps is not None else " • velocidade não medida"),
            f"Espaço livre na saída: {storage.output_free_gb:.2f} GB",
            f"Espaço livre no scratch: {storage.temporary_free_gb:.2f} GB • reserva: {settings.minimum_free_gb:.0f} GB",
            f"Cache: {cache_current_gb:.2f}/{settings.cache_quota_gb:.0f} GB • crescimento previsto até ~{storage_estimate.cache_growth_gb:.2f} GB",
            f"Lotes neurais: Real-ESRGAN até {storage_estimate.ai_chunk_frames} frames • RIFE até {storage_estimate.rife_chunk_frames} frames",
            f"Processamento: {'Somente CPU' if settings.use_cpu else 'Aceleração automática'} • até {settings.cpu_threads} threads de CPU",
            f"Hardware: {self._hardware.gpu or self._hardware.cpu} • perfil sugerido {self._hardware.quality_tier}",
            "",
            f"PLANO REAL DO PIPELINE • {render_plan.fingerprint}",
        ] + render_plan.user_lines()
        if storage_estimate.stages:
            lines += ["", "ARMAZENAMENTO POR ETAPA:"] + [f"• {stage.line()}" for stage in storage_estimate.stages]
        if warnings:
            lines += ["", "Avisos:"] + [f"• {warning}" for warning in warnings]
        if blocking:
            lines += ["", "BLOQUEADO:"] + [f"• {reason}" for reason in blocking_reasons]
        elif not warnings:
            lines += ["", "Projeto pronto para processar."]
        return {
            "text": "\n".join(lines), "warnings": warnings, "blocking": blocking,
            "output_gb": output_gb, "temp_gb": temp_gb,
            "free_gb": storage.output_free_gb,
            "blocking_reasons": blocking_reasons,
            "render_plan": render_plan.to_dict(),
            "render_plan_fingerprint": render_plan.fingerprint,
            "delivery_plan": delivery_plan,
            "storage_estimate": asdict(storage_estimate),
            "scratch_dir": str(scratch_path),
            "cache_current_gb": cache_current_gb,
            "cache_quota_gb": settings.cache_quota_gb,
            "scratch_probe": asdict(scratch_probe),
        }

    def _show_preflight(self) -> None:
        settings = self._settings()
        if not self._validate(settings, False):
            return
        try:
            report = self._preflight_report(settings, False)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Não foi possível verificar o projeto.\n\n{exc}")
            return
        if report["blocking"]:
            messagebox.showerror(APP_TITLE, report["text"])
        else:
            messagebox.showinfo(APP_TITLE, report["text"])

    def _confirm_preflight(self, settings: RenderSettings, preview: bool) -> bool:
        try:
            report = self._preflight_report(settings, preview)
        except Exception as exc:
            self._set_feedback(
                "error", "Pré-verificação falhou",
                "O processamento não foi iniciado porque a validação não pôde ser concluída.",
                category="Projeto", primary=("Rever projeto", lambda: self._open_tab(1)),
                secondary=("Ver log", self._show_log), technical_detail=str(exc),
            )
            messagebox.showerror(APP_TITLE, f"A pré-verificação falhou.\n\n{exc}")
            return False
        self._log(report["text"].replace("\n", " | "))
        if report["blocking"]:
            reasons = " • ".join(report.get("blocking_reasons") or []) or "A pré-verificação encontrou um bloqueio."
            self._set_feedback(
                "error", "Processamento bloqueado pela pré-verificação", reasons,
                category="Projeto", primary=("Rever projeto", lambda: self._open_tab(1)),
            )
            messagebox.showerror(APP_TITLE, report["text"])
            return False
        if not preview and report["warnings"]:
            warning_detail = " • ".join(report["warnings"][:3])
            self._set_feedback(
                "warning", f"Pré-verificação encontrou {len(report['warnings'])} aviso(s)", warning_detail,
                category="Projeto", primary=("Rever qualidade", lambda: self._open_tab(2)),
            )
            return messagebox.askyesno(APP_TITLE, report["text"] + "\n\nDeseja continuar?")
        return True

    def _validate(self, settings: RenderSettings, preview: bool) -> bool:
        if not FFMPEG or not FFPROBE:
            detail = "FFmpeg e FFprobe não foram encontrados. O processamento não pode iniciar sem as ferramentas obrigatórias."
            self._set_feedback(
                "error", "Ferramentas obrigatórias ausentes", detail, category="Sistema",
                primary=("Componentes", self._install_components), secondary=("Diagnóstico", self._create_diagnostics),
            )
            messagebox.showerror(APP_TITLE, "FFmpeg e FFprobe não foram encontrados.")
            return False
        if not settings.video or not Path(settings.video).is_file():
            self._set_feedback(
                "error", "Vídeo de entrada inválido",
                "Selecione um arquivo de vídeo existente antes de continuar.",
                category="Projeto", primary=("Rever projeto", lambda: self._open_tab(1)),
            )
            messagebox.showwarning(APP_TITLE, "Selecione um vídeo válido.")
            return False
        if settings.mode == MODE_MUSIC and (not settings.audio or not Path(settings.audio).is_file()):
            self._set_feedback(
                "error", "Música do loop ausente",
                "O modo Loop musical precisa de um arquivo de áudio existente para definir a duração do projeto.",
                category="Projeto", primary=("Rever projeto", lambda: self._open_tab(1)),
            )
            messagebox.showwarning(APP_TITLE, "Selecione a música do projeto.")
            return False
        if not preview and not settings.output:
            self._set_feedback(
                "error", "Destino do vídeo final ausente",
                "Escolha onde o CinePulse deve gravar o resultado final.",
                category="Projeto", primary=("Rever destino", lambda: self._open_tab(1)),
            )
            messagebox.showwarning(APP_TITLE, "Escolha onde salvar o vídeo.")
            return False
        if not preview:
            path_errors = validate_output_path(
                Path(settings.output),
                tuple(Path(value) for value in (settings.video, settings.audio) if value),
            )
            if path_errors:
                detail = " • ".join(path_errors)
                self._set_feedback(
                    "error", "Destino de saída inválido", detail, category="Projeto",
                    primary=("Rever destino", lambda: self._open_tab(1)),
                )
                messagebox.showerror(APP_TITLE, "\n".join(path_errors))
                return False
        try:
            check_directory_writable(Path(settings.output) if not preview else PREVIEW_DIR / "preview.mp4")
            scratch_path = resolve_scratch_dir(settings.scratch_dir, WORK_DIR)
            scratch_path.mkdir(parents=True, exist_ok=True)
            check_directory_writable(scratch_path / "render.tmp")
        except OSError as exc:
            self._set_feedback(
                "error", "Sem acesso de gravação",
                "O CinePulse não consegue gravar a saída ou os temporários no caminho atual.",
                category="Projeto", primary=("Rever destino", lambda: self._open_tab(1)),
                secondary=("Diagnóstico", self._create_diagnostics), technical_detail=str(exc),
            )
            messagebox.showerror(APP_TITLE, f"O CinePulse não consegue gravar os arquivos necessários.\n\n{exc}")
            return False
        ai_upscale_required = settings.enhancement == ENHANCE_AI and self._ai_upscale_required(settings, preview)
        if ai_upscale_required and not REAL_ESRGAN.is_file():
            self._set_feedback(
                "error", "Real-ESRGAN necessário para esta configuração",
                "O upscale por IA foi selecionado, mas o componente local não está instalado.",
                category="IA local", primary=("Abrir IA local", lambda: self._open_tab(5)),
            )
            messagebox.showerror(APP_TITLE, "O módulo local Real-ESRGAN não foi encontrado.")
            return False
        if settings.use_cpu and ai_upscale_required:
            self._set_feedback(
                "error", "Upscale por IA requer GPU neste pipeline",
                "Troque para Lanczos para usar somente CPU ou reative o processamento por GPU.",
                category="Qualidade", primary=("Rever qualidade", lambda: self._open_tab(2)),
            )
            messagebox.showerror(APP_TITLE, "O Real-ESRGAN local usa a GPU. Escolha upscale simples para usar somente CPU.")
            return False
        return True

    def _add_to_queue(self) -> None:
        if self._busy:
            return
        settings = self._settings()
        if not self._validate(settings, False):
            return
        if not self._confirm_preflight(settings, False):
            return
        output = Path(settings.output)
        if output.exists() and not messagebox.askyesno(
            APP_TITLE,
            f"O arquivo já existe e será substituído quando a fila chegar nele:\n\n{output}\n\nAdicionar mesmo assim?",
        ):
            return
        resolved = str(output.resolve()).lower()
        if any(str(Path(item["settings"].output).resolve()).lower() == resolved for item in self._queue_items):
            messagebox.showwarning(APP_TITLE, "Já existe um item na fila usando esse mesmo arquivo de saída.")
            return
        self._queue_serial += 1
        self._queue_items.append({
            "id": self._queue_serial,
            "settings": settings,
            "status": "Aguardando",
            "error": "",
            "report": "",
            "history": "",
            "progress": 0.0,
            "stage": "Aguardando na fila",
        })
        self._save_queue()
        self._refresh_queue_tree(select_id=self._queue_serial)
        self.status.set(f"Projeto adicionado à fila. Total: {len(self._queue_items)}")

    def _selected_queue_item(self) -> dict | None:
        if not hasattr(self, "queue_tree"):
            return None
        selected = self.queue_tree.selection()
        if not selected:
            return None
        try:
            selected_id = int(selected[0])
        except (TypeError, ValueError):
            return None
        return next((item for item in self._queue_items if int(item["id"]) == selected_id), None)

    def _refresh_queue_overview(self) -> None:
        summary = summarize_queue(self._queue_items)
        self.queue_waiting_text.set(str(summary.waiting))
        self.queue_active_text.set(str(summary.active))
        self.queue_done_text.set(str(summary.done))
        self.queue_attention_text.set(str(summary.attention))
        if summary.total == 0:
            self.queue_overview_text.set("Nenhum projeto aguardando processamento.")
            self.queue_empty_text.set("Adicione um projeto usando ‘Adicionar à fila’ no rodapé. A fila é salva automaticamente.")
        else:
            self.queue_empty_text.set("")
            if summary.active:
                self.queue_overview_text.set(f"{summary.total} projeto(s) • processamento em andamento • {summary.remaining} ainda exigem ação/processamento")
            elif summary.remaining:
                self.queue_overview_text.set(f"{summary.total} projeto(s) • {summary.remaining} ainda não concluído(s)")
            else:
                self.queue_overview_text.set(f"{summary.total} projeto(s) • todos concluídos")
        if hasattr(self, "start_queue_button"):
            can_start = (not self._busy and not self._queue_running and summary.remaining > 0)
            self.start_queue_button.configure(state="normal" if can_start else "disabled")
        if hasattr(self, "queue_stop_button"):
            self.queue_stop_button.configure(state="normal" if self._queue_running else "disabled")

    def _set_queue_selected_badge_style(self, status: str) -> None:
        if not hasattr(self, "queue_selected_badge_label"):
            return
        if status == "Concluído":
            style = "StatusOk.TLabel"
        elif status == "Renderizando":
            style = "CardStatus.TLabel"
        elif status in ATTENTION_STATUSES:
            style = "StatusWarning.TLabel" if status != "Erro" else "StatusError.TLabel"
        else:
            style = "StatusMuted.TLabel"
        self.queue_selected_badge_label.configure(style=style)

    def _refresh_queue_selected_detail(self) -> None:
        item = self._selected_queue_item()
        if item is None:
            self.queue_selected_badge.set("Nenhum item")
            self.queue_selected_title.set("Selecione um projeto para ver os detalhes.")
            self.queue_selected_profile.set("Arquivos, perfil, VFX e último estado aparecem aqui.")
            self.queue_selected_input.set("—")
            self.queue_selected_output.set("—")
            self.queue_selected_processing.set("—")
            self.queue_selected_effects.set("—")
            self.queue_selected_note.set("Nenhum detalhe registrado.")
            self.queue_selected_stage.set("Aguardando seleção")
            self.queue_selected_progress.set(0.0)
            self.queue_selected_progress_text.set("0%")
            self._set_queue_selected_badge_style("")
            return
        settings: RenderSettings = item["settings"]
        status = queue_normalize_status(item.get("status"))
        progress = queue_item_progress(item)
        self.queue_selected_badge.set(queue_status_text(item))
        self.queue_selected_title.set(queue_project_name(settings))
        self.queue_selected_profile.set(queue_profile_text(settings))
        self.queue_selected_input.set(str(settings.video) or "—")
        self.queue_selected_output.set(str(settings.output) or "—")
        self.queue_selected_processing.set(queue_processing_text(settings))
        self.queue_selected_effects.set(queue_effects_text(settings))
        note = str(item.get("error") or item.get("report") or "Nenhum erro ou relatório registrado ainda.")
        self.queue_selected_note.set(note)
        self.queue_selected_stage.set(str(item.get("stage") or status))
        self.queue_selected_progress.set(progress)
        self.queue_selected_progress_text.set(f"{progress:.0f}%")
        self._set_queue_selected_badge_style(status)

    def _queue_selection_changed(self, _event=None) -> None:
        self._refresh_queue_selected_detail()

    def _refresh_queue_tree(self, select_id: int | None = None) -> None:
        if not hasattr(self, "queue_tree"):
            return
        previous = self.queue_tree.selection()
        previous_id = previous[0] if previous else None
        for item_id in self.queue_tree.get_children():
            self.queue_tree.delete(item_id)
        # Semantic colors are supplementary to the textual state, never the only signal.
        self.queue_tree.tag_configure("done", foreground=COLORS["success"])
        self.queue_tree.tag_configure("active", foreground=COLORS["primary"])
        self.queue_tree.tag_configure("attention", foreground=COLORS["warning"])
        self.queue_tree.tag_configure("error", foreground=COLORS["danger"])
        for position, item in enumerate(self._queue_items, start=1):
            settings: RenderSettings = item["settings"]
            status = queue_normalize_status(item.get("status"))
            progress = queue_item_progress(item)
            tag = (
                "done" if status == "Concluído" else
                "active" if status == "Renderizando" else
                "error" if status == "Erro" else
                "attention" if status in ATTENTION_STATUSES else ""
            )
            self.queue_tree.insert(
                "",
                "end",
                iid=str(item["id"]),
                values=(position, queue_project_name(settings), queue_profile_text(settings), f"{progress:.0f}%", status),
                tags=(tag,) if tag else (),
            )
        target = str(select_id) if select_id is not None else previous_id
        if target and self.queue_tree.exists(target):
            self.queue_tree.selection_set(target)
            self.queue_tree.focus(target)
            self.queue_tree.see(target)
        elif self._queue_items:
            first = str(self._queue_items[0]["id"])
            self.queue_tree.selection_set(first)
            self.queue_tree.focus(first)
        self._refresh_queue_overview()
        self._refresh_queue_selected_detail()

    def _update_active_queue_ui(self) -> None:
        active = self._active_queue_item()
        if active is None or not hasattr(self, "queue_tree"):
            return
        iid = str(active["id"])
        if self.queue_tree.exists(iid):
            values = list(self.queue_tree.item(iid, "values"))
            if len(values) >= 5:
                values[3] = f"{queue_item_progress(active):.0f}%"
                values[4] = queue_normalize_status(active.get("status"))
                self.queue_tree.item(iid, values=values, tags=("active",))
        selected = self.queue_tree.selection()
        if selected and selected[0] == iid:
            self._refresh_queue_selected_detail()

    def _move_queue_item(self, direction: int) -> None:
        if self._queue_running or self._busy:
            messagebox.showinfo(APP_TITLE, "A ordem só pode ser alterada com a fila parada.")
            return
        item = self._selected_queue_item()
        if item is None:
            return
        selected_id = int(item["id"])
        if not queue_can_move(self._queue_items, selected_id, direction):
            return
        index = next(index for index, current in enumerate(self._queue_items) if int(current["id"]) == selected_id)
        target = index + direction
        self._queue_items[index], self._queue_items[target] = self._queue_items[target], self._queue_items[index]
        self._save_queue()
        self._refresh_queue_tree(select_id=selected_id)
        self.status.set("Ordem da fila atualizada.")

    def _retry_queue_item(self) -> None:
        if self._queue_running or self._busy:
            messagebox.showinfo(APP_TITLE, "Aguarde ou cancele a execução atual antes de reenfileirar um item.")
            return
        item = self._selected_queue_item()
        if item is None or not queue_can_retry(item):
            return
        item["status"] = "Aguardando"
        item["error"] = ""
        item["progress"] = 0.0
        item["stage"] = "Reenfileirado manualmente"
        self._save_queue()
        self._refresh_queue_tree(select_id=int(item["id"]))
        self.status.set("Item reenfileirado e pronto para uma nova tentativa.")

    def _remove_queue_item(self) -> None:
        if self._queue_running:
            messagebox.showinfo(APP_TITLE, "Pare ou conclua a fila antes de remover itens.")
            return
        item = self._selected_queue_item()
        if item is None:
            return
        selected_id = int(item["id"])
        self._queue_items = [current for current in self._queue_items if int(current["id"]) != selected_id]
        self._save_queue()
        self._refresh_queue_tree()
        self.status.set("Item removido da fila. Nenhum arquivo de mídia foi apagado.")

    def _clear_completed_queue(self) -> None:
        if self._queue_running:
            messagebox.showinfo(APP_TITLE, "A fila está em execução.")
            return
        completed = sum(queue_normalize_status(item.get("status")) == "Concluído" for item in self._queue_items)
        if not completed:
            return
        self._queue_items = [item for item in self._queue_items if queue_normalize_status(item.get("status")) != "Concluído"]
        self._save_queue()
        self._refresh_queue_tree()
        self.status.set(f"{completed} item(ns) concluído(s) removido(s) da lista. Os vídeos finais foram preservados.")

    def _clear_queue(self) -> None:
        if self._queue_running:
            messagebox.showinfo(APP_TITLE, "A fila está em execução.")
            return
        if not self._queue_items:
            return
        if not messagebox.askyesno(
            APP_TITLE,
            f"Remover os {len(self._queue_items)} item(ns) da fila?\n\nOs vídeos de entrada, saídas já concluídas e relatórios não serão apagados.",
        ):
            return
        self._queue_items.clear()
        self._save_queue()
        self._refresh_queue_tree()
        self.status.set("Fila limpa. Arquivos de mídia e renders concluídos foram preservados.")

    def _open_queue_path(self, path_value: str, *, prefer_parent: bool = False) -> None:
        path = Path(path_value).expanduser() if path_value else None
        if path is None:
            return
        target = path.parent if prefer_parent and path.parent.exists() else path
        if not target.exists():
            if path.parent.exists():
                target = path.parent
            else:
                messagebox.showinfo(APP_TITLE, f"O caminho ainda não existe:\n\n{path}")
                return
        try:
            os.startfile(target)  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            self.status.set(f"Caminho disponível: {target}")

    def _open_selected_queue_output(self) -> None:
        item = self._selected_queue_item()
        if item is None:
            return
        output = str(item["settings"].output or "")
        self._open_queue_path(output, prefer_parent=not Path(output).is_file() if output else True)

    def _open_selected_queue_report(self) -> None:
        item = self._selected_queue_item()
        if item is None:
            return
        report = str(item.get("report") or "")
        if not report:
            messagebox.showinfo(APP_TITLE, "Este item ainda não possui relatório final.")
            return
        self._open_queue_path(report)

    def _open_selected_queue_history(self) -> None:
        item = self._selected_queue_item()
        if item is None:
            return
        history = str(item.get("history") or "")
        if not history:
            messagebox.showinfo(APP_TITLE, "Este item ainda não possui histórico técnico persistente.")
            return
        self._open_queue_path(history)

    def _load_selected_queue_item(self) -> None:
        if self._busy or self._queue_running:
            messagebox.showinfo(APP_TITLE, "Aguarde o processamento atual terminar antes de carregar outro item no editor.")
            return
        item = self._selected_queue_item()
        if item is None:
            return
        settings: RenderSettings = item["settings"]
        mapping = (
            (self.mode, settings.mode), (self.video, settings.video), (self.audio, settings.audio),
            (self.output, settings.output), (self.resolution, settings.resolution), (self.fps, settings.fps),
            (self.aspect, settings.aspect), (self.enhancement, settings.enhancement), (self.fit_mode, settings.fit_mode),
            (self.use_cpu, settings.use_cpu), (self.preserve_audio, settings.preserve_audio), (self.color, settings.color),
            (self.intensity, settings.intensity * 100.0), (self.occupancy, settings.occupancy * 100.0),
            (self.audio_focus, settings.audio_focus), (self.reaction_smoothing, settings.reaction_smoothing * 100.0),
            (self.reaction_expression, settings.reaction_expression * 100.0), (self.auto_loop, settings.auto_loop),
            (self.dynamic_sections, settings.dynamic_sections), (self.section_dynamics, settings.section_dynamics * 100.0),
            (self.transition, settings.transition), (self.transition_duration, settings.transition_duration),
            (self.preview_seconds, settings.preview_seconds), (self.audio_mode, settings.audio_mode),
            (self.interpolation, settings.interpolation), (self.cpu_threads, settings.cpu_threads),
            (self.minimum_free_gb, settings.minimum_free_gb), (self.scratch_dir, settings.scratch_dir),
            (self.cache_quota_gb, settings.cache_quota_gb), (self.quality_check, settings.quality_check),
            (self.deep_verify, settings.deep_verify), (self.visual_direction, settings.visual_direction),
            (self.comparison_preview, settings.comparison_preview), (self.use_stems, settings.use_stems),
            (self.delivery_profile, settings.delivery_profile),
        )
        for variable, value in mapping:
            variable.set(value)
        for name, variable in self.effect_vars.items():
            variable.set(name in settings.effects)
        self.color_swatch.configure(background=self.color.get())
        self._visual_scale_changed()
        self._update_mode()
        self._update_summary()
        self.notebook.select(1)
        self.status.set(f"‘{queue_project_name(settings)}’ carregado no editor. O item original da fila permanece intacto.")

    def _start_queue(self) -> None:
        if self._busy or self._queue_running:
            return
        if not any(item["status"] in {"Aguardando", "Erro", "Interrompido", "Cancelado"} for item in self._queue_items):
            messagebox.showinfo(APP_TITLE, "Adicione pelo menos um projeto à fila.")
            return
        for item in self._queue_items:
            if item["status"] in {"Erro", "Interrompido", "Cancelado"}:
                item["status"] = "Aguardando"
                item["error"] = ""
                item["progress"] = 0.0
                item["stage"] = "Aguardando na fila"
        self._save_queue()
        self._queue_running = True
        self._refresh_queue_tree()
        self._set_feedback(
            "busy", "Fila iniciada",
            f"{sum(item['status'] == 'Aguardando' for item in self._queue_items)} projeto(s) aguardando execução sequencial.",
            category="Fila", primary=("Abrir fila", lambda: self._open_tab(4)), record=True,
        )
        self._run_next_queue_item()

    def _run_next_queue_item(self) -> None:
        if not self._queue_running:
            return
        next_item = next((item for item in self._queue_items if item["status"] == "Aguardando"), None)
        if next_item is None:
            self._queue_running = False
            self._active_queue_id = None
            failures = sum(item["status"] == "Erro" for item in self._queue_items)
            self._refresh_queue_tree()
            if failures:
                self._set_feedback(
                    "warning", "Fila concluída com atenção",
                    f"A execução terminou, mas {failures} item(ns) precisam de revisão antes de uma nova tentativa.",
                    category="Fila", primary=("Abrir fila", lambda: self._open_tab(4)),
                    secondary=("Ver atividade", self._show_activity_center),
                )
            else:
                self._set_feedback(
                    "success", "Fila concluída",
                    "Todos os projetos da fila terminaram sem erro registrado.",
                    category="Fila", primary=("Abrir fila", lambda: self._open_tab(4)),
                )
            return
        settings: RenderSettings = next_item["settings"]
        if not self._validate(settings, False):
            next_item["status"] = "Erro"
            next_item["error"] = "Validação recusada ou arquivos indisponíveis."
            next_item["stage"] = "Validação falhou"
            self._refresh_queue_tree(select_id=int(next_item["id"]))
            self._save_queue()
            self._schedule(100, self._run_next_queue_item)
            return
        try:
            preflight = self._preflight_report(settings, False)
            if preflight["blocking"]:
                raise RuntimeError(preflight["text"])
        except Exception as exc:
            next_item["status"] = "Erro"
            next_item["error"] = f"Pré-verificação: {exc}"
            next_item["stage"] = "Pré-verificação falhou"
            self._refresh_queue_tree(select_id=int(next_item["id"]))
            self._save_queue()
            self._schedule(100, self._run_next_queue_item)
            return
        next_item["status"] = "Renderizando"
        next_item["progress"] = 0.0
        next_item["stage"] = "Preparando"
        self._active_queue_id = next_item["id"]
        self._refresh_queue_tree(select_id=int(next_item["id"]))
        self._save_queue()
        self._launch_worker(settings, False)

    def _active_queue_item(self) -> dict | None:
        return next((item for item in self._queue_items if item["id"] == self._active_queue_id), None)

    def _start(self, preview: bool) -> None:
        if self._busy:
            return
        settings = self._settings()
        if not self._validate(settings, preview):
            return
        if not self._confirm_preflight(settings, preview):
            return
        if preview:
            PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
            source_name = Path(settings.video).stem[:60] or "video"
            stamp = time.strftime("%Y%m%d_%H%M%S")
            output = PREVIEW_DIR / f"{source_name}_PREVIEW_{settings.preview_seconds}s_{stamp}.mp4"
            settings.output = str(output)
        else:
            output = Path(settings.output)
            if output.exists() and not messagebox.askyesno(APP_TITLE, "O arquivo já existe. Deseja substituí-lo?"):
                return
        self._launch_worker(settings, preview)

    def _launch_worker(self, settings: RenderSettings, preview: bool) -> None:
        self._cancelled = False
        self._busy = True
        self._started_at = time.monotonic()
        self._progress_value = 0
        self._logs = []
        self.bar["value"] = 0
        self.progress_text.set("0%")
        self.stage.set("Preparando")
        self._set_feedback(
            "busy",
            "Preparando o processamento",
            "Validando mídia e calculando o fluxo de processamento.",
            category="Preview" if preview else "Render",
            secondary=("Ver log", self._show_log),
        )
        self.render_button.configure(state="disabled")
        self.preview_button.configure(state="disabled")
        self.add_queue_button.configure(state="disabled")
        self.start_queue_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.cancel_button.pack(side="left", padx=(8, 0))
        self._refresh_footer_density()
        self._write_render_lock(preview)
        threading.Thread(target=self._worker, args=(settings, preview), daemon=True).start()

    def _worker(self, settings: RenderSettings, preview: bool) -> None:
        temp_paths: list[Path] = []
        temp_dirs: list[Path] = []
        atomic_output: AtomicOutput | None = None
        history: RenderHistory | None = None
        try:
            history = RenderHistory.start(
                PATHS.logs / "renders", settings, preview=preview, app_version=__version__,
                queue_id=self._active_queue_id if self._queue_running else None,
            )
            self._active_render_history = history
        except Exception as exc:
            # History should be reliable, but failure to create support metadata
            # must not destroy an otherwise valid local render.
            self._events.put(("log", f"[{time.strftime('%H:%M:%S')}] HISTORY WARNING: {exc}"))
        scratch_root = resolve_scratch_dir(settings.scratch_dir, WORK_DIR)
        scratch_root.mkdir(parents=True, exist_ok=True)
        self._prune_work(scratch_root)
        prune = enforce_cache_quota(PATHS.cache, settings.cache_quota_gb)
        if prune.removed_files:
            self._log(
                f"CACHE LRU: removidos {prune.removed_files} arquivo(s), {prune.removed_gb:.2f} GB; "
                f"uso atual {prune.after_gb:.2f}/{settings.cache_quota_gb:.0f} GB."
            )
        job_dir = Path(tempfile.mkdtemp(prefix="job_", dir=scratch_root))
        self._log(f"STORAGE Phase 6: scratch={scratch_root} • cache quota={settings.cache_quota_gb:.0f} GB")
        try:
            video_info = probe_media(settings.video)
            source_color = ColorProfile.from_probe(video_info)
            video_duration = media_duration(video_info)
            source_duration = video_duration
            source_w, source_h = first_video_size(video_info)
            source_fps = first_video_fps(video_info)
            source_has_audio = has_audio(video_info)
            if settings.mode == MODE_MUSIC:
                audio_info = probe_media(settings.audio)
                if not has_audio(audio_info):
                    raise RuntimeError("A música selecionada não contém áudio.")
                project_duration = media_duration(audio_info)
                audio_source = settings.audio
            else:
                project_duration = video_duration
                audio_source = settings.video
                if settings.effects and not source_has_audio:
                    raise RuntimeError("VFX dinâmicos precisam de áudio. Este vídeo não possui uma faixa de áudio.")
            # Phase 3: VFX normalization always sees the full reactive source.
            # A short rendered preview slices this same envelope instead of
            # recalculating percentiles only over preview_seconds (CP-013).
            full_analysis_duration = float(project_duration)
            loop_start = 0.0
            loop_score = 0.0
            if settings.mode == MODE_MUSIC and settings.auto_loop and source_duration >= 1.5:
                self._set_stage("Analisando loop", "Comparando movimento, luz e semelhança entre o começo e o final.")
                loop_start, loop_end, loop_score = self._find_best_loop(settings.video, source_duration)
                video_duration = max(0.5, loop_end - loop_start)
                self._log(
                    f"Loop automático: início {loop_start:.3f}s, fim {loop_end:.3f}s, "
                    f"duração {video_duration:.3f}s, diferença {loop_score:.5f}."
                )
            if preview:
                project_duration = min(project_duration, settings.preview_seconds)
                video_duration = min(video_duration, settings.preview_seconds)

            target_w, target_h = self._target_size(settings.resolution, settings.aspect, (source_w, source_h))
            target_fps = settings.fps
            if preview:
                target_w, target_h = self._target_size("720p HD", settings.aspect, (source_w, source_h))
                target_fps = min(60, target_fps)

            output_path = Path(settings.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.resolve() == Path(settings.video).resolve():
                raise RuntimeError("O arquivo de saída precisa ser diferente do vídeo de entrada.")
            atomic_output = AtomicOutput.for_path(output_path)
            partial_output = atomic_output.prepare()
            self._render_journal.write(
                atomic_output,
                preview,
                {"duration": project_duration, "width": target_w, "height": target_h, "fps": target_fps},
            )

            self._log(f"Fonte: {source_w}x{source_h}, {source_fps:.3f} fps, {video_duration:.3f} s")
            self._log(f"Destino: {target_w}x{target_h}, {target_fps} fps, {project_duration:.3f} s")

            effects_active = bool(settings.effects)
            transition_label = settings.transition
            transition_duration = settings.transition_duration
            if (
                settings.mode == MODE_MUSIC
                and settings.auto_loop
                and TRANSITIONS[transition_label] is None
                and loop_score > 0.030
            ):
                transition_label = "Dissolver suave"
                transition_duration = min(0.55, max(0.25, video_duration / 8))
                self._log("A emenda ainda tinha diferença visível; dissolução curta escolhida automaticamente.")
            transition_active = settings.mode == MODE_MUSIC and TRANSITIONS[transition_label] is not None

            render_plan = self._build_render_plan(
                settings,
                preview=preview,
                source_w=source_w,
                source_h=source_h,
                source_fps=source_fps,
                target_w=target_w,
                target_h=target_h,
                target_fps=target_fps,
                color_profile=source_color,
                transition_active=transition_active,
                auto_loop_may_add_transition=False,
            )
            self._log(f"RenderPlan {render_plan.fingerprint} • {render_plan.architecture_version}")
            for step in render_plan.steps:
                self._log("PLAN " + step.summary())
            for risk in render_plan.risks:
                self._log(f"PLAN RISK [{risk.severity.upper()} {risk.code}] {risk.title}: {risk.detail}")
            if history is not None:
                history.write_plan(render_plan)

            color_plan = build_color_pipeline(
                source_color,
                effects_active=effects_active,
                transition_active=transition_active,
                enhancement_mode=self._normalized_enhancement_mode(settings.enhancement),
                rife_active=(
                    render_plan.step("rife_base").attempts or render_plan.step("rife_final").attempts
                ) and settings.interpolation == RIFE_OPTION,
            )
            self._log(f"COLOR {color_plan.label}: {color_plan.reason}")
            for assumption in color_plan.assumptions:
                self._log(f"COLOR WARNING: {assumption}")

            delivery_plan = build_delivery_plan(
                output="preview.mp4" if preview else settings.output,
                profile=settings.delivery_profile, color_plan=color_plan,
                width=target_w, height=target_h, fps=target_fps, preview=preview,
                use_cpu=settings.use_cpu, nvenc_available=self._nvenc,
                available_encoders=detect_ffmpeg_encoders(FFMPEG),
            )
            self._log(f"DELIVERY {delivery_plan.profile}: {delivery_plan.label}")
            for issue in delivery_plan.issues:
                self._log(f"DELIVERY {issue.severity.upper()} [{issue.code}] {issue.message}")
            if delivery_plan.blocking:
                raise RuntimeError("Perfil de entrega incompatível: " + " • ".join(delivery_plan.errors))

            expected_audio = settings.mode == MODE_MUSIC or (settings.preserve_audio and source_has_audio)
            audio_probe = audio_info if settings.mode == MODE_MUSIC else video_info
            audio_stream = next(
                (stream for stream in audio_probe.get("streams", []) if stream.get("codec_type") == "audio"), {}
            ) if expected_audio else {}
            try:
                expected_audio_channels = int(audio_stream.get("channels")) if audio_stream.get("channels") is not None else None
            except (TypeError, ValueError):
                expected_audio_channels = None
            if expected_audio and delivery_plan.audio_codec in {"AAC", "Opus"}:
                expected_audio_sample_rate = 48000
            else:
                try:
                    expected_audio_sample_rate = int(audio_stream.get("sample_rate")) if audio_stream.get("sample_rate") else None
                except (TypeError, ValueError):
                    expected_audio_sample_rate = None

            estimated_bitrate = self._estimated_bitrate_mbps(target_w, target_h, target_fps)
            estimated_output_gb = estimated_bitrate * project_duration / 8 / 1024 * 1.08
            storage_contract = estimate_storage(
                render_plan, clip_duration=video_duration, project_duration=project_duration,
                output_gb=estimated_output_gb,
                cache_current_gb=cache_usage_bytes(PATHS.cache) / (1024 ** 3),
                cache_quota_gb=settings.cache_quota_gb,
            )
            if history is not None:
                history.write_contracts(
                    color=color_plan, delivery=delivery_plan, storage=storage_contract,
                    verification_expected={
                        "width": target_w, "height": target_h, "fps": target_fps,
                        "duration": project_duration, "expect_audio": expected_audio,
                        "audio_channels": expected_audio_channels,
                        "audio_sample_rate": expected_audio_sample_rate,
                        "deep": bool(settings.deep_verify and not preview),
                    },
                )

            working_video = settings.video
            working_w, working_h = source_w, source_h
            working_start = loop_start
            progress_base = 0.0
            color_already_converted = False

            # Neural stages currently operate in SDR and are treated as 8-bit
            # boundaries.  When they are the first processing stage, perform
            # the explicit HDR->SDR / 10->8 conversion *before* handing frames
            # to the model.  If a master precedes RIFE, that conversion is
            # fused into the master instead of materializing an extra file.
            color_step = render_plan.step("color")
            ai_will_run = render_plan.step("enhancement").attempts and settings.enhancement == ENHANCE_AI
            color_prepass = color_step.runs and (
                ai_will_run
                or render_plan.step("rife_base").runs
                or (render_plan.step("rife_final").attempts and not render_plan.needs_master)
            )
            if color_prepass:
                converted = self._temp_file(job_dir, "studio_color_", temp_paths, suffix=".mkv")
                working_video = self._prepare_color_source(
                    settings.video,
                    converted,
                    loop_start,
                    video_duration,
                    source_fps,
                    color_plan,
                    settings.cpu_threads,
                    progress_base,
                    5.0,
                )
                progress_base += 5.0
                working_start = 0.0
                color_already_converted = True

            if render_plan.step("enhancement").attempts and settings.enhancement == ENHANCE_AI:
                consumed_before_ai = working_video
                working_video, working_w, working_h = self._enhance_clip_ai(
                    working_video, job_dir, working_start, video_duration, source_fps, source_w, source_h,
                    temp_paths, temp_dirs, settings.cpu_threads, progress_base, 20,
                    cache_source_video=settings.video, cache_quota_gb=settings.cache_quota_gb,
                )
                self._release_temp_path(consumed_before_ai, temp_paths)
                progress_base += 20.0
                working_start = 0.0
                color_already_converted = True

            working_fps = source_fps
            rife_base_step = render_plan.step("rife_base")
            if rife_base_step.runs and settings.interpolation == RIFE_OPTION:
                base_rife_weight = 18.0
                try:
                    self._set_stage(
                        "RIFE do clipe",
                        f"Interpolando o clipe reutilizável uma única vez para {target_fps} fps antes de expandir o loop.",
                    )
                    previous_working = working_video
                    working_video = self._interpolate_rife(
                        working_video, job_dir, working_start, video_duration, working_fps, target_fps,
                        settings.use_cpu, settings.cpu_threads, temp_paths, progress_base, base_rife_weight,
                        color_plan=color_plan,
                    )
                    self._release_temp_path(previous_working, temp_paths)
                    working_start = 0.0
                    working_fps = float(target_fps)
                    progress_base += base_rife_weight
                    color_already_converted = True
                    self._log(
                        f"RIFE loop-aware: clipe {video_duration:.3f}s interpolado uma vez; "
                        f"timeline final {project_duration:.3f}s reutiliza esse master."
                    )
                except InterruptedError:
                    raise
                except Exception as exc:
                    self._log(f"RIFE do clipe falhou; o master usará fallback FFmpeg: {exc}")

            needs_master = render_plan.needs_master
            visual_source = working_video
            # This flag must exist for every project shape, including the
            # original-video fast path where no master/VFX stage runs.
            finalized_in_vfx = False
            # Hotfix 1.1.3 keeps RIFE one-shot: music loops process the reusable
            # clip before master/VFX; original-video projects may still use the
            # final RIFE stage after visual composition.
            if needs_master:
                master_step = render_plan.step("master")
                if master_step.output_spec is None:
                    raise RuntimeError("RenderPlan inválido: master marcado para execução sem especificação de saída.")
                work_w, work_h = master_step.output_spec.width, master_step.output_spec.height
                work_fps = float(master_step.output_spec.fps)
                master_suffix = ".mkv" if color_plan.needs_lossless_intermediate else ".mp4"
                master = self._temp_file(job_dir, "studio_master_", temp_paths, suffix=master_suffix)
                self._set_stage("Preparando master", f"Convertendo o vídeo para {work_w}×{work_h} em {work_fps:g} fps.")
                master_filter = self._scale_filter(
                    work_w, work_h, work_fps, settings.fit_mode, working_fps, settings.interpolation,
                    spatial_mode=self._normalized_enhancement_mode(settings.enhancement),
                    source_size=(working_w, working_h),
                    color_plan=color_plan,
                    color_already_converted=color_already_converted,
                )
                command = [
                    FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
                ]
                if working_start > 0:
                    command += ["-ss", f"{working_start:.6f}"]
                command += [
                    "-i", working_video,
                    "-map", "0:v:0", "-an", "-t", f"{video_duration:.6f}", "-vf", master_filter,
                ] + self._intermediate_encoder(work_w, work_h, settings.use_cpu, color_plan) + [
                    "-threads", str(settings.cpu_threads), "-progress", "pipe:1", "-nostats", str(master)
                ]
                self._run_ffmpeg(command, video_duration, progress_base, 10)
                self._release_temp_path(working_video, temp_paths)
                progress_base += 10
                visual_source = str(master)
                color_already_converted = color_already_converted or color_step.runs
                if transition_active:
                    transitioned = self._temp_file(job_dir, "studio_transition_", temp_paths, suffix=master_suffix)
                    previous_visual = visual_source
                    visual_source = self._create_transition(
                        str(master), transitioned, video_duration, transition_label,
                        transition_duration, work_w, work_h, settings.use_cpu, progress_base, 7,
                        settings.cpu_threads, color_plan,
                    )
                    if visual_source != previous_visual:
                        self._release_temp_path(previous_visual, temp_paths)
                    progress_base += 7
                if effects_active:
                    # Music VFX is the only project-long visual stage after the
                    # loop-aware RIFE hotfix. Fuse it with delivery so 8K/120
                    # never writes a full-length lossless VFX intermediate.
                    fuse_vfx_delivery = (
                        settings.mode == MODE_MUSIC
                        and not render_plan.step("rife_final").attempts
                    )
                    vfx_output = (
                        partial_output
                        if fuse_vfx_delivery
                        else self._temp_file(job_dir, "studio_vfx_", temp_paths, suffix=master_suffix)
                    )
                    self._set_stage(
                        "VFX dinâmicos",
                        "Compondo VFX e codificando diretamente a saída final."
                        if fuse_vfx_delivery
                        else "Reutilizando o envelope musical completo e desenhando VFX target-aware.",
                    )
                    remaining_for_vfx = max(1.0, 95.0 - progress_base) if fuse_vfx_delivery else (35 if settings.mode == MODE_MUSIC else 45)
                    reactive_audio = audio_source
                    if settings.use_stems:
                        try:
                            reactive_audio = self._prepare_reactive_audio(
                                audio_source, settings.audio_focus, settings.use_cpu, settings.cpu_threads,
                            )
                        except InterruptedError:
                            raise
                        except Exception as exc:
                            self._log(f"Demucs indisponível; VFX seguirá a mistura original: {exc}")

                    final_audio_filter = ""
                    final_video_args = None
                    final_audio_args = None
                    final_muxer_args = None
                    final_audio_source = None
                    if fuse_vfx_delivery:
                        measurements = None
                        if settings.audio_mode != "Preservar dinâmica original":
                            self._set_stage("Áudio 1/2", "Medindo loudness, true peak e faixa dinâmica da trilha completa.")
                            try:
                                measurements = analyze_loudness(FFMPEG, audio_source, project_duration, settings.audio_mode)
                                self._log(f"Medição de loudness: {measurements}")
                            except Exception as exc:
                                self._log(f"Medição em duas passagens indisponível; usando normalização dinâmica: {exc}")
                        final_audio_filter = build_audio_filter(settings.audio_mode, measurements)
                        final_video_args = delivery_plan.video_args(
                            use_cpu=settings.use_cpu, nvenc_available=self._nvenc,
                            bitrate_mbps=estimated_bitrate, fps=target_fps,
                        )
                        final_audio_source = settings.audio
                        final_audio_args = delivery_plan.audio_args()
                        final_muxer_args = delivery_plan.muxer_args()
                        self._log(
                            "STORAGE Hotfix 1.1.3: VFX full-length será entregue por streaming; "
                            "nenhum FFV1 full-length será materializado no scratch."
                        )

                    previous_visual = visual_source
                    try:
                        vfx.render_vfx_intermediate(
                            FFMPEG, visual_source, reactive_audio, str(vfx_output), project_duration,
                            settings.effects, settings.color, settings.intensity, settings.occupancy,
                            work_w, work_h, work_fps, "100M" if max(work_w, work_h) > 1280 else "50M",
                            "180M", "360M", settings.use_cpu, settings.cpu_threads,
                            settings.audio_focus, settings.reaction_smoothing, settings.reaction_expression,
                            settings.dynamic_sections, settings.section_dynamics,
                            lambda fraction: self._push_progress(progress_base + remaining_for_vfx * fraction),
                            lambda: self._cancelled,
                            lambda process: setattr(self, "_process", process),
                            self._log,
                            analysis_duration=full_analysis_duration,
                            analysis_offset=0.0,
                            output_pixel_format=color_plan.working_pix_fmt,
                            output_primaries=color_plan.working.primaries,
                            output_transfer=color_plan.working.transfer,
                            output_space=color_plan.working.space,
                            output_range=color_plan.working.range,
                            lossless_intermediate=color_plan.needs_lossless_intermediate and not fuse_vfx_delivery,
                            final_video_args=final_video_args,
                            final_audio_source=final_audio_source,
                            final_audio_filter=final_audio_filter,
                            final_audio_args=final_audio_args,
                            final_muxer_args=final_muxer_args,
                        )
                    except vfx.RenderCancelled as exc:
                        raise InterruptedError from exc
                    self._release_temp_path(previous_visual, temp_paths)
                    visual_source = str(vfx_output)
                    progress_base += remaining_for_vfx
                    color_already_converted = True
                    finalized_in_vfx = fuse_vfx_delivery

            visual_fps = (
                float(render_plan.step("master").output_spec.fps)
                if needs_master and render_plan.step("master").output_spec is not None
                else float(working_fps)
            )
            effective_interpolation = settings.interpolation
            rife_final_step = render_plan.step("rife_final")
            if rife_final_step.attempts and settings.interpolation == RIFE_OPTION:
                rife_weight = max(1.0, min(35.0, max(1.0, 95.0 - progress_base) * 0.65))
                try:
                    self._set_stage("RIFE final", f"Interpolando movimento neural para {target_fps} fps.")
                    previous_visual = visual_source
                    visual_source = self._interpolate_rife(
                        visual_source, job_dir, 0.0, project_duration, visual_fps, target_fps,
                        settings.use_cpu, settings.cpu_threads, temp_paths, progress_base, rife_weight,
                        color_plan=color_plan,
                    )
                    self._release_temp_path(previous_visual, temp_paths)
                    visual_fps = float(target_fps)
                    progress_base += rife_weight
                except InterruptedError:
                    raise
                except Exception as exc:
                    effective_interpolation = "Movimento suave — FFmpeg"
                    self._log(f"RIFE final falhou; fallback FFmpeg ativado: {exc}")
            if not finalized_in_vfx:
                self._set_stage("Finalizando", f"Codificando em {target_w}×{target_h} a {target_fps} fps com áudio correto.")
                final_input_spec = render_plan.step("finalize").input_spec
                final_source_size = (
                    (final_input_spec.width, final_input_spec.height)
                    if final_input_spec is not None
                    else (working_w, working_h)
                )
                final_filter = self._scale_filter(
                    target_w, target_h, target_fps, settings.fit_mode, visual_fps, effective_interpolation,
                    spatial_mode=self._normalized_enhancement_mode(settings.enhancement),
                    source_size=final_source_size,
                    color_plan=color_plan,
                    color_already_converted=color_already_converted,
                )
                command = [FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error"]
                if settings.mode == MODE_MUSIC and not effects_active:
                    command += ["-stream_loop", "-1"]
                command += ["-i", visual_source]
                if settings.mode == MODE_MUSIC:
                    command += ["-i", settings.audio, "-map", "0:v:0", "-map", "1:a:0"]
                elif settings.preserve_audio and source_has_audio:
                    command += ["-i", settings.video, "-map", "0:v:0", "-map", "1:a:0"]
                else:
                    command += ["-map", "0:v:0", "-an"]
                command += ["-vf", final_filter]
                bitrate_mbps = estimated_bitrate
                command += delivery_plan.video_args(
                    use_cpu=settings.use_cpu, nvenc_available=self._nvenc,
                    bitrate_mbps=bitrate_mbps, fps=target_fps,
                )
                command += color_plan.metadata_args(output=True)
                if settings.mode == MODE_MUSIC or (settings.preserve_audio and source_has_audio):
                    measurements = None
                    if settings.audio_mode != "Preservar dinâmica original":
                        self._set_stage("Áudio 1/2", "Medindo loudness, true peak e faixa dinâmica da trilha completa.")
                        try:
                            measurements = analyze_loudness(FFMPEG, audio_source, project_duration, settings.audio_mode)
                            self._log(f"Medição de loudness: {measurements}")
                        except Exception as exc:
                            self._log(f"Medição em duas passagens indisponível; usando normalização dinâmica: {exc}")
                    self._set_stage("Áudio 2/2", "Aplicando masterização e proteção de pico durante a codificação final.")
                    audio_filter = build_audio_filter(settings.audio_mode, measurements)
                    if audio_filter:
                        command += ["-af", audio_filter]
                    command += delivery_plan.audio_args()
                command += ["-threads", str(settings.cpu_threads), "-t", f"{project_duration:.6f}"]
                command += delivery_plan.muxer_args()
                command += ["-progress", "pipe:1", "-nostats", str(partial_output)]
                self._run_ffmpeg(command, project_duration, progress_base, 100 - progress_base)
                self._release_temp_path(visual_source, temp_paths)
            else:
                self._set_stage("Finalizando", "VFX e entrega já foram codificados no mesmo passe; iniciando verificação final.")
                self._push_progress(98.0)
            verification = self._verify_output(
                str(partial_output), project_duration, target_w, target_h, target_fps,
                delivery_plan=delivery_plan, expected_audio=expected_audio,
                expected_audio_channels=expected_audio_channels,
                expected_audio_sample_rate=expected_audio_sample_rate,
                deep=bool(settings.deep_verify and not preview),
            )
            if history is not None:
                history.write_verification(verification["verification"])
            output_path = atomic_output.commit()
            self._render_journal.clear()
            report_path = ""
            if not preview:
                report_path = self._write_quality_report(
                    output_path, settings, verification, project_duration, render_plan=render_plan,
                )
            if history is not None:
                history.finish("success", output=output_path, report=report_path)
            display_path = output_path
            if preview and settings.comparison_preview:
                display_path = self._create_comparison_preview(
                    output_path, settings, project_duration, loop_start, settings.cpu_threads,
                )
            self._events.put(("done", str(display_path), preview, display_path.stat().st_size, report_path, history.path if history else ""))
        except InterruptedError:
            if atomic_output:
                atomic_output.discard()
            self._render_journal.clear()
            if history is not None:
                history.finish("cancelled", error="Execução cancelada pelo usuário.")
            self._events.put(("cancelled", history.path if history else ""))
        except Exception as exc:
            self._log("ERRO: " + str(exc))
            if history is not None:
                history.finish("error", error=str(exc), output=atomic_output.final if atomic_output and atomic_output.final.exists() else None)
            self._events.put(("error", str(exc), history.path if history else ""))
        finally:
            self._process = None
            if self._active_render_history is history:
                self._active_render_history = None
            for path in temp_paths:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            for directory in temp_dirs:
                safe_rmtree(directory)
            safe_rmtree(job_dir)

    @staticmethod
    def _audio_filter(mode: str) -> str:
        return build_audio_filter(mode)

    def _prepare_color_source(
        self,
        video: str,
        output: Path,
        start_time: float,
        duration: float,
        source_fps: float,
        color_plan: ColorPipeline,
        cpu_threads: int,
        base: float,
        weight: float,
    ) -> str:
        """Materialize an explicit color conversion before an 8-bit neural stage.

        The file is FFV1 so HDR tone mapping / 10->8 dithering is not followed
        by an avoidable lossy generation before Real-ESRGAN or RIFE.
        """

        if not (color_plan.tone_maps_to_sdr or color_plan.precision_reduction):
            return video
        self._set_stage("Gerenciando cor", color_plan.reason)
        command = [FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error"]
        if start_time > 0:
            command += ["-ss", f"{start_time:.6f}"]
        command += [
            "-i", video,
            "-map", "0:v:0", "-an", "-t", f"{duration:.6f}",
            "-vf", color_plan.normalize_filter(stage="working"),
            "-c:v", "ffv1", "-level", "3", "-coder", "1", "-context", "1",
            "-g", "1", "-slicecrc", "1", "-pix_fmt", color_plan.working_pix_fmt,
        ] + color_plan.metadata_args(output=False) + [
            "-threads", str(max(1, cpu_threads)), "-progress", "pipe:1", "-nostats", str(output),
        ]
        self._run_ffmpeg(command, duration, base, weight)
        return str(output)

    def _scale_filter(
        self, width: int, height: int, fps: float, fit_mode: str, source_fps: float, interpolation: str,
        *, spatial_mode: str = "lanczos", source_size: tuple[int, int] | None = None,
        color_plan: ColorPipeline | None = None, color_already_converted: bool = False,
    ) -> str:
        """Build the spatial/temporal/color filter chain.

        Temporal filtering is omitted when the input cadence already equals the
        requested cadence.  ``preserve`` never enlarges source pixels; when a
        requested cover would require upscale it falls back to a contained,
        centered native/downscaled image inside the requested canvas.  Phase 4
        performs real tone mapping/range conversion before spatial filtering
        when a HDR source must enter an SDR-only stage.
        """

        filters: list[str] = []
        if fps > source_fps + 0.01:
            if interpolation == "Quadros repetidos — rápido":
                filters.append(f"fps={fps:.8f}")
            else:
                filters.append(f"minterpolate=fps={fps:.8f}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1")
        elif fps < source_fps - 0.01:
            # Deliberate downsampling only when the destination asks for fewer frames.
            filters.append(f"fps={fps:.8f}")

        if color_plan is not None and not color_already_converted:
            if color_plan.tone_maps_to_sdr or color_plan.precision_reduction:
                filters.append(color_plan.normalize_filter(stage="working"))

        preserve_without_upscale = False
        if spatial_mode == "preserve" and source_size is not None:
            source_w, source_h = source_size
            normalized_fit = "cover" if fit_mode == FIT_COVER else "contain"
            required_scale = spatial_scale_factor(source_w, source_h, width, height, normalized_fit)
            preserve_without_upscale = required_scale > 1.0001

        if spatial_mode == "preserve" and source_size is not None:
            source_w, source_h = source_size
            if fit_mode == FIT_COVER and not preserve_without_upscale:
                scale = max(width / source_w, height / source_h)
                scaled_w = max(2, round(source_w * scale / 2) * 2)
                scaled_h = max(2, round(source_h * scale / 2) * 2)
                framing = (
                    f"scale={scaled_w}:{scaled_h}:flags=lanczos+accurate_rnd+full_chroma_int,"
                    f"crop={width}:{height}"
                )
            else:
                # Contain is the safe fallback whenever filling the canvas would
                # require enlarging source pixels.  Downscale remains allowed.
                scale = min(1.0, width / source_w, height / source_h)
                scaled_w = max(2, round(source_w * scale / 2) * 2)
                scaled_h = max(2, round(source_h * scale / 2) * 2)
                scaled_w = min(width, scaled_w)
                scaled_h = min(height, scaled_h)
                framing = (
                    f"scale={scaled_w}:{scaled_h}:flags=lanczos+accurate_rnd+full_chroma_int,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
                )
        elif fit_mode == FIT_COVER:
            framing = (
                f"scale={width}:{height}:force_original_aspect_ratio=increase:"
                "flags=lanczos+accurate_rnd+full_chroma_int,"
                f"crop={width}:{height}"
            )
        else:
            framing = (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease:"
                "flags=lanczos+accurate_rnd+full_chroma_int,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
            )
        filters.append(framing)
        if color_plan is not None:
            filters.append(
                f"format={color_plan.working_pix_fmt},{color_plan.setparams_filter()}"
            )
        else:
            # Unit-test/legacy fallback is deliberately honest SDR 8-bit.
            filters.append(
                "format=yuv420p,setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709"
            )
        return ",".join(filters)

    def _create_comparison_preview(
        self, processed: Path, settings: RenderSettings, duration: float, loop_start: float, cpu_threads: int,
    ) -> Path:
        comparison = processed.with_name(processed.stem + "_COMPARACAO.mp4")
        self._set_stage("Comparando", "Montando original e resultado lado a lado para conferência visual.")
        command = [FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error"]
        if settings.mode == MODE_MUSIC:
            command += ["-stream_loop", "-1"]
        if loop_start > 0:
            command += ["-ss", f"{loop_start:.6f}"]
        command += ["-i", settings.video, "-i", str(processed)]
        graph = (
            "[0:v]scale=640:720:force_original_aspect_ratio=decrease:flags=lanczos,"
            "pad=640:720:(ow-iw)/2:(oh-ih)/2:color=black[left];"
            "[1:v]scale=640:720:force_original_aspect_ratio=decrease:flags=lanczos,"
            "pad=640:720:(ow-iw)/2:(oh-ih)/2:color=black[right];"
            "[left][right]hstack=inputs=2,format=yuv420p[out]"
        )
        command += [
            "-filter_complex", graph, "-map", "[out]", "-map", "1:a:0?",
        ] + self._h264_encoder(1280, 720, settings.use_cpu) + [
            "-c:a", "copy", "-threads", str(cpu_threads), "-t", f"{duration:.6f}",
            "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(comparison),
        ]
        self._run_ffmpeg(command, duration, 100, 0)
        return comparison

    def _h264_encoder(self, width: int, height: int, use_cpu: bool) -> list[str]:
        if not use_cpu and self._nvenc and max(width, height) <= 8192:
            return [
                "-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq", "-rc", "vbr",
                "-cq", "10", "-b:v", "80M", "-maxrate", "180M", "-bufsize", "360M",
                "-pix_fmt", "yuv420p",
            ]
        return ["-c:v", "libx264", "-preset", "slow", "-crf", "12", "-pix_fmt", "yuv420p"]

    def _intermediate_encoder(self, width: int, height: int, use_cpu: bool, color_plan: ColorPipeline) -> list[str]:
        """Encode intermediate video without silently collapsing HDR/10-bit.

        Color-critical inputs (HDR or >8-bit) use FFV1 in Matroska.  Ordinary
        SDR 8-bit keeps the existing high-quality H.264 path to avoid exploding
        scratch usage before the Storage Engine phase.
        """

        if color_plan.needs_lossless_intermediate:
            return [
                "-c:v", "ffv1", "-level", "3", "-coder", "1", "-context", "1",
                "-g", "1", "-slicecrc", "1", "-pix_fmt", color_plan.working_pix_fmt,
            ] + color_plan.metadata_args(output=False)
        return self._h264_encoder(width, height, use_cpu) + color_plan.metadata_args(output=False)

    def _final_encoder(
        self, width: int, height: int, fps: int, preview: bool, use_cpu: bool,
        color_plan: ColorPipeline,
    ) -> list[str]:
        pixels_ratio = width * height / (1920 * 1080)
        target = max(8, min(600, round(12 * pixels_ratio * max(1, fps / 60))))
        if preview:
            target = min(target, 24)
        color_args = color_plan.metadata_args(output=True)
        ten_bit = color_plan.output.bit_depth > 8
        if not use_cpu and self._nvenc and max(width, height) <= 8192:
            args = [
                "-c:v", "hevc_nvenc", "-preset", "p7", "-tune", "hq",
                "-profile:v", "main10" if ten_bit else "main",
                "-rc", "vbr", "-cq", "14", "-b:v", f"{target}M", "-maxrate", f"{target * 2}M",
                "-bufsize", f"{target * 4}M", "-spatial-aq", "1", "-temporal-aq", "1",
                "-aq-strength", "8", "-multipass", "fullres", "-b_ref_mode", "middle",
                "-g", str(max(12, fps // 2)), "-bf", "2", "-tag:v", "hvc1",
                "-pix_fmt", "p010le" if ten_bit else "yuv420p",
            ]
            return args + color_args
        return [
            "-c:v", "libx265", "-preset", "medium", "-crf", "16",
            "-pix_fmt", "yuv420p10le" if ten_bit else "yuv420p",
            "-tag:v", "hvc1",
        ] + color_args

    def _create_transition(
        self, master: str, output: Path, duration: float, label: str,
        requested: float, width: int, height: int, use_cpu: bool, base: float, weight: float,
        cpu_threads: int, color_plan: ColorPipeline,
    ) -> str:
        transition = TRANSITIONS[label]
        if not transition or duration < 0.6:
            return master
        blend = max(0.10, min(requested, duration / 3))
        core_end = duration - blend
        graph = (
            f"[0:v]split=3[core][tail][head];"
            f"[core]trim=start={blend:.6f}:end={core_end:.6f},setpts=PTS-STARTPTS[c];"
            f"[tail]trim=start={core_end:.6f}:end={duration:.6f},setpts=PTS-STARTPTS[t];"
            f"[head]trim=start=0:end={blend:.6f},setpts=PTS-STARTPTS[h];"
            f"[t][h]xfade=transition={transition}:duration={blend:.6f}:offset=0[x];"
            f"[c][x]concat=n=2:v=1:a=0,format={color_plan.working_pix_fmt},"
            f"{color_plan.setparams_filter()}[v]"
        )
        expected = max(0.1, duration - blend)
        command = [
            FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error", "-i", master,
            "-filter_complex", graph, "-map", "[v]", "-an",
        ] + self._intermediate_encoder(width, height, use_cpu, color_plan) + [
            "-threads", str(cpu_threads), "-progress", "pipe:1", "-nostats", str(output)
        ]
        self._set_stage("Criando transição", f"Mesclando o final e o início com ‘{label}’ por {blend:.2f} s.")
        self._run_ffmpeg(command, expected, base, weight)
        return str(output)

    def _find_best_loop(self, video: str, duration: float) -> tuple[float, float, float]:
        analysis_fps = 6
        width, height = 96, 54
        command = [
            FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            video,
            "-an",
            "-vf",
            f"fps={analysis_fps},scale={width}:{height}:flags=area,format=gray",
            "-f",
            "rawvideo",
            "pipe:1",
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
        frame_size = width * height
        frame_count = len(result.stdout) // frame_size
        if result.returncode or frame_count < analysis_fps:
            self._log("Análise automática do loop indisponível; usando o clipe inteiro.")
            return 0.0, duration, 0.0
        frames = np.frombuffer(result.stdout[: frame_count * frame_size], dtype=np.uint8)
        frames = frames.reshape(frame_count, height, width).astype(np.float32) / 255.0
        search_frames = min(int(2.0 * analysis_fps), max(1, frame_count // 4))
        start_candidates = range(0, search_frames + 1)
        end_first = max(frame_count - search_frames - 1, int(frame_count * 0.65))
        end_candidates = range(end_first, frame_count)
        minimum_gap = max(int(1.2 * analysis_fps), int(frame_count * 0.50))
        best = (float("inf"), 0, frame_count - 1)
        for start in start_candidates:
            start_motion = frames[min(start + 1, frame_count - 1)] - frames[start]
            for end in end_candidates:
                if end - start < minimum_gap:
                    continue
                end_motion = frames[end] - frames[max(0, end - 1)]
                visual = float(np.mean((frames[start] - frames[end]) ** 2))
                motion = float(np.mean((start_motion - end_motion) ** 2))
                trim_penalty = (start + (frame_count - 1 - end)) / frame_count * 0.012
                score = visual + motion * 0.32 + trim_penalty
                if score < best[0]:
                    best = (score, start, end)
        score, start_frame, end_frame = best
        start_time = start_frame / analysis_fps
        end_time = min(duration, (end_frame + 1) / analysis_fps)
        if end_time - start_time < max(1.0, duration * 0.50):
            return 0.0, duration, float(score)
        return start_time, end_time, float(score)

    @staticmethod
    def _ai_cache_key(
        video: str,
        start_time: float,
        duration: float,
        source_fps: float,
        source_w: int,
        source_h: int,
    ) -> str:
        source = Path(video)
        stat = source.stat()
        model = REAL_ESRGAN_MODELS / "realesr-animevideov3-x2.bin"
        model_stat = model.stat() if model.is_file() else None
        identity = {
            "path": str(source.resolve()),
            "size": stat.st_size,
            "mtime": stat.st_mtime_ns,
            "start": round(start_time, 5),
            "duration": round(duration, 5),
            "fps": round(source_fps, 5),
            "width": source_w,
            "height": source_h,
            "model_size": model_stat.st_size if model_stat else 0,
            "model_mtime": model_stat.st_mtime_ns if model_stat else 0,
            "scale": 2,
        }
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()[:24]

    def _enhance_clip_ai(
        self, video: str, output_dir: Path, start_time: float, duration: float, source_fps: float,
        source_w: int, source_h: int, temp_paths: list[Path], temp_dirs: list[Path],
        cpu_threads: int, base: float, weight: float, *, cache_source_video: str | None = None,
        cache_quota_gb: float = 50.0,
    ) -> tuple[str, int, int]:
        """Run Real-ESRGAN with a bounded PNG working set (CP-012/CP-021).

        Phase 6 no longer extracts the complete clip to PNG.  Each bounded
        chunk is extracted, enhanced, encoded losslessly to FFV1, and its PNG
        directories are removed before the next chunk.  Chunk videos are then
        concatenated into the deterministic cache entry.
        """

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_key = self._ai_cache_key(cache_source_video or video, start_time, duration, source_fps, source_w, source_h)
        cache_path = CACHE_DIR / f"{cache_key}.mkv"
        if cache_path.is_file():
            try:
                cached_info = probe_media(str(cache_path))
                cached_w, cached_h = first_video_size(cached_info)
                cached_duration = media_duration(cached_info)
                if (
                    (cached_w, cached_h) == (source_w * 2, source_h * 2)
                    and abs(cached_duration - duration) <= 0.20
                ):
                    touch_cache_entry(cache_path)
                    self._set_stage("Cache da IA", "Master aprimorado encontrado; pulando o Real-ESRGAN.")
                    self._log(f"Cache IA reutilizado: {cache_path.name}")
                    self._push_progress(base + weight)
                    return str(cache_path), cached_w, cached_h
            except Exception:
                pass
            try:
                cache_path.unlink(missing_ok=True)
            except OSError:
                pass

        total_frames = max(1, round(duration * source_fps))
        chunk_frames = choose_chunk_frames(
            FrameSpec(source_w, source_h, source_fps, "RGBA/PNG"),
            FrameSpec(source_w * 2, source_h * 2, source_fps, "RGBA/PNG"),
        )
        chunk_root = Path(tempfile.mkdtemp(prefix="studio_ai_chunks_", dir=output_dir))
        temp_dirs.append(chunk_root)
        chunks: list[Path] = []
        self._log(
            f"STORAGE Real-ESRGAN: {total_frames} frames em lotes de até {chunk_frames}; "
            "PNGs são liberados após cada lote."
        )

        processed = 0
        chunk_index = 0
        while processed < total_frames:
            if self._cancelled:
                raise InterruptedError
            count = min(chunk_frames, total_frames - processed)
            chunk_index += 1
            chunk_start = start_time + processed / max(1.0, source_fps)
            chunk_duration = count / max(1.0, source_fps)
            chunk_dir = chunk_root / f"chunk_{chunk_index:05d}"
            incoming, outgoing = chunk_dir / "entrada", chunk_dir / "melhorado"
            incoming.mkdir(parents=True)
            outgoing.mkdir(parents=True)
            fraction_before = processed / total_frames
            fraction_chunk = count / total_frames
            stage_base = base + weight * fraction_before * 0.90

            self._set_stage(
                "IA 1/3",
                f"Lote {chunk_index}: extraindo {count} quadro(s) ({processed + 1}–{processed + count}/{total_frames}).",
            )
            extract = [FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error"]
            if chunk_start > 0:
                extract += ["-ss", f"{chunk_start:.6f}"]
            extract += [
                "-i", video,
                "-map", "0:v:0", "-an", "-vf", f"fps={source_fps:.8f}",
                "-frames:v", str(count), "-start_number", "1",
                "-progress", "pipe:1", "-nostats", str(incoming / "frame%08d.png"),
            ]
            self._run_ffmpeg(extract, chunk_duration, stage_base, weight * fraction_chunk * 0.18)
            frames = len(list(incoming.glob("frame*.png")))
            if frames < 1:
                raise RuntimeError("A IA não recebeu nenhum quadro do vídeo.")

            self._set_stage("IA 2/3", f"Lote {chunk_index}: Real-ESRGAN em {frames} quadro(s).")
            command = [
                str(REAL_ESRGAN), "-i", str(incoming), "-o", str(outgoing), "-m", str(REAL_ESRGAN_MODELS),
                "-n", "realesr-animevideov3", "-s", "2", "-f", "png", "-t", "256", "-j", "2:2:2",
            ]
            self._run_ai(
                command, outgoing, frames,
                stage_base + weight * fraction_chunk * 0.18,
                weight * fraction_chunk * 0.58,
            )

            self._set_stage("IA 3/3", f"Lote {chunk_index}: compactando o resultado lossless e liberando PNGs.")
            chunk_video = chunk_root / f"segment_{chunk_index:05d}.mkv"
            merge = [
                FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
                "-framerate", f"{source_fps:.8f}", "-start_number", "1", "-i", str(outgoing / "frame%08d.png"),
                "-map", "0:v:0", "-an", "-frames:v", str(frames),
                "-c:v", "ffv1", "-level", "3", "-coder", "1", "-context", "1", "-g", "1", "-slicecrc", "1",
                "-pix_fmt", "yuv420p", "-threads", str(cpu_threads),
                "-progress", "pipe:1", "-nostats", str(chunk_video),
            ]
            self._run_ffmpeg(
                merge, chunk_duration,
                stage_base + weight * fraction_chunk * 0.76,
                weight * fraction_chunk * 0.14,
            )
            chunks.append(chunk_video)
            safe_rmtree(chunk_dir)
            processed += count

        if not chunks:
            raise RuntimeError("Real-ESRGAN não produziu segmentos.")
        enhanced = self._temp_file(output_dir, "studio_ai_x2_", temp_paths, suffix=".mkv")
        concat_file = chunk_root / "concat.txt"
        concat_file.write_text(
            "\n".join("file '" + str(item.resolve()).replace("'", "'\\''") + "'" for item in chunks) + "\n",
            encoding="utf-8",
        )
        self._set_stage("IA 3/3", f"Unindo {len(chunks)} lote(s) lossless no master aprimorado.")
        concat = [
            FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(concat_file), "-map", "0:v:0", "-an", "-c", "copy",
            "-progress", "pipe:1", "-nostats", str(enhanced),
        ]
        self._run_ffmpeg(concat, duration, base + weight * 0.90, weight * 0.10)
        for item in chunks:
            item.unlink(missing_ok=True)
        safe_rmtree(chunk_root)
        try:
            temp_dirs.remove(chunk_root)
        except ValueError:
            pass

        info = probe_media(str(enhanced))
        width, height = first_video_size(info)
        try:
            try:
                os.replace(enhanced, cache_path)
            except OSError:
                # A custom scratch may live on another volume.  Cross-volume
                # os.replace is not atomic, so copy to a staging file *inside*
                # the cache volume and promote there atomically.
                cache_temp = cache_path.with_name(f".{cache_path.name}.{time.time_ns()}.partial")
                try:
                    shutil.copy2(enhanced, cache_temp)
                    os.replace(cache_temp, cache_path)
                    enhanced.unlink(missing_ok=True)
                    self._log("Cache IA: promoção cross-volume concluída por staging local no volume de cache.")
                finally:
                    cache_temp.unlink(missing_ok=True)
            if enhanced in temp_paths:
                temp_paths.remove(enhanced)
            touch_cache_entry(cache_path)
            prune = enforce_cache_quota(PATHS.cache, cache_quota_gb, protected=(cache_path,))
            if prune.removed_files:
                self._log(f"CACHE LRU pós-IA: removidos {prune.removed_files} arquivo(s), {prune.removed_gb:.2f} GB.")
            if prune.after_bytes > prune.quota_bytes:
                self._log(
                    f"CACHE WARNING: a entrada ativa mantém o cache em {prune.after_gb:.2f} GB, "
                    f"acima da quota de {cache_quota_gb:.0f} GB; ela será reavaliada no próximo job."
                )
            self._log(f"Master aprimorado salvo no cache: {cache_path.name}")
            return str(cache_path), width, height
        except OSError as exc:
            self._log(f"Cache IA indisponível; usando master temporário deste job: {exc}")
            return str(enhanced), width, height

    def _run_ai(self, command: list[str], output_dir: Path, frames: int, base: float, weight: float) -> None:
        self._log("Comando IA: " + subprocess.list2cmdline(command))
        recent: deque[str] = deque(maxlen=50)
        process = subprocess.Popen(
            command, cwd=str(REAL_ESRGAN_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", **popen_group_kwargs(),
        )
        self._process = process

        def reader() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                clean = line.strip()
                if clean:
                    recent.append(clean); self._log(clean)
        thread = threading.Thread(target=reader, daemon=True); thread.start()
        while process.poll() is None:
            if self._cancelled:
                terminate_process_tree(process, self._log); break
            done = len(list(output_dir.glob("frame*.png")))
            self._push_progress(base + weight * min(1, done / max(1, frames)))
            time.sleep(0.25)
        code = process.wait(); thread.join(timeout=2)
        if self._cancelled:
            raise InterruptedError
        if code:
            raise RuntimeError("A melhoria por IA falhou.\n\n" + "\n".join(recent))
        self._push_progress(base + weight)

    def _prepare_reactive_audio(self, audio: str, focus: str, use_cpu: bool, cpu_threads: int) -> str:
        selected = stems_for_focus(focus)
        if not selected:
            return audio
        source = Path(audio)
        cache_root = PATHS.cache / "stems" / stem_cache_key(source)
        model_repo = ai_suite.MODELS / "demucs" / "local_repo"
        separated = cache_root / "htdemucs_ft" / source.stem

        def locate(name: str) -> Path | None:
            direct = separated / f"{name}.wav"
            if direct.is_file():
                return direct
            return next(cache_root.rglob(f"{name}.wav"), None) if cache_root.exists() else None

        if not all(locate(name) for name in ("bass", "drums", "vocals", "other")):
            self._set_stage("Demucs", "Separando baixo, bateria, voz e instrumentos para dirigir os VFX.")
            cache_root.mkdir(parents=True, exist_ok=True)
            command = build_demucs_command(ai_suite.VENV_PYTHON, model_repo, cache_root, source, use_cpu)
            self._log("Comando Demucs: " + subprocess.list2cmdline(command))
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                **popen_group_kwargs(),
            )
            self._process = process
            assert process.stdout is not None
            recent: deque[str] = deque(maxlen=80)
            for line in process.stdout:
                clean = line.strip()
                if clean:
                    recent.append(clean)
                    self._log(clean)
                if self._cancelled and process.poll() is None:
                    terminate_process_tree(process, self._log)
            code = process.wait()
            if self._cancelled:
                raise InterruptedError
            if code:
                raise RuntimeError("Demucs falhou.\n" + "\n".join(recent))

        stems = [locate(name) for name in selected]
        if not all(stems):
            raise RuntimeError(f"Demucs não produziu os stems necessários: {', '.join(selected)}")
        if len(stems) == 1:
            return str(stems[0])
        mixed = cache_root / ("reactive_" + "_".join(selected) + ".wav")
        if not mixed.is_file():
            command = [FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error"]
            for stem in stems:
                command += ["-i", str(stem)]
            inputs = "".join(f"[{index}:a]" for index in range(len(stems)))
            command += [
                "-filter_complex", f"{inputs}amix=inputs={len(stems)}:normalize=0,alimiter=limit=0.95[out]",
                "-map", "[out]", "-c:a", "pcm_s24le", "-threads", str(cpu_threads), str(mixed),
            ]
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.returncode:
                raise RuntimeError(result.stderr[-2000:])
        self._log(f"VFX guiado por stems: {', '.join(selected)}")
        return str(mixed)

    def _interpolate_rife(
        self,
        video: str,
        job_dir: Path,
        start_time: float,
        duration: float,
        source_fps: float,
        target_fps: float,
        use_cpu: bool,
        cpu_threads: int,
        temp_paths: list[Path],
        base: float,
        weight: float,
        *,
        color_plan: ColorPipeline,
    ) -> str:
        """Interpolate with RIFE using bounded frame chunks (CP-012).

        The previous implementation materialized every input and output PNG at
        once. Phase 6 processes contiguous chunks, converts each result to a
        lossless FFV1 segment, deletes its PNG workset, then concatenates the
        segments. This bounds scratch usage to one neural chunk plus compressed
        intermediates.
        """

        paths = RifePaths(RIFE_EXE, RIFE_MODEL)
        if not paths.available:
            raise RuntimeError("RIFE NCNN ou modelo rife-v4.6 não encontrado.")
        source_count = target_frame_count(duration, source_fps)
        total_target_count = target_frame_count(duration, target_fps)
        if total_target_count <= source_count:
            return video
        info = probe_media(video)
        frame_w, frame_h = first_video_size(info)
        ratio = target_fps / max(1.0, source_fps)
        chunk_frames = choose_chunk_frames(
            FrameSpec(frame_w, frame_h, source_fps, "RGBA/PNG"),
            FrameSpec(frame_w, frame_h, target_fps, "RGBA/PNG"),
            output_frames_per_input=ratio,
        )
        chunk_root = Path(tempfile.mkdtemp(prefix=f"rife_{time.time_ns()}_", dir=job_dir))
        chunks: list[Path] = []
        processed_source = 0
        produced_target = 0
        chunk_index = 0
        self._log(
            f"STORAGE RIFE: {source_count}→{total_target_count} frames em lotes de até {chunk_frames} frames fonte; "
            "PNGs são liberados após cada lote."
        )
        try:
            while processed_source < source_count:
                if self._cancelled:
                    raise InterruptedError
                remaining = source_count - processed_source
                count = min(chunk_frames, remaining)
                if remaining - count == 1:
                    count += 1
                count = min(count, remaining)
                if count < 2:
                    # A one-frame tail cannot be interpolated independently;
                    # it is intentionally represented by the preceding chunk.
                    break
                chunk_index += 1
                chunk_start = start_time + processed_source / max(1.0, source_fps)
                chunk_duration = count / max(1.0, source_fps)
                desired = min(
                    total_target_count - produced_target,
                    max(2, round(chunk_duration * target_fps)),
                )
                incoming = chunk_root / f"chunk_{chunk_index:05d}_in"
                outgoing = chunk_root / f"chunk_{chunk_index:05d}_out"
                incoming.mkdir(parents=True)
                outgoing.mkdir(parents=True)
                fraction_before = processed_source / source_count
                fraction_chunk = count / source_count
                stage_base = base + weight * fraction_before * 0.90

                self._set_stage(
                    "RIFE 1/3",
                    f"Lote {chunk_index}: extraindo {count} quadro(s) fonte ({processed_source + 1}–{processed_source + count}/{source_count}).",
                )
                extract = [FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error"]
                if chunk_start > 0:
                    extract += ["-ss", f"{chunk_start:.6f}"]
                extract += [
                    "-i", video, "-map", "0:v:0", "-an", "-vf", f"fps={source_fps:.8f}",
                    "-frames:v", str(count), "-start_number", "0",
                    "-progress", "pipe:1", "-nostats", str(incoming / "%08d.png"),
                ]
                self._run_ffmpeg(extract, chunk_duration, stage_base, weight * fraction_chunk * 0.18)
                extracted = len(list(incoming.glob("*.png")))
                if extracted < 2:
                    raise RuntimeError("RIFE recebeu menos de dois quadros no lote.")

                self._set_stage("RIFE 2/3", f"Lote {chunk_index}: gerando {desired} quadros com rife-v4.6.")
                command = build_rife_command(paths, incoming, outgoing, desired, use_cpu)
                self._log("Comando RIFE: " + subprocess.list2cmdline(command))
                recent: deque[str] = deque(maxlen=60)
                process = subprocess.Popen(
                    command,
                    cwd=str(RIFE_EXE.parent),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    **popen_group_kwargs(),
                )
                self._process = process

                def reader() -> None:
                    assert process.stdout is not None
                    for line in process.stdout:
                        clean = line.strip()
                        if clean:
                            recent.append(clean)
                            self._log(clean)

                reader_thread = threading.Thread(target=reader, daemon=True)
                reader_thread.start()
                while process.poll() is None:
                    if self._cancelled:
                        terminate_process_tree(process, self._log)
                        break
                    completed = len(list(outgoing.glob("*.png")))
                    self._push_progress(
                        stage_base + weight * fraction_chunk * (0.18 + 0.58 * min(1.0, completed / max(1, desired)))
                    )
                    time.sleep(0.25)
                code = process.wait()
                reader_thread.join(timeout=2)
                if self._cancelled:
                    raise InterruptedError
                if code:
                    raise RuntimeError("RIFE falhou.\n" + "\n".join(recent))
                frames = sorted(outgoing.glob("*.png"))
                if len(frames) < max(2, desired - 1):
                    raise RuntimeError(f"RIFE produziu {len(frames)} de {desired} quadros esperados no lote.")

                self._set_stage("RIFE 3/3", f"Lote {chunk_index}: compactando lossless e liberando PNGs.")
                first_number = int(frames[0].stem)
                chunk_video = chunk_root / f"segment_{chunk_index:05d}.mkv"
                merge = [
                    FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
                    "-framerate", f"{target_fps:.8f}", "-start_number", str(first_number),
                    "-i", str(outgoing / "%08d.png"), "-map", "0:v:0", "-an",
                    "-frames:v", str(len(frames)),
                    "-c:v", "ffv1", "-level", "3", "-coder", "1", "-context", "1", "-g", "1", "-slicecrc", "1",
                    "-pix_fmt", color_plan.working_pix_fmt if color_plan.working_pix_fmt in {"yuv420p", "yuv420p10le"} else "yuv420p",
                    "-threads", str(cpu_threads), "-progress", "pipe:1", "-nostats", str(chunk_video),
                ]
                self._run_ffmpeg(
                    merge, max(0.01, len(frames) / target_fps),
                    stage_base + weight * fraction_chunk * 0.76,
                    weight * fraction_chunk * 0.14,
                )
                chunks.append(chunk_video)
                safe_rmtree(incoming)
                safe_rmtree(outgoing)
                processed_source += count
                produced_target += len(frames)

            if not chunks:
                raise RuntimeError("RIFE não produziu segmentos interpolados.")
            concat_file = chunk_root / "concat.txt"
            concat_file.write_text(
                "\n".join("file '" + str(item.resolve()).replace("'", "'\\''") + "'" for item in chunks) + "\n",
                encoding="utf-8",
            )
            interpolated = self._temp_file(
                job_dir,
                "studio_rife_",
                temp_paths,
                suffix=".mkv",
            )
            self._set_stage("RIFE 3/3", f"Unindo {len(chunks)} lote(s) lossless no master interpolado.")
            concat = [
                FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", str(concat_file), "-map", "0:v:0", "-an", "-c", "copy",
                "-t", f"{duration:.6f}", "-progress", "pipe:1", "-nostats", str(interpolated),
            ]
            self._run_ffmpeg(concat, duration, base + weight * 0.90, weight * 0.10)
            return str(interpolated)
        finally:
            safe_rmtree(chunk_root)

    @staticmethod
    def _release_temp_path(value: str | Path, paths: list[Path]) -> None:
        path = Path(value)
        try:
            tracked = next((item for item in paths if item == path), None)
        except OSError:
            tracked = None
        if tracked is None:
            return
        try:
            tracked.unlink(missing_ok=True)
        except OSError:
            return
        try:
            paths.remove(tracked)
        except ValueError:
            pass

    @staticmethod
    def _temp_file(directory: Path, prefix: str, paths: list[Path], suffix: str = ".mp4") -> Path:
        handle = tempfile.NamedTemporaryFile(prefix=prefix, suffix=suffix, dir=directory, delete=False)
        path = Path(handle.name); handle.close(); paths.append(path); return path

    def _run_ffmpeg(self, command: list[str], duration: float, base: float, weight: float) -> None:
        self._log("Comando FFmpeg: " + subprocess.list2cmdline(command))
        recent: deque[str] = deque(maxlen=60)
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", **popen_group_kwargs(),
        )
        self._process = process
        assert process.stdout is not None
        for raw in process.stdout:
            line = raw.strip()
            if line:
                recent.append(line); self._log(line)
            if line.startswith("out_time="):
                try:
                    hours, minutes, seconds = line.split("=", 1)[1].split(":")
                    elapsed = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                    self._push_progress(base + weight * min(1, elapsed / max(0.001, duration)))
                except ValueError:
                    pass
            if self._cancelled and process.poll() is None:
                terminate_process_tree(process, self._log)
        code = process.wait()
        if self._cancelled:
            raise InterruptedError
        if code:
            raise RuntimeError("A etapa de vídeo falhou.\n\n" + "\n".join(recent))
        self._push_progress(base + weight)

    def _verify_output(
        self, path: str, duration: float, width: int, height: int, fps: int,
        *, delivery_plan: DeliveryPlan | None = None, expected_audio: bool = False,
        expected_audio_channels: int | None = None, expected_audio_sample_rate: int | None = None,
        deep: bool = False,
    ) -> dict:
        mode = "profunda" if deep else "rápida"
        self._set_stage(
            "Verificando",
            f"Verificação {mode}: resolução, CFR, quadros, duração, streams, codecs e sincronismo A/V."
            + (" Decodificando até EOF." if deep else ""),
        )
        expected = VerifyExpectation(
            width=width, height=height, fps=float(fps), duration=float(duration),
            expect_audio=bool(expected_audio),
            video_codec=delivery_plan.video_codec if delivery_plan else None,
            audio_codec=delivery_plan.audio_codec if delivery_plan and expected_audio else None,
            audio_channels=expected_audio_channels if expected_audio else None,
            audio_sample_rate=expected_audio_sample_rate if expected_audio else None,
        )
        result = (
            deep_verify(FFMPEG, FFPROBE, path, expected)
            if deep else quick_verify(FFPROBE, path, expected)
        )
        for issue in result.issues:
            self._log(f"VERIFY {issue.severity.upper()} [{issue.code}] {issue.message}")
        if not result.passed:
            errors = " • ".join(issue.message for issue in result.errors)
            raise RuntimeError("A verificação final falhou: " + errors)
        self._log(
            f"VERIFY {result.mode.upper()} PASS: {result.width}x{result.height} • {result.fps:.3f} fps • "
            f"frames={result.frame_count if result.frame_count is not None else '?'} / esperado~{result.expected_frame_count} • "
            f"CFR={result.cfr} • decodeEOF={result.decoded_to_eof} • "
            f"A/V delta={result.av_sync_delta if result.av_sync_delta is not None else 'n/a'}"
        )
        return {
            "info": result.probe, "width": result.width, "height": result.height,
            "fps": result.fps, "duration": result.duration, "verification": result,
        }

    def _sample_quality_warnings(self, path: str, duration: float) -> list[str]:
        warnings: list[str] = []
        for position in (duration * 0.18, duration * 0.50, duration * 0.82):
            command = [
                FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", f"{max(0, position):.4f}",
                "-i", path, "-an", "-vf",
                "fps=12,scale=320:180:force_original_aspect_ratio=decrease:flags=area,"
                "pad=320:180:(ow-iw)/2:(oh-ih)/2:color=black,format=gray",
                "-frames:v", "2", "-f", "rawvideo", "pipe:1",
            ]
            result = subprocess.run(command, capture_output=True, creationflags=CREATE_NO_WINDOW, check=False)
            frame_size = 320 * 180
            if result.returncode or len(result.stdout) < frame_size:
                continue
            frames = np.frombuffer(result.stdout[: frame_size * 2], dtype=np.uint8)
            if frames.size >= frame_size * 2:
                frames = frames.reshape(2, 180, 320).astype(np.float32) / 255.0
                temporal_change = float(np.mean(np.abs(frames[1] - frames[0])))
                if temporal_change > 0.30:
                    warnings.append(f"Possível cintilação ou mudança muito brusca perto de {format_time(position)}.")
                frame = frames[0]
            else:
                frame = frames[:frame_size].reshape(180, 320).astype(np.float32) / 255.0
            clipped = float(np.mean((frame < 0.01) | (frame > 0.99)))
            edge = float((np.mean(np.abs(np.diff(frame, axis=0))) + np.mean(np.abs(np.diff(frame, axis=1)))) / 2)
            if clipped > 0.62:
                warnings.append(f"Grande área sem detalhe em sombras/luzes perto de {format_time(position)}; pode ser intencional.")
            if edge > 0.24:
                warnings.append(f"Nitidez muito alta perto de {format_time(position)}; confira halos no comparador de preview.")
        return list(dict.fromkeys(warnings))

    def _write_quality_report(
        self,
        output_path: Path,
        settings: RenderSettings,
        verification: dict,
        project_duration: float,
        *,
        render_plan: RenderPlan | None = None,
    ) -> str:
        self._set_stage("Relatório final", "Registrando qualidade, codecs, áudio e possíveis alertas.")
        info = verification["info"]
        streams = info.get("streams", [])
        video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
        audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
        format_info = info.get("format", {})
        try:
            bitrate_value = int(format_info.get("bit_rate") or 0)
        except (TypeError, ValueError):
            bitrate_value = 0
        bitrate_mbps = bitrate_value / 1_000_000
        warnings = self._sample_quality_warnings(str(output_path), project_duration) if settings.quality_check else []
        vmaf_score: float | None = None
        if settings.quality_check and settings.mode == MODE_ORIGINAL:
            try:
                vmaf_score = measure_vmaf(FFMPEG, settings.video, str(output_path), project_duration)
                self._log(f"VMAF amostral: {vmaf_score:.2f}")
            except Exception as exc:
                self._log(f"VMAF não disponível para esta saída: {exc}")
        if not warnings and settings.quality_check:
            warnings = ["A amostragem automática não encontrou sinais evidentes de cintilação, clipping visual ou nitidez excessiva."]
        lines = [
            "RELATÓRIO FINAL — CINEPULSE",
            "=" * 44,
            "",
            f"Arquivo: {output_path}",
            f"Criado em: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Tamanho: {output_path.stat().st_size / (1024 ** 3):.3f} GB",
            f"Duração: {format_time(verification['duration'])}",
            f"Imagem: {verification['width']}×{verification['height']} • {verification['fps']:.3f} fps",
            f"Vídeo: {video_stream.get('codec_name', 'desconhecido')} • {video_stream.get('pix_fmt', 'desconhecido')} • {bitrate_mbps:.2f} Mb/s total",
            f"Áudio: {audio_stream.get('codec_name', 'sem áudio')} • {audio_stream.get('sample_rate', '-')} Hz • {audio_stream.get('channels', '-')} canais",
            "",
            "CONFIGURAÇÃO",
            f"Melhoria: {settings.enhancement}",
            f"Interpolação: {settings.interpolation}",
            f"Tratamento do áudio: {settings.audio_mode}",
            f"Direção musical: {settings.visual_direction}",
            f"VFX: {', '.join(sorted(settings.effects)) if settings.effects else 'nenhum'}",
            f"Processamento: {'Somente CPU' if settings.use_cpu else 'Aceleração automática'} • {settings.cpu_threads} threads de CPU",
            f"Scratch: {resolve_scratch_dir(settings.scratch_dir, WORK_DIR)}",
            f"Quota de cache: {settings.cache_quota_gb:.0f} GB • política LRU automática",
        ]
        active_history = getattr(self, "_active_render_history", None)
        if active_history is not None:
            lines.append(f"Histórico técnico: {active_history.path}")
        verified = verification.get("verification")
        if verified is not None:
            lines += [
                "",
                "VERIFICAÇÃO TÉCNICA",
                f"Modo: {verified.mode}",
                f"Resultado: {'PASS' if verified.passed else 'FAIL'}",
                f"Quadros: {verified.frame_count if verified.frame_count is not None else '?'} • esperado ~{verified.expected_frame_count}",
                f"Cadência CFR: {verified.cfr}",
                f"Decode até EOF: {'sim' if verified.decoded_to_eof else 'não executado'}",
                f"A/V sync delta: {verified.av_sync_delta:.3f}s" if verified.av_sync_delta is not None else "A/V sync delta: n/a",
            ]
            if verified.issues:
                lines += [f"• [{issue.severity.upper()} {issue.code}] {issue.message}" for issue in verified.issues]
        if render_plan is not None:
            lines += [
                "",
                f"RENDERPLAN • {render_plan.fingerprint}",
                f"Arquitetura: {render_plan.architecture_version}",
            ] + [f"• {step.summary()}" for step in render_plan.steps]
            if render_plan.risks:
                lines += ["", "RISCOS ESTRUTURAIS DECLARADOS"] + [
                    f"• [{risk.severity.upper()} {risk.code}] {risk.title}: {risk.detail}" for risk in render_plan.risks
                ]
        lines += [
            "",
            "ANÁLISE AUTOMÁTICA",
        ]
        if vmaf_score is not None:
            lines += [f"• VMAF perceptivo amostral: {vmaf_score:.2f}/100 (referência: vídeo de entrada)."]
        lines += [f"• {warning}" for warning in warnings] if warnings else ["Análise de artefatos desativada pelo usuário."]
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        report_path = REPORT_DIR / f"{output_path.stem}_{stamp}_relatorio.txt"
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._log(f"Relatório salvo em: {report_path}")
        return str(report_path)

    def _push_progress(self, value: float) -> None:
        self._events.put(("progress", max(0.0, min(100.0, value))))

    def _set_stage(self, stage: str, detail: str) -> None:
        self._events.put(("stage", stage, detail))
        self._log(f"[{stage}] {detail}")

    def _log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        history = getattr(self, "_active_render_history", None)
        if history is not None:
            try:
                history.append_log(message)
            except OSError:
                pass
        self._events.put(("log", f"[{stamp}] {message}"))

    def _show_log(self) -> None:
        if self._log_window and self._log_window.winfo_exists():
            self._log_window.lift(); return
        window = Toplevel(self.root)
        window.title("Log do processamento")
        window.geometry("900x520")
        frame = ttk.Frame(window, padding=10); frame.pack(fill="both", expand=True)
        text = Text(frame, wrap="none", font=("Consolas", 9), background="#101418", foreground="#D7E0E8")
        vertical = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        text.grid(row=0, column=0, sticky="nsew"); vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1); frame.columnconfigure(0, weight=1)
        text.insert("end", "\n".join(self._logs)); text.configure(state="disabled")
        self._log_window, self._log_text = window, text

    def _create_diagnostics(self) -> None:
        try:
            from .diagnostics import write_report

            report = write_report()
            self._set_feedback(
                "success", "Diagnóstico criado",
                "O relatório foi gerado sem nomes de mídia e está pronto para inspeção.",
                category="Diagnóstico", primary=("Abrir relatório", lambda value=report: self._open_external_path(value)),
            )
            self._open_external_path(report)
        except Exception as exc:
            self._log(f"Falha ao criar diagnóstico: {exc}")
            self._set_feedback(
                "error", "Não foi possível criar o diagnóstico",
                "O CinePulse preservou o estado atual; consulte o detalhe técnico antes de tentar novamente.",
                category="Diagnóstico", secondary=("Ver log", self._show_log), technical_detail=str(exc),
            )

    def _install_components(self) -> None:
        installer = APP_DIR / "installer" / "Start-CinePulse.ps1"
        if not installer.is_file():
            self._set_feedback(
                "error", "Instalador de componentes ausente",
                "O script de instalação completa não está presente nesta cópia do CinePulse.",
                category="IA local", secondary=("Diagnóstico", self._create_diagnostics),
            )
            return
        try:
            command = [
                find_powershell().executable, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(installer),
            ]
            if installation_mode(APP_DIR) == "installed":
                command.append("-NonPortable")
            command.append("-InstallOnly")
            subprocess.Popen(
                command,
                cwd=str(APP_DIR),
                creationflags=0x00000010 if os.name == "nt" else 0,
            )
            self._set_feedback(
                "info", "Instalador completo aberto",
                "A instalação continua em uma janela separada. Quando terminar, reinicie o CinePulse para reverificar os componentes.",
                category="IA local", primary=("Abrir IA local", lambda: self._open_tab(5)),
            )
        except OSError as exc:
            self._set_feedback(
                "error", "Não foi possível abrir o instalador",
                "Nenhuma instalação foi iniciada; a configuração atual permanece intacta.",
                category="IA local", secondary=("Diagnóstico", self._create_diagnostics), technical_detail=str(exc),
            )

    def _startup_update_check(self) -> None:
        # Startup discovery is deliberately silent and asynchronous: network
        # latency must never delay the editor or produce a modal error dialog.
        self._check_updates(silent=True)

    def _hide_update_cta(self) -> None:
        self._available_update = None
        if hasattr(self, "update_button"):
            self.update_button.configure(text="Atualizações", command=self._check_updates, state="normal")
        if hasattr(self, "header_update_button") and self.header_update_button.winfo_manager():
            self.header_update_button.pack_forget()

    def _show_update_cta(self, info: update_manager.UpdateInfo) -> None:
        self._available_update = info
        label = f"Atualizar v{info.version}"
        if hasattr(self, "update_button"):
            self.update_button.configure(text=label, command=self._apply_available_update, state="normal")
        if hasattr(self, "header_update_button"):
            self.header_update_button.configure(text=label, state="normal")
            if not self.header_update_button.winfo_manager():
                self.header_update_button.pack(side="left", padx=(0, 8), before=self.header_help_button)

    def _check_updates(self, *, silent: bool = False) -> None:
        if self._update_check_running:
            return
        self._update_check_running = True
        if hasattr(self, "update_button"):
            self.update_button.configure(state="disabled")
        if not silent:
            self._set_feedback(
                "busy", "Verificando atualizações",
                "Consultando a última release Stable do GitHub sem alterar a instalação atual.",
                category="Atualização",
            )
        install_mode = installation_mode(APP_DIR)

        def worker() -> None:
            try:
                info = update_manager.check_available(
                    __version__, installation=install_mode, timeout=5,
                )
                self._events.put(("update_checked", info, silent))
            except Exception as exc:
                self._events.put(("update_error", "check", str(exc), silent))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_available_update(self) -> None:
        info = self._available_update
        if info is None:
            self._check_updates(silent=False)
            return
        if self._busy or self._queue_running or self._ai_installing:
            self._set_feedback(
                "warning", "Atualização aguardando",
                "Conclua ou cancele o processamento atual; o CinePulse não fecha um render para instalar uma atualização.",
                category="Atualização",
            )
            return
        if hasattr(self, "header_update_button"):
            self.header_update_button.configure(state="disabled")
        if hasattr(self, "update_button"):
            self.update_button.configure(state="disabled")
        self._stage_update(info)

    def _stage_update(self, info: update_manager.UpdateInfo) -> None:
        package = "MSI" if info.package_kind == "msi" else "pacote portátil"
        self._set_feedback(
            "busy", f"Baixando CinePulse {info.version}",
            f"Baixando o {package} da release oficial e verificando SHA-256 antes de fechar o programa.",
            category="Atualização",
        )

        def worker() -> None:
            try:
                staged = update_manager.stage(info)
                self._events.put(("update_ready", info, str(staged)))
            except Exception as exc:
                self._events.put(("update_error", "stage", str(exc), False))

        threading.Thread(target=worker, daemon=True).start()

    def _launch_prepared_update(self, info: update_manager.UpdateInfo, staged: str) -> None:
        update_manager.launch_staged(info, Path(staged), APP_DIR, os.getpid())
        self._set_feedback(
            "success", f"CinePulse {info.version} verificado",
            "A atualização será aplicada assim que esta janela fechar e o CinePulse abrirá novamente automaticamente.",
            category="Atualização",
        )
        self._on_close()

    def _recover_interrupted_render(self) -> None:
        payload = self._render_journal.read()
        if not payload:
            return
        try:
            pid = int(payload.get("pid") or 0)
        except (TypeError, ValueError):
            pid = 0
        if pid != os.getpid() and process_alive(pid):
            self._set_feedback(
                "warning", "Há outro CinePulse processando",
                f"Outro processo CinePulse está renderizando (PID {pid}). Esta janela não tentará recuperar ou substituir a saída.",
                category="Recuperação",
            )
            return
        partial_value = payload.get("partial")
        final_value = payload.get("final")
        if not partial_value or not final_value:
            self._render_journal.clear()
            return
        partial = Path(partial_value)
        final = Path(final_value)
        if not partial.is_file():
            self._render_journal.clear()
            return
        try:
            info = probe_media(str(partial))
            valid = media_duration(info) > 0 and first_video_size(info) != (0, 0)
        except Exception:
            valid = False
        if valid and messagebox.askyesno(
            APP_TITLE,
            "Uma renderização anterior terminou, mas não foi promovida para o arquivo final.\n\n"
            f"Recuperar agora?\n\n{final}",
        ):
            atomic = AtomicOutput(final, partial, final.with_name(f".{final.name}.previous"))
            try:
                recovered = atomic.commit()
                self._render_journal.clear()
                self._set_feedback(
                    "success", "Renderização anterior recuperada",
                    f"{recovered.name} foi promovido para a saída final após validação do arquivo parcial.",
                    category="Recuperação", primary=("Abrir arquivo", lambda value=recovered: self._open_external_path(value)),
                )
                return
            except Exception as exc:
                self._set_feedback(
                    "error", "A recuperação não pôde ser concluída",
                    "O arquivo parcial foi preservado e não será apagado automaticamente.",
                    category="Recuperação", secondary=("Ver log", self._show_log), technical_detail=str(exc),
                )
                return
        self._set_feedback(
            "warning", "Saída interrompida preservada",
            f"{partial.name} permanece guardado para análise; o CinePulse não o promoveu sem validação.",
            category="Recuperação", primary=("Abrir arquivo", lambda value=partial: self._open_external_path(value)),
        )

    def _append_log_ui(self, line: str) -> None:
        self._logs.append(line)
        if self._log_text and self._log_text.winfo_exists():
            self._log_text.configure(state="normal")
            self._log_text.insert("end", line + "\n")
            self._log_text.see("end")
            self._log_text.configure(state="disabled")

    def _tick_clock(self) -> None:
        if self._busy and self._started_at is not None:
            elapsed = max(0, time.monotonic() - self._started_at)
            if self._progress_value >= 1:
                total = elapsed / (self._progress_value / 100)
                remaining = max(0, total - elapsed)
                eta = format_time(remaining)
            else:
                eta = "--:--:--"
            self.time_text.set(f"Decorrido {format_time(elapsed)}  •  Restante estimado {eta}")
        self._schedule(500, self._tick_clock)

    def _poll_events(self) -> None:
        try:
            while True:
                event = self._events.get_nowait()
                kind = event[0]
                if kind == "progress":
                    self._progress_value = float(event[1]); self.bar["value"] = self._progress_value
                    self.progress_text.set(f"{self._progress_value:.1f}%")
                    if self._queue_running:
                        active = self._active_queue_item()
                        if active:
                            active["progress"] = self._progress_value
                            self._update_active_queue_ui()
                elif kind == "stage":
                    self.stage.set(event[1])
                    self._set_feedback(
                        "busy", event[1], event[2],
                        category="Fila" if self._queue_running else "Render",
                        secondary=("Ver log", self._show_log),
                        record=False,
                    )
                    if self._queue_running:
                        active = self._active_queue_item()
                        if active:
                            active["stage"] = event[1]
                            self._update_active_queue_ui()
                elif kind == "log":
                    self._append_log_ui(event[1])
                elif kind == "home_preview":
                    _, serial, image, source, source_path, used_video = event
                    if serial == self._home_preview_serial and hasattr(self, "home_preview_label"):
                        if source is not None:
                            self._home_preview_source = source
                            self._home_preview_source_path = source_path
                        self._home_preview_photo = PhotoImage(data=to_ppm_bytes(image), format="PPM")
                        self.home_preview_label.configure(image=self._home_preview_photo)
                        self.home_preview_source_text.set(
                            "Frame real do vídeo • VFX demonstrados sem render completo"
                            if used_video else
                            "Demonstração interna • selecione um vídeo para usar um frame real"
                        )
                elif kind == "project_video":
                    _, serial, source_path, media_summary, source_size, source_frame, probe_info, error = event
                    if serial == self._project_video_serial and source_path == self.video.get().strip():
                        if error or media_summary is None:
                            self.project_video_badge.set("⚠ Não foi possível analisar")
                            self._set_project_status_style("video", "error")
                            self.project_video_headline.set(Path(source_path).name if source_path else "Vídeo inválido")
                            self.project_video_detail.set(error or "FFprobe não retornou metadados válidos.")
                            self._project_source_rgb = None
                            self._project_source_path = ""
                            self._project_video_size = None
                            self._project_video_probe = None
                            self._project_video_probe_path = ""
                        else:
                            self.project_video_badge.set("✓ " + media_summary.badge)
                            self._set_project_status_style("video", "ok")
                            self.project_video_headline.set(media_summary.headline)
                            self.project_video_detail.set(media_summary.detail)
                            self._project_video_size = source_size
                            self._project_video_probe = probe_info
                            self._project_video_probe_path = source_path
                            if source_frame is not None:
                                self._project_source_rgb = source_frame
                                self._project_source_path = source_path
                            else:
                                self._project_source_rgb = None
                                self._project_source_path = ""
                        self._refresh_project_framing_sync()
                        self._refresh_quality_impact()
                elif kind == "project_audio":
                    _, serial, source_path, media_summary, probe_info, error = event
                    if serial == self._project_audio_serial and source_path == self.audio.get().strip():
                        if error or media_summary is None:
                            self.project_audio_badge.set("⚠ Não foi possível analisar")
                            self._set_project_status_style("audio", "error")
                            self.project_audio_headline.set(Path(source_path).name if source_path else "Áudio inválido")
                            self.project_audio_detail.set(error or "FFprobe não retornou metadados válidos.")
                            self._project_audio_probe = None
                            self._project_audio_probe_path = ""
                        else:
                            self.project_audio_badge.set("✓ " + media_summary.badge)
                            self._set_project_status_style("audio", "ok")
                            self.project_audio_headline.set(media_summary.headline)
                            self.project_audio_detail.set(media_summary.detail)
                            self._project_audio_probe = probe_info
                            self._project_audio_probe_path = source_path
                        self._refresh_quality_impact()
                elif kind == "project_preflight":
                    _, serial, report, error = event
                    if serial == self._project_preflight_serial:
                        self._apply_project_preflight_report(report, error)
                elif kind == "visual_preview":
                    _, serial, image, variants, source, source_path, used_video = event
                    if serial == self._visual_preview_serial and hasattr(self, "visual_preview_label"):
                        if source is not None:
                            self._visual_preview_source = source
                            self._visual_preview_source_path = source_path
                        self._visual_preview_photo = PhotoImage(data=to_ppm_bytes(image), format="PPM")
                        self.visual_preview_label.configure(image=self._visual_preview_photo)
                        for key, variant_image in variants.items():
                            if key not in getattr(self, "_visual_variant_labels", {}):
                                continue
                            photo = PhotoImage(data=to_ppm_bytes(variant_image), format="PPM")
                            self._visual_variant_photos[key] = photo
                            self._visual_variant_labels[key].configure(image=photo)
                        self.visual_preview_source_text.set(
                            "Frame real do vídeo • VFX reais • reação musical demonstrativa"
                            if used_video else
                            "Demonstração interna • VFX reais • reação musical demonstrativa"
                        )
                elif kind == "update_checked":
                    info = event[1]
                    silent = bool(event[2]) if len(event) > 2 else False
                    self._update_check_running = False
                    if info is None:
                        self._hide_update_cta()
                        if not silent:
                            self._set_feedback(
                                "success", "CinePulse atualizado",
                                "Você já está usando a versão Stable mais recente publicada no GitHub.",
                                category="Atualização",
                            )
                    else:
                        self._show_update_cta(info)
                        self._set_feedback(
                            "info", f"CinePulse {info.version} disponível",
                            "Nova versão verificada. Clique em Atualizar; o download, a verificação e o reinício são automáticos.",
                            category="Atualização", primary=("Atualizar agora", self._apply_available_update),
                        )
                elif kind == "update_ready":
                    info = event[1]
                    staged = str(event[2])
                    try:
                        self._launch_prepared_update(info, staged)
                    except Exception as exc:
                        self._events.put(("update_error", "launch", str(exc), False))
                elif kind == "update_error":
                    phase = str(event[1]) if len(event) > 1 else "check"
                    detail = str(event[2]) if len(event) > 2 else "Falha desconhecida."
                    silent = bool(event[3]) if len(event) > 3 else False
                    self._update_check_running = False
                    if self._available_update is not None:
                        self._show_update_cta(self._available_update)
                    elif hasattr(self, "update_button"):
                        self.update_button.configure(text="Atualizações", command=self._check_updates, state="normal")
                    if silent and phase == "check":
                        self._log("Verificação automática de atualização indisponível: " + detail)
                    else:
                        self._set_feedback(
                            "error", "Não foi possível concluir a atualização",
                            "A versão atual foi preservada; nenhuma substituição incompleta foi promovida.",
                            category="Atualização", secondary=("Ver log", self._show_log), technical_detail=detail,
                        )
                elif kind == "ai_install_done":
                    self._finish_ai_component_install()
                    self.ai_install_progress.set(100.0)
                    self.ai_install_progress_text.set("Concluído")
                    self.ai_install_status_text.set("Instalação concluída e inventário verificado novamente.")
                    self.stage.set("Componentes prontos")
                    installed_names = ", ".join(str(name) for name in event[1])
                    self._set_feedback(
                        "success", "Componentes instalados e verificados",
                        f"A suíte local foi reverificada: {installed_names}.",
                        category="IA local", primary=("Abrir IA local", lambda: self._open_tab(5)),
                    )
                elif kind == "ai_install_error":
                    self._finish_ai_component_install()
                    self.ai_install_progress_text.set("Interrompido")
                    self.ai_install_status_text.set("A instalação foi interrompida com segurança; consulte o log para o último detalhe.")
                    self.stage.set("Erro na instalação")
                    self._set_feedback(
                        "error", "Instalação de componentes interrompida",
                        "Nenhum componente incompleto foi anunciado como pronto. Reveja o inventário ou o log antes de tentar novamente.",
                        category="IA local", primary=("Abrir IA local", lambda: self._open_tab(5)),
                        secondary=("Ver log", self._show_log), technical_detail=str(event[1]),
                    )
                elif kind == "done":
                    _, path, preview, size, report_path, *extra = event
                    history_path = str(extra[0]) if extra else ""
                    self._finish_busy(); self.bar["value"] = 100; self.progress_text.set("100%")
                    self.stage.set("Concluído")
                    result_label = "Preview criado e verificado" if preview else "Vídeo final criado e verificado"
                    self._set_feedback(
                        "success", result_label,
                        f"{Path(path).name} • {size / (1024**2):.1f} MB",
                        category="Preview" if preview else ("Fila" if self._queue_running else "Render"),
                        primary=("Abrir arquivo", lambda value=path: self._open_external_path(value)),
                        secondary=("Abrir relatório", lambda value=report_path: self._open_external_path(value)) if report_path else None,
                    )
                    if self._queue_running and not preview:
                        active = self._active_queue_item()
                        if active:
                            active["status"] = "Concluído"
                            active["progress"] = 100.0
                            active["stage"] = "Concluído"
                            active["report"] = report_path
                            active["history"] = history_path
                        self._active_queue_id = None
                        self._refresh_queue_tree()
                        self._save_queue()
                        self._schedule(250, self._run_next_queue_item)
                    elif preview:
                        self._open_external_path(path)
                elif kind == "cancelled":
                    history_path = str(event[1]) if len(event) > 1 else ""
                    self._finish_busy(); self.stage.set("Cancelado")
                    self._set_feedback(
                        "warning", "Processamento cancelado",
                        "A etapa atual foi encerrada com segurança e os temporários do job foram removidos.",
                        category="Fila" if self._queue_running else "Render", secondary=("Ver log", self._show_log),
                    )
                    if self._queue_running:
                        active = self._active_queue_item()
                        if active:
                            active["status"] = "Cancelado"
                            active["progress"] = self._progress_value
                            active["stage"] = "Cancelado pelo usuário"
                            active["error"] = "Execução cancelada pelo usuário."
                            active["history"] = history_path
                        self._queue_running = False
                        self._active_queue_id = None
                        self._refresh_queue_tree()
                        self._save_queue()
                elif kind == "error":
                    history_path = str(event[2]) if len(event) > 2 else ""
                    self._finish_busy(); self.stage.set("Erro")
                    self._announce_failure(str(event[1]), category="Fila" if self._queue_running else "Render")
                    if self._queue_running:
                        active = self._active_queue_item()
                        if active:
                            active["status"] = "Erro"
                            active["progress"] = self._progress_value
                            active["stage"] = "Falha no processamento"
                            active["error"] = event[1]
                            active["history"] = history_path
                        self._active_queue_id = None
                        self._refresh_queue_tree()
                        self._save_queue()
                        self._schedule(250, self._run_next_queue_item)
                    else:
                        pass
        except queue.Empty:
            pass
        self._schedule(100, self._poll_events)

    def _finish_busy(self) -> None:
        self._busy = False
        self.render_button.configure(state="normal")
        self.preview_button.configure(state="normal")
        self.add_queue_button.configure(state="normal")
        self.start_queue_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.cancel_button.pack_forget()
        self._refresh_footer_density()
        self._refresh_queue_overview()

    def _write_render_lock(self, preview: bool) -> None:
        PATHS.locks.mkdir(parents=True, exist_ok=True)
        lock = PATHS.locks / "render.json"
        temporary = lock.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"schema": 1, "pid": os.getpid(), "started_at": time.time(), "preview": bool(preview)},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        os.replace(temporary, lock)


    def _cancel(self) -> None:
        if not self._busy:
            return
        self._cancelled = True
        self.stage.set("Cancelando")
        self._set_feedback(
            "busy", "Cancelando com segurança",
            "Encerrando a árvore de processos e preservando a saída final anterior. Aguarde a confirmação.",
            category="Fila" if self._queue_running else "Render", secondary=("Ver log", self._show_log), record=False,
        )
        if self._process and self._process.poll() is None:
            terminate_process_tree(self._process, self._log)

    def _on_close(self) -> None:
        if self._closing:
            return
        if self._busy and not messagebox.askyesno(APP_TITLE, "Existe um processamento em andamento. Cancelar e sair?"):
            return
        if self._busy:
            self._cancel()
        # From this point on no Studio-owned timer is allowed to touch Tk.
        self._closing = True
        self._visual_preview_playing = False
        self._save_queue()
        self._save_ui_state()
        self._cancel_scheduled_callbacks()
        self.root.destroy()


def main() -> None:
    enable_windows_dpi_awareness()
    root = Tk()
    icon = APP_DIR / "assets" / "cinepulse.ico"
    if os.name == "nt" and icon.is_file():
        try:
            root.iconbitmap(default=str(icon))
        except Exception:
            pass
    VideoOptimizerStudio(root)
    root.mainloop()


if __name__ == "__main__":
    main()
