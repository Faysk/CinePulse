from pathlib import Path


path = Path("src/cinepulse/studio.py")
text = path.read_text(encoding="utf-8")

import_anchor = "from .rife_engine import RifePaths, build_command as build_rife_command, target_frame_count\n"
import_insert = (
    "from .rife_engine import RifePaths, build_command as build_rife_command, target_frame_count\n"
    "from .pipeline_budget import derive_pipeline_budget\n"
    "from .pipeline_runtime import measure_resource_headroom\n"
)
if "from .pipeline_runtime import measure_resource_headroom" not in text:
    if import_anchor not in text:
        raise SystemExit("H4 import anchor not found")
    text = text.replace(import_anchor, import_insert, 1)

budget_anchor = (
    '            machine_mode = "dedicated" if settings.cpu_threads >= dedicated_threshold else "balanced"\n'
    '            cpu_tuning = CpuTuningStore(PATHS.cache / "hardware" / "cpu-tuning.json")\n'
)
budget_block = (
    '            machine_mode = "dedicated" if settings.cpu_threads >= dedicated_threshold else "balanced"\n'
    '            cpu_tuning = CpuTuningStore(PATHS.cache / "hardware" / "cpu-tuning.json")\n'
    '\n'
    '            neural_steps_active = bool(\n'
    '                render_plan.step("enhancement").attempts\n'
    '                or render_plan.step("rife_base").runs\n'
    '                or render_plan.step("rife_final").attempts\n'
    '            )\n'
    '            neural_headroom = measure_resource_headroom(\n'
    '                job_dir, gpu_index=0, probe_write=neural_steps_active, probe_size_mb=32\n'
    '            )\n'
    '            h4_common = dict(\n'
    '                ram_available_gb=neural_headroom.ram_available_gb,\n'
    '                vram_free_mb=neural_headroom.vram_free_mb,\n'
    '                scratch_free_gb=neural_headroom.scratch_free_gb,\n'
    '                scratch_write_mbps=neural_headroom.scratch_write_mbps,\n'
    '                dedicated=(machine_mode == "dedicated"),\n'
    '            )\n'
    '            realesrgan_budget = derive_pipeline_budget("realesrgan", **h4_common)\n'
    '            rife_budget = derive_pipeline_budget("rife", **h4_common)\n'
    '            self._log(\n'
    '                "H4 HEADROOM: "\n'
    '                f"RAM={neural_headroom.ram_available_gb if neural_headroom.ram_available_gb is not None else \"n/a\"} GiB • "\n'
    '                f"VRAM livre={neural_headroom.vram_free_mb if neural_headroom.vram_free_mb is not None else \"n/a\"} MiB • "\n'
    '                f"scratch livre={neural_headroom.scratch_free_gb:.2f} GiB • "\n'
    '                f"write={neural_headroom.scratch_write_mbps if neural_headroom.scratch_write_mbps is not None else \"n/a\"} MB/s • "\n'
    '                f"probe={neural_headroom.probe_bytes / (1024 ** 2):.0f} MiB"\n'
    '            )\n'
    '            self._log(f"H4 Real-ESRGAN budget: {realesrgan_budget.reason}")\n'
    '            self._log(f"H4 RIFE budget: {rife_budget.reason}")\n'
)
if "H4 HEADROOM:" not in text:
    if budget_anchor not in text:
        raise SystemExit("H4 budget insertion anchor not found")
    text = text.replace(budget_anchor, budget_block, 1)

enhance_signature = (
    "        cpu_threads: int, base: float, weight: float, *, cache_source_video: str | None = None,\n"
    "        cache_quota_gb: float = 50.0,\n"
    "    ) -> tuple[str, int, int]:\n"
)
enhance_new_signature = (
    "        cpu_threads: int, base: float, weight: float, *, cache_source_video: str | None = None,\n"
    "        cache_quota_gb: float = 50.0, chunk_budget_gb: float = 4.0,\n"
    "    ) -> tuple[str, int, int]:\n"
)
if "cache_quota_gb: float = 50.0, chunk_budget_gb:" not in text:
    if enhance_signature not in text:
        raise SystemExit("Real-ESRGAN signature anchor not found")
    text = text.replace(enhance_signature, enhance_new_signature, 1)

enhance_chunk = (
    "        chunk_frames = choose_chunk_frames(\n"
    "            FrameSpec(source_w, source_h, source_fps, \"RGBA/PNG\"),\n"
    "            FrameSpec(source_w * 2, source_h * 2, source_fps, \"RGBA/PNG\"),\n"
    "        )\n"
)
enhance_chunk_new = (
    "        chunk_frames = choose_chunk_frames(\n"
    "            FrameSpec(source_w, source_h, source_fps, \"RGBA/PNG\"),\n"
    "            FrameSpec(source_w * 2, source_h * 2, source_fps, \"RGBA/PNG\"),\n"
    "            budget_gb=max(0.5, float(chunk_budget_gb)),\n"
    "        )\n"
)
if enhance_chunk in text:
    text = text.replace(enhance_chunk, enhance_chunk_new, 1)

rife_signature = (
    "        *,\n"
    "        color_plan: ColorPipeline,\n"
    "    ) -> str:\n"
)
rife_new_signature = (
    "        *,\n"
    "        color_plan: ColorPipeline,\n"
    "        chunk_budget_gb: float = 4.0,\n"
    "    ) -> str:\n"
)
if "color_plan: ColorPipeline,\n        chunk_budget_gb: float = 4.0," not in text:
    if rife_signature not in text:
        raise SystemExit("RIFE signature anchor not found")
    text = text.replace(rife_signature, rife_new_signature, 1)

rife_chunk = (
    "        chunk_frames = choose_chunk_frames(\n"
    "            FrameSpec(frame_w, frame_h, source_fps, \"RGBA/PNG\"),\n"
    "            FrameSpec(frame_w, frame_h, target_fps, \"RGBA/PNG\"),\n"
    "            output_frames_per_input=ratio,\n"
    "        )\n"
)
rife_chunk_new = (
    "        chunk_frames = choose_chunk_frames(\n"
    "            FrameSpec(frame_w, frame_h, source_fps, \"RGBA/PNG\"),\n"
    "            FrameSpec(frame_w, frame_h, target_fps, \"RGBA/PNG\"),\n"
    "            budget_gb=max(0.5, float(chunk_budget_gb)),\n"
    "            output_frames_per_input=ratio,\n"
    "        )\n"
)
if rife_chunk in text:
    text = text.replace(rife_chunk, rife_chunk_new, 1)


def inject_call_kwarg(source: str, marker: str, keyword_line: str) -> tuple[str, int]:
    cursor = 0
    touched = 0
    calls = 0
    while True:
        start = source.find(marker, cursor)
        if start < 0:
            break
        calls += 1
        depth = 0
        close = None
        index = start + len(marker) - 1
        while index < len(source):
            char = source[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    close = index
                    break
            index += 1
        if close is None:
            raise SystemExit(f"unclosed call for {marker}")
        call = source[start : close + 1]
        if "chunk_budget_gb=" not in call:
            line_start = source.rfind("\n", start, close) + 1
            close_prefix = source[line_start:close]
            indent = close_prefix[: len(close_prefix) - len(close_prefix.lstrip())]
            insertion = indent + "    " + keyword_line + "\n"
            source = source[:close] + insertion + source[close:]
            close += len(insertion)
            touched += 1
        cursor = close + 1
    if calls == 0:
        raise SystemExit(f"no calls found for {marker}")
    return source, touched


text, _ = inject_call_kwarg(
    text,
    "self._enhance_clip_ai(",
    "chunk_budget_gb=realesrgan_budget.chunk_budget_gb,",
)
text, _ = inject_call_kwarg(
    text,
    "self._interpolate_rife(",
    "chunk_budget_gb=rife_budget.chunk_budget_gb,",
)

path.write_text(text, encoding="utf-8", newline="\n")
