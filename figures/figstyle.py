"""Shared Matplotlib style for the AuthRefine statistical figures.

Times New Roman text, STIX (Times-compatible) mathematics, TrueType font
embedding and vector PDF output. Widths are given in inches for the ACM
manuscript text block (430 pt = 5.95 in).

The look follows the project plotting kit: soft pastel fills with thin black
edges, one hatch per series so grouped and stacked bars stay separable in
grayscale, a single-row legend above the axes, no chart title, and a short
wide aspect for column-width figures.

Byte-identical regeneration needs the exact Times New Roman files that
produced the manuscript figures (``DECLARED_FONTS``). They are proprietary and
not distributed; point ``AUTHREFINE_FONT_DIR`` at a directory holding them, or
install them where Matplotlib finds system fonts. Without them the figures are
still drawn, with every data check, in a substitute serif face, and
``font_status()`` reports that byte comparison is unavailable.
"""
import hashlib
import os
from pathlib import Path

import matplotlib as mpl
from matplotlib import font_manager

TEXT_WIDTH = 5.95

# SHA-256 of the Times New Roman 7.12 TrueType files used for the manuscript.
DECLARED_FONTS = {
    "times.ttf": "931c5de5c70401d9324d5014c123802b4fb753000360ceb2f56c589403cd58c5",
    "timesbd.ttf": "54fbe2c70af7c85a97bed0573227e3ccc4b2486012e3ca2a40c6bc77065846f5",
    "timesi.ttf": "e7f7a88b65188328aea58670f955022e23c712f55679524729da1e4e03c49d88",
    "timesbi.ttf": "3a29d114cb5229e8dbda5bef6c69be4a210a13b7277de4d66e9fc86963226f6c",
}
_FONT_STATUS = {"status": "not-configured"}

# Soft pastel fills with thin black edges. Every series also carries its own
# hatch, marker or line style, so the figures survive grayscale printing and
# colour-vision deficiency.
GREEN = "#86C788"
ORANGE = "#FFA625"
BLUE = "#8FCAF9"
PURPLE = "#CE92D8"
SAND = "#F6D488"
ROSE = "#F2A0A0"
SKY = "#CBE8FD"
INK = "#111111"
EDGE = "#111111"
GRAY = "#8C8C8C"
LIGHT = "#EDEDED"
VERMILLION = ROSE

# One hatch per series position, in the kit's order.
HATCHES = ("///", "\\\\\\", "xxx", "...", "|||", "+++", "---")
PALETTE = (GREEN, ORANGE, BLUE, PURPLE, SAND, ROSE)


def hatch(index):
    """Hatch pattern for series ``index``."""
    return HATCHES[index % len(HATCHES)]


def colour(index):
    """Pastel fill for series ``index``."""
    return PALETTE[index % len(PALETTE)]


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def configure_fonts():
    """Register the declared Times New Roman files and report how text is set."""
    candidates = []
    if os.environ.get("AUTHREFINE_FONT_DIR"):
        candidates.append(("AUTHREFINE_FONT_DIR", Path(os.environ["AUTHREFINE_FONT_DIR"])))
    candidates.append(("user font directory", Path.home() / ".local/share/fonts/tnr"))
    for origin, directory in candidates:
        files = {name: directory / name for name in DECLARED_FONTS}
        if all(path.is_file() for path in files.values()) and \
                all(_sha256(path) == DECLARED_FONTS[name] for name, path in files.items()):
            for path in files.values():
                font_manager.fontManager.addfont(str(path))
            _FONT_STATUS.update(status="declared", origin=origin, family="Times New Roman")
            return "Times New Roman"
    system = [f.fname for f in font_manager.fontManager.ttflist if f.name == "Times New Roman"]
    if system:
        _FONT_STATUS.update(status="undeclared-times-new-roman",
                            sha256=sorted({_sha256(path) for path in system}),
                            family="Times New Roman")
        return "Times New Roman"
    _FONT_STATUS.update(status="substitute", family="DejaVu Serif")
    return "DejaVu Serif"


def font_status():
    """Font provenance of the current run; byte identity needs status 'declared'."""
    return dict(_FONT_STATUS)


def apply(base_size=8.0):
    family = configure_fonts()
    mpl.rcParams.update({
        "font.family": "serif",
        "font.serif": [family],
        "mathtext.fontset": "stix",
        "font.size": base_size,
        "axes.titlesize": base_size,
        "axes.labelsize": base_size,
        "xtick.labelsize": base_size - 0.5,
        "ytick.labelsize": base_size - 0.5,
        "legend.fontsize": base_size - 0.5,
        "axes.linewidth": 0.6,
        "axes.edgecolor": INK,
        "axes.labelcolor": INK,
        "xtick.color": INK,
        "ytick.color": INK,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "xtick.minor.width": 0.4,
        "ytick.minor.width": 0.4,
        "xtick.major.size": 2.5,
        "ytick.major.size": 2.5,
        "xtick.minor.size": 1.5,
        "ytick.minor.size": 1.5,
        "lines.linewidth": 1.1,
        "lines.markersize": 4.0,
        "hatch.linewidth": 0.5,
        "patch.linewidth": 0.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.linewidth": 0.4,
        "grid.color": "#CCCCCC",
        "grid.alpha": 0.7,
        "legend.frameon": False,
        "legend.handlelength": 1.5,
        "legend.borderaxespad": 0.2,
        "legend.columnspacing": 1.1,
        "axes.titleweight": "normal",
        "axes.titlepad": 3.0,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
        "figure.dpi": 150,
    })


def panel_title(ax, text):
    """Left-aligned panel label such as '(a) Retained bindings'."""
    ax.set_title(text, loc="left", fontsize=mpl.rcParams["font.size"])


def value_label(ax, x, y, text, rotation=0, ha="center", va="center", size=None):
    """Small value label on a white rounded box, as in the plotting kit."""
    ax.text(x, y, text, ha=ha, va=va, rotation=rotation,
            fontsize=size or mpl.rcParams["font.size"] - 1.0, color=INK, zorder=6,
            bbox=dict(boxstyle="round,pad=0.14", facecolor="white", edgecolor="none",
                      alpha=0.85))


def save(fig, path):
    """Vector PDF without volatile metadata so reruns are byte-stable."""
    fig.savefig(path, metadata={"CreationDate": None, "Creator": None, "Producer": None,
                                "ModDate": None})
