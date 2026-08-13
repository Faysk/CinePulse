from __future__ import annotations

import os
import queue
import shutil
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from tkinter import Tk

from cinepulse.color_pipeline import build_color_pipeline
from cinepulse.loop_engine import first_video_fps, first_video_size, media_duration, probe_media
from cinepulse.media_profile import ColorProfile
from cinepulse import studio
from cinepulse.studio import VideoOptimizerStudio

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True)


def write_fake_realesrgan(path: Path) -> None:
    script = """#!/usr/bin/env python3
import pathlib, subprocess, sys
args=sys.argv[1:]
def val(flag): return args[args.index(flag)+1]
inp=pathlib.Path(val('-i')); out=pathlib.Path(val('-o')); out.mkdir(parents=True, exist_ok=True)
for src in sorted(inp.glob('frame*.png')):
    dst=out/src.name
    subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(src),'-vf','scale=iw*2:ih*2:flags=neighbor',str(dst)],check=True)
    print(dst.name, flush=True)
"""
    if os.name == "nt":
        script_path = path.with_suffix(".py")
        script_path.write_text(script, encoding="utf-8")
        path.write_text(f'@echo off\n"{sys.executable}" "{script_path}" %*\n', encoding="utf-8")
    else:
        path.write_text(script, encoding="utf-8")
        path.chmod(0o755)


def write_fake_rife(path: Path) -> None:
    script = """#!/usr/bin/env python3
import pathlib, shutil, sys
args=sys.argv[1:]
def val(flag): return args[args.index(flag)+1]
inp=pathlib.Path(val('-i')); out=pathlib.Path(val('-o')); count=int(val('-n'))
out.mkdir(parents=True, exist_ok=True)
sources=sorted(inp.glob('*.png'))
if not sources: raise SystemExit(2)
for i in range(count):
    src=sources[min(len(sources)-1, int(i*len(sources)/max(1,count)))]
    shutil.copy2(src, out/f'{i:08d}.png')
    print(i, flush=True)
"""
    if os.name == "nt":
        script_path = path.with_suffix(".py")
        script_path.write_text(script, encoding="utf-8")
        path.write_text(f'@echo off\n"{sys.executable}" "{script_path}" %*\n', encoding="utf-8")
    else:
        path.write_text(script, encoding="utf-8")
        path.chmod(0o755)


def drain_logs(app: VideoOptimizerStudio) -> list[str]:
    lines=[]
    while True:
        try:
            event=app._events.get_nowait()
        except queue.Empty:
            break
        if event[0]=='log': lines.append(event[1])
    return lines


def main() -> None:
    root_dir=Path(tempfile.mkdtemp(prefix='cinepulse_neural_chunks_'))
    source=root_dir/'source.mp4'
    run([FFMPEG,'-y','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=64x36:rate=10','-t','1.3','-c:v','libx264','-pix_fmt','yuv420p',str(source)])
    fake_dir=root_dir/'fake'; fake_dir.mkdir()
    executable_suffix = '.cmd' if os.name == 'nt' else ''
    fake_ai=fake_dir/f'realesrgan-ncnn-vulkan{executable_suffix}'; write_fake_realesrgan(fake_ai)
    fake_models=fake_dir/'models'; fake_models.mkdir(); (fake_models/'realesr-animevideov3-x2.bin').write_bytes(b'x')
    fake_rife=fake_dir/f'rife-ncnn-vulkan{executable_suffix}'; write_fake_rife(fake_rife)
    fake_rife_model=fake_dir/'rife-v4.6'; fake_rife_model.mkdir(); (fake_rife_model/'flownet.param').write_bytes(b'x')
    scratch=root_dir/'scratch'; scratch.mkdir()
    cache=root_dir/'cache'; cache.mkdir()

    original=(studio.REAL_ESRGAN, studio.REAL_ESRGAN_DIR, studio.REAL_ESRGAN_MODELS, studio.RIFE_EXE, studio.RIFE_MODEL, studio.CACHE_DIR, studio.PATHS, studio.choose_chunk_frames)
    studio.REAL_ESRGAN=fake_ai
    studio.REAL_ESRGAN_DIR=fake_dir
    studio.REAL_ESRGAN_MODELS=fake_models
    studio.RIFE_EXE=fake_rife
    studio.RIFE_MODEL=fake_rife_model
    studio.CACHE_DIR=cache/'ai'
    studio.PATHS=replace(studio.PATHS, cache=cache)
    studio.choose_chunk_frames=lambda *args, **kwargs: 5

    tk=Tk(); tk.withdraw(); app=VideoOptimizerStudio(tk)
    try:
        temp_paths=[]; temp_dirs=[]
        enhanced,w,h=app._enhance_clip_ai(
            str(source), scratch, 0.0, 1.3, 10.0, 64, 36,
            temp_paths, temp_dirs, 2, 0.0, 50.0,
            cache_source_video=str(source), cache_quota_gb=1.0,
        )
        info=probe_media(enhanced)
        if first_video_size(info)!=(128,72):
            raise RuntimeError(f'AI chunk output size inesperado: {first_video_size(info)}')
        logs=drain_logs(app)
        if not any('lotes de até 5' in line for line in logs):
            raise RuntimeError('AI não registrou política de chunks.')
        for d in temp_dirs:
            # The chunk root survives until worker-finally, but no PNG chunk
            # directories or segment videos may remain after assembly.
            if list(d.glob('chunk_*')) or list(d.glob('segment_*.mkv')):
                raise RuntimeError(f'AI deixou workset de chunk materializado: {d}')

        source_profile=ColorProfile.from_probe(probe_media(str(source)))
        color=build_color_pipeline(
            source_profile, effects_active=False, transition_active=False,
            enhancement_mode='preserve', rife_active=True,
        )
        temp_paths2=[]
        interpolated=app._interpolate_rife(
            str(source), scratch, 0.0, 1.3, 10.0, 20.0, True, 2,
            temp_paths2, 0.0, 50.0, color_plan=color,
        )
        rife_info=probe_media(interpolated)
        fps=first_video_fps(rife_info)
        if abs(fps-20.0)>0.01:
            raise RuntimeError(f'RIFE chunk output FPS inesperado: {fps}')
        if abs(media_duration(rife_info)-1.3)>0.15:
            raise RuntimeError(f'RIFE chunk duração inesperada: {media_duration(rife_info)}')
        logs=drain_logs(app)
        if not any('STORAGE RIFE' in line and 'lotes de até 5' in line for line in logs):
            raise RuntimeError('RIFE não registrou política de chunks.')
        if list(scratch.glob('rife_*')):
            raise RuntimeError('RIFE deixou diretório PNG após o processamento.')
        print('CINEPULSE_NEURAL_CHUNKS_OK ai=13frames/5 rife=13->26/5')
    finally:
        tk.destroy()
        (studio.REAL_ESRGAN, studio.REAL_ESRGAN_DIR, studio.REAL_ESRGAN_MODELS, studio.RIFE_EXE, studio.RIFE_MODEL, studio.CACHE_DIR, studio.PATHS, studio.choose_chunk_frames)=original
        shutil.rmtree(root_dir, ignore_errors=True)


if __name__=='__main__':
    main()
