from __future__ import annotations

import json
import hashlib
import os
import queue
import shutil
import subprocess
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
from .hardware import detect_hardware
from .media_profile import ColorProfile
from .process_control import terminate_process_tree
from .safe_output import AtomicOutput, RenderJournal, process_alive
from .rife_engine import RifePaths, build_command as build_rife_command, target_frame_count
from .audio_mastering import analyze_loudness, build_audio_filter
from . import __version__
from .quality_metrics import measure_vmaf
from .stem_engine import build_demucs_command, stem_cache_key, stems_for_focus
from . import update_manager
from .preflight import (
    build_storage_plan,
    check_directory_writable,
    quality_warnings as preflight_quality_warnings,
    validate_output_path,
)


APP_TITLE = "CinePulse"
APP_DIR = PATHS.root
APP_TEMP = PATHS.temp
PREVIEW_DIR = PATHS.previews
WORK_DIR = PATHS.work
CONFIG_DIR = PATHS.config
PRESETS_FILE = CONFIG_DIR / "presets.json"
QUEUE_FILE = CONFIG_DIR / "queue.json"
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
    visual_direction: str
    comparison_preview: bool
    use_stems: bool = False


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
        self.canvas.bind("<MouseWheel>", self._mousewheel)

    def _content_changed(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _canvas_changed(self, event) -> None:
        self.canvas.itemconfigure(self.window, width=event.width)

    def _mousewheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")


class VideoOptimizerStudio:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1040x800")
        self.root.minsize(820, 680)

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
        self.dark_mode = BooleanVar(value=False)
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
        self.quality_check = BooleanVar(value=True)
        self.visual_direction = StringVar(value="Cinematográfica")
        self.comparison_preview = BooleanVar(value=True)
        self.use_stems = BooleanVar(value=False)
        self.status = StringVar(value="Configure o projeto e gere um preview antes do vídeo final.")
        self.stage = StringVar(value="Pronto")
        self.progress_text = StringVar(value="0%")
        self.time_text = StringVar(value="Decorrido 00:00:00  •  Restante --:--:--")
        self.summary = StringVar()
        self.preset_name = StringVar(value="Meu padrão — 8K 120 fps Aurora")

        self._events: queue.Queue = queue.Queue()
        self._process: subprocess.Popen | None = None
        self._cancelled = False
        self._busy = False
        self._started_at: float | None = None
        self._progress_value = 0.0
        self._logs: list[str] = []
        self._log_window: Toplevel | None = None
        self._log_text: Text | None = None
        self._scrollable_tabs: list[ScrollableTab] = []
        self._nvenc = nvenc_available()
        self._hardware = detect_hardware()
        self._render_journal = RenderJournal(PATHS.locks / "render.json")
        self._custom_presets: dict[str, dict] = self._load_custom_presets()
        self._presets: dict[str, dict] = {**BUILTIN_PRESETS, **self._custom_presets}
        self._queue_items: list[dict] = []
        self._queue_serial = 0
        self._queue_running = False
        self._active_queue_id: int | None = None

        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        self._prune_previews()
        self._prune_work()

        self._configure_style()
        self._build_ui()
        self._apply_selected_preset()
        self._load_queue()
        self.root.after(100, self._poll_events)
        self.root.after(500, self._tick_clock)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(350, self._recover_interrupted_render)

    def _configure_style(self) -> None:
        self.style = ttk.Style()
        try:
            self.style.theme_use("vista")
        except Exception:
            pass
        self.style.configure("Title.TLabel", font=("Segoe UI", 21, "bold"))
        self.style.configure("Subtitle.TLabel", font=("Segoe UI", 10), foreground="#505050")
        self.style.configure("Section.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        self.style.configure("Studio.Horizontal.TProgressbar", thickness=18)
        self.style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(16, 8))

    def _apply_theme(self) -> None:
        dark = self.dark_mode.get()
        if dark:
            background = "#171A1F"
            panel = "#20242B"
            field = "#2A2F38"
            foreground = "#F2F4F7"
            muted = "#B8C0CC"
            accent = "#48B8FF"
            try:
                self.style.theme_use("clam")
            except Exception:
                pass
            self.root.configure(background=background)
            self.style.configure(".", background=background, foreground=foreground)
            self.style.configure("TFrame", background=background)
            self.style.configure("TLabel", background=background, foreground=foreground)
            self.style.configure("TLabelframe", background=background, foreground=foreground)
            self.style.configure("TLabelframe.Label", background=background, foreground=foreground)
            self.style.configure("TCheckbutton", background=background, foreground=foreground)
            self.style.map("TCheckbutton", background=[("active", panel)])
            self.style.configure("TButton", background=panel, foreground=foreground, bordercolor="#3A414D")
            self.style.map("TButton", background=[("active", "#303640")])
            self.style.configure("TEntry", fieldbackground=field, foreground=foreground, insertcolor=foreground)
            self.style.configure("TCombobox", fieldbackground=field, foreground=foreground, arrowcolor=foreground)
            self.style.map("TCombobox", fieldbackground=[("readonly", field)], foreground=[("readonly", foreground)])
            self.style.configure("TSpinbox", fieldbackground=field, foreground=foreground, arrowcolor=foreground)
            self.style.configure("TNotebook", background=background, bordercolor="#343A44")
            self.style.configure("TNotebook.Tab", background=panel, foreground=muted, padding=(12, 6))
            self.style.map("TNotebook.Tab", background=[("selected", field)], foreground=[("selected", foreground)])
            self.style.configure("Treeview", background=field, fieldbackground=field, foreground=foreground, rowheight=24)
            self.style.map("Treeview", background=[("selected", "#176A96")], foreground=[("selected", "#FFFFFF")])
            self.style.configure("Treeview.Heading", background=panel, foreground=foreground)
            self.style.configure("Studio.Horizontal.TProgressbar", background=accent, troughcolor=field, thickness=18)
            self.style.configure("Title.TLabel", background=background, foreground=foreground, font=("Segoe UI", 21, "bold"))
            self.style.configure("Subtitle.TLabel", background=background, foreground=muted, font=("Segoe UI", 10))
            canvas_color = background
        else:
            try:
                self.style.theme_use("vista")
            except Exception:
                self.style.theme_use("clam")
            self.root.configure(background="#F0F0F0")
            self.style.configure(".", background="#F0F0F0", foreground="#111111")
            self.style.configure("TFrame", background="#F0F0F0")
            self.style.configure("TLabel", background="#F0F0F0", foreground="#111111")
            self.style.configure("TLabelframe", background="#F0F0F0", foreground="#111111")
            self.style.configure("TLabelframe.Label", background="#F0F0F0", foreground="#111111")
            self.style.configure("TCheckbutton", background="#F0F0F0", foreground="#111111")
            self.style.configure("TButton", background="SystemButtonFace", foreground="SystemButtonText")
            self.style.configure("TEntry", fieldbackground="SystemWindow", foreground="SystemWindowText")
            self.style.configure("TCombobox", fieldbackground="SystemWindow", foreground="SystemWindowText")
            self.style.configure("TSpinbox", fieldbackground="SystemWindow", foreground="SystemWindowText")
            self.style.configure("TNotebook", background="#F0F0F0")
            self.style.configure("TNotebook.Tab", background="SystemButtonFace", foreground="SystemButtonText", padding=(12, 6))
            self.style.configure("Treeview", background="SystemWindow", fieldbackground="SystemWindow", foreground="SystemWindowText", rowheight=24)
            self.style.configure("Treeview.Heading", background="SystemButtonFace", foreground="SystemButtonText")
            self.style.configure("Title.TLabel", font=("Segoe UI", 21, "bold"), foreground="#111111")
            self.style.configure("Subtitle.TLabel", font=("Segoe UI", 10), foreground="#505050")
            self.style.configure("Section.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
            self.style.configure("Studio.Horizontal.TProgressbar", thickness=18)
            self.style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(16, 8))
            canvas_color = "#F0F0F0"
        for tab in self._scrollable_tabs:
            tab.canvas.configure(background=canvas_color)

    def _processor_changed(self) -> None:
        if self.use_cpu.get() and self.enhancement.get() == ENHANCE_AI:
            self.enhancement.set(ENHANCE_SIMPLE)
            self.status.set("Modo CPU ativado: melhoria alterada para Lanczos, pois o Real-ESRGAN usa GPU.")
        self._update_summary()

    def _enhancement_changed(self) -> None:
        if self.use_cpu.get() and self.enhancement.get() == ENHANCE_AI:
            self.use_cpu.set(False)
            self.status.set("Real-ESRGAN selecionado: GPU automática reativada.")
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
    def _prune_work() -> None:
        cutoff = time.time() - 24 * 60 * 60
        try:
            for directory in WORK_DIR.glob("job_*"):
                if directory.is_dir() and directory.stat().st_mtime < cutoff:
                    shutil.rmtree(directory, ignore_errors=True)
        except OSError:
            pass

    @staticmethod
    def _load_custom_presets() -> dict[str, dict]:
        if not PRESETS_FILE.is_file():
            return {}
        try:
            data = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_custom_presets(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        temporary = PRESETS_FILE.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self._custom_presets, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, PRESETS_FILE)

    @staticmethod
    def _settings_from_dict(data: dict) -> RenderSettings:
        defaults = {
            "audio_mode": "Preservar dinâmica original",
            "interpolation": "Movimento suave — FFmpeg",
            "cpu_threads": max(1, min(8, os.cpu_count() or 4)),
            "minimum_free_gb": 20.0,
            "quality_check": True,
            "visual_direction": "Personalizada",
            "comparison_preview": True,
            "use_stems": False,
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
            })
        temporary = QUEUE_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, QUEUE_FILE)

    def _load_queue(self) -> None:
        if not QUEUE_FILE.is_file():
            return
        try:
            payload = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
            restored = []
            for saved in payload if isinstance(payload, list) else []:
                settings = self._settings_from_dict(saved["settings"])
                status = saved.get("status", "Aguardando")
                if status == "Renderizando":
                    status = "Aguardando"
                    saved["error"] = "Recuperado após encerramento; o item será reiniciado com segurança."
                restored.append({
                    "id": int(saved["id"]), "settings": settings, "status": status,
                    "error": saved.get("error", ""), "report": saved.get("report", ""),
                })
            self._queue_items = restored
            self._queue_serial = max((item["id"] for item in restored), default=0)
            self._refresh_queue_tree()
            if restored:
                self.status.set(f"Fila restaurada: {len(restored)} projeto(s).")
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self._log(f"Não foi possível restaurar a fila: {exc}")

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
            "quality_check": self.quality_check.get(),
            "visual_direction": self.visual_direction.get(),
            "comparison_preview": self.comparison_preview.get(),
            "use_stems": self.use_stems.get(),
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
            (self.quality_check, "quality_check"),
            (self.visual_direction, "visual_direction"),
            (self.comparison_preview, "comparison_preview"),
            (self.use_stems, "use_stems"),
        )
        for variable, key in mapping:
            if key in data:
                variable.set(data[key])
        selected = set(data.get("effects", []))
        for name, variable in self.effect_vars.items():
            variable.set(name in selected)
        self.color_swatch.configure(background=self.color.get())
        self._visual_scale_changed()
        self._update_mode()
        self.status.set(f"Preset aplicado: {self.preset_name.get()}")

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
        self.status.set(f"Preset salvo: {name}")

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
        self._save_custom_presets()
        self._presets = {**BUILTIN_PRESETS, **self._custom_presets}
        self.preset_box.configure(values=tuple(self._presets))
        self.preset_name.set(next(iter(BUILTIN_PRESETS)))
        self.status.set("Preset personalizado excluído.")

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
        outer = ttk.Frame(self.root, padding=(20, 16, 20, 18))
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(side="left")
        ttk.Checkbutton(
            header,
            text="Modo escuro",
            variable=self.dark_mode,
            command=self._apply_theme,
        ).pack(side="right", padx=(12, 0))
        ttk.Label(
            outer,
            text="Upscale, interpolação, loops musicais, transições e VFX dinâmicos com processamento local.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(1, 12))

        preset_bar = ttk.LabelFrame(outer, text="Preset", padding=(10, 7))
        preset_bar.pack(fill="x", pady=(0, 10))
        self.preset_box = ttk.Combobox(
            preset_bar,
            textvariable=self.preset_name,
            values=tuple(self._presets),
            state="readonly",
        )
        self.preset_box.pack(side="left", fill="x", expand=True)
        ttk.Button(preset_bar, text="Aplicar", command=self._apply_selected_preset).pack(side="left", padx=(8, 0))
        ttk.Button(preset_bar, text="Salvar como novo…", command=self._save_new_preset).pack(side="left", padx=(8, 0))
        ttk.Button(preset_bar, text="Excluir", command=self._delete_preset).pack(side="left", padx=(8, 0))

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True)
        home_tab = ScrollableTab(self.notebook)
        project = ScrollableTab(self.notebook)
        output = ScrollableTab(self.notebook)
        visual = ScrollableTab(self.notebook)
        queue_tab = ttk.Frame(self.notebook, padding=14)
        ai_tab = ttk.Frame(self.notebook, padding=14)
        self._scrollable_tabs = [home_tab, project, output, visual]
        self.notebook.add(home_tab, text="  Início  ")
        self.notebook.add(project, text="  Projeto  ")
        self.notebook.add(output, text="  Qualidade e saída  ")
        self.notebook.add(visual, text="  Visual e transições  ")
        self.notebook.add(queue_tab, text="  Fila  ")
        self.notebook.add(ai_tab, text="  IA local  ")
        self._build_home_tab(home_tab.content)
        self._build_project_tab(project.content)
        self._build_output_tab(output.content)
        self._build_visual_tab(visual.content)
        self._build_queue_tab(queue_tab)
        self._build_ai_tab(ai_tab)

        footer = ttk.Frame(outer, padding=(0, 12, 0, 0))
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self.summary, wraplength=920, foreground="#4A4A4A").pack(anchor="w", pady=(0, 7))
        self.bar = ttk.Progressbar(footer, maximum=100, style="Studio.Horizontal.TProgressbar")
        self.bar.pack(fill="x")
        progress_row = ttk.Frame(footer)
        progress_row.pack(fill="x", pady=(4, 0))
        ttk.Label(progress_row, textvariable=self.stage).pack(side="left")
        ttk.Label(progress_row, textvariable=self.progress_text, font=("Segoe UI", 9, "bold")).pack(side="right")
        ttk.Label(footer, textvariable=self.time_text, foreground="#555555").pack(anchor="w", pady=(2, 4))
        ttk.Label(footer, textvariable=self.status, wraplength=920).pack(anchor="w")
        buttons = ttk.Frame(footer)
        buttons.pack(fill="x", pady=(9, 0))
        self.log_button = ttk.Button(buttons, text="Ver log", command=self._show_log)
        self.log_button.pack(side="left")
        ttk.Button(buttons, text="Diagnóstico", command=self._create_diagnostics).pack(side="left", padx=(8, 0))
        self.add_queue_button = ttk.Button(buttons, text="Adicionar à fila", command=self._add_to_queue)
        self.add_queue_button.pack(side="left", padx=(8, 0))
        self.cancel_button = ttk.Button(buttons, text="Cancelar", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="right")
        self.render_button = ttk.Button(buttons, text="Criar vídeo final", style="Primary.TButton", command=lambda: self._start(False))
        self.render_button.pack(side="right", padx=8)
        self.preview_button = ttk.Button(buttons, text="Gerar preview", style="Primary.TButton", command=lambda: self._start(True))
        self.preview_button.pack(side="right")

    def _build_home_tab(self, parent) -> None:
        parent.columnconfigure(0, weight=1)
        gpu_text = self._hardware.gpu or "Nenhuma GPU NVIDIA detectada"
        vram_text = f"{self._hardware.vram_mb / 1024:.1f} GB de VRAM" if self._hardware.vram_mb else "VRAM não detectada"
        ttk.Label(parent, text=f"CinePulse {__version__}", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            parent,
            text="Configure o projeto manualmente ou comece por um nível adequado a este computador.",
            wraplength=850,
        ).grid(row=1, column=0, sticky="w", pady=(2, 14))
        hardware_box = ttk.LabelFrame(parent, text="Este computador", padding=12)
        hardware_box.grid(row=2, column=0, sticky="ew")
        ttk.Label(hardware_box, text=f"GPU: {gpu_text} • {vram_text}").pack(anchor="w")
        ttk.Label(hardware_box, text=f"CPU: {self._hardware.cpu_threads} threads • perfil sugerido: {self._hardware.quality_tier}").pack(anchor="w", pady=(4, 0))
        ttk.Label(hardware_box, text=f"FFmpeg: {'pronto' if FFMPEG else 'não encontrado'} • NVIDIA: {'pronta' if self._nvenc else 'fallback por CPU'}").pack(anchor="w", pady=(4, 0))

        profiles = ttk.LabelFrame(parent, text="Níveis de qualidade", padding=12)
        profiles.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        for label, description in (
            ("Rápido", "1080p/60, Lanczos e configuração leve para previews e máquinas sem GPU."),
            ("Recomendado", "4K/60, Real-ESRGAN e VFX suaves; equilíbrio indicado para GPUs com pelo menos 6 GB."),
            ("Máximo", "8K/120, Real-ESRGAN, RIFE e qualidade máxima; processamento muito mais demorado."),
        ):
            row = ttk.Frame(profiles)
            row.pack(fill="x", pady=4)
            ttk.Button(row, text=label, width=14, command=lambda value=label: self._apply_quality_level(value)).pack(side="left")
            ttk.Label(row, text=description, wraplength=680).pack(side="left", padx=(10, 0))

        actions = ttk.Frame(parent)
        actions.grid(row=4, column=0, sticky="w", pady=(14, 0))
        ttk.Button(actions, text="Criar diagnóstico", command=self._create_diagnostics).pack(side="left")
        self.update_button = ttk.Button(actions, text="Verificar atualizações", command=self._check_updates)
        self.update_button.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Abrir dados do CinePulse", command=lambda: os.startfile(PATHS.data)).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Abrir componentes", command=lambda: os.startfile(PATHS.components)).pack(side="left", padx=(8, 0))

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
        self.status.set(f"Nível {level} aplicado. Revise o projeto e gere um preview antes do vídeo final.")
        self.notebook.select(1)

    def _build_project_tab(self, parent) -> None:
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text="Tipo de projeto").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=7)
        mode_box = ttk.Combobox(parent, textvariable=self.mode, values=(MODE_MUSIC, MODE_ORIGINAL), state="readonly")
        mode_box.grid(row=0, column=1, columnspan=2, sticky="ew", pady=7)
        mode_box.bind("<<ComboboxSelected>>", lambda _e: self._update_mode())
        self._file_row(parent, 1, "Vídeo", self.video, self._choose_video)
        self.audio_label = ttk.Label(parent, text="Música (WAV recomendado)")
        self.audio_label.grid(row=2, column=0, sticky="w", padx=(0, 12), pady=7)
        self.audio_entry = ttk.Entry(parent, textvariable=self.audio)
        self.audio_entry.grid(row=2, column=1, sticky="ew", pady=7)
        self.audio_button = ttk.Button(parent, text="Selecionar…", command=self._choose_audio)
        self.audio_button.grid(row=2, column=2, padx=(8, 0), pady=7)
        self._file_row(parent, 3, "Salvar como", self.output, self._choose_output)

        preview_box = ttk.LabelFrame(parent, text="Preview rápido", style="Section.TLabelframe", padding=14)
        preview_box.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(18, 8))
        ttk.Label(preview_box, text="Duração do preview:").pack(side="left")
        ttk.Spinbox(preview_box, from_=1, to=30, textvariable=self.preview_seconds, width=5).pack(side="left", padx=(8, 4))
        ttk.Label(preview_box, text="segundos (1 a 30)").pack(side="left")
        ttk.Button(
            preview_box,
            text="Abrir pasta de previews",
            command=lambda: os.startfile(PREVIEW_DIR),
        ).pack(side="right")
        ttk.Button(preview_box, text="Verificar projeto", command=self._show_preflight).pack(side="right", padx=(0, 8))
        ttk.Label(
            parent,
            text="O preview usa até 720p/60 fps para mostrar rapidamente cores, VFX e transição sem renderizar o projeto inteiro.",
            wraplength=800,
            foreground="#555555",
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(3, 10))
        ttk.Checkbutton(
            parent,
            text="Criar também comparação lado a lado — original à esquerda, resultado à direita",
            variable=self.comparison_preview,
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(0, 8))

    def _build_output_tab(self, parent) -> None:
        parent.columnconfigure(1, weight=1)
        self._combo_row(parent, 0, "Resolução", self.resolution, tuple(RESOLUTIONS), self._update_summary)
        self._combo_row(parent, 1, "Quadros por segundo", self.fps, FPS_OPTIONS, self._update_summary)
        self._combo_row(
            parent,
            2,
            "Formato da tela",
            self.aspect,
            (ASPECT_ORIGINAL, ASPECT_LANDSCAPE, ASPECT_PORTRAIT, ASPECT_IMAX, ASPECT_WIDE),
            self._update_summary,
        )
        self._combo_row(parent, 3, "Melhoria de imagem", self.enhancement, (ENHANCE_NONE, ENHANCE_SIMPLE, ENHANCE_AI), self._enhancement_changed)
        self._combo_row(parent, 4, "Ajuste no enquadramento", self.fit_mode, (FIT_COVER, FIT_CONTAIN), self._update_summary)
        self.cpu_check = ttk.Checkbutton(
            parent,
            text="Usar somente CPU — desativar aceleração NVIDIA",
            variable=self.use_cpu,
            command=self._processor_changed,
        )
        self.cpu_check.grid(row=5, column=0, columnspan=3, sticky="w", pady=(14, 4))
        self.keep_audio_check = ttk.Checkbutton(
            parent,
            text="Manter o áudio original no modo ‘Melhorar vídeo original’",
            variable=self.preserve_audio,
            command=self._update_summary,
        )
        self.keep_audio_check.grid(row=6, column=0, columnspan=3, sticky="w", pady=4)
        warning = ttk.LabelFrame(parent, text="Uso de máquina", style="Section.TLabelframe", padding=14)
        warning.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Label(
            warning,
            text=(
                "No automático, resoluções até 8K usam a NVIDIA. O modo CPU força x264/x265 e não aceita o Real-ESRGAN. "
                "10K e 12K usam o processador. "
                "240/480 fps e combinações acima de 8K podem levar muitas horas e gerar arquivos enormes."
            ),
            wraplength=790,
        ).pack(anchor="w")
        cache_row = ttk.Frame(parent)
        cache_row.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        ttk.Label(cache_row, text="Cache da IA reutiliza clipes já aprimorados e economiza tempo.").pack(side="left")
        ttk.Button(cache_row, text="Abrir cache", command=lambda: os.startfile(CACHE_DIR)).pack(side="right")
        ttk.Button(cache_row, text="Abrir relatórios", command=lambda: os.startfile(REPORT_DIR)).pack(side="right", padx=(0, 8))
        ttk.Button(cache_row, text="Limpar cache…", command=self._clear_ai_cache).pack(side="right", padx=(0, 8))

        advanced = ttk.LabelFrame(parent, text="Áudio, fluidez e recursos", style="Section.TLabelframe", padding=14)
        advanced.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        advanced.columnconfigure(1, weight=1)
        ttk.Label(advanced, text="Tratamento do áudio").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=6)
        audio_box = ttk.Combobox(advanced, textvariable=self.audio_mode, values=AUDIO_MODES, state="readonly")
        audio_box.grid(row=0, column=1, columnspan=2, sticky="ew", pady=6)
        audio_box.bind("<<ComboboxSelected>>", lambda _e: self._update_summary())
        ttk.Label(advanced, text="Interpolação de FPS").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=6)
        interpolation_box = ttk.Combobox(advanced, textvariable=self.interpolation, values=INTERPOLATION_OPTIONS, state="readonly")
        interpolation_box.grid(row=1, column=1, columnspan=2, sticky="ew", pady=6)
        interpolation_box.bind("<<ComboboxSelected>>", lambda _e: self._update_summary())
        ttk.Label(advanced, text="Máximo de threads da CPU").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=6)
        ttk.Spinbox(advanced, from_=1, to=max(1, os.cpu_count() or 32), textvariable=self.cpu_threads, width=7).grid(row=2, column=1, sticky="w", pady=6)
        ttk.Label(advanced, text="Reserva mínima no disco (GB)").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=6)
        ttk.Spinbox(advanced, from_=1, to=500, increment=1, textvariable=self.minimum_free_gb, width=7).grid(row=3, column=1, sticky="w", pady=6)
        ttk.Checkbutton(
            advanced,
            text="Analisar possíveis artefatos no relatório final",
            variable=self.quality_check,
            command=self._update_summary,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 2))
        rife_text = "RIFE local detectado." if RIFE_EXE.is_file() else "RIFE ainda não instalado; o Studio usa interpolação de movimento do FFmpeg."
        ttk.Label(advanced, text=rife_text, foreground="#555555").grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))

    def _build_visual_tab(self, parent) -> None:
        effects_box = ttk.LabelFrame(parent, text="VFX dinâmicos — podem ser combinados", style="Section.TLabelframe", padding=14)
        effects_box.pack(fill="x")
        for index, name in enumerate(EFFECT_NAMES):
            ttk.Checkbutton(
                effects_box,
                text=name,
                variable=self.effect_vars[name],
                command=self._update_summary,
            ).grid(row=index // 2, column=index % 2, sticky="w", padx=(0, 28), pady=4)

        direction = ttk.LabelFrame(parent, text="Direção musical", style="Section.TLabelframe", padding=14)
        direction.pack(fill="x", pady=(14, 0))
        direction.columnconfigure(0, weight=1)
        ttk.Combobox(
            direction, textvariable=self.visual_direction, values=tuple(VISUAL_DIRECTIONS), state="readonly",
        ).grid(row=0, column=0, sticky="ew")
        ttk.Button(direction, text="Aplicar direção", command=self._apply_visual_direction).grid(row=0, column=1, padx=(8, 0))
        ttk.Label(
            direction,
            text="Ajusta reação, suavidade, intensidade e evolução musical sem trocar os VFX selecionados.",
            foreground="#555555",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(7, 0))

        controls = ttk.LabelFrame(parent, text="Aparência dos VFX", style="Section.TLabelframe", padding=14)
        controls.pack(fill="x", pady=(14, 0))
        controls.columnconfigure(1, weight=1)
        ttk.Label(controls, text="Cor principal").grid(row=0, column=0, sticky="w", pady=7)
        color_row = ttk.Frame(controls)
        color_row.grid(row=0, column=1, sticky="ew", pady=7)
        self.color_swatch = ttk.Label(color_row, text="      ", background=self.color.get(), relief="solid")
        self.color_swatch.pack(side="left", padx=(0, 8))
        ttk.Button(color_row, text="Escolher cor…", command=self._choose_color).pack(side="left")
        ttk.Label(controls, text="Intensidade").grid(row=1, column=0, sticky="w", pady=7)
        ttk.Scale(
            controls,
            from_=25,
            to=200,
            variable=self.intensity,
            command=self._visual_scale_changed,
        ).grid(row=1, column=1, sticky="ew", pady=7)
        ttk.Label(controls, textvariable=self.intensity_text, width=6, anchor="e").grid(row=1, column=2, padx=(10, 0))
        ttk.Label(controls, text="Área ocupada").grid(row=2, column=0, sticky="w", pady=7)
        ttk.Scale(
            controls,
            from_=10,
            to=100,
            variable=self.occupancy,
            command=self._visual_scale_changed,
        ).grid(row=2, column=1, sticky="ew", pady=7)
        ttk.Label(controls, textvariable=self.occupancy_text, width=6, anchor="e").grid(row=2, column=2, padx=(10, 0))
        ttk.Label(controls, text="Reagir a").grid(row=3, column=0, sticky="w", pady=7)
        focus_box = ttk.Combobox(
            controls,
            textvariable=self.audio_focus,
            values=AUDIO_FOCUS_OPTIONS,
            state="readonly",
        )
        focus_box.grid(row=3, column=1, columnspan=2, sticky="ew", pady=7)
        focus_box.bind("<<ComboboxSelected>>", lambda _e: self._update_summary())
        ttk.Label(controls, text="Suavização").grid(row=4, column=0, sticky="w", pady=7)
        ttk.Scale(
            controls,
            from_=0,
            to=100,
            variable=self.reaction_smoothing,
            command=self._visual_scale_changed,
        ).grid(row=4, column=1, sticky="ew", pady=7)
        ttk.Label(controls, textvariable=self.smoothing_text, width=6, anchor="e").grid(row=4, column=2, padx=(10, 0))
        ttk.Label(controls, text="Expressividade").grid(row=5, column=0, sticky="w", pady=7)
        ttk.Scale(
            controls,
            from_=25,
            to=200,
            variable=self.reaction_expression,
            command=self._visual_scale_changed,
        ).grid(row=5, column=1, sticky="ew", pady=7)
        ttk.Label(controls, textvariable=self.expression_text, width=6, anchor="e").grid(row=5, column=2, padx=(10, 0))
        ttk.Label(
            controls,
            text=(
                "Mais suavização produz movimentos naturais. Expressividade baixa evita explosões; "
                "expressividade alta destaca mais os picos da música."
            ),
            wraplength=760,
            foreground="#555555",
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(7, 0))
        ttk.Checkbutton(
            controls,
            text="Adaptar intensidade a versos, refrões e clímax",
            variable=self.dynamic_sections,
            command=self._update_summary,
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(12, 4))
        ttk.Label(controls, text="Dinâmica entre seções").grid(row=8, column=0, sticky="w", pady=7)
        ttk.Scale(
            controls,
            from_=0,
            to=100,
            variable=self.section_dynamics,
            command=self._visual_scale_changed,
        ).grid(row=8, column=1, sticky="ew", pady=7)
        ttk.Label(controls, textvariable=self.section_dynamics_text, width=6, anchor="e").grid(row=8, column=2, padx=(10, 0))
        ttk.Checkbutton(
            controls,
            text="Separar instrumentos com Demucs para uma reação mais limpa (usa cache)",
            variable=self.use_stems,
            command=self._update_summary,
        ).grid(row=9, column=0, columnspan=3, sticky="w", pady=(10, 0))

        transitions = ttk.LabelFrame(parent, text="Transição do loop", style="Section.TLabelframe", padding=14)
        transitions.pack(fill="x", pady=(14, 0))
        transitions.columnconfigure(1, weight=1)
        ttk.Label(transitions, text="Efeito na emenda").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=7)
        ttk.Combobox(transitions, textvariable=self.transition, values=tuple(TRANSITIONS), state="readonly").grid(row=0, column=1, sticky="ew", pady=7)
        ttk.Label(transitions, text="Duração da transição").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=7)
        ttk.Spinbox(transitions, from_=0.15, to=3.0, increment=0.05, textvariable=self.transition_duration, width=8).grid(row=1, column=1, sticky="w", pady=7)
        ttk.Label(
            transitions,
            text="A transição só é aplicada ao modo Loop musical. Corte seco mantém exatamente o comportamento clássico.",
            wraplength=780,
            foreground="#555555",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(7, 0))
        ttk.Checkbutton(
            transitions,
            text="Encontrar automaticamente o melhor ponto de loop",
            variable=self.auto_loop,
            command=self._update_summary,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def _build_queue_tab(self, parent) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        columns = ("projeto", "saida", "perfil", "status")
        self.queue_tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        self.queue_tree.heading("projeto", text="Projeto")
        self.queue_tree.heading("saida", text="Arquivo de saída")
        self.queue_tree.heading("perfil", text="Qualidade")
        self.queue_tree.heading("status", text="Status")
        self.queue_tree.column("projeto", width=190, anchor="w")
        self.queue_tree.column("saida", width=300, anchor="w")
        self.queue_tree.column("perfil", width=180, anchor="w")
        self.queue_tree.column("status", width=100, anchor="center")
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.queue_tree.yview)
        self.queue_tree.configure(yscrollcommand=scrollbar.set)
        self.queue_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        buttons = ttk.Frame(parent)
        buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(buttons, text="Remover selecionado", command=self._remove_queue_item).pack(side="left")
        ttk.Button(buttons, text="Limpar fila", command=self._clear_queue).pack(side="left", padx=(8, 0))
        self.start_queue_button = ttk.Button(
            buttons,
            text="Iniciar fila",
            style="Primary.TButton",
            command=self._start_queue,
        )
        self.start_queue_button.pack(side="right")
        ttk.Label(
            parent,
            text="Cada item guarda seus próprios arquivos, qualidade, efeitos e reação musical.",
            foreground="#555555",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _build_ai_tab(self, parent) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        installed, total = ai_suite.installed_count()
        ttk.Label(
            parent,
            text=f"Suíte de máxima qualidade: {installed}/{total} módulos encontrados",
            font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))
        columns = ("modulo", "funcao", "estado")
        tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        tree.heading("modulo", text="Módulo")
        tree.heading("funcao", text="O que melhora")
        tree.heading("estado", text="Estado")
        tree.column("modulo", width=180, anchor="w")
        tree.column("funcao", width=430, anchor="w")
        tree.column("estado", width=210, anchor="w")
        for item in ai_suite.inventory():
            if item["installed"]:
                state = "Instalado • " + item["activation"].lower()
            else:
                state = "Arquivos incompletos"
            tree.insert("", "end", values=(item["name"], item["purpose"], state))
        tree.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        tree.configure(yscrollcommand=scrollbar.set)
        actions = ttk.Frame(parent)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(actions, text="Abrir pasta da IA", command=lambda: os.startfile(ai_suite.AI_ROOT)).pack(side="left")
        ttk.Button(
            actions,
            text="Ler instalação e ativação",
            command=lambda: os.startfile(APP_DIR / "docs" / "AI_COMPONENTS.md"),
        ).pack(side="left", padx=(8, 0))
        ttk.Label(
            parent,
            text=(
                "Os novos motores permanecem fora do render principal até a primeira validação. "
                "Isso impede que uma instalação ainda não conferida comprometa um vídeo longo."
            ),
            wraplength=820,
            foreground="#555555",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def _file_row(self, parent, row: int, label: str, variable: StringVar, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=7)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=7)
        ttk.Button(parent, text="Selecionar…", command=command).grid(row=row, column=2, padx=(8, 0), pady=7)

    def _combo_row(self, parent, row, label, variable, values, changed) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=7)
        box = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly")
        box.grid(row=row, column=1, columnspan=2, sticky="ew", pady=7)
        box.bind("<<ComboboxSelected>>", lambda _e: changed())

    def _choose_video(self) -> None:
        path = filedialog.askopenfilename(title="Selecione o vídeo", filetypes=[("Vídeos", "*.mp4 *.mov *.mkv *.webm *.avi"), ("Todos", "*.*")])
        if path:
            self.video.set(path)
            self._suggest_output()

    def _choose_audio(self) -> None:
        path = filedialog.askopenfilename(title="Selecione a música", filetypes=[("Áudio", "*.wav *.flac *.mp3 *.m4a *.aac *.ogg"), ("Todos", "*.*")])
        if path:
            self.audio.set(path)
            self._suggest_output()

    def _choose_output(self) -> None:
        current = self.output.get() or "video_otimizado.mp4"
        path = filedialog.asksaveasfilename(
            title="Salvar vídeo final", defaultextension=".mp4", initialdir=str(Path(current).parent),
            initialfile=Path(current).name, filetypes=[("Vídeo MP4", "*.mp4")],
        )
        if path:
            self.output.set(path)

    def _choose_color(self) -> None:
        _rgb, value = colorchooser.askcolor(color=self.color.get(), title="Cor principal dos VFX")
        if value:
            self.color.set(value.upper())
            self.color_swatch.configure(background=value)
            self._update_summary()

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
        self.audio_label.configure(foreground="" if music else "#777777")
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
            f"áudio: {self.audio_mode.get()} • {self.interpolation.get()} • "
            f"{'CPU' if self.use_cpu.get() else 'GPU automática'}"
        )

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
            quality_check=self.quality_check.get(), visual_direction=self.visual_direction.get(),
            comparison_preview=self.comparison_preview.get(),
            use_stems=self.use_stems.get(),
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
        bitrate = self._estimated_bitrate_mbps(target_w, target_h, target_fps)
        output_gb = bitrate * project_duration / 8 / 1024 * 1.08
        temp_gb = max(0.5, output_gb * 0.35)
        if settings.enhancement == ENHANCE_AI:
            enhanced_seconds = min(source_duration, settings.preview_seconds) if preview else source_duration
            frames = max(1, round(enhanced_seconds * source_fps))
            temp_gb += source_w * source_h * frames * 10 / (1024 ** 3)
        output_path = Path(settings.output).expanduser() if settings.output else PREVIEW_DIR / "preview.mp4"
        storage = build_storage_plan(
            output_path,
            WORK_DIR,
            output_gb,
            temp_gb,
            settings.minimum_free_gb,
        )
        warnings: list[str] = []
        warnings.extend(color_profile.warnings_for_sdr_pipeline(bool(settings.effects)))
        warnings.extend(preflight_quality_warnings(
            source_w, source_h, source_fps, target_w, target_h, target_fps,
            self._hardware.vram_mb,
            settings.enhancement == ENHANCE_AI,
            settings.interpolation == RIFE_OPTION,
        ))
        if not settings.use_cpu and not self._nvenc and max(target_w, target_h) <= 8192:
            warnings.append("A aceleração NVIDIA não foi detectada; a codificação usará CPU e será mais lenta.")
        if settings.mode == MODE_MUSIC and Path(settings.audio).suffix.lower() not in {".wav", ".flac"}:
            warnings.append("Para preservar melhor a música, prefira WAV ou FLAC como fonte.")
        blocking_reasons = list(storage.blocking_reasons)
        blocking = bool(blocking_reasons)
        lines = [
            "PRÉ-VERIFICAÇÃO DO PROJETO",
            "",
            f"Fonte: {source_w}×{source_h} • {source_fps:.2f} fps • {format_time(source_duration)}",
            f"Cor da fonte: {color_profile.label}",
            f"Destino: {target_w}×{target_h} • {target_fps} fps • {format_time(project_duration)}",
            f"Saída estimada: {output_gb:.2f} GB",
            f"Temporários estimados: {temp_gb:.2f} GB",
            f"Espaço livre na saída: {storage.output_free_gb:.2f} GB",
            f"Espaço livre nos temporários: {storage.temporary_free_gb:.2f} GB • reserva: {settings.minimum_free_gb:.0f} GB",
            f"Processamento: {'CPU' if settings.use_cpu else 'GPU automática'} • até {settings.cpu_threads} threads de CPU",
            f"Hardware: {self._hardware.gpu or self._hardware.cpu} • perfil sugerido {self._hardware.quality_tier}",
        ]
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
            messagebox.showerror(APP_TITLE, f"A pré-verificação falhou.\n\n{exc}")
            return False
        self._log(report["text"].replace("\n", " | "))
        if report["blocking"]:
            messagebox.showerror(APP_TITLE, report["text"])
            return False
        if not preview and report["warnings"]:
            return messagebox.askyesno(APP_TITLE, report["text"] + "\n\nDeseja continuar?")
        return True

    def _validate(self, settings: RenderSettings, preview: bool) -> bool:
        if not FFMPEG or not FFPROBE:
            messagebox.showerror(APP_TITLE, "FFmpeg e FFprobe não foram encontrados.")
            return False
        if not settings.video or not Path(settings.video).is_file():
            messagebox.showwarning(APP_TITLE, "Selecione um vídeo válido.")
            return False
        if settings.mode == MODE_MUSIC and (not settings.audio or not Path(settings.audio).is_file()):
            messagebox.showwarning(APP_TITLE, "Selecione a música do projeto.")
            return False
        if not preview and not settings.output:
            messagebox.showwarning(APP_TITLE, "Escolha onde salvar o vídeo.")
            return False
        if not preview:
            path_errors = validate_output_path(
                Path(settings.output),
                tuple(Path(value) for value in (settings.video, settings.audio) if value),
            )
            if path_errors:
                messagebox.showerror(APP_TITLE, "\n".join(path_errors))
                return False
        try:
            check_directory_writable(Path(settings.output) if not preview else PREVIEW_DIR / "preview.mp4")
            check_directory_writable(WORK_DIR / "render.tmp")
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"O CinePulse não consegue gravar os arquivos necessários.\n\n{exc}")
            return False
        if settings.enhancement == ENHANCE_AI and not REAL_ESRGAN.is_file():
            messagebox.showerror(APP_TITLE, "O módulo local Real-ESRGAN não foi encontrado.")
            return False
        if settings.use_cpu and settings.enhancement == ENHANCE_AI:
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
        self._queue_items.append({"id": self._queue_serial, "settings": settings, "status": "Aguardando", "error": "", "report": ""})
        self._save_queue()
        self._refresh_queue_tree()
        self.status.set(f"Projeto adicionado à fila. Total: {len(self._queue_items)}")

    def _refresh_queue_tree(self) -> None:
        for item_id in self.queue_tree.get_children():
            self.queue_tree.delete(item_id)
        for item in self._queue_items:
            settings: RenderSettings = item["settings"]
            project = Path(settings.video).stem
            profile = f"{settings.resolution} / {settings.fps} fps / {settings.aspect.split(' — ')[0]}"
            self.queue_tree.insert(
                "",
                "end",
                iid=str(item["id"]),
                values=(project, Path(settings.output).name, profile, item["status"]),
            )

    def _remove_queue_item(self) -> None:
        if self._queue_running:
            messagebox.showinfo(APP_TITLE, "Pare ou conclua a fila antes de remover itens.")
            return
        selected = self.queue_tree.selection()
        if not selected:
            return
        selected_id = int(selected[0])
        self._queue_items = [item for item in self._queue_items if item["id"] != selected_id]
        self._save_queue()
        self._refresh_queue_tree()

    def _clear_queue(self) -> None:
        if self._queue_running:
            messagebox.showinfo(APP_TITLE, "A fila está em execução.")
            return
        self._queue_items.clear()
        self._save_queue()
        self._refresh_queue_tree()

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
        self._save_queue()
        self._queue_running = True
        self._run_next_queue_item()

    def _run_next_queue_item(self) -> None:
        if not self._queue_running:
            return
        next_item = next((item for item in self._queue_items if item["status"] == "Aguardando"), None)
        if next_item is None:
            self._queue_running = False
            self._active_queue_id = None
            failures = sum(item["status"] == "Erro" for item in self._queue_items)
            messagebox.showinfo(
                APP_TITLE,
                "Fila concluída." if not failures else f"Fila concluída com {failures} item(ns) com erro.",
            )
            return
        settings: RenderSettings = next_item["settings"]
        if not self._validate(settings, False):
            next_item["status"] = "Erro"
            next_item["error"] = "Validação recusada ou arquivos indisponíveis."
            self._refresh_queue_tree()
            self._save_queue()
            self.root.after(100, self._run_next_queue_item)
            return
        try:
            preflight = self._preflight_report(settings, False)
            if preflight["blocking"]:
                raise RuntimeError(preflight["text"])
        except Exception as exc:
            next_item["status"] = "Erro"
            next_item["error"] = f"Pré-verificação: {exc}"
            self._refresh_queue_tree()
            self._save_queue()
            self.root.after(100, self._run_next_queue_item)
            return
        next_item["status"] = "Renderizando"
        self._active_queue_id = next_item["id"]
        self._refresh_queue_tree()
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
        self.status.set("Validando mídia e calculando o fluxo de processamento.")
        self.render_button.configure(state="disabled")
        self.preview_button.configure(state="disabled")
        self.add_queue_button.configure(state="disabled")
        self.start_queue_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self._write_render_lock(preview)
        threading.Thread(target=self._worker, args=(settings, preview), daemon=True).start()

    def _worker(self, settings: RenderSettings, preview: bool) -> None:
        temp_paths: list[Path] = []
        temp_dirs: list[Path] = []
        atomic_output: AtomicOutput | None = None
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        job_dir = Path(tempfile.mkdtemp(prefix="job_", dir=WORK_DIR))
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
            working_video = settings.video
            working_w, working_h = source_w, source_h
            working_start = loop_start
            progress_base = 0.0
            if settings.enhancement == ENHANCE_AI:
                working_video, working_w, working_h = self._enhance_clip_ai(
                    settings.video, job_dir, loop_start, video_duration, source_fps, source_w, source_h,
                    temp_paths, temp_dirs, settings.cpu_threads, 0, 20,
                )
                progress_base = 20.0
                working_start = 0.0

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
            needs_master = settings.mode == MODE_MUSIC or effects_active or transition_active
            visual_source = working_video
            working_fps = source_fps
            if settings.interpolation == RIFE_OPTION and needs_master and target_fps >= 48 and source_fps < 59.99:
                rife_base_fps = min(60, target_fps)
                try:
                    self._set_stage("RIFE base", f"Criando movimento neural em {rife_base_fps} fps antes dos VFX.")
                    working_video = self._interpolate_rife(
                        working_video, job_dir, working_start, video_duration, source_fps, rife_base_fps,
                        settings.use_cpu, settings.cpu_threads, temp_paths, progress_base, 18,
                    )
                    visual_source = working_video
                    working_start = 0.0
                    working_fps = float(rife_base_fps)
                    progress_base += 18
                except InterruptedError:
                    raise
                except Exception as exc:
                    self._log(f"RIFE base indisponível; fallback FFmpeg ativado: {exc}")
            if needs_master:
                if target_w >= target_h:
                    work_w, work_h = ((2560, 1440) if settings.enhancement == ENHANCE_AI and not preview else (1280, 720))
                else:
                    work_w, work_h = ((1440, 2560) if settings.enhancement == ENHANCE_AI and not preview else (720, 1280))
                master = self._temp_file(job_dir, "studio_master_", temp_paths)
                self._set_stage("Preparando master", f"Convertendo o vídeo para {work_w}×{work_h} em 60 fps.")
                master_filter = self._scale_filter(work_w, work_h, 60, settings.fit_mode, working_fps, settings.interpolation)
                command = [
                    FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
                ]
                if working_start > 0:
                    command += ["-ss", f"{working_start:.6f}"]
                command += [
                    "-i", working_video,
                    "-map", "0:v:0", "-an", "-t", f"{video_duration:.6f}", "-vf", master_filter,
                ] + self._h264_encoder(work_w, work_h, settings.use_cpu) + [
                    "-threads", str(settings.cpu_threads), "-progress", "pipe:1", "-nostats", str(master)
                ]
                self._run_ffmpeg(command, video_duration, progress_base, 10)
                progress_base += 10
                visual_source = str(master)
                if transition_active:
                    transitioned = self._temp_file(job_dir, "studio_transition_", temp_paths)
                    visual_source = self._create_transition(
                        str(master), transitioned, video_duration, transition_label,
                        transition_duration, work_w, work_h, settings.use_cpu, progress_base, 7,
                        settings.cpu_threads,
                    )
                    progress_base += 7
                if effects_active:
                    vfx_output = self._temp_file(job_dir, "studio_vfx_", temp_paths)
                    self._set_stage("VFX dinâmicos", "Analisando o áudio e desenhando os efeitos selecionados em tempo real.")
                    remaining_for_vfx = 35 if settings.mode == MODE_MUSIC else 45
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
                    try:
                        vfx.render_vfx_intermediate(
                            FFMPEG, visual_source, reactive_audio, str(vfx_output), project_duration,
                            settings.effects, settings.color, settings.intensity, settings.occupancy,
                            work_w, work_h, "100M" if max(work_w, work_h) > 1280 else "50M",
                            "180M", "360M", settings.use_cpu, settings.cpu_threads,
                            settings.audio_focus, settings.reaction_smoothing, settings.reaction_expression,
                            settings.dynamic_sections, settings.section_dynamics,
                            lambda fraction: self._push_progress(progress_base + remaining_for_vfx * fraction),
                            lambda: self._cancelled,
                            lambda process: setattr(self, "_process", process),
                            self._log,
                        )
                    except vfx.RenderCancelled as exc:
                        raise InterruptedError from exc
                    visual_source = str(vfx_output)
                    progress_base += remaining_for_vfx

            visual_fps = 60.0 if needs_master else source_fps
            effective_interpolation = settings.interpolation
            if settings.interpolation == RIFE_OPTION and target_fps > visual_fps + 0.01:
                rife_weight = max(1.0, min(35.0, max(1.0, 95.0 - progress_base) * 0.65))
                try:
                    self._set_stage("RIFE final", f"Interpolando movimento neural para {target_fps} fps.")
                    visual_source = self._interpolate_rife(
                        visual_source, job_dir, 0.0, project_duration, visual_fps, target_fps,
                        settings.use_cpu, settings.cpu_threads, temp_paths, progress_base, rife_weight,
                    )
                    visual_fps = float(target_fps)
                    progress_base += rife_weight
                except InterruptedError:
                    raise
                except Exception as exc:
                    effective_interpolation = "Movimento suave — FFmpeg"
                    self._log(f"RIFE final falhou; fallback FFmpeg ativado: {exc}")
            self._set_stage("Finalizando", f"Codificando em {target_w}×{target_h} a {target_fps} fps com áudio correto.")
            preserve_hdr = source_color.hdr and settings.mode == MODE_ORIGINAL and not effects_active
            final_filter = self._scale_filter(
                target_w, target_h, target_fps, settings.fit_mode, visual_fps, effective_interpolation,
                source_color, preserve_hdr,
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
            command += self._final_encoder(
                target_w, target_h, target_fps, preview, settings.use_cpu, source_color, preserve_hdr,
            )
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
                command += ["-c:a", "aac", "-b:a", "384k", "-ar", "48000", "-ac", "2"]
            command += [
                "-threads", str(settings.cpu_threads), "-t", f"{project_duration:.6f}", "-movflags", "+faststart",
                "-progress", "pipe:1", "-nostats", str(partial_output),
            ]
            self._run_ffmpeg(command, project_duration, progress_base, 100 - progress_base)
            verification = self._verify_output(str(partial_output), project_duration, target_w, target_h, target_fps)
            output_path = atomic_output.commit()
            self._render_journal.clear()
            report_path = ""
            if not preview:
                report_path = self._write_quality_report(output_path, settings, verification, project_duration)
            display_path = output_path
            if preview and settings.comparison_preview:
                display_path = self._create_comparison_preview(
                    output_path, settings, project_duration, loop_start, settings.cpu_threads,
                )
            self._events.put(("done", str(display_path), preview, display_path.stat().st_size, report_path))
        except InterruptedError:
            if atomic_output:
                atomic_output.discard()
            self._render_journal.clear()
            self._events.put(("cancelled",))
        except Exception as exc:
            self._log("ERRO: " + str(exc))
            self._events.put(("error", str(exc)))
        finally:
            self._process = None
            for path in temp_paths:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            for directory in temp_dirs:
                shutil.rmtree(directory, ignore_errors=True)
            shutil.rmtree(job_dir, ignore_errors=True)

    @staticmethod
    def _audio_filter(mode: str) -> str:
        return build_audio_filter(mode)

    def _scale_filter(
        self, width: int, height: int, fps: int, fit_mode: str, source_fps: float, interpolation: str,
        color_profile: ColorProfile | None = None, preserve_hdr: bool = False,
    ) -> str:
        if fps > source_fps + 0.01:
            if interpolation == "Quadros repetidos — rápido":
                frame = f"fps={fps}"
            else:
                frame = f"minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"
        else:
            frame = f"fps={fps}"
        if fit_mode == FIT_COVER:
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
        if preserve_hdr and color_profile and color_profile.hdr:
            color = "format=yuv420p10le"
        else:
            color = (
                "setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709,"
                "format=yuv420p10le"
            )
        return frame + "," + framing + "," + color

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

    def _final_encoder(
        self, width: int, height: int, fps: int, preview: bool, use_cpu: bool,
        color_profile: ColorProfile | None = None, preserve_hdr: bool = False,
    ) -> list[str]:
        pixels_ratio = width * height / (1920 * 1080)
        target = max(8, min(600, round(12 * pixels_ratio * max(1, fps / 60))))
        if preview:
            target = min(target, 24)
        if preserve_hdr and color_profile and color_profile.hdr:
            color_args = [
                "-color_primaries", color_profile.primaries,
                "-color_trc", color_profile.transfer,
                "-colorspace", color_profile.space,
                "-color_range", "pc" if color_profile.range == "pc" else "tv",
            ]
        else:
            color_args = [
                "-color_primaries", "bt709", "-color_trc", "bt709",
                "-colorspace", "bt709", "-color_range", "tv",
            ]
        if not use_cpu and self._nvenc and max(width, height) <= 8192:
            return [
                "-c:v", "hevc_nvenc", "-preset", "p7", "-tune", "hq", "-profile:v", "main10",
                "-rc", "vbr", "-cq", "14", "-b:v", f"{target}M", "-maxrate", f"{target * 2}M",
                "-bufsize", f"{target * 4}M", "-spatial-aq", "1", "-temporal-aq", "1",
                "-aq-strength", "8", "-multipass", "fullres", "-b_ref_mode", "middle",
                "-g", str(max(12, fps // 2)), "-bf", "2", "-tag:v", "hvc1",
                "-pix_fmt", "p010le",
            ] + color_args
        return [
            "-c:v", "libx265", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p10le",
            "-tag:v", "hvc1",
        ] + color_args

    def _create_transition(
        self, master: str, output: Path, duration: float, label: str,
        requested: float, width: int, height: int, use_cpu: bool, base: float, weight: float,
        cpu_threads: int,
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
            "[c][x]concat=n=2:v=1:a=0,format=yuv420p[v]"
        )
        expected = max(0.1, duration - blend)
        command = [
            FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error", "-i", master,
            "-filter_complex", graph, "-map", "[v]", "-an",
        ] + self._h264_encoder(width, height, use_cpu) + [
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
        cpu_threads: int, base: float, weight: float,
    ) -> tuple[str, int, int]:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_key = self._ai_cache_key(video, start_time, duration, source_fps, source_w, source_h)
        cache_path = CACHE_DIR / f"{cache_key}.mp4"
        if cache_path.is_file():
            try:
                cached_info = probe_media(str(cache_path))
                cached_w, cached_h = first_video_size(cached_info)
                cached_duration = media_duration(cached_info)
                if (
                    (cached_w, cached_h) == (source_w * 2, source_h * 2)
                    and abs(cached_duration - duration) <= 0.20
                ):
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
        work = Path(tempfile.mkdtemp(prefix="studio_ai_", dir=output_dir))
        incoming, outgoing = work / "entrada", work / "melhorado"
        incoming.mkdir(); outgoing.mkdir(); temp_dirs.append(work)
        enhanced = self._temp_file(output_dir, "studio_ai_x2_", temp_paths)
        self._set_stage("IA 1/3", "Extraindo os quadros do trecho que será aprimorado.")
        extract = [
            FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
        ]
        if start_time > 0:
            extract += ["-ss", f"{start_time:.6f}"]
        extract += [
            "-i", video,
            "-map", "0:v:0", "-an", "-t", f"{duration:.6f}", "-fps_mode", "passthrough",
            "-start_number", "1", "-progress", "pipe:1", "-nostats", str(incoming / "frame%08d.png"),
        ]
        self._run_ffmpeg(extract, duration, base, weight * 0.2)
        frames = len(list(incoming.glob("frame*.png")))
        if not frames:
            raise RuntimeError("A IA não recebeu nenhum quadro do vídeo.")
        self._set_stage("IA 2/3", f"Real-ESRGAN está recuperando detalhes em {frames} quadros.")
        command = [
            str(REAL_ESRGAN), "-i", str(incoming), "-o", str(outgoing), "-m", str(REAL_ESRGAN_MODELS),
            "-n", "realesr-animevideov3", "-s", "2", "-f", "png", "-g", "0", "-t", "256", "-j", "2:2:2",
        ]
        self._run_ai(command, outgoing, frames, base + weight * 0.2, weight * 0.6)
        self._set_stage("IA 3/3", "Montando o master aprimorado sem o áudio do vídeo.")
        merge = [
            FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
            "-framerate", f"{source_fps:.8f}", "-start_number", "1", "-i", str(outgoing / "frame%08d.png"),
            "-map", "0:v:0", "-an",
        ] + self._h264_encoder(source_w * 2, source_h * 2, False) + [
            "-threads", str(cpu_threads), "-progress", "pipe:1", "-nostats", str(enhanced)
        ]
        self._run_ffmpeg(merge, duration, base + weight * 0.8, weight * 0.2)
        info = probe_media(str(enhanced))
        width, height = first_video_size(info)
        try:
            os.replace(enhanced, cache_path)
            if enhanced in temp_paths:
                temp_paths.remove(enhanced)
            self._log(f"Master aprimorado salvo no cache: {cache_path.name}")
            return str(cache_path), width, height
        except OSError:
            return str(enhanced), width, height

    def _run_ai(self, command: list[str], output_dir: Path, frames: int, base: float, weight: float) -> None:
        self._log("Comando IA: " + subprocess.list2cmdline(command))
        recent: deque[str] = deque(maxlen=50)
        process = subprocess.Popen(
            command, cwd=str(REAL_ESRGAN_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW,
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
                creationflags=CREATE_NO_WINDOW,
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
    ) -> str:
        paths = RifePaths(RIFE_EXE, RIFE_MODEL)
        if not paths.available:
            raise RuntimeError("RIFE NCNN ou modelo rife-v4.6 não encontrado.")
        token = f"rife_{time.time_ns()}"
        incoming = job_dir / f"{token}_in"
        outgoing = job_dir / f"{token}_out"
        incoming.mkdir(parents=True)
        outgoing.mkdir(parents=True)
        source_count = target_frame_count(duration, source_fps)
        target_count = target_frame_count(duration, target_fps)
        if target_count <= source_count:
            return video

        self._set_stage("RIFE 1/3", f"Extraindo {source_count} quadros para interpolação neural.")
        extract = [FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error"]
        if start_time > 0:
            extract += ["-ss", f"{start_time:.6f}"]
        extract += [
            "-i", video, "-map", "0:v:0", "-an", "-t", f"{duration:.6f}",
            "-vf", f"fps={source_fps:.8f}", "-start_number", "0",
            "-progress", "pipe:1", "-nostats", str(incoming / "%08d.png"),
        ]
        self._run_ffmpeg(extract, duration, base, weight * 0.20)
        extracted = len(list(incoming.glob("*.png")))
        if extracted < 2:
            raise RuntimeError("RIFE recebeu menos de dois quadros.")

        self._set_stage("RIFE 2/3", f"Gerando {target_count} quadros com o modelo rife-v4.6.")
        command = build_rife_command(paths, incoming, outgoing, target_count, use_cpu)
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
            creationflags=CREATE_NO_WINDOW,
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
            self._push_progress(base + weight * (0.20 + 0.65 * min(1.0, completed / target_count)))
            time.sleep(0.25)
        code = process.wait()
        reader_thread.join(timeout=2)
        if self._cancelled:
            raise InterruptedError
        if code:
            raise RuntimeError("RIFE falhou.\n" + "\n".join(recent))
        frames = sorted(outgoing.glob("*.png"))
        if len(frames) < max(2, target_count - 1):
            raise RuntimeError(f"RIFE produziu {len(frames)} de {target_count} quadros esperados.")

        self._set_stage("RIFE 3/3", "Montando o master interpolado com cadência constante.")
        first_number = int(frames[0].stem)
        interpolated = self._temp_file(job_dir, "studio_rife_", temp_paths)
        merge = [
            FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
            "-framerate", f"{target_fps:.8f}", "-start_number", str(first_number),
            "-i", str(outgoing / "%08d.png"), "-map", "0:v:0", "-an",
        ] + self._h264_encoder(1920, 1080, use_cpu) + [
            "-threads", str(cpu_threads), "-t", f"{duration:.6f}",
            "-progress", "pipe:1", "-nostats", str(interpolated),
        ]
        self._run_ffmpeg(merge, duration, base + weight * 0.85, weight * 0.15)
        return str(interpolated)

    @staticmethod
    def _temp_file(directory: Path, prefix: str, paths: list[Path]) -> Path:
        handle = tempfile.NamedTemporaryFile(prefix=prefix, suffix=".mp4", dir=directory, delete=False)
        path = Path(handle.name); handle.close(); paths.append(path); return path

    def _run_ffmpeg(self, command: list[str], duration: float, base: float, weight: float) -> None:
        self._log("Comando FFmpeg: " + subprocess.list2cmdline(command))
        recent: deque[str] = deque(maxlen=60)
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW,
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

    def _verify_output(self, path: str, duration: float, width: int, height: int, fps: int) -> dict:
        self._set_stage("Verificando", "Conferindo resolução, FPS, duração e integridade do arquivo final.")
        info = probe_media(path)
        out_w, out_h = first_video_size(info)
        out_fps = first_video_fps(info)
        out_duration = media_duration(info)
        if (out_w, out_h) != (width, height):
            raise RuntimeError(f"Resolução final inesperada: {out_w}×{out_h}.")
        if abs(out_fps - fps) > 0.02:
            raise RuntimeError(f"FPS final inesperado: {out_fps:.3f}.")
        if abs(out_duration - duration) > 0.35:
            raise RuntimeError("A duração final não corresponde ao projeto.")
        return {
            "info": info, "width": out_w, "height": out_h, "fps": out_fps,
            "duration": out_duration,
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
        self, output_path: Path, settings: RenderSettings, verification: dict, project_duration: float,
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
            f"Processamento: {'CPU' if settings.use_cpu else 'GPU automática'} • {settings.cpu_threads} threads de CPU",
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
            messagebox.showinfo(APP_TITLE, f"Diagnóstico criado sem nomes de mídia:\n\n{report}")
            os.startfile(report)
        except Exception as exc:
            self._log(f"Falha ao criar diagnóstico: {exc}")
            messagebox.showerror(APP_TITLE, f"Não foi possível criar o diagnóstico.\n\n{exc}")

    def _check_updates(self) -> None:
        feed = update_manager.configured_feed()
        if not feed:
            messagebox.showinfo(
                APP_TITLE,
                "O atualizador está pronto, mas o canal público será ativado quando o repositório GitHub do CinePulse for publicado.",
            )
            return
        self.update_button.configure(state="disabled")
        self.status.set("Verificando atualizações do CinePulse…")

        def worker() -> None:
            try:
                info = update_manager.check(feed, __version__)
                self._events.put(("update_checked", info))
            except Exception as exc:
                self._events.put(("update_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _stage_update(self, info: update_manager.UpdateInfo) -> None:
        self.status.set(f"Baixando e verificando CinePulse {info.version}…")

        def worker() -> None:
            try:
                update_manager.stage(info)
                self._events.put(("update_ready", info.version))
            except Exception as exc:
                self._events.put(("update_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _recover_interrupted_render(self) -> None:
        payload = self._render_journal.read()
        if not payload:
            return
        try:
            pid = int(payload.get("pid") or 0)
        except (TypeError, ValueError):
            pid = 0
        if pid != os.getpid() and process_alive(pid):
            self.status.set(f"Outro processo CinePulse está renderizando (PID {pid}).")
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
                self.status.set(f"Renderização recuperada: {recovered.name}")
                messagebox.showinfo(APP_TITLE, f"Renderização recuperada com sucesso:\n\n{recovered}")
                return
            except Exception as exc:
                messagebox.showerror(APP_TITLE, f"A recuperação não pôde ser concluída.\n\n{exc}")
        self.status.set(f"Saída interrompida preservada para análise: {partial.name}")

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
        self.root.after(500, self._tick_clock)

    def _poll_events(self) -> None:
        try:
            while True:
                event = self._events.get_nowait()
                kind = event[0]
                if kind == "progress":
                    self._progress_value = float(event[1]); self.bar["value"] = self._progress_value
                    self.progress_text.set(f"{self._progress_value:.1f}%")
                elif kind == "stage":
                    self.stage.set(event[1]); self.status.set(event[2])
                elif kind == "log":
                    self._append_log_ui(event[1])
                elif kind == "update_checked":
                    info = event[1]
                    if info is None:
                        self.update_button.configure(state="normal")
                        self.status.set("O CinePulse já está atualizado.")
                        messagebox.showinfo(APP_TITLE, "Você já está usando a versão mais recente do CinePulse.")
                    elif messagebox.askyesno(
                        APP_TITLE,
                        f"CinePulse {info.version} está disponível.\n\nBaixar e preparar a atualização agora?",
                    ):
                        self._stage_update(info)
                    else:
                        self.update_button.configure(state="normal")
                        self.status.set("Atualização adiada pelo usuário.")
                elif kind == "update_ready":
                    self.update_button.configure(state="normal")
                    self.status.set(f"CinePulse {event[1]} pronto para instalar ao reiniciar.")
                    messagebox.showinfo(
                        APP_TITLE,
                        f"CinePulse {event[1]} foi baixado e verificado.\n\nFeche e abra o programa para concluir a atualização.",
                    )
                elif kind == "update_error":
                    self.update_button.configure(state="normal")
                    self.status.set("Não foi possível verificar ou preparar a atualização.")
                    messagebox.showerror(APP_TITLE, f"A atualização foi cancelada com segurança.\n\n{event[1]}")
                elif kind == "done":
                    _, path, preview, size, report_path = event
                    self._finish_busy(); self.bar["value"] = 100; self.progress_text.set("100%")
                    self.stage.set("Concluído"); self.status.set(f"Arquivo verificado • {size / (1024**2):.1f} MB")
                    if self._queue_running and not preview:
                        active = self._active_queue_item()
                        if active:
                            active["status"] = "Concluído"
                            active["report"] = event[4] if len(event) > 4 else ""
                        self._active_queue_id = None
                        self._refresh_queue_tree()
                        self._save_queue()
                        self.root.after(250, self._run_next_queue_item)
                    elif preview:
                        messagebox.showinfo(APP_TITLE, f"Preview criado:\n\n{path}")
                        try: os.startfile(path)
                        except OSError: pass
                    else:
                        messagebox.showinfo(
                            APP_TITLE,
                            f"Vídeo final criado e verificado:\n\n{path}\n\nRelatório:\n{report_path}",
                        )
                elif kind == "cancelled":
                    self._finish_busy(); self.stage.set("Cancelado"); self.status.set("Processamento cancelado e temporários removidos.")
                    if self._queue_running:
                        active = self._active_queue_item()
                        if active:
                            active["status"] = "Cancelado"
                        self._queue_running = False
                        self._active_queue_id = None
                        self._refresh_queue_tree()
                        self._save_queue()
                elif kind == "error":
                    self._finish_busy(); self.stage.set("Erro"); self.status.set("Abra ‘Ver log’ para conferir os detalhes técnicos.")
                    if self._queue_running:
                        active = self._active_queue_item()
                        if active:
                            active["status"] = "Erro"
                            active["error"] = event[1]
                        self._active_queue_id = None
                        self._refresh_queue_tree()
                        self._save_queue()
                        self.root.after(250, self._run_next_queue_item)
                    else:
                        messagebox.showerror(APP_TITLE, event[1])
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _finish_busy(self) -> None:
        self._busy = False
        self.render_button.configure(state="normal")
        self.preview_button.configure(state="normal")
        self.add_queue_button.configure(state="normal")
        self.start_queue_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")

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
        self.status.set("Encerrando a etapa atual com segurança…")
        if self._process and self._process.poll() is None:
            terminate_process_tree(self._process, self._log)

    def _on_close(self) -> None:
        if self._busy and not messagebox.askyesno(APP_TITLE, "Existe um processamento em andamento. Cancelar e sair?"):
            return
        if self._busy:
            self._cancel()
        self._save_queue()
        self.root.destroy()


def main() -> None:
    root = Tk()
    VideoOptimizerStudio(root)
    root.mainloop()


if __name__ == "__main__":
    main()
