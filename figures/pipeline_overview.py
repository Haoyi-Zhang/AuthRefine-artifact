"""Render the checked active-support diagnosis as a compact journal diagram."""
from __future__ import annotations

from pathlib import Path
import sys

from figure_typography import (
    ACCENT, INK, NEGATIVE, PALE_BLUE, PALE_GREEN, PALE_ORANGE,
    POSITIVE, SECONDARY, WIDTH,
)
from journal_diagram import JournalCanvas, export_svg


def checked_partition():
    """Check every illustrated member, projection, result and shortest word."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from checker import reference_step, support
    from diagnostic_example import run

    result = run()
    policy, machine = result["policy"], result["machine"]
    initial = machine["initial"]
    state = machine["observations"][initial]
    request = machine["alphabet"][0]
    edge = machine["transitions"][initial][0]
    observed = (edge[0], machine["observations"][edge[1]])
    dependencies = tuple(support(policy, state, request))
    if state != 0 or request[-1] != "a" or dependencies != ("z_a",) or observed != ("allow", 1):
        raise ValueError("Overview cell differs from the checked example")
    groups, profiles = {}, {}
    for row in result["profiles"]:
        binding = row["binding"]
        members = tuple(binding[name] for name in ("z_a", "z_b"))
        projected = tuple(binding[name] for name in dependencies)
        actual = reference_step(policy, state, request, binding)
        group = groups.setdefault(projected, {"members": [], "result": actual})
        if group["result"] != actual:
            raise ValueError("Support-equivalent bindings have different cell results")
        group["members"].append(members)
        word = "".join(step["request"][-1] for step in (row["trace"] or ()))
        profiles[members] = None if row["equivalent"] else word
    expected = {
        ("r",): {"members": [("r", "r"), ("r", "t")], "result": ("allow", 1)},
        ("t",): {"members": [("t", "r"), ("t", "t")], "result": ("deny", 0)},
    }
    if groups != expected or profiles != {("r", "r"): None, ("r", "t"): "ab",
                                          ("t", "r"): "a", ("t", "t"): "a"}:
        raise ValueError("Overview partition or profile differs from the checked example")
    next_state = edge[1]
    next_request = next(req for req in machine["alphabet"] if req[-1] == "b")
    request_index = machine["alphabet"].index(next_request)
    next_edge = machine["transitions"][next_state][request_index]
    if (next_edge[0], machine["observations"][next_edge[1]]) != ("allow", 0):
        raise ValueError("Overview second observed cell differs")
    if tuple(support(policy, 1, next_request)) != ("z_b",):
        raise ValueError("Overview second support differs")
    for value, expected_result in (("r", ("allow", 0)), ("t", ("deny", 1))):
        if reference_step(policy, 1, next_request, {"z_a": "r", "z_b": value}) != expected_result:
            raise ValueError("Overview second group result differs")
    return groups, profiles


def draw(output: Path, *, variant: str = "final") -> Path:
    groups, profiles = checked_partition()
    output.mkdir(parents=True, exist_ok=True)
    path = output / "authrefine-overview.pdf"
    d = JournalCanvas(path, WIDTH, 178, "Active-support diagnosis")

    # Inputs are identified by icons, not explanatory cards.
    inputs = [(18, "document", "P"), (52, "target", "T"),
              (86, "family", "F"), (120, "person", "C")]
    for x, icon, label in inputs:
        d.icon(x, 17, icon, 13)
        d.text(x, 34, label, font="Math", size=9.6)
    d.arrow([(137, 19), (164, 19)], color=SECONDARY)
    d.icon(178, 19, "check", 14)
    d.text(178, 36, "admit", size=8.3, color=SECONDARY)

    # The one shared target traversal is shown as states and labelled edges.
    d.icon(209, 19, "graph", 14)
    for x, state in ((238, "p=0"), (298, "p=1"), (360, "p=0")):
        d.circle(x, 19, 11, stroke=ACCENT, fill=PALE_BLUE)
        d.text(x, 22.2, state, font="Math", size=8.7)
    d.arrow([(250, 19), (286, 19)], color=ACCENT)
    d.arrow([(310, 19), (348, 19)], color=ACCENT)
    d.text(268, 8, "a / allow", size=8.1, color=SECONDARY)
    d.text(329, 8, "b / allow", size=8.1, color=SECONDARY)

    # Compact column labels; the caption carries the full explanation.
    d.text(34, 54, "binding", font="Bold", size=9.4)
    d.text(126, 54, "active support", font="Bold", size=9.4)
    d.text(230, 54, "local result", font="Bold", size=9.4)
    d.text(350, 54, "profile", font="Bold", size=9.4)

    rows = [76, 101, 129, 154]
    members = [("r", "r"), ("r", "t"), ("t", "r"), ("t", "t")]
    for y, member in zip(rows, members):
        d.text(34, y + 3.3, f"({member[0]}, {member[1]})", font="Math", size=10.2)

    # Projection at request a: two legal groups, each evaluated once.
    d.bracket(76, 71, 106, side="right")
    d.arrow([(81, 88.5), (103, 88.5)], color=SECONDARY)
    d.rect(104, 71.5, 44, 34, stroke=ACCENT, fill=PALE_BLUE, radius=6)
    d.text(126, 84, "z(a)=r", font="Math", size=9.3)
    d.text(126, 97, "allow", size=8.4, color=POSITIVE)

    d.bracket(76, 124, 159, side="right")
    d.arrow([(81, 141.5), (103, 141.5)], color=SECONDARY)
    d.rect(104, 124.5, 44, 34, stroke=ACCENT, fill=PALE_BLUE, radius=6)
    d.text(126, 137, "z(a)=t", font="Math", size=9.3)
    d.text(126, 150, "deny", size=8.4, color=NEGATIVE)

    # The surviving group is split only when request b activates z_b.
    d.arrow([(149, 88.5), (171, 88.5), (171, 76), (196, 76)], color=SECONDARY)
    d.arrow([(171, 88.5), (171, 101), (196, 101)], color=SECONDARY)
    for y, value, decision, state, fill in ((76, "r", "allow", "p=0", PALE_GREEN),
                                             (101, "t", "deny", "p=1", PALE_ORANGE)):
        d.rect(197, y - 14, 52, 28, stroke=SECONDARY, fill=fill, radius=6)
        d.text(223, y - 2, f"z(b)={value}", font="Math", size=9.1)
        d.text(223, y + 9, f"{decision}, {state}", size=8.0,
               color=POSITIVE if decision == "allow" else NEGATIVE)

    # The excluded group bypasses b but still receives separate certificates.
    d.arrow([(149, 141.5), (291, 141.5)], color=SECONDARY)
    d.bracket(296, 129, 154, side="right")

    # Per-member output: symbols and short words, no summary sentence.
    outputs = [(76, True, "match"), (101, False, "ab"),
               (129, False, "a"), (154, False, "a")]
    for y, ok, label in outputs:
        d.status(323, y, ok, radius=5.7)
        d.text(337, y + 3.2, label, font="Math" if label in {"a", "ab"} else "Bold",
               size=9.6, align="left", color=POSITIVE if ok else NEGATIVE)
    d.arrow([(250, 76), (307, 76)], color=SECONDARY, dash=(3, 2))
    d.arrow([(250, 101), (307, 101)], color=SECONDARY)
    d.arrow([(301, 129), (307, 129)], color=SECONDARY)
    d.arrow([(301, 154), (307, 154)], color=SECONDARY)

    return d.finish()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--variant", default="final")
    args = parser.parse_args()
    draw(args.output_directory, variant=args.variant)
