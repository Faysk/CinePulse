from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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

    @property
    def installed(self) -> bool:
        return all(path.exists() for path in self.required)

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

MODULES = (
    AiModule(
        "realesrgan", "Real-ESRGAN NCNN", "Upscale local com recuperação de detalhes",
        (
            component_path("real-esrgan") / "realesrgan-ncnn-vulkan.exe",
            component_path("real-esrgan") / "models" / "realesr-animevideov3-x2.bin",
        ),
        "Integrado e validado em render real",
    ),
    AiModule(
        "rife", "RIFE 4.6 NCNN / 4.25", "Interpolação neural de quadros para 60/120 fps",
        (VENV_PYTHON, RIFE_SCRIPT, RIFE_PYTHON_MODEL, RIFE_EXE),
        "Integrado, validado e com fallback FFmpeg",
    ),
    AiModule(
        "basicvsrpp", "BasicVSR++ NTIRE", "Upscale e restauração temporal consistente",
        (REPOS / "mmagic", MODELS / "basicvsrpp" / "basicvsrpp_ntire_vsr_x4.pth",
         MODELS / "basicvsrpp" / "basicvsrpp_ntire_decompress.pth"),
    ),
    AiModule(
        "demucs", "Hybrid Transformer Demucs", "Separação de voz, bateria, baixo e instrumentos",
        tuple(MODELS / "demucs" / name for name in (
            "f7e0c4bc-ba3fe64a.th", "d12395a8-e57c48e6.th",
            "92cfc3b6-ef3bcb9c.th", "04573f0d-f3cf25b2.th",
        )), "Integrado e validado para condução dos VFX",
    ),
    AiModule(
        "clap", "LAION CLAP HTSAT", "Atmosfera, intenção e direção musical",
        (MODELS / "clap" / "clap-htsat-fused" / "pytorch_model.bin",),
    ),
    AiModule(
        "depth", "Video Depth Anything", "Profundidade temporal para VFX em camadas",
        (MODELS / "video-depth-anything" / "video_depth_anything_vitl.pth",
         MODELS / "video-depth-anything" / "video_depth_anything_vits.pth"),
    ),
    AiModule(
        "sam2", "SAM 2.1", "Segmentação e acompanhamento de objetos",
        (MODELS / "sam2" / "sam2.1_hiera_large.pt", MODELS / "sam2" / "sam2.1_hiera_small.pt"),
    ),
    AiModule(
        "cotracker", "CoTracker 3", "Tracking de pontos para prender VFX à cena",
        (MODELS / "cotracker" / "scaled_offline.pth", MODELS / "cotracker" / "scaled_online.pth"),
    ),
    AiModule(
        "codeformer", "CodeFormer", "Restauração opcional de rostos",
        (MODELS / "codeformer" / "codeformer.pth",
         MODELS / "codeformer" / "detection_Resnet50_Final.pth",
         MODELS / "codeformer" / "parsing_parsenet.pth"),
    ),
    AiModule(
        "vmaf", "Netflix VMAF", "Medição perceptiva e comparação de qualidade",
        (REPOS / "vmaf", AI_ROOT / "runtime" / "ffmpeg-vmaf"),
        "Integrado e validado em amostra perceptiva",
    ),
    AiModule(
        "ltx2", "LTX-2.3", "Geração local opcional de áudio e vídeo",
        (REPOS / "ltx-2",), "Código instalado; checkpoint de 22B não ativado",
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
        }
        for module in MODULES
    ]


def installed_count() -> tuple[int, int]:
    items = inventory()
    return sum(item["installed"] for item in items), len(items)
