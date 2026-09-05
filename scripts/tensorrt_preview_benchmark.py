from __future__ import annotations

"""Physical H7 benchmark for an externally installed TensorRT Preview runner.

The caller supplies a lossless PNG sequence produced by the already-proven NCNN
baseline plus its measured wall time. TensorRT version is taken only from the
runner's side-effect-free protocol response. The script installs/downloads
nothing and never grants a global TensorRT PASS.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from cinepulse.rife_safe_runner import validate_png, validate_png_sequence
from cinepulse.tensorrt_preview import TensorRtEvidence, TensorRtKey, TensorRtPreviewStore, build_external_command, probe_external_backend
from cinepulse.hardware import detect_hardware


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CinePulse Preview TensorRT vs proven NCNN benchmark")
    p.add_argument("--runner", required=True); p.add_argument("--model", choices=("realesrgan", "rife"), required=True)
    p.add_argument("--model-path", type=Path, required=True); p.add_argument("--input", type=Path, required=True)
    p.add_argument("--baseline", type=Path, required=True, help="Approved NCNN lossless PNG sequence")
    p.add_argument("--baseline-seconds", type=float, required=True); p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--precision", choices=("fp32", "fp16"), default="fp32"); p.add_argument("--ffmpeg", default="ffmpeg")
    p.add_argument("--timeout", type=float, default=1800.0)
    return p


def model_fingerprint(path: Path) -> str:
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024): digest.update(chunk)
        return digest.hexdigest()[:24]
    if path.is_dir():
        rows=[]
        for item in sorted(path.rglob("*")):
            if item.is_file():
                stat=item.stat(); rows.append(f"{item.relative_to(path)}:{stat.st_size}:{stat.st_mtime_ns}")
        return hashlib.sha256("\n".join(rows).encode()).hexdigest()[:24]
    raise FileNotFoundError(path)


def metric(ffmpeg: str, baseline: Path, candidate: Path, name: str, timeout: float) -> float:
    result=subprocess.run([ffmpeg,"-hide_banner","-nostdin","-framerate","1","-i",str(baseline/"%08d.png"),"-framerate","1","-i",str(candidate/"%08d.png"),"-lavfi",f"[0:v:0][1:v:0]{name}","-an","-f","null","-"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8",errors="replace",timeout=max(1.0,timeout),check=False)
    if result.returncode: raise RuntimeError(result.stderr[-3000:])
    marker="average:" if name=="psnr" else "All:"
    values=[]
    for line in result.stderr.splitlines():
        if marker in line:
            raw=line.split(marker,1)[1].strip().split()[0]
            try: values.append(999.0 if raw.lower()=="inf" else float(raw))
            except ValueError: pass
    if not values: raise RuntimeError(f"could not parse {name}")
    return values[-1]


def black_frame_ok(ffmpeg: str, frames: list[Path]) -> bool:
    selected=[frames[0],frames[len(frames)//2],frames[-1]] if frames else []
    for frame in dict.fromkeys(selected):
        result=subprocess.run([ffmpeg,"-hide_banner","-loglevel","error","-i",str(frame),"-vf","scale=64:36:flags=area,format=gray","-frames:v","1","-f","rawvideo","pipe:1"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,check=False)
        if result.returncode or len(result.stdout)!=64*36 or max(result.stdout,default=0)<=1: return False
    return True


def main() -> int:
    args=parser().parse_args(); ffmpeg=shutil.which(args.ffmpeg) or (str(args.ffmpeg) if Path(args.ffmpeg).is_file() else "")
    if not ffmpeg: raise SystemExit("FFmpeg required for quality gates")
    backend=probe_external_backend(args.runner)
    if backend is None: raise SystemExit("external runner did not satisfy cinepulse-tensorrt-preview-v1 with runtime version")
    baseline_frames=validate_png_sequence(args.baseline,len(list(args.baseline.glob("*.png"))))
    if not baseline_frames: raise SystemExit("approved NCNN baseline sequence is empty")
    width,height=validate_png(baseline_frames[0]); hardware=detect_hardware()
    if not hardware.gpu: raise SystemExit("NVIDIA GPU required; no physical TensorRT evidence recorded")
    key=TensorRtKey(hardware.gpu,hardware.driver or "unknown-driver",backend.tensorrt_version,backend.fingerprint,args.model,model_fingerprint(args.model_path),width,height,args.precision)
    with tempfile.TemporaryDirectory(prefix="cinepulse-h7-") as temporary:
        output=Path(temporary)/"candidate"; output.mkdir()
        command=build_external_command(backend,model=args.model,model_path=args.model_path,input_path=args.input,output_path=output,width=width,height=height,precision=args.precision)
        started=time.perf_counter(); result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace",timeout=max(1.0,args.timeout),check=False); candidate_seconds=max(.000001,time.perf_counter()-started)
        text=result.stdout or ""; oom=any(t in text.lower() for t in ("out of memory","oom","failed to allocate","cuda_error_out_of_memory"))
        integrity=frame_ok=black=False; psnr=ssim=0.0
        if result.returncode==0:
            try:
                frames=validate_png_sequence(output,len(baseline_frames)); integrity=True; frame_ok=len(frames)==len(baseline_frames); black=black_frame_ok(ffmpeg,frames); psnr=metric(ffmpeg,args.baseline,output,"psnr",args.timeout); ssim=metric(ffmpeg,args.baseline,output,"ssim",args.timeout)
            except (OSError,ValueError,RuntimeError): integrity=False
        evidence=TensorRtEvidence(max(0.0,args.baseline_seconds),candidate_seconds,integrity,frame_ok,black,frame_ok and integrity,psnr,ssim,None,oom)
        recorded=TensorRtPreviewStore(args.cache).record(key,backend,evidence)
    print(json.dumps({"physical_acceptance":"exact-preview-evidence-recorded-not-global-pass" if recorded else "rejected","preview_only":True,"stable_fallback":"NCNN Vulkan","hardware":hardware.as_dict(),"backend":{"version":backend.version,"tensorrt_version":backend.tensorrt_version,"license_id":backend.license_id,"fingerprint":backend.fingerprint},"model":args.model,"precision":args.precision,"resolution":[width,height],"speedup":evidence.speedup,"psnr_db":psnr,"ssim":ssim,"accepted":evidence.accepted,"cache_key":key.token()},ensure_ascii=False,indent=2))
    return 0 if recorded else 2

if __name__=="__main__": raise SystemExit(main())
