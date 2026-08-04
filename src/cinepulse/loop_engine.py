from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
from collections import deque
from pathlib import Path
from tkinter import Tk, StringVar, filedialog, messagebox
from tkinter import ttk

from . import aurora
from .paths import PATHS, component_path


APP_TITLE = "CinePulse — modo clássico"
WIDTH = 7680
HEIGHT = 4320
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
PROFILE_YOUTUBE = "YouTube — 8K 60 fps (recomendado)"
PROFILE_LOCAL_120 = "Máxima qualidade — 8K 120 fps"
EFFECT_AURORA = "Aurora Cinematográfica (recomendado)"
EFFECT_NONE = "Sem efeito musical"
AI_REAL_ESRGAN_X2 = "Real-ESRGAN x2 — mais detalhes (recomendado)"
AI_OFF = "Sem melhoria por IA — mais rápido"
APP_DIR = PATHS.root
REAL_ESRGAN_DIR = component_path("real-esrgan")
REAL_ESRGAN = REAL_ESRGAN_DIR / "realesrgan-ncnn-vulkan.exe"
REAL_ESRGAN_MODELS = REAL_ESRGAN_DIR / "models"


def find_program(name: str) -> str | None:
    portable = PATHS.components / "ffmpeg" / "bin" / f"{name}.exe"
    if portable.is_file():
        return str(portable)
    found = shutil.which(name)
    if found:
        return found

    if os.name == "nt":
        winget = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
        matches = sorted(winget.glob(f"**/{name}.exe"), reverse=True)
        if matches:
            return str(matches[0])
    return None


FFMPEG = find_program("ffmpeg")
FFPROBE = find_program("ffprobe")


def probe_media(path: str) -> dict:
    if not FFPROBE:
        raise RuntimeError("FFprobe não foi encontrado.")
    command = [
        FFPROBE,
        "-v",
        "error",
        "-show_entries",
        (
            "format=duration,bit_rate,format_name:"
            "stream=codec_type,codec_name,profile,width,height,r_frame_rate,avg_frame_rate,pix_fmt,"
            "bits_per_raw_sample,color_range,color_space,color_transfer,color_primaries,channels,sample_rate,bit_rate"
        ),
        "-of",
        "json",
        path,
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Não foi possível analisar o arquivo.")
    return json.loads(result.stdout)


def media_duration(data: dict) -> float:
    try:
        duration = float(data["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("O arquivo não possui uma duração válida.") from exc
    if duration <= 0:
        raise RuntimeError("O arquivo está vazio ou possui duração inválida.")
    return duration


def first_video_size(data: dict) -> tuple[int, int]:
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and stream.get("width"):
            return int(stream["width"]), int(stream["height"])
    raise RuntimeError("O arquivo selecionado não contém vídeo.")


def first_video_fps(data: dict) -> float:
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and stream.get("r_frame_rate"):
            numerator, denominator = stream["r_frame_rate"].split("/", 1)
            return float(numerator) / float(denominator)
    raise RuntimeError("Não foi possível verificar os quadros por segundo.")


def has_audio(data: dict) -> bool:
    return any(stream.get("codec_type") == "audio" for stream in data.get("streams", []))


def format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def nvenc_available() -> bool:
    if not FFMPEG:
        return False
    result = subprocess.run(
        [FFMPEG, "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
    return result.returncode == 0 and "hevc_nvenc" in result.stdout


class LoopMusicApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("840x640")
        self.root.minsize(740, 600)

        self.video = StringVar()
        self.audio = StringVar()
        self.output = StringVar()
        self.profile = StringVar(value=PROFILE_LOCAL_120)
        self.effect = StringVar(value=EFFECT_AURORA)
        self.ai_mode = StringVar(value=AI_REAL_ESRGAN_X2)
        self.status = StringVar(value="Selecione o vídeo curto e a música.")
        self.detail = StringVar(value="Saída: 7680 × 4320, 120 fps, Aurora Cinematográfica, HEVC 10-bit.")
        self.progress = StringVar(value="0%")
        self._events: queue.Queue = queue.Queue()
        self._process: subprocess.Popen | None = None
        self._cancelled = False
        self._busy = False

        self._build_ui()
        self.root.after(100, self._poll_events)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=22)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text=APP_TITLE, font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="Transforme um clipe curto em um vídeo musical contínuo para o YouTube.",
        ).pack(anchor="w", pady=(2, 18))

        form = ttk.Frame(outer)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        self._file_row(form, 0, "Vídeo do loop", self.video, self._choose_video)
        self._file_row(form, 1, "Música (WAV recomendado)", self.audio, self._choose_audio)
        self._file_row(form, 2, "Salvar como", self.output, self._choose_output)

        ttk.Label(form, text="Perfil de saída").grid(row=3, column=0, sticky="w", pady=6, padx=(0, 12))
        profile_box = ttk.Combobox(
            form,
            textvariable=self.profile,
            values=(PROFILE_YOUTUBE, PROFILE_LOCAL_120),
            state="readonly",
        )
        profile_box.grid(row=3, column=1, columnspan=2, sticky="ew", pady=6)
        profile_box.bind("<<ComboboxSelected>>", self._profile_changed)

        ttk.Label(form, text="Efeito visual").grid(row=4, column=0, sticky="w", pady=6, padx=(0, 12))
        effect_box = ttk.Combobox(
            form,
            textvariable=self.effect,
            values=(EFFECT_AURORA, EFFECT_NONE),
            state="readonly",
        )
        effect_box.grid(row=4, column=1, columnspan=2, sticky="ew", pady=6)
        effect_box.bind("<<ComboboxSelected>>", self._effect_changed)

        ttk.Label(form, text="Melhoria por IA").grid(row=5, column=0, sticky="w", pady=6, padx=(0, 12))
        ai_box = ttk.Combobox(
            form,
            textvariable=self.ai_mode,
            values=(AI_REAL_ESRGAN_X2, AI_OFF),
            state="readonly",
        )
        ai_box.grid(row=5, column=1, columnspan=2, sticky="ew", pady=6)
        ai_box.bind("<<ComboboxSelected>>", self._ai_changed)

        info = ttk.LabelFrame(outer, text="Qualidade", padding=12)
        info.pack(fill="x", pady=(18, 12))
        ttk.Label(
            info,
            text=(
                "Real-ESRGAN AnimeVideo-v3 • 8K UHD • HEVC 10-bit • bitrate alto • WAV como fonte\n"
                "A IA melhora o clipe curto; Aurora, luz, vinheta e pulso reagem à música inteira."
            ),
        ).pack(anchor="w")

        self.bar = ttk.Progressbar(outer, maximum=100, mode="determinate")
        self.bar.pack(fill="x", pady=(8, 3))
        progress_line = ttk.Frame(outer)
        progress_line.pack(fill="x")
        ttk.Label(progress_line, textvariable=self.status).pack(side="left")
        ttk.Label(progress_line, textvariable=self.progress).pack(side="right")
        ttk.Label(outer, textvariable=self.detail, foreground="#555555").pack(anchor="w", pady=(3, 14))

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x")
        self.start_button = ttk.Button(buttons, text="Criar vídeo 8K", command=self._start)
        self.start_button.pack(side="right")
        self.cancel_button = ttk.Button(buttons, text="Cancelar", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="right", padx=(0, 8))

    def _profile_changed(self, _event=None) -> None:
        if self.profile.get() == PROFILE_LOCAL_120:
            self.status.set("120 fps é para reprodução local; o YouTube exibirá no máximo 60 fps.")
            self.detail.set("Saída: 7680 × 4320, 120 fps. Arquivo e tempo aproximadamente dobrados.")
            if self.output.get().endswith("_8K_60fps.mp4"):
                self.output.set(self.output.get()[:-13] + "_8K_120fps.mp4")
        else:
            self.status.set("Perfil recomendado para upload no YouTube.")
            self.detail.set("Saída: 7680 × 4320, 60 fps, HEVC 10-bit, BT.709.")
            if self.output.get().endswith("_8K_120fps.mp4"):
                self.output.set(self.output.get()[:-14] + "_8K_60fps.mp4")

    def _effect_changed(self, _event=None) -> None:
        if self.effect.get() == EFFECT_AURORA:
            self.status.set("Aurora Cinematográfica reagirá à música inteira.")
            self.detail.set("Render completo audio-reactive: mais lento, com maior uso temporário de disco.")
        else:
            self.status.set("O vídeo será repetido sem camada audio-reactive.")
            self.detail.set("Modo mais rápido; preserva o loop original sem efeitos adicionais.")

    def _ai_changed(self, _event=None) -> None:
        if self.ai_mode.get() == AI_REAL_ESRGAN_X2:
            self.status.set("A IA melhorará detalhes e contornos do clipe curto antes do loop.")
            self.detail.set("Real-ESRGAN AnimeVideo-v3 x2; requer mais tempo e espaço temporário.")
        else:
            self.status.set("Melhoria por IA desativada.")
            self.detail.set("O programa usará somente redimensionamento Lanczos e interpolação tradicional.")

    def _file_row(self, parent, row: int, label: str, variable: StringVar, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6, padx=(0, 12))
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=6)
        ttk.Button(parent, text="Selecionar…", command=command).grid(row=row, column=2, pady=6, padx=(8, 0))

    def _choose_video(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecione o vídeo do loop",
            filetypes=[("Vídeos", "*.mp4 *.mov *.mkv *.webm *.avi"), ("Todos os arquivos", "*.*")],
        )
        if path:
            self.video.set(path)
            self._suggest_output()

    def _choose_audio(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecione a música",
            filetypes=[("Áudio sem perdas (recomendado)", "*.wav *.flac"), ("Outros áudios", "*.mp3 *.m4a *.aac *.ogg"), ("Todos os arquivos", "*.*")],
        )
        if path:
            self.audio.set(path)
            self._suggest_output()

    def _choose_output(self) -> None:
        initial = self.output.get() or "video_musical_8k.mp4"
        path = filedialog.asksaveasfilename(
            title="Salvar vídeo final",
            defaultextension=".mp4",
            initialdir=str(Path(initial).parent),
            initialfile=Path(initial).name,
            filetypes=[("Vídeo MP4", "*.mp4")],
        )
        if path:
            self.output.set(path)

    def _suggest_output(self) -> None:
        if self.output.get():
            return
        source = self.audio.get() or self.video.get()
        if source:
            path = Path(source)
            fps = 120 if self.profile.get() == PROFILE_LOCAL_120 else 60
            self.output.set(str(path.with_name(f"{path.stem}_8K_{fps}fps.mp4")))

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.start_button.configure(state="disabled" if busy else "normal")
        self.cancel_button.configure(state="normal" if busy else "disabled")

    def _start(self) -> None:
        if not FFMPEG or not FFPROBE:
            messagebox.showerror(APP_TITLE, "FFmpeg/FFprobe não foram encontrados neste computador.")
            return

        video = self.video.get().strip()
        audio = self.audio.get().strip()
        output = self.output.get().strip()
        fps = 120 if self.profile.get() == PROFILE_LOCAL_120 else 60
        effect = self.effect.get()
        ai_mode = self.ai_mode.get()
        if not video or not audio or not output:
            messagebox.showwarning(APP_TITLE, "Selecione o vídeo, a música e o arquivo de saída.")
            return
        if not Path(video).is_file() or not Path(audio).is_file():
            messagebox.showerror(APP_TITLE, "Um dos arquivos selecionados não existe.")
            return
        if Path(output).suffix.lower() != ".mp4":
            output += ".mp4"
            self.output.set(output)
        if Path(output).exists() and not messagebox.askyesno(APP_TITLE, "O arquivo de saída já existe. Deseja substituí-lo?"):
            return
        if Path(output).resolve() in (Path(video).resolve(), Path(audio).resolve()):
            messagebox.showerror(APP_TITLE, "O arquivo de saída precisa ter um nome diferente das entradas.")
            return

        self._cancelled = False
        self.bar["value"] = 0
        self.progress.set("0%")
        self.status.set("Analisando os arquivos…")
        self.detail.set("Preparando a conversão.")
        self._set_busy(True)
        threading.Thread(
            target=self._worker,
            args=(video, audio, output, fps, effect, ai_mode),
            daemon=True,
        ).start()

    def _worker(self, video: str, audio: str, output: str, fps: int, effect: str, ai_mode: str) -> None:
        temp_paths: list[Path] = []
        temp_dirs: list[Path] = []
        try:
            video_info = probe_media(video)
            audio_info = probe_media(audio)
            video_duration = media_duration(video_info)
            audio_duration = media_duration(audio_info)
            source_w, source_h = first_video_size(video_info)
            source_fps = first_video_fps(video_info)
            if not has_audio(audio_info):
                raise RuntimeError("O arquivo de música não contém uma faixa de áudio.")

            use_nvenc = nvenc_available()
            encoder_name = "NVIDIA RTX (HEVC 10-bit)" if use_nvenc else "processador (x265 10-bit)"
            loops = max(1, int(audio_duration / video_duration + 0.999999))

            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            bitrate_mbps = 240 if fps == 120 else 160
            estimated_bytes = (bitrate_mbps * 1_000_000 / 8) * (audio_duration + video_duration)
            use_ai = ai_mode == AI_REAL_ESRGAN_X2
            if use_ai:
                if not REAL_ESRGAN.is_file() or not REAL_ESRGAN_MODELS.is_dir():
                    raise RuntimeError(
                        "O módulo Real-ESRGAN não foi encontrado na pasta tools\\real-esrgan."
                    )
                source_frames = max(1, int(video_duration * source_fps + 0.5))
                # Reserva conservadora para PNGs de entrada e saída durante o processamento x2.
                estimated_bytes += source_w * source_h * source_frames * 3 * 5
            if effect == EFFECT_AURORA:
                if not use_nvenc:
                    raise RuntimeError("A Aurora Cinematográfica em 8K requer o encoder NVIDIA desta máquina.")
                estimated_bytes += (50_000_000 / 8) * (audio_duration + video_duration)
            estimated_gb = estimated_bytes / (1024 ** 3)
            free_bytes = shutil.disk_usage(output_path.parent).free
            if free_bytes < estimated_bytes * 1.25:
                free_gb = free_bytes / (1024 ** 3)
                raise RuntimeError(
                    f"Espaço insuficiente. A conversão pode precisar de cerca de {estimated_gb:.1f} GB, "
                    f"mas há somente {free_gb:.1f} GB livres no destino."
                )
            self._events.put((
                "detail",
                f"Clipe {source_w}×{source_h} • música {format_time(audio_duration)} • {loops} repetições • "
                f"{fps} fps • {effect} • {ai_mode} • estimativa temporária {estimated_gb:.1f} GB • {encoder_name}.",
            ))

            working_video = video
            working_w, working_h = source_w, source_h
            ai_progress = 0.0
            if use_ai:
                working_video, working_w, working_h = self._enhance_clip_ai(
                    video,
                    output_path.parent,
                    video_duration,
                    source_fps,
                    source_w,
                    source_h,
                    use_nvenc,
                    temp_paths,
                    temp_dirs,
                )
                ai_progress = 20.0

            if effect == EFFECT_AURORA:
                self._render_aurora_pipeline(
                    working_video,
                    audio,
                    output,
                    video_duration,
                    audio_duration,
                    working_w,
                    working_h,
                    fps,
                    temp_paths,
                    ai_progress,
                )
                self._verify_and_finish(output, audio_duration, fps)
                return

            temp_file = tempfile.NamedTemporaryFile(
                prefix="loop_master_8k_", suffix=".mp4", dir=output_path.parent, delete=False
            )
            temp_path = Path(temp_file.name)
            temp_file.close()
            temp_paths.append(temp_path)

            target_ratio = WIDTH / HEIGHT
            source_ratio = source_w / source_h
            is_16_9 = abs(source_ratio - target_ratio) / target_ratio < 0.01

            if use_nvenc and is_16_9:
                video_filter = (
                    f"minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
                    "setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709,"
                    "format=p010le,hwupload_cuda,"
                    f"scale_cuda={WIDTH}:{HEIGHT}:interp_algo=lanczos:format=p010le"
                )
            else:
                video_filter = (
                    f"minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
                    "setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709,"
                    f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease:"
                    "flags=lanczos+accurate_rnd+full_chroma_int,"
                    f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,format=yuv420p10le"
                )

            command_master = [
                FFMPEG,
                "-y",
                "-hide_banner",
                "-nostdin",
                "-loglevel",
                "error",
                "-i",
                working_video,
                "-map",
                "0:v:0",
                "-an",
                "-vf",
                video_filter,
            ]
            if use_nvenc:
                target_bitrate = "240M" if fps == 120 else "160M"
                max_bitrate = "400M" if fps == 120 else "240M"
                buffer_size = "800M" if fps == 120 else "480M"
                command_master += [
                    "-c:v", "hevc_nvenc",
                    "-preset", "p7",
                    "-tune", "hq",
                    "-profile:v", "main10",
                    "-rc", "vbr",
                    "-cq", "14",
                    "-b:v", target_bitrate,
                    "-maxrate", max_bitrate,
                    "-bufsize", buffer_size,
                    "-spatial-aq", "1",
                    "-temporal-aq", "1",
                    "-aq-strength", "8",
                    "-multipass", "fullres",
                    "-b_ref_mode", "middle",
                    "-g", str(fps // 2),
                    "-bf", "2",
                ]
            else:
                command_master += [
                    "-c:v", "libx265",
                    "-preset", "medium",
                    "-crf", "16",
                    "-pix_fmt", "yuv420p10le",
                    "-g", str(fps // 2),
                    "-bf", "2",
                ]
            command_master += [
                "-color_primaries", "bt709",
                "-color_trc", "bt709",
                "-colorspace", "bt709",
                "-color_range", "tv",
                "-tag:v", "hvc1",
                "-movflags", "+faststart",
                "-progress", "pipe:1",
                "-nostats",
                str(temp_path),
            ]

            self._events.put(("status", f"Criando o master 8K/{fps}…"))
            self._run_ffmpeg(command_master, video_duration, ai_progress, 90 - ai_progress)
            if self._cancelled:
                raise InterruptedError

            command_final = [
                FFMPEG,
                "-y",
                "-hide_banner",
                "-nostdin",
                "-loglevel",
                "error",
                "-stream_loop",
                "-1",
                "-i",
                str(temp_path),
                "-i",
                audio,
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "384k",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-t",
                f"{audio_duration:.6f}",
                "-movflags",
                "+faststart",
                "-progress",
                "pipe:1",
                "-nostats",
                output,
            ]
            self._events.put(("status", "Repetindo o clipe até o fim da música…"))
            self._run_ffmpeg(command_final, audio_duration, 90, 10)
            if self._cancelled:
                raise InterruptedError

            final_info = probe_media(output)
            final_duration = media_duration(final_info)
            final_w, final_h = first_video_size(final_info)
            final_fps = first_video_fps(final_info)
            if final_w != WIDTH or final_h != HEIGHT:
                raise RuntimeError(f"A verificação encontrou resolução inesperada: {final_w}×{final_h}.")
            if abs(final_fps - fps) > 0.01:
                raise RuntimeError(f"A verificação encontrou {final_fps:.2f} fps em vez de {fps} fps.")
            if abs(final_duration - audio_duration) > 0.25:
                raise RuntimeError("A duração final não corresponde à música.")

            size_gb = Path(output).stat().st_size / (1024 ** 3)
            self._events.put(("done", output, final_duration, size_gb, fps))
        except InterruptedError:
            self._events.put(("cancelled",))
        except Exception as exc:
            self._events.put(("error", str(exc)))
        finally:
            self._process = None
            for temp_path in temp_paths:
                if not temp_path.exists():
                    continue
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            for temp_dir in temp_dirs:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)

    def _enhance_clip_ai(
        self,
        video: str,
        output_dir: Path,
        video_duration: float,
        source_fps: float,
        source_w: int,
        source_h: int,
        use_nvenc: bool,
        temp_paths: list[Path],
        temp_dirs: list[Path],
    ) -> tuple[str, int, int]:
        work_dir = Path(tempfile.mkdtemp(prefix="real_esrgan_", dir=output_dir))
        input_frames = work_dir / "entrada"
        output_frames = work_dir / "melhorado"
        input_frames.mkdir()
        output_frames.mkdir()
        temp_dirs.append(work_dir)

        enhanced_handle = tempfile.NamedTemporaryFile(
            prefix="clipe_ia_x2_", suffix=".mp4", dir=output_dir, delete=False
        )
        enhanced_video = Path(enhanced_handle.name)
        enhanced_handle.close()
        temp_paths.append(enhanced_video)

        extract_command = [
            FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
            "-i", video, "-map", "0:v:0", "-an", "-fps_mode", "passthrough",
            "-start_number", "1", "-progress", "pipe:1", "-nostats",
            str(input_frames / "frame%08d.png"),
        ]
        self._events.put(("status", "IA 1/3 — extraindo os quadros do clipe curto…"))
        self._run_ffmpeg(extract_command, video_duration, 0, 4)
        if self._cancelled:
            raise InterruptedError

        frame_count = len(list(input_frames.glob("frame*.png")))
        if frame_count == 0:
            raise RuntimeError("Não foi possível extrair os quadros para a melhoria por IA.")

        ai_command = [
            str(REAL_ESRGAN),
            "-i", str(input_frames),
            "-o", str(output_frames),
            "-m", str(REAL_ESRGAN_MODELS),
            "-n", "realesr-animevideov3",
            "-s", "2",
            "-f", "png",
            "-g", "0",
            "-t", "256",
            "-j", "2:2:2",
        ]
        self._events.put(("status", "IA 2/3 — recuperando detalhes com Real-ESRGAN x2…"))
        self._run_ai_process(ai_command, output_frames, frame_count, 4, 12)
        if self._cancelled:
            raise InterruptedError

        merge_command = [
            FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
            "-framerate", f"{source_fps:.8f}",
            "-start_number", "1", "-i", str(output_frames / "frame%08d.png"),
            "-map", "0:v:0", "-an",
        ]
        if use_nvenc:
            merge_command += [
                "-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq",
                "-rc", "vbr", "-cq", "10", "-b:v", "80M",
                "-maxrate", "140M", "-bufsize", "280M",
            ]
        else:
            merge_command += ["-c:v", "libx264", "-preset", "slow", "-crf", "10"]
        merge_command += [
            "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-colorspace", "bt709", "-movflags", "+faststart",
            "-progress", "pipe:1", "-nostats", str(enhanced_video),
        ]
        self._events.put(("status", "IA 3/3 — montando o clipe aprimorado…"))
        self._run_ffmpeg(merge_command, video_duration, 16, 4)
        if self._cancelled:
            raise InterruptedError

        info = probe_media(str(enhanced_video))
        enhanced_w, enhanced_h = first_video_size(info)
        expected_w, expected_h = source_w * 2, source_h * 2
        if enhanced_w != expected_w or enhanced_h != expected_h:
            raise RuntimeError(
                f"A IA gerou {enhanced_w}×{enhanced_h}; era esperado {expected_w}×{expected_h}."
            )
        return str(enhanced_video), enhanced_w, enhanced_h

    def _run_ai_process(
        self,
        command: list[str],
        output_dir: Path,
        frame_count: int,
        base: float,
        weight: float,
    ) -> None:
        recent: deque[str] = deque(maxlen=40)
        self._process = subprocess.Popen(
            command,
            cwd=str(REAL_ESRGAN_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )

        def drain_output() -> None:
            assert self._process is not None and self._process.stdout is not None
            for raw_line in self._process.stdout:
                line = raw_line.strip()
                if line:
                    recent.append(line)

        reader = threading.Thread(target=drain_output, daemon=True)
        reader.start()
        last_done = -1
        while self._process.poll() is None:
            if self._cancelled:
                self._process.terminate()
                break
            done = len(list(output_dir.glob("frame*.png")))
            if done != last_done:
                fraction = min(1.0, done / max(1, frame_count))
                self._events.put(("progress", base + weight * fraction))
                last_done = done
            threading.Event().wait(0.25)
        return_code = self._process.wait()
        reader.join(timeout=2)
        if self._cancelled:
            raise InterruptedError
        if return_code != 0:
            useful = "\n".join(recent)
            raise RuntimeError(
                f"A melhoria por IA falhou.\n\n{useful}" if useful else "A melhoria por IA falhou sem detalhes."
            )
        self._events.put(("progress", base + weight))

    def _render_aurora_pipeline(
        self,
        video: str,
        audio: str,
        output: str,
        video_duration: float,
        audio_duration: float,
        source_w: int,
        source_h: int,
        fps: int,
        temp_paths: list[Path],
        progress_base: float,
    ) -> None:
        output_dir = Path(output).parent

        def temporary_path(prefix: str) -> Path:
            handle = tempfile.NamedTemporaryFile(prefix=prefix, suffix=".mp4", dir=output_dir, delete=False)
            path = Path(handle.name)
            handle.close()
            temp_paths.append(path)
            return path

        ai_enhanced = progress_base > 0
        work_width, work_height = (2560, 1440) if ai_enhanced else (1280, 720)
        work_bitrate = "100M" if ai_enhanced else "50M"
        work_maxrate = "180M" if ai_enhanced else "100M"
        work_bufsize = "360M" if ai_enhanced else "200M"
        loop_master = temporary_path(f"loop_master_{work_height}p60_")
        reactive_master = temporary_path(f"aurora_reactive_{work_height}p60_")
        source_ratio = source_w / source_h
        if abs(source_ratio - (16 / 9)) / (16 / 9) < 0.01:
            master_filter = (
                "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
                f"scale={work_width}:{work_height}:flags=lanczos+accurate_rnd+full_chroma_int,"
                "setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709,"
                "format=yuv420p"
            )
        else:
            master_filter = (
                "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
                f"scale={work_width}:{work_height}:force_original_aspect_ratio=decrease:"
                "flags=lanczos+accurate_rnd+full_chroma_int,"
                f"pad={work_width}:{work_height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                "setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709,"
                "format=yuv420p"
            )
        command_loop_master = [
            FFMPEG,
            "-y",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-i",
            video,
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            master_filter,
            "-c:v",
            "h264_nvenc",
            "-preset",
            "p7",
            "-tune",
            "hq",
            "-rc",
            "vbr",
            "-cq",
            "10",
            "-b:v",
            work_bitrate,
            "-maxrate",
            work_maxrate,
            "-bufsize",
            work_bufsize,
            "-g",
            "30",
            "-bf",
            "2",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-colorspace",
            "bt709",
            "-color_range",
            "tv",
            "-movflags",
            "+faststart",
            "-progress",
            "pipe:1",
            "-nostats",
            str(loop_master),
        ]
        self._events.put(("status", f"Preparando o loop aprimorado em {work_height}p/60…"))
        remaining = 100.0 - progress_base
        self._run_ffmpeg(command_loop_master, video_duration, progress_base, remaining * 0.08)
        if self._cancelled:
            raise InterruptedError

        self._events.put(("status", "Etapa 2/3 — sincronizando a Aurora Cinematográfica…"))
        try:
            aurora.render_reactive_intermediate(
                FFMPEG,
                str(loop_master),
                audio,
                str(reactive_master),
                audio_duration,
                lambda fraction: self._events.put((
                    "progress", progress_base + remaining * (0.08 + 0.32 * fraction)
                )),
                lambda: self._cancelled,
                lambda process: setattr(self, "_process", process),
                work_width,
                work_height,
                work_bitrate,
                work_maxrate,
                work_bufsize,
            )
        except aurora.RenderCancelled as exc:
            raise InterruptedError from exc
        if self._cancelled:
            raise InterruptedError

        if fps == 120:
            frame_filter = "minterpolate=fps=120:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
        else:
            frame_filter = "fps=60,"
        final_filter = (
            frame_filter
            + "setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709,"
            "format=p010le,hwupload_cuda,"
            f"scale_cuda={WIDTH}:{HEIGHT}:interp_algo=lanczos:format=p010le"
        )
        target_bitrate = "240M" if fps == 120 else "160M"
        max_bitrate = "400M" if fps == 120 else "240M"
        buffer_size = "800M" if fps == 120 else "480M"
        command_final = [
            FFMPEG,
            "-y",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-i",
            str(reactive_master),
            "-i",
            audio,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-vf",
            final_filter,
            "-c:v",
            "hevc_nvenc",
            "-preset",
            "p7",
            "-tune",
            "hq",
            "-profile:v",
            "main10",
            "-rc",
            "vbr",
            "-cq",
            "14",
            "-b:v",
            target_bitrate,
            "-maxrate",
            max_bitrate,
            "-bufsize",
            buffer_size,
            "-spatial-aq",
            "1",
            "-temporal-aq",
            "1",
            "-aq-strength",
            "8",
            "-multipass",
            "fullres",
            "-b_ref_mode",
            "middle",
            "-g",
            str(fps // 2),
            "-bf",
            "2",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-colorspace",
            "bt709",
            "-color_range",
            "tv",
            "-tag:v",
            "hvc1",
            "-c:a",
            "aac",
            "-b:a",
            "384k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-t",
            f"{audio_duration:.6f}",
            "-movflags",
            "+faststart",
            "-progress",
            "pipe:1",
            "-nostats",
            output,
        ]
        self._events.put(("status", f"Etapa 3/3 — finalizando em 8K/{fps} com bitrate alto…"))
        self._run_ffmpeg(
            command_final,
            audio_duration,
            progress_base + remaining * 0.40,
            remaining * 0.60,
        )
        if self._cancelled:
            raise InterruptedError

    def _verify_and_finish(self, output: str, audio_duration: float, fps: int) -> None:
        final_info = probe_media(output)
        final_duration = media_duration(final_info)
        final_w, final_h = first_video_size(final_info)
        final_fps = first_video_fps(final_info)
        if final_w != WIDTH or final_h != HEIGHT:
            raise RuntimeError(f"A verificação encontrou resolução inesperada: {final_w}×{final_h}.")
        if abs(final_fps - fps) > 0.01:
            raise RuntimeError(f"A verificação encontrou {final_fps:.2f} fps em vez de {fps} fps.")
        if abs(final_duration - audio_duration) > 0.25:
            raise RuntimeError("A duração final não corresponde à música.")
        size_gb = Path(output).stat().st_size / (1024 ** 3)
        self._events.put(("done", output, final_duration, size_gb, fps))

    def _run_ffmpeg(self, command: list[str], duration: float, base: float, weight: float) -> None:
        recent = deque(maxlen=30)
        self._process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
        assert self._process.stdout is not None
        for raw_line in self._process.stdout:
            line = raw_line.strip()
            if line:
                recent.append(line)
            if line.startswith("out_time="):
                value = line.split("=", 1)[1]
                try:
                    hours, minutes, seconds = value.split(":")
                    elapsed = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                    fraction = min(1.0, elapsed / duration)
                    self._events.put(("progress", base + weight * fraction))
                except (ValueError, ZeroDivisionError):
                    pass

        return_code = self._process.wait()
        if self._cancelled:
            raise InterruptedError
        if return_code != 0:
            useful = "\n".join(recent)
            raise RuntimeError(f"A conversão falhou.\n\n{useful}" if useful else "A conversão falhou sem detalhes.")

    def _cancel(self) -> None:
        if not self._busy:
            return
        self._cancelled = True
        self.status.set("Cancelando…")
        process = self._process
        if process and process.poll() is None:
            process.terminate()

    def _poll_events(self) -> None:
        try:
            while True:
                event = self._events.get_nowait()
                kind = event[0]
                if kind == "progress":
                    value = float(event[1])
                    self.bar["value"] = value
                    self.progress.set(f"{value:.0f}%")
                elif kind == "status":
                    self.status.set(event[1])
                elif kind == "detail":
                    self.detail.set(event[1])
                elif kind == "done":
                    _, output, duration, size_gb, fps = event
                    self.bar["value"] = 100
                    self.progress.set("100%")
                    self.status.set("Vídeo concluído e verificado.")
                    self.detail.set(f"8K/{fps} fps • duração {format_time(duration)} • tamanho {size_gb:.2f} GB.")
                    self._set_busy(False)
                    messagebox.showinfo(APP_TITLE, f"Vídeo criado com sucesso:\n\n{output}")
                elif kind == "cancelled":
                    self.status.set("Conversão cancelada.")
                    self.detail.set("O master temporário foi removido.")
                    self._set_busy(False)
                elif kind == "error":
                    self.status.set("Não foi possível criar o vídeo.")
                    self.detail.set("Confira a mensagem de erro.")
                    self._set_busy(False)
                    messagebox.showerror(APP_TITLE, event[1])
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _on_close(self) -> None:
        if self._busy:
            if not messagebox.askyesno(APP_TITLE, "Existe uma conversão em andamento. Deseja cancelar e sair?"):
                return
            self._cancel()
        self.root.destroy()


def main() -> None:
    root = Tk()
    try:
        ttk.Style().theme_use("vista")
    except Exception:
        pass
    LoopMusicApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
