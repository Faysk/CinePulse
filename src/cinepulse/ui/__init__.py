"""Componentes visuais e utilitários de UI do CinePulse.

O pacote ``cinepulse.ui`` existe para separar apresentação da orquestração de
renderização. Ele é deliberadamente leve: Tk/ttk + NumPy, sem introduzir uma
nova stack de interface antes do 1.0 estável.
"""

from .tokens import COLORS, SPACING

__all__ = ["COLORS", "SPACING"]
