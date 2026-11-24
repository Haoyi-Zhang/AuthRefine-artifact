"""Typography and colors for AuthRefine's journal figures.

The figure layer uses embedded TrueType fonts from the TeX distribution.  This
avoids the Type-1 encoding drift and extractor warnings found in the previous
figure set while keeping mathematical variables visually distinct from prose.
"""
from __future__ import annotations

from pathlib import Path
import os
import subprocess

from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# PDF points at native manuscript display width.
WIDTH = 396
COMPACT_WIDTH = 352
TEXT = 10.8
EMPHASIS = 11.3
MATH = 11.2

# A restrained, grayscale-safe palette.  Shape and line style remain the
# primary encodings; color is redundant and deliberately low saturation.
INK = HexColor("#1D2730")
SECONDARY = HexColor("#5B6770")
ACCENT = HexColor("#1E5A73")
POSITIVE = HexColor("#2E7658")
NEGATIVE = HexColor("#A24B31")
GUIDE = HexColor("#98A4AE")
GRID = HexColor("#DCE3E8")
LIGHT = HexColor("#F5F7F8")
PALE_BLUE = HexColor("#EAF2F5")
PALE_GREEN = HexColor("#EAF4EF")
PALE_ORANGE = HexColor("#F7EEE9")
WHITE = HexColor("#FFFFFF")


def label_size(font: str, requested: float) -> float:
    """Cap accidental over-large labels while preserving readable 9--11 pt text."""
    limits = {"Body": TEXT, "Bold": EMPHASIS, "Italic": TEXT, "Math": MATH,
              "Sans": TEXT, "SansBold": EMPHASIS}
    return min(requested, limits.get(font, TEXT))


def tex_file(name: str) -> str:
    """Resolve a font distributed with TeX (or an explicitly supplied tree)."""
    if tree := os.environ.get("AUTHREFINE_TEXMF"):
        paths = tuple(Path(tree).rglob(name))
        if len(paths) != 1:
            raise FileNotFoundError(f"Expected exactly one {name} in the supplied font tree")
        return str(paths[0])
    path = subprocess.check_output(["kpsewhich", name], text=True).strip()
    if not path or not Path(path).is_file():
        raise FileNotFoundError(f"Missing manuscript font resource: {name}")
    return path


def _register(name: str, filename: str) -> None:
    try:
        pdfmetrics.getFont(name)
        return
    except KeyError:
        pass
    pdfmetrics.registerFont(TTFont(name, tex_file(filename), subfontIndex=0))


def register_fonts() -> None:
    """Register embedded fonts with stable metrics and Unicode mappings."""
    _register("Body", "LiberationSerif-Regular.ttf")
    _register("Bold", "LiberationSerif-Bold.ttf")
    _register("Italic", "LiberationSerif-Italic.ttf")
    _register("Math", "LiberationSerif-Italic.ttf")
    # Compatibility aliases used by a few data-plot helpers.
    _register("Sans", "LiberationSerif-Regular.ttf")
    _register("SansBold", "LiberationSerif-Bold.ttf")
