from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src" / "cinepulse" / "ui" / "overlay_view.py"
REVISION = 1


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, got {count}")
    return text.replace(old, new, 1)


def integrate(text: str) -> str:
    if "self.visualizer_secondary_color" in text and "self.mirror_var" in text:
        return text

    text = replace_once(
        text,
        '        self.visualizer_color = StringVar(value="#F2E5C9")\n'
        '        self.sensitivity_var = DoubleVar(value=100.0)\n',
        '        self.visualizer_color = StringVar(value="#F2E5C9")\n'
        '        self.visualizer_secondary_color = StringVar(value="#42D8FF")\n'
        '        self.sensitivity_var = DoubleVar(value=100.0)\n'
        '        self.thickness_var = DoubleVar(value=42.0)\n'
        '        self.bars_var = DoubleVar(value=48.0)\n'
        '        self.mirror_var = BooleanVar(value=False)\n',
        "visualizer variables",
    )

    old_controls = '''        self._number_row(properties, 14, "Sensibilidade %", self.sensitivity_var)
        color_row = ttk.Frame(properties, style="PanelAlt.TFrame")
        color_row.grid(row=15, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(color_row, text="Cor do gráfico…", command=self._choose_visualizer_color).pack(fill="x")
'''
    new_controls = '''        self._number_row(properties, 14, "Sensibilidade %", self.sensitivity_var)
        self._number_row(properties, 15, "Espessura %", self.thickness_var)
        self._number_row(properties, 16, "Barras", self.bars_var)
        ttk.Checkbutton(
            properties,
            text="Espelhar no eixo central",
            variable=self.mirror_var,
            command=self._apply_properties,
        ).grid(row=17, column=0, columnspan=2, sticky="w", pady=(4, 2))
        color_row = ttk.Frame(properties, style="PanelAlt.TFrame")
        color_row.grid(row=18, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(color_row, text="Cor principal…", command=self._choose_visualizer_color).pack(fill="x")
        ttk.Button(color_row, text="Cor secundária…", command=self._choose_visualizer_secondary_color).pack(fill="x", pady=(4, 0))
        ttk.Label(
            properties,
            text="Waveform usa a cor principal; barras/espectro podem combinar as duas cores.",
            style="PanelAlt.TLabel",
            wraplength=180,
        ).grid(row=19, column=0, columnspan=2, sticky="w", pady=(5, 0))
'''
    text = replace_once(text, old_controls, new_controls, "visualizer controls")

    text = replace_once(
        text,
        '            self.visualizer_color.set(layer.visualizer.color)\n'
        '            self.sensitivity_var.set(layer.visualizer.sensitivity * 100.0)\n',
        '            self.visualizer_color.set(layer.visualizer.color)\n'
        '            self.visualizer_secondary_color.set(layer.visualizer.secondary_color)\n'
        '            self.sensitivity_var.set(layer.visualizer.sensitivity * 100.0)\n'
        '            self.thickness_var.set(layer.visualizer.thickness * 100.0)\n'
        '            self.bars_var.set(float(layer.visualizer.bars))\n'
        '            self.mirror_var.set(layer.visualizer.mirror)\n',
        "refresh fidelity properties",
    )

    old_replace = '''                visualizer = replace(
                    visualizer,
                    style=self.visualizer_style.get(),
                    focus=self.visualizer_focus.get(),
                    color=self.visualizer_color.get(),
                    sensitivity=max(0.05, min(8.0, float(self.sensitivity_var.get()) / 100.0)),
                )
'''
    new_replace = '''                visualizer = replace(
                    visualizer,
                    style=self.visualizer_style.get(),
                    focus=self.visualizer_focus.get(),
                    color=self.visualizer_color.get(),
                    secondary_color=self.visualizer_secondary_color.get(),
                    sensitivity=max(0.05, min(8.0, float(self.sensitivity_var.get()) / 100.0)),
                    thickness=max(0.02, min(1.0, float(self.thickness_var.get()) / 100.0)),
                    bars=max(4, min(256, int(round(float(self.bars_var.get()))))),
                    mirror=self.mirror_var.get(),
                )
'''
    text = replace_once(text, old_replace, new_replace, "apply fidelity properties")

    anchor = '''    def _safe_area_changed(self) -> None:
'''
    method = '''    def _choose_visualizer_secondary_color(self) -> None:
        layer = self._selected_layer()
        if layer is None or layer.visualizer is None:
            return
        value = colorchooser.askcolor(
            initialcolor=layer.visualizer.secondary_color,
            title="Cor secundária do visualizador",
        )[1]
        if value:
            self.visualizer_secondary_color.set(value.upper())
            self._apply_properties()

'''
    text = replace_once(text, anchor, method + anchor, "secondary color method")
    return text


def main() -> None:
    original = TARGET.read_text(encoding="utf-8")
    integrated = integrate(original)
    if integrated == original:
        print("CINEPULSE_OVERLAY_PHASE9_UI_ALREADY_INTEGRATED")
        return
    TARGET.write_text(integrated, encoding="utf-8")
    print(f"CINEPULSE_OVERLAY_PHASE9_UI_OK revision={REVISION}")


if __name__ == "__main__":
    main()
