from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"{label}: expected one anchor, got {text.count(old)}")
    return text.replace(old, new, 1)


def patch_telemetry() -> None:
    path = Path("src/cinepulse/hardware_telemetry.py")
    text = path.read_text(encoding="utf-8")
    anchor = '''    def stop(self, *, status: str = "finished") -> dict[str, Any]:
'''
    addition = '''    def latest_sample(self) -> HardwareSample | None:
        """Return the newest observational sample without stopping telemetry."""
        with self._lock:
            return self._samples[-1] if self._samples else None

    def stop(self, *, status: str = "finished") -> dict[str, Any]:
'''
    text = replace_once(text, anchor, addition, "telemetry latest sample")
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_history() -> None:
    path = Path("src/cinepulse/render_history.py")
    text = path.read_text(encoding="utf-8")
    anchor = '''    def write_plan(self, plan: Any) -> Path:
'''
    addition = '''    def latest_hardware_sample(self):
        telemetry = self._telemetry
        if telemetry is None:
            return None
        try:
            return telemetry.latest_sample()
        except Exception:
            return None

    def write_plan(self, plan: Any) -> Path:
'''
    text = replace_once(text, anchor, addition, "history live telemetry")
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_studio() -> None:
    path = Path("src/cinepulse/studio.py")
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        'from collections import deque\n',
        'from collections import deque\nfrom collections.abc import Callable\n',
        "studio Callable import",
    )
    text = replace_once(
        text,
        'from .pipeline_budget import derive_pipeline_budget\n',
        'from .pipeline_budget import derive_pipeline_budget\nfrom .adaptive_runtime import AdaptiveRuntimeController, RuntimePressureDecision\n',
        "studio H5 import",
    )

    h4_anchor = '''            self._log(f"H4 Real-ESRGAN budget: {realesrgan_budget.reason}")
            self._log(f"H4 RIFE budget: {rife_budget.reason}")

            def stage_threads(stage: str, *, gpu_active: bool = False) -> int:
'''
    h5_block = '''            self._log(f"H4 Real-ESRGAN budget: {realesrgan_budget.reason}")
            self._log(f"H4 RIFE budget: {rife_budget.reason}")

            h5_ai_controller = AdaptiveRuntimeController(
                gpu_index=0,
                allow_extract_overlap=realesrgan_budget.overlap_extract,
                allow_pack_overlap=realesrgan_budget.overlap_pack,
            )
            h5_rife_controller = AdaptiveRuntimeController(
                gpu_index=0,
                allow_extract_overlap=(rife_budget.overlap_extract and not settings.use_cpu),
                allow_pack_overlap=False,
            )

            def h5_guard(controller: AdaptiveRuntimeController) -> Callable[[], RuntimePressureDecision]:
                def observe() -> RuntimePressureDecision:
                    previous = controller.level
                    sample = history.latest_hardware_sample() if history is not None else None
                    decision = controller.observe(sample)
                    if decision.level > previous:
                        reason = ", ".join(decision.reasons) or "pressão observada"
                        self._log(
                            f"H5 DOWNSHIFT level={decision.level}: {reason}; "
                            f"chunk={decision.chunk_scale:.2f}x, extract_overlap={decision.allow_extract_overlap}, "
                            f"pack_overlap={decision.allow_pack_overlap}. Qualidade/modelo/FPS permanecem inalterados."
                        )
                    return decision
                return observe

            h5_ai_guard = h5_guard(h5_ai_controller)
            h5_rife_guard = h5_guard(h5_rife_controller)

            def stage_threads(stage: str, *, gpu_active: bool = False) -> int:
'''
    text = replace_once(text, h4_anchor, h5_block, "worker H5 controllers")

    ai_call_anchor = '''                    overlap_extract=realesrgan_budget.overlap_extract,
                    overlap_pack=realesrgan_budget.overlap_pack,
)'''
    ai_call_new = '''                    overlap_extract=realesrgan_budget.overlap_extract,
                    overlap_pack=realesrgan_budget.overlap_pack,
                    runtime_guard=h5_ai_guard,
)'''
    text = replace_once(text, ai_call_anchor, ai_call_new, "AI H5 call")

    rife_call_anchor = '''                        overlap_extract=(rife_budget.overlap_extract and not settings.use_cpu),
)'''
    if text.count(rife_call_anchor) != 2:
        raise SystemExit(f"RIFE H5 call: expected two anchors, got {text.count(rife_call_anchor)}")
    text = text.replace(
        rife_call_anchor,
        '''                        overlap_extract=(rife_budget.overlap_extract and not settings.use_cpu),
                        runtime_guard=h5_rife_guard,
)''',
    )

    ai_sig = '''        cache_quota_gb: float = 50.0, chunk_budget_gb: float = 4.0, overlap_extract: bool = False,
        overlap_pack: bool = False,
    ) -> tuple[str, int, int]:
'''
    ai_sig_new = '''        cache_quota_gb: float = 50.0, chunk_budget_gb: float = 4.0, overlap_extract: bool = False,
        overlap_pack: bool = False,
        runtime_guard: Callable[[], RuntimePressureDecision] | None = None,
    ) -> tuple[str, int, int]:
'''
    text = replace_once(text, ai_sig, ai_sig_new, "AI H5 signature")

    ai_loop = '''            while processed < total_frames:
                if self._cancelled:
                    raise InterruptedError
                count = min(chunk_frames, total_frames - processed)
                chunk_index += 1
'''
    ai_loop_new = '''            while processed < total_frames:
                if self._cancelled:
                    raise InterruptedError
                decision = runtime_guard() if runtime_guard is not None else None
                if decision is not None:
                    if decision.level > 0 and prefetch is not None:
                        prefetched_dir = prefetch[2]
                        task = prefetch[4]
                        task.cancel()
                        try:
                            task.wait(timeout=5.0)
                        except Exception:
                            pass
                        safe_rmtree(prefetched_dir)
                        prefetch = None
                    overlap_extract = overlap_extract and decision.allow_extract_overlap
                    overlap_pack = overlap_pack and decision.allow_pack_overlap
                    active_chunk_frames = decision.limit_chunk_frames(chunk_frames)
                else:
                    active_chunk_frames = chunk_frames
                count = min(active_chunk_frames, total_frames - processed)
                chunk_index += 1
'''
    text = replace_once(text, ai_loop, ai_loop_new, "AI H5 loop")

    rife_sig = '''        chunk_budget_gb: float = 4.0,
        overlap_extract: bool = False,
    ) -> str:
'''
    rife_sig_new = '''        chunk_budget_gb: float = 4.0,
        overlap_extract: bool = False,
        runtime_guard: Callable[[], RuntimePressureDecision] | None = None,
    ) -> str:
'''
    text = replace_once(text, rife_sig, rife_sig_new, "RIFE H5 signature")

    source_count_fn = '''        def source_chunk_count(offset: int) -> int:
            remaining = source_count - offset
            count = min(chunk_frames, remaining)
'''
    source_count_new = '''        def source_chunk_count(offset: int, limit: int | None = None) -> int:
            remaining = source_count - offset
            count = min(max(2, int(limit or chunk_frames)), remaining)
'''
    text = replace_once(text, source_count_fn, source_count_new, "RIFE dynamic chunk helper")

    rife_loop = '''            while processed_source < source_count:
                if self._cancelled:
                    raise InterruptedError
                count = source_chunk_count(processed_source)
                if count < 2:
'''
    rife_loop_new = '''            while processed_source < source_count:
                if self._cancelled:
                    raise InterruptedError
                decision = runtime_guard() if runtime_guard is not None else None
                if decision is not None:
                    if decision.level > 0 and prefetch is not None:
                        prefetched_incoming = prefetch[2]
                        task = prefetch[3]
                        task.cancel()
                        try:
                            task.wait(timeout=5.0)
                        except Exception:
                            pass
                        safe_rmtree(prefetched_incoming)
                        prefetch = None
                    overlap_extract = overlap_extract and decision.allow_extract_overlap
                    active_chunk_frames = decision.limit_chunk_frames(chunk_frames, minimum=2)
                else:
                    active_chunk_frames = chunk_frames
                count = source_chunk_count(processed_source, active_chunk_frames)
                if count < 2:
'''
    text = replace_once(text, rife_loop, rife_loop_new, "RIFE H5 loop")

    next_count = '''                next_count = source_chunk_count(next_processed) if next_processed < source_count else 0
'''
    next_count_new = '''                next_count = source_chunk_count(next_processed, active_chunk_frames) if next_processed < source_count else 0
'''
    text = replace_once(text, next_count, next_count_new, "RIFE H5 prefetch size")

    path.write_text(text, encoding="utf-8", newline="\n")


patch_telemetry()
patch_history()
patch_studio()
print("H5 runtime integration applied")
