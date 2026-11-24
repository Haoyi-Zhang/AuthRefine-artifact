"""Generate the five checked mechanism figures from executable evidence."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from figure_typography import ACCENT, GUIDE, INK, NEGATIVE, PALE_BLUE, PALE_GREEN, PALE_ORANGE, POSITIVE, SECONDARY, WIDTH
from journal_diagram import JournalCanvas
from binding_overview import draw as worked_overview
from credential_pair import draw as observed_pair
from pipeline_overview import draw as pipeline_overview

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from diagnostic_example import run as checked_example


def square(output: Path) -> Path:
    # The square is semantic, not decorative: horizontal edges are transitions;
    # vertical dashed edges are complete observations.
    d = JournalCanvas(output / "semantic-square.pdf", WIDTH, 118,
                      "Transition commutation under complete observation")
    d.text(14, 31, "reference", font="Bold", size=9.4, align="left")
    d.text(14, 91, "target", font="Bold", size=9.4, align="left")

    d.circle(116, 28, 18, stroke=ACCENT, fill=PALE_BLUE)
    d.text(116, 31.5, "s=ν(q)", font="Math", size=9.7)
    d.circle(318, 28, 18, stroke=ACCENT, fill=PALE_BLUE)
    d.text(318, 31.5, "s'=ν(q')", font="Math", size=9.3)
    d.arrow([(138, 28), (296, 28)], color=ACCENT)
    d.text(217, 17, "Pβ : x / d", font="Math", size=9.0)

    d.circle(116, 91, 16, stroke=INK, fill="white")
    d.text(116, 94.5, "q", font="Math", size=10.0)
    d.circle(318, 91, 16, stroke=INK, fill="white")
    d.text(318, 94.5, "q'", font="Math", size=10.0)
    d.arrow([(136, 91), (298, 91)], color=INK)
    d.text(217, 81, "M : x / d", font="Math", size=9.0)

    for x in (116, 318):
        d.arrow([(x, 72), (x, 48)], color=SECONDARY, dash=(3, 2), head=3.6)
        d.text(x + 10, 63, "ν", font="Math", size=9.3, align="left", color=SECONDARY)
    return d.finish()


def trace(output: Path) -> Path:
    example = checked_example()
    row = next(r for r in example["profiles"] if r["binding"] == {"z_a": "r", "z_b": "t"})
    first, second = row["trace"]
    if ([s["request"][-1] for s in (first, second)] != ["a", "b"]
            or first["target"] != ["allow", 1] or first["source"] != ["allow", 1]
            or second["target"] != ["allow", 0] or second["source"] != ["deny", 1]
            or not (first["decision_equal"] and first["state_equal"])
            or second["decision_equal"] or second["state_equal"]):
        raise ValueError("Illustrated trace differs from the checked example")

    d = JournalCanvas(output / "diagnostic-trace.pdf", WIDTH, 142,
                      "Shortest disagreement for one fixed binding")
    d.icon(24, 17, "family", 13)
    d.text(38, 20, "β=(r,t)", font="Math", size=9.5, align="left")
    d.text(168, 20, "a", font="Math", size=9.5)
    d.text(294, 20, "b", font="Math", size=9.5)

    lanes = ((54, "target", "target"), (102, "reference", "source"))
    for y, label, key in lanes:
        d.text(14, y + 3.4, label, font="Bold", size=9.2, align="left")
        values = (0, first[key][1], second[key][1])
        for x, value in zip((104, 224, 348), values):
            fill = PALE_GREEN if x < 348 else (PALE_GREEN if key == "target" else PALE_ORANGE)
            stroke = ACCENT if x < 348 else (POSITIVE if key == "target" else NEGATIVE)
            d.circle(x, y, 15, stroke=stroke, fill=fill)
            d.text(x, y + 3.3, f"p={value}", font="Math", size=9.5)
        d.arrow([(122, y), (206, y)], color=SECONDARY)
        d.arrow([(242, y), (330, y)], color=SECONDARY)
        d.text(164, y - 10, first[key][0], size=8.5, color=SECONDARY)
        d.text(286, y - 10, second[key][0], size=8.5,
               color=POSITIVE if key == "target" else NEGATIVE)

    # A vertical marker makes the exact first differing cell apparent.
    d.line(318, 34, 318, 122, color=GUIDE, width=.7, dash=(2, 2))
    d.status(374, 54, True, radius=4.8)
    d.status(374, 102, False, radius=4.8)
    d.text(14, 136, "shortest word", size=8.6, color=SECONDARY, align="left")
    d.text(83, 136, "ab", font="Math", size=9.5, align="left")
    d.text(318, 136, "first difference", size=8.6, color=SECONDARY)
    return d.finish()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--math-font", type=Path,
                        help="Legacy option retained for command compatibility")
    args = parser.parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=True)
    for compose in (pipeline_overview, worked_overview, observed_pair, square, trace):
        compose(args.output_directory)


if __name__ == "__main__":
    main()
