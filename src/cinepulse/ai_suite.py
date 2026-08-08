from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import os
import shutil
import subprocess

from .paths import PATHS, component_path


ROOT = PATHS.root
AI_ROOT = component_path("ai")
MODELS = AI_ROOT / "models"
REPOS = AI_ROOT / "repos"
VENV_PYTHON = AI_ROOT / "venv" / "Scripts" / "python.exe"


@dataclass(frozen=True)
class AiModule:
    key: str
    name: str
    purpose: str
    required: tuple[Path, ...]
    activation: str = "Aguardando validação"
    detector: Callable[[], bool] | None = None
    installer_component: str | None = None
    experimental: bool = False
    license: str = ""
    download_bytes: int = 0

    @property
    def installed(self) -> bool:
        return self.detector() if self.detector else all(path.exists() for path in self.required)

    @property
    def size_bytes(self) -> int:
        total = 0
        for path in self.required:
            if path.is_file():
                total += path.stat().st_size
        return total


RIFE_DIR = MODELS / "rife" / "portable" / "rife-ncnn-vulkan-20221029-windows"
RIFE_EXE = RIFE_DIR / "rife-ncnn-vulkan.exe"
RIFE_PYTHON_MODEL = MODELS / "rife" / "practical-rife-4.25" / "train_log" / "flownet.pkl"
RIFE_SCRIPT = REPOS / "practical-rife" / "inference_video.py"
RIFE_NCNN_MODEL = RIFE_DIR / "rife-v4.6"


def _vmaf_available() -> bool:
    ffmpeg = PATHS.components / "ffmpeg" / "bin" / "ffmpeg.exe"
    executable = str(ffmpeg) if ffmpeg.is_file() else shutil.which("ffmpeg")
    if not executable:
        return False
    try:
        result = subprocess.run(
            [executable, "-hide_banner", "-filters"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=8,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        return result.returncode == 0 and "libvmaf" in result.stdout.lower()
    except (OSError, subprocess.SubprocessError):
        return False

MODULES = (
    AiModule(
        "realesrgan", "Real-ESRGAN NCNN", "Upscale local com recuperação de detalhes",
        (
            component_path("real-esrgan") / "realesrgan-ncnn-vulkan.exe",
            component_path("real-esrgan") / "models" / "realesr-animevideov3-x2.bin",
        ),
        "Integrado e validado em render real", None, "real-esrgan", download_bytes=8 * 1024 * 1024,
    ),
    AiModule(
        "rife", "RIFE 4.6 NCNN / 4.25", "Interpolação neural de quadros para 60/120 fps",
        (RIFE_EXE, RIFE_NCNN_MODEL / "flownet.bin", RIFE_NCNN_MODEL / "flownet.param"),
        "Integrado, validado e com fallback FFmpeg", None, "rife", download_bytes=400 * 1024 * 1024,
    ),
    AiModule(
        "basicvsrpp", "BasicVSR++ NTIRE", "Upscale e restauração temporal consistente",
        (MODELS / "basicvsrpp" / "basicvsrpp_ntire_vsr_x4.pth",
         MODELS / "basicvsrpp" / "basicvsrpp_ntire_decompress.pth"),
        installer_component="basicvsrpp", experimental=True, license="Apache-2.0", download_bytes=351646456,
    ),
    AiModule(
        "demucs", "Hybrid Transformer Demucs", "Separação de voz, bateria, baixo e instrumentos",
        (VENV_PYTHON,) + tuple(MODELS / "demucs" / "local_repo" / name for name in (
            "f7e0c4bc-ba3fe64a.th", "d12395a8-e57c48e6.th",
            "92cfc3b6-ef3bcb9c.th", "04573f0d-f3cf25b2.th",
        )), "Integrado e validado para condução dos VFX", None, "demucs", download_bytes=3500 * 1024 * 1024,
    ),
    AiModule(
        "clap", "LAION CLAP HTSAT", "Atmosfera, intenção e direção musical",
        (MODELS / "clap" / "clap-htsat-fused" / "pytorch_model.bin",),
        installer_component="clap", experimental=True, license="Apache-2.0", download_bytes=614596545,
    ),
    AiModule(
        "depth", "Video Depth Anything", "Profundidade temporal para VFX em camadas",
        (MODELS / "video-depth-anything" / "video_depth_anything_vitl.pth",
         MODELS / "video-depth-anything" / "video_depth_anything_vits.pth"),
        installer_component="depth", experimental=True, license="Large: CC-BY-NC-4.0", download_bytes=1654832768,
    ),
    AiModule(
        "sam2", "SAM 2.1", "Segmentação e acompanhamento de objetos",
        (MODELS / "sam2" / "sam2.1_hiera_large.pt", MODELS / "sam2" / "sam2.1_hiera_small.pt"),
        installer_component="sam2", experimental=True, license="Apache-2.0", download_bytes=1082499896,
    ),
    AiModule(
        "cotracker", "CoTracker 3", "Tracking de pontos para prender VFX à cena",
        (MODELS / "cotracker" / "scaled_offline.pth", MODELS / "cotracker" / "scaled_online.pth"),
        installer_component="cotracker", experimental=True, license="CC-BY-NC-4.0", download_bytes=203586548,
    ),
    AiModule(
        "codeformer", "CodeFormer", "Restauração opcional de rostos",
        (MODELS / "codeformer" / "codeformer.pth",
         MODELS / "codeformer" / "detection_Resnet50_Final.pth",
         MODELS / "codeformer" / "parsing_parsenet.pth"),
        installer_component="codeformer", experimental=True, license="S-Lab 1.0; não comercial", download_bytes=571466852,
    ),
    AiModule(
        "vmaf", "Netflix VMAF", "Medição perceptiva e comparação de qualidade",
        (), "Integrado e validado em amostra perceptiva", _vmaf_available, "ffmpeg", download_bytes=250 * 1024 * 1024,
    ),
    AiModule(
        "ltx2", "LTX-2.3", "Geração local opcional de áudio e vídeo",
        (REPOS / "ltx-2", MODELS / "ltx-2.3" / "ltx-2.3-22b-distilled-1.1.safetensors",
         MODELS / "ltx-2.3" / "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"),
        "Arquivos de 22B instalados; ainda não integrado ao CinePulse",
        installer_component="ltx2", experimental=True, license="LTX-2 Community License", download_bytes=47146217249,
    ),
)


def inventory() -> list[dict]:
    return [
        {
            "key": module.key,
            "name": module.name,
            "purpose": module.purpose,
            "installed": module.installed,
            "activation": module.activation,
            "size_bytes": module.size_bytes,
            "installable": module.installer_component is not None,
            "installer_component": module.installer_component,
            "experimental": module.experimental,
            "license": module.license,
            "download_bytes": module.download_bytes,
        }
        for module in MODULES
    ]


def installed_count() -> tuple[int, int]:
    items = inventory()
    return sum(item["installed"] for item in items), len(items)
