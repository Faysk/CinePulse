from __future__ import annotations

"""Physical H5 resident decode/scale/NVENC equivalence benchmark.

The CPU baseline and CUDA candidate use the same NvencContract. Therefore the
only variable is how frames reach the encoder. The script records one exact
hardware/driver/FFmpeg/source/geometry/color/encoder contract and never grants a
generic NVENC PASS.
"""

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from cinepulse.gpu_encode import NvencContract, ResidentEncodeEvidence, ResidentEncodeKey, ResidentEncodeStore
from cinepulse.gpu_media import detect_gpu_media_capabilities
from cinepulse.hardware import detect_hardware
from cinepulse.media_profile import ColorProfile

PSNR_RE = re.compile(r"average:([0-9]+(?:\.[0-9]+)?|inf)", re.I)
SSIM_RE = re.compile(r"All:([0-9]+(?:\.[0-9]+)?)", re.I)


def run(command: list[str], timeout: float, capture: bool = False) -> tuple[float, str]:
    started = time.perf_counter()
    result = subprocess.run(command, stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                            timeout=max(1.0, timeout), check=False)
    elapsed = max(0.000001, time.perf_counter() - started)
    text = (result.stdout or "") + "\n" + (result.stderr or "")
    if result.returncode:
        raise RuntimeError("FFmpeg failed:\n" + "\n".join(text.splitlines()[-30:]))
    return elapsed, text


def probe(ffprobe: str, path: Path) -> dict:
    result = subprocess.run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-count_frames", "-of", "json", str(path)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    return json.loads(result.stdout)


def video(payload: dict) -> dict:
    return next((s for s in payload.get("streams", []) if s.get("codec_type") == "video"), {})


def audio(payload: dict) -> dict:
    return next((s for s in payload.get("streams", []) if s.get("codec_type") == "audio"), {})


def frames(stream: dict) -> int | None:
    for name in ("nb_read_frames", "nb_frames"):
        value = stream.get(name)
        if value not in (None, "", "N/A"):
            try: return int(value)
            except (TypeError, ValueError): pass
    return None


def duration(payload: dict) -> float | None:
    try: return float(payload.get("format", {}).get("duration"))
    except (TypeError, ValueError): return None


def signature(stream: dict) -> tuple[object, ...]:
    return tuple(stream.get(name) for name in (
        "width", "height", "pix_fmt", "color_range", "color_space", "color_transfer", "color_primaries"
    ))


def metric(ffmpeg: str, baseline: Path, candidate: Path, name: str, timeout: float) -> float:
    _elapsed, text = run([ffmpeg, "-hide_banner", "-nostdin", "-i", str(baseline), "-i", str(candidate),
                          "-lavfi", f"[0:v:0][1:v:0]{name}", "-an", "-f", "null", "-"], timeout, True)
    match = (PSNR_RE if name == "psnr" else SSIM_RE).search(text)
    if not match: raise RuntimeError(f"could not parse {name}")
    raw = match.group(1).lower()
    return 999.0 if raw == "inf" else float(raw)


def color_args(profile: ColorProfile) -> list[str]:
    return ["-color_primaries", profile.primaries, "-color_trc", profile.transfer,
            "-colorspace", profile.space, "-color_range", "pc" if profile.range in {"pc", "full"} else "tv"]


def baseline_command(ffmpeg: str, source: Path, output: Path, *, contract: NvencContract, profile: ColorProfile,
                     width: int, height: int, seek: float, clip: float) -> list[str]:
    command = [ffmpeg, "-y", "-hide_banner", "-nostdin"]
    if seek > 0: command += ["-ss", f"{seek:.6f}"]
    command += ["-i", str(source)]
    if clip > 0: command += ["-t", f"{clip:.6f}"]
    filters = []
    if width > 0 and height > 0:
        filters.append(f"zscale=w={width}:h={height}:dither=error_diffusion")
    filters.append(f"format={contract.pixel_format}")
    command += ["-map", "0:v:0", "-map", "0:a?", "-vf", ",".join(filters)] + contract.ffmpeg_args()
    return command + color_args(profile) + ["-c:a", "copy", str(output)]


def candidate_command(ffmpeg: str, source: Path, output: Path, *, decoder: str, scaler: str | None,
                      contract: NvencContract, profile: ColorProfile, width: int, height: int,
                      seek: float, clip: float, gpu_index: int) -> list[str]:
    command = [ffmpeg, "-y", "-hide_banner", "-nostdin", "-hwaccel", "cuda", "-hwaccel_device", str(gpu_index),
               "-hwaccel_output_format", "cuda", "-c:v", decoder]
    if seek > 0: command += ["-ss", f"{seek:.6f}"]
    command += ["-i", str(source)]
    if clip > 0: command += ["-t", f"{clip:.6f}"]
    command += ["-map", "0:v:0", "-map", "0:a?"]
    if scaler:
        command += ["-vf", f"{scaler}=w={width}:h={height}:format={contract.pixel_format}"]
    # With no scaler frames stay CUDA-resident and NVENC consumes them directly.
    command += contract.ffmpeg_args() + color_args(profile) + ["-c:a", "copy", str(output)]
    return command


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CinePulse H5 resident NVDEC/CUDA/NVENC benchmark")
    p.add_argument("--input", type=Path, required=True); p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--ffmpeg", default="ffmpeg"); p.add_argument("--ffprobe", default="ffprobe")
    p.add_argument("--encoder", choices=("h264_nvenc", "hevc_nvenc", "av1_nvenc"), default="h264_nvenc")
    p.add_argument("--preset", default="p7"); p.add_argument("--rc", choices=("constqp", "vbr", "cbr"), default="vbr")
    p.add_argument("--pix-fmt", default="yuv420p"); p.add_argument("--profile", default="")
    p.add_argument("--cq", type=int, default=18); p.add_argument("--qp", type=int)
    p.add_argument("--bitrate-kbps", type=int, default=30000); p.add_argument("--maxrate-kbps", type=int, default=45000)
    p.add_argument("--bufsize-kbps", type=int, default=90000); p.add_argument("--lookahead", type=int, default=16); p.add_argument("--bframes", type=int, default=3)
    p.add_argument("--width", type=int, default=0); p.add_argument("--height", type=int, default=0); p.add_argument("--gpu-index", type=int, default=0)
    p.add_argument("--seek-seconds", type=float, default=1.0); p.add_argument("--seek-clip-seconds", type=float, default=1.0)
    p.add_argument("--timeout", type=float, default=1800.0)
    return p


def main() -> int:
    args = parser().parse_args(); ffmpeg = shutil.which(args.ffmpeg) or ""; ffprobe = shutil.which(args.ffprobe) or ""
    if not ffmpeg or not ffprobe: raise SystemExit("FFmpeg/FFprobe required")
    source_probe = probe(ffprobe, args.input); sv = video(source_probe)
    if not sv: raise SystemExit("video stream required")
    profile = ColorProfile.from_probe({"streams": [sv]})
    if profile.hdr or any(v in {"", "unknown", "unspecified", "reserved"} for v in (profile.primaries, profile.transfer, profile.space, profile.range)):
        raise SystemExit("initial resident encode envelope requires known SDR color metadata")
    caps = detect_gpu_media_capabilities(ffmpeg); codec = str(sv.get("codec_name") or "")
    decoder = caps.decoder_for(codec)
    if not decoder or args.encoder not in caps.encoders: raise SystemExit("required NVDEC/NVENC capability unavailable")
    source_w, source_h = int(sv.get("width") or 0), int(sv.get("height") or 0)
    width, height = (args.width or source_w), (args.height or source_h)
    do_scale = (width, height) != (source_w, source_h)
    scaler = caps.cuda_scale if do_scale else None
    if do_scale and not scaler: raise SystemExit("CUDA scaler unavailable for requested geometry")
    contract = NvencContract(args.encoder, args.preset, args.rc, args.pix_fmt, args.profile,
                             args.cq, args.qp, args.bitrate_kbps, args.maxrate_kbps, args.bufsize_kbps, args.lookahead, args.bframes)
    hardware = detect_hardware()
    if not hardware.gpu: raise SystemExit("NVIDIA GPU required")
    key = ResidentEncodeKey(hardware.gpu, hardware.driver or "unknown-driver", caps.fingerprint, codec,
                            source_w, source_h, width, height, profile.pixel_format, profile.primaries,
                            profile.transfer, profile.space, profile.range, scaler or "none", contract.token())
    with tempfile.TemporaryDirectory(prefix="cinepulse-h5-resident-") as tmp:
        root = Path(tmp); baseline = root/"baseline.mkv"; candidate = root/"candidate.mkv"
        bsec,_ = run(baseline_command(ffmpeg,args.input,baseline,contract=contract,profile=profile,width=width,height=height,seek=0,clip=0), args.timeout)
        csec,_ = run(candidate_command(ffmpeg,args.input,candidate,decoder=decoder,scaler=scaler,contract=contract,profile=profile,width=width,height=height,seek=0,clip=0,gpu_index=args.gpu_index), args.timeout)
        bp,cp=probe(ffprobe,baseline),probe(ffprobe,candidate); bv,cv=video(bp),video(cp)
        frame_ok=frames(bv) is not None and frames(bv)==frames(cv); metadata_ok=signature(bv)==signature(cv)
        db,dc=duration(bp),duration(cp); audio_ok=db is not None and dc is not None and abs(db-dc)<=0.020 and bool(audio(source_probe))==bool(audio(bp))==bool(audio(cp))
        psnr=metric(ffmpeg,baseline,candidate,"psnr",args.timeout); ssim=metric(ffmpeg,baseline,candidate,"ssim",args.timeout)
        sb=root/"seek-baseline.mkv"; sc=root/"seek-candidate.mkv"; seek=max(.001,args.seek_seconds); clip=max(.05,args.seek_clip_seconds)
        run(baseline_command(ffmpeg,args.input,sb,contract=contract,profile=profile,width=width,height=height,seek=seek,clip=clip),args.timeout)
        run(candidate_command(ffmpeg,args.input,sc,decoder=decoder,scaler=scaler,contract=contract,profile=profile,width=width,height=height,seek=seek,clip=clip,gpu_index=args.gpu_index),args.timeout)
        spb,spc=probe(ffprobe,sb),probe(ffprobe,sc); seek_ok=frames(video(spb))==frames(video(spc)) and signature(video(spb))==signature(video(spc)) and metric(ffmpeg,sb,sc,"psnr",args.timeout)>=55 and metric(ffmpeg,sb,sc,"ssim",args.timeout)>=.999
        decode_ok=bool(video(bp)) and bool(video(cp))
        ev=ResidentEncodeEvidence(bsec,csec,psnr,ssim,frame_ok,metadata_ok,audio_ok,seek_ok,decode_ok,baseline.stat().st_size,candidate.stat().st_size)
        recorded=ResidentEncodeStore(args.cache).record(key,contract,ev)
    print(json.dumps({"physical_acceptance":"exact-evidence-recorded-not-global-pass" if recorded else "rejected","hardware":hardware.as_dict(),"decoder":decoder,"scaler":scaler,"contract":contract.token(),"speedup":ev.speedup,"psnr_db":psnr,"ssim":ssim,"seek_alignment_ok":seek_ok,"accepted":ev.accepted,"cache_key":key.token()},indent=2,ensure_ascii=False))
    return 0 if recorded else 2

if __name__ == "__main__": raise SystemExit(main())
