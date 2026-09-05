"""Desktop controls for isolated Preview restoration export."""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import StringVar, TclError, filedialog, ttk

from ..loop_engine import FFMPEG, first_video_size, probe_media
from ..restoration_export import PreviewExportCancelled, export_preview_restoration
from ..restoration_preview import build_preview_restoration_plan
from .restoration_lab import RestorationUiState


_LABEL_TO_PRESET = {
    "Neutro": "neutral",
    "Desbotado": "faded",
    "Flat / log leve": "flat",
    "Quente": "warm",
    "Frio": "cool",
}


def _controls(studio):
    return RestorationUiState(
        remove_overlays=bool(studio.restoration_remove_overlays.get()),
        preset=_LABEL_TO_PRESET.get(studio.restoration_preset.get(), "neutral"),
        brightness=float(studio.restoration_brightness.get()),
        contrast=float(studio.restoration_contrast.get()),
        saturation=float(studio.restoration_saturation.get()),
        gamma=float(studio.restoration_gamma.get()),
        temperature=float(studio.restoration_temperature.get()),
        tint=float(studio.restoration_tint.get()),
    ).controls()


def _source_size(source: str) -> tuple[int, int] | None:
    try:
        size = first_video_size(probe_media(source))
        if not size:
            return None
        width, height = int(size[0]), int(size[1])
        return (width, height) if width > 0 and height > 0 else None
    except Exception:
        return None


def build_restoration_export_panel(studio, parent) -> None:
    """Attach Preview-only export actions below the restoration lab."""

    studio.restoration_export_status = StringVar(
        value="Exportação Preview usa um arquivo temporário e só publica o resultado completo."
    )
    studio._restoration_export_cancel = None
    studio._restoration_export_running = False

    shell = ttk.Frame(parent, style="Card.TFrame", padding=14)
    shell.grid(row=4, column=0, sticky="ew", pady=(10, 0))
    shell.columnconfigure(0, weight=1)

    head = ttk.Frame(shell, style="Card.TFrame")
    head.grid(row=0, column=0, sticky="ew")
    head.columnconfigure(0, weight=1)
    ttk.Label(head, text="Exportar restauração", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(
        head,
        text="Gera um arquivo separado pelo pipeline Preview. O botão Renderizar do Stable não é reutilizado.",
        style="CardMuted.TLabel",
        wraplength=820,
    ).grid(row=1, column=0, sticky="w", pady=(2, 0))

    actions = ttk.Frame(head, style="Card.TFrame")
    actions.grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))
    studio.restoration_export_button = ttk.Button(
        actions,
        text="Exportar Preview restaurado",
        style="Primary.TButton",
        command=lambda: _start_export(studio),
    )
    studio.restoration_export_button.pack(side="left")
    studio.restoration_cancel_button = ttk.Button(
        actions,
        text="Cancelar",
        state="disabled",
        command=lambda: _cancel_export(studio),
    )
    studio.restoration_cancel_button.pack(side="left", padx=(7, 0))

    ttk.Label(
        shell,
        textvariable=studio.restoration_export_status,
        style="CardMuted.TLabel",
        wraplength=1000,
        justify="left",
    ).grid(row=1, column=0, sticky="w", pady=(10, 0))


def _build_export_plan(studio, source: str):
    size = _source_size(source)
    if size is None:
        raise ValueError("Não foi possível identificar a resolução da fonte com segurança.")

    evidence = ()
    if bool(studio.restoration_remove_overlays.get()):
        if getattr(studio, "_restoration_plan_source", "") != source or getattr(studio, "_restoration_plan", None) is None:
            raise ValueError("Analise os overlays desta fonte antes de exportar com remoção ativada.")
        evidence = tuple(studio._restoration_plan.evidence)

    return build_preview_restoration_plan(
        evidence,
        frame_width=size[0],
        frame_height=size[1],
        color=_controls(studio),
    )


def _default_output(source: Path) -> Path:
    suffix = source.suffix.lower() if source.suffix.lower() in {".mp4", ".mkv", ".mov"} else ".mp4"
    return source.with_name(f"{source.stem}-restaurado-preview{suffix}")


def _start_export(studio) -> None:
    if getattr(studio, "_restoration_export_running", False):
        return
    source_text = str(studio.video.get()).strip()
    source = Path(source_text)
    if not source.is_file():
        studio.restoration_export_status.set("Selecione um vídeo válido antes de exportar.")
        return

    try:
        plan = _build_export_plan(studio, source_text)
    except Exception as exc:
        studio.restoration_export_status.set(str(exc).strip() or exc.__class__.__name__)
        return
    if not plan.has_work:
        studio.restoration_export_status.set("Nada para restaurar: ajuste a cor ou ative/análise a remoção de overlays.")
        return

    suggested = _default_output(source)
    output_text = filedialog.asksaveasfilename(
        parent=studio.root,
        title="Exportar Preview restaurado",
        initialdir=str(suggested.parent),
        initialfile=suggested.name,
        defaultextension=suggested.suffix,
        filetypes=(("Vídeo", "*.mp4 *.mkv *.mov"), ("Todos os arquivos", "*.*")),
    )
    if not output_text:
        return
    output = Path(output_text)
    if output.resolve() == source.resolve():
        studio.restoration_export_status.set("Escolha outro arquivo: o Preview nunca sobrescreve a fonte.")
        return

    cancel_event = threading.Event()
    studio._restoration_export_cancel = cancel_event
    studio._restoration_export_running = True
    studio.restoration_export_status.set("Exportando Preview restaurado… o Stable continua livre para tocar a vida dele.")
    try:
        studio.restoration_export_button.configure(state="disabled")
        studio.restoration_cancel_button.configure(state="normal")
    except TclError:
        pass

    def worker() -> None:
        result = None
        error = None
        cancelled = False
        try:
            result = export_preview_restoration(
                FFMPEG,
                source,
                output,
                plan,
                cancel_event=cancel_event,
            )
        except PreviewExportCancelled:
            cancelled = True
        except Exception as exc:
            error = str(exc).strip() or exc.__class__.__name__

        def finish() -> None:
            studio._restoration_export_running = False
            studio._restoration_export_cancel = None
            try:
                studio.restoration_export_button.configure(state="normal")
                studio.restoration_cancel_button.configure(state="disabled")
            except TclError:
                pass
            if cancelled:
                studio.restoration_export_status.set("Exportação Preview cancelada; arquivo temporário removido.")
            elif error is not None:
                studio.restoration_export_status.set(f"Falha no Preview: {error}")
            elif result is not None:
                studio.restoration_export_status.set(
                    f"Preview concluído em {result.elapsed_seconds:.1f}s: {result.output}"
                )

        try:
            studio.root.after(0, finish)
        except TclError:
            return

    threading.Thread(target=worker, name="cinepulse-restoration-export", daemon=True).start()


def _cancel_export(studio) -> None:
    cancel_event = getattr(studio, "_restoration_export_cancel", None)
    if cancel_event is None:
        return
    cancel_event.set()
    studio.restoration_export_status.set("Cancelando Preview e limpando o arquivo temporário…")
    try:
        studio.restoration_cancel_button.configure(state="disabled")
    except TclError:
        pass
