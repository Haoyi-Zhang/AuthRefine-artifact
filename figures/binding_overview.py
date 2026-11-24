"""Render the checked target automaton and first disagreement per binding."""
from __future__ import annotations

from pathlib import Path
import sys

from figure_typography import ACCENT, GUIDE, INK, NEGATIVE, PALE_BLUE, POSITIVE, SECONDARY, WIDTH
from journal_diagram import JournalCanvas

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from diagnostic_example import run


def draw(output: Path) -> Path:
    example = run()
    machine = example["machine"]
    assert example["all_lengths_agree"]
    observations = machine["observations"]
    assert sorted(observations) == [0, 1] and observations[machine["initial"]] == 0
    assert [item[-1] for item in machine["alphabet"]] == ["a", "b"]
    by_observation = {
        before: [(decision, observations[successor]) for decision, successor in outgoing]
        for before, outgoing in zip(observations, machine["transitions"])
    }
    assert by_observation == {0: [("allow", 1), ("deny", 0)],
                              1: [("deny", 1), ("allow", 0)]}
    rows = {(row["binding"]["z_a"], row["binding"]["z_b"]): row
            for row in example["profiles"]}
    assert set(rows) == {("r", "r"), ("r", "t"), ("t", "r"), ("t", "t")}
    stages = {}
    for binding, item in rows.items():
        trace = "".join(step["request"][-1] for step in (item["trace"] or ()))
        if not item["equivalent"] and len(trace) != item["length"]:
            raise ValueError("Witness label does not match the trace length")
        stages.setdefault(trace, []).append(binding)
    if stages != {"": [("r", "r")], "ab": [("r", "t")], "a": [("t", "r"), ("t", "t")]}:
        raise ValueError("Illustrated prefixes do not match the specified profile")

    output.mkdir(parents=True, exist_ok=True)
    path = output / "analysis-workflow.pdf"
    d = JournalCanvas(path, WIDTH, 250, "Target automaton and first disagreement")

    # Compact target graph.  Edge labels sit beside their actual transition.
    d.icon(18, 25, "graph", 15)
    d.text(31, 28, "target", font="Bold", size=9.2, align="left")
    for x, state in ((125, "p=0"), (276, "p=1")):
        d.circle(x, 55, 19, stroke=ACCENT, fill=PALE_BLUE)
        d.text(x, 58.5, state, font="Math", size=10.1)
    d.arrow([(145, 50), (256, 50)], color=ACCENT)
    d.arrow([(256, 64), (145, 64)], color=SECONDARY)
    d.text(200, 40, "a / allow", size=8.7, color=SECONDARY)
    d.text(200, 78, "b / allow", size=8.7, color=SECONDARY)

    # Self-loops are small and local, rather than large enclosing arcs.
    for x, label in ((125, "b / deny"), (276, "a / deny")):
        c = d.c
        c.saveState(); c.setStrokeColor(SECONDARY); c.setLineWidth(.9)
        p = c.beginPath(); p.moveTo(x - 11, d._py(39))
        p.curveTo(x - 26, d._py(12), x + 26, d._py(12), x + 11, d._py(39))
        c.drawPath(p, fill=0, stroke=1); c.restoreState()
        d.arrow([(x + 11, 39), (x + 13, 44)], color=SECONDARY, head=3.4)
        d.text(x, 12, label, size=8.5, color=SECONDARY)

    # Matrix: position is the prefix length, fill marks the first disagreement.
    columns = [(40, "binding"), (126, "start"), (210, "a"), (294, "ab"), (365, "result")]
    for x, label in columns:
        d.text(x, 112, label, font="Bold" if label in {"binding", "result"} else "Math",
               size=9.2)
    d.line(20, 120, 384, 120, color=GUIDE, width=.6)

    ys = (142, 169, 196, 223)
    for y, binding in zip(ys, sorted(rows)):
        first = next(word for word, group in stages.items() if binding in group)
        d.text(40, y + 3.3, f"({binding[0]}, {binding[1]})", font="Math", size=9.8)
        d.circle(126, y, 3.8, stroke=SECONDARY, fill="white")
        d.arrow([(133, y), (202, y)], color=GUIDE, head=3.8)
        d.circle(210, y, 3.8, stroke=ACCENT if first == "a" else SECONDARY,
                 fill=ACCENT if first == "a" else "white")
        if first == "a":
            d.text(365, y + 3.2, "a", font="Math", size=9.8, color=NEGATIVE)
            continue
        d.arrow([(217, y), (286, y)], color=GUIDE, head=3.8)
        d.circle(294, y, 3.8, stroke=ACCENT if first == "ab" else SECONDARY,
                 fill=ACCENT if first == "ab" else "white")
        if first == "ab":
            d.text(365, y + 3.2, "ab", font="Math", size=9.8, color=NEGATIVE)
        else:
            d.arrow([(301, y), (344, y)], color=GUIDE, head=3.8)
            d.status(350, y, True, radius=4.8)
            d.text(365, y + 3.2, "match", size=8.8, align="left", color=POSITIVE)

    d.circle(102, 240, 3.5, stroke=SECONDARY, fill="white")
    d.text(111, 243, "agrees", size=8.4, align="left", color=SECONDARY)
    d.circle(190, 240, 3.5, stroke=ACCENT, fill=ACCENT)
    d.text(199, 243, "first difference", size=8.4, align="left", color=SECONDARY)
    return d.finish()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    draw(args.output_directory)
