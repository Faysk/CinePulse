from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "src" / "cinepulse" / "studio.py"
INTEGRATION_REVISION = 2


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, got {count}")
    return text.replace(old, new, 1)


def integrate(text: str) -> str:
    if "overlay_scene_json: str = \"\"" in text and "visualizer_audio_index" in text:
        return text

    text = replace_once(
        text,
        "from .safe_output import AtomicOutput, RenderJournal, process_alive\n",
        "from .safe_output import AtomicOutput, RenderJournal, process_alive\n"
        "from .overlay_composer import OverlayScene, OverlaySceneError\n"
        "from .overlay_ffmpeg import build_overlay_ffmpeg_plan\n"
        "from .overlay_runtime import has_visualizer as overlay_has_visualizer, summary as overlay_summary, validate_scene_sources\n",
        "overlay imports",
    )
    text = replace_once(
        text,
        "    cache_quota_gb: float = 50.0\n\n\nclass ScrollableTab",
        "    cache_quota_gb: float = 50.0\n"
        "    overlay_scene_json: str = \"\"\n\n\nclass ScrollableTab",
        "RenderSettings overlay field",
    )
    text = replace_once(
        text,
        "        self.visual_preview_position = DoubleVar(value=38.0)\n\n        # Phase 3 — Project workspace state.",
        "        self.visual_preview_position = DoubleVar(value=38.0)\n"
        "        self.overlay_scene = OverlayScene()\n"
        "        self.overlay_scene_json = self.overlay_scene.to_json()\n\n"
        "        # Phase 3 — Project workspace state.",
        "Studio overlay state",
    )
    text = replace_once(
        text,
        "            \"use_stems\": False,\n            \"delivery_profile\": PROFILE_AUTO,\n        }\n        accepted = {field.name for field in fields(RenderSettings)}",
        "            \"use_stems\": False,\n            \"delivery_profile\": PROFILE_AUTO,\n"
        "            \"overlay_scene_json\": OverlayScene().to_json(),\n"
        "        }\n        accepted = {field.name for field in fields(RenderSettings)}",
        "settings defaults",
    )
    text = replace_once(
        text,
        "            \"use_stems\": self.use_stems.get(),\n            \"delivery_profile\": self.delivery_profile.get(),\n        }\n\n    def _apply_selected_preset",
        "            \"use_stems\": self.use_stems.get(),\n            \"delivery_profile\": self.delivery_profile.get(),\n"
        "            \"overlay_scene_json\": getattr(self, \"overlay_scene_json\", OverlayScene().to_json()),\n"
        "        }\n\n    def _apply_selected_preset",
        "preset capture",
    )
    text = replace_once(
        text,
        "        for variable, key in mapping:\n            if key in data:\n                variable.set(data[key])\n",
        "        for variable, key in mapping:\n            if key in data:\n                variable.set(data[key])\n"
        "        if \"overlay_scene_json\" in data:\n"
        "            try:\n"
        "                scene = OverlayScene.from_json(str(data.get(\"overlay_scene_json\") or \"\"))\n"
        "            except OverlaySceneError:\n"
        "                scene = OverlayScene()\n"
        "            self.overlay_scene = scene\n"
        "            self.overlay_scene_json = scene.to_json()\n"
        "            if hasattr(self, \"overlay_composer_view\"):\n"
        "                self.overlay_composer_view.set_scene(scene)\n",
        "preset apply",
    )
    text = replace_once(
        text,
        "            use_stems=self.use_stems.get(),\n            delivery_profile=self.delivery_profile.get(),\n        )\n\n    @staticmethod\n    def _normalized_enhancement_mode",
        "            use_stems=self.use_stems.get(),\n            delivery_profile=self.delivery_profile.get(),\n"
        "            overlay_scene_json=getattr(self, \"overlay_scene_json\", OverlayScene().to_json()),\n"
        "        )\n\n    @staticmethod\n    def _normalized_enhancement_mode",
        "settings capture",
    )
    text = replace_once(
        text,
        "        for variable, value in mapping:\n            variable.set(value)\n        for name, variable in self.effect_vars.items():\n",
        "        for variable, value in mapping:\n            variable.set(value)\n"
        "        try:\n"
        "            scene = OverlayScene.from_json(settings.overlay_scene_json or OverlayScene().to_json())\n"
        "        except OverlaySceneError:\n"
        "            scene = OverlayScene()\n"
        "        self.overlay_scene = scene\n"
        "        self.overlay_scene_json = scene.to_json()\n"
        "        if hasattr(self, \"overlay_composer_view\"):\n"
        "            self.overlay_composer_view.set_scene(scene)\n"
        "        for name, variable in self.effect_vars.items():\n",
        "queue/editor restore",
    )
    text = replace_once(
        text,
        "            else:\n                project_duration = video_duration\n                audio_source = settings.video\n                if settings.effects and not source_has_audio:\n                    raise RuntimeError(\"VFX dinâmicos precisam de áudio. Este vídeo não possui uma faixa de áudio.\")\n            # Phase 3: VFX normalization always sees the full reactive source.\n",
        "            else:\n                project_duration = video_duration\n                audio_source = settings.video\n                if settings.effects and not source_has_audio:\n                    raise RuntimeError(\"VFX dinâmicos precisam de áudio. Este vídeo não possui uma faixa de áudio.\")\n"
        "            try:\n"
        "                overlay_scene = OverlayScene.from_json(settings.overlay_scene_json or OverlayScene().to_json())\n"
        "            except OverlaySceneError as exc:\n"
        "                raise RuntimeError(f\"Overlay Composer: cena persistida inválida: {exc}\") from exc\n"
        "            overlay_validation = validate_scene_sources(\n"
        "                overlay_scene, audio_available=(settings.mode == MODE_MUSIC or source_has_audio),\n"
        "            )\n"
        "            if overlay_validation.errors:\n"
        "                raise RuntimeError(\"Overlay Composer: \" + \" • \".join(overlay_validation.errors))\n"
        "            for warning in overlay_validation.warnings:\n"
        "                self._log(\"OVERLAY WARNING: \" + warning)\n"
        "            if overlay_scene.active_layers:\n"
        "                self._log(f\"OVERLAY Preview: {overlay_summary(overlay_scene)} • {overlay_scene.fingerprint[:12]}\")\n"
        "            # Phase 3: VFX normalization always sees the full reactive source.\n",
        "worker overlay validation",
    )

    old_final = '''            command = [FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error"]
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
'''
    new_final = '''            command = [FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error"]
            if settings.mode == MODE_MUSIC and not effects_active:
                command += ["-stream_loop", "-1"]
            command += ["-i", visual_source]
            next_input_index = 1
            output_audio_index: int | None = None
            if settings.mode == MODE_MUSIC:
                command += ["-i", settings.audio]
                output_audio_index = next_input_index
                next_input_index += 1
            elif settings.preserve_audio and source_has_audio:
                command += ["-i", settings.video]
                output_audio_index = next_input_index
                next_input_index += 1

            if overlay_scene.active_layers:
                visualizer_audio_index: int | None = None
                if overlay_has_visualizer(overlay_scene):
                    visualizer_audio_source = settings.audio if settings.mode == MODE_MUSIC else settings.video
                    command += ["-i", visualizer_audio_source]
                    visualizer_audio_index = next_input_index
                    next_input_index += 1
                overlay_plan = build_overlay_ffmpeg_plan(
                    overlay_scene,
                    canvas_width=target_w,
                    canvas_height=target_h,
                    fps=target_fps,
                    first_asset_input_index=next_input_index,
                    base_video_label="overlay_base",
                    audio_label=(f"{visualizer_audio_index}:a" if visualizer_audio_index is not None else None),
                )
                command += list(overlay_plan.input_args)
                overlay_graph = f"[0:v]{final_filter}[overlay_base]"
                if overlay_plan.filter_complex:
                    overlay_graph += ";" + overlay_plan.filter_complex
                command += ["-filter_complex", overlay_graph, "-map", f"[{overlay_plan.output_label}]"]
                self._set_stage(
                    "Overlay Composer",
                    "Aplicando PNG/GIF e visualizador musical depois de IA/VFX, sem reinterpolar os overlays.",
                )
            else:
                command += ["-map", "0:v:0", "-vf", final_filter]

            if output_audio_index is not None:
                command += ["-map", f"{output_audio_index}:a:0"]
            else:
                command += ["-an"]
'''
    text = replace_once(text, old_final, new_final, "final overlay graph")
    return text


def main() -> None:
    original = STUDIO.read_text(encoding="utf-8")
    integrated = integrate(original)
    if integrated == original:
        print("CINEPULSE_OVERLAY_STUDIO_ALREADY_INTEGRATED")
        return
    STUDIO.write_text(integrated, encoding="utf-8")
    print(f"CINEPULSE_OVERLAY_STUDIO_PATCH_OK revision={INTEGRATION_REVISION}")


if __name__ == "__main__":
    main()
