"""Draw the checked native session trace as one shared state timeline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from figure_typography import (
    ACCENT, GUIDE, INK, NEGATIVE, PALE_BLUE, PALE_GREEN, PALE_ORANGE,
    POSITIVE, SECONDARY, WIDTH,
)
from journal_diagram import JournalCanvas, export_svg

ART = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ART / "results/native-session"


def evidence(directory: Path):
    native = json.loads((directory / "native-observations.json").read_text())
    diagnostic = json.loads((directory / "diagnosis.json").read_text())
    replay = json.loads((directory / "native-witness-replay.json").read_text())
    machine = native["baseline"]["machine"]
    family = diagnostic["supplied_family"]
    expected = [
        {"credential-for-row-a": "credential-a", "credential-for-row-b": "credential-b"},
        {"credential-for-row-a": "credential-b", "credential-for-row-b": "credential-a"},
    ]
    if family != expected:
        raise ValueError("illustrated correspondence family differs")
    profiles = diagnostic["profiles"]["baseline"]["binding_profile"]["profiles"]
    if [(r["equivalent"], r["length"]) for r in profiles] != [(True, None), (False, 2)]:
        raise ValueError("illustrated family diagnosis differs")
    failed = profiles[1]
    requests = [["client", "row-a", "remove"], ["client", "credential-a", "lookup"]]
    if [step["request"] for step in failed["trace"]] != requests:
        raise ValueError("illustrated shortest request sequence differs")
    expected_trace = [(["allow", 2], ["allow", 2]), (["allow", 2], ["deny", 2])]
    if [(step["source"], step["target"]) for step in failed["trace"]] != expected_trace:
        raise ValueError("illustrated state/decision trace differs")
    if machine["observations"][machine["initial"]] != 3:
        raise ValueError("illustrated initial presence state differs")
    observed = next(r for r in replay if r["profile"] == "baseline" and r["mode"] == "full")
    records = [r["observation"] for r in observed["observations"]]
    if [r["request"] for r in records] != requests or [(r["before_state"], r["after_state"]) for r in records] != [(3, 2), (2, 2)]:
        raise ValueError("native replay does not realize illustrated states")
    if records[0]["returned_user_id"] is not None or records[0]["removed_ids"] != [1]:
        raise ValueError("native removal does not complete as illustrated")
    if records[1]["decision"] != "deny" or records[1]["selected_record"] is not None:
        raise ValueError("native credential lookup does not deny as illustrated")
    users = {r["user_id"] for r in records[0]["before_rows"]}
    if users != {101}:
        raise ValueError("illustrated sessions do not share the fixture user")
    if diagnostic["profiles"]["baseline"]["independent"][1]["richer_selected_identity"]["length"] != 1:
        raise ValueError("separate richer identity comparison differs")
    return {"family": family, "requests": requests, "native": records, "profiles": profiles}


def draw(output: Path, directory: Path = DEFAULT_RESULTS, *, svg: Path | None = None,
         variant: str = "final") -> Path:
    evidence(directory)
    output.parent.mkdir(parents=True, exist_ok=True)
    d = JournalCanvas(output, WIDTH, 220, "Credential correspondence after a state change")

    def token(x, y, name):
        d.icon(x - 12, y, "key", 13)
        d.text(x + 5, y + 3.2, name, font="Math", size=10.0)

    def obj(x, y, name, present=True):
        d.icon(x - 11, y, "object", 14, color=ACCENT if present else GUIDE)
        d.text(x + 5, y + 3.2, name, font="Math", size=10.0,
               color=INK if present else GUIDE)
        if not present:
            d.line(x - 18, y + 8, x + 13, y - 8, color=GUIDE, width=1.0)

    # Two supplied fixed correspondences.
    for cx, title, mapping in ((104, "identity", (("a", "A"), ("b", "B"))),
                               (292, "swap", (("a", "B"), ("b", "A")))):
        d.text(cx, 15, title, font="Bold", size=9.7)
        for yy, (cred, row) in zip((38, 65), mapping):
            token(cx - 47, yy, cred)
            obj(cx + 45, yy, row)
            d.arrow([(cx - 21, yy), (cx + 25, yy)], color=SECONDARY)

    # One target execution is shared by both interpretations.
    y = 104
    obj(24, y, "A")
    obj(60, y, "B")
    d.arrow([(78, y), (126, y)], color=ACCENT)
    d.icon(102, y - 13, "cross", 10, color=NEGATIVE)
    d.text(102, y + 19, "remove A", size=8.6, color=SECONDARY)
    obj(149, y, "B")
    d.arrow([(167, y), (218, y)], color=ACCENT)
    token(192, y - 13, "a")
    d.text(192, y + 19, "lookup", size=8.6, color=SECONDARY)
    d.icon(242, y, "target", 15)
    d.text(260, y + 3.2, "deny", font="Bold", size=9.8, color=NEGATIVE, align="left")

    # The target result is a fixed comparison column; no long return arrows.
    d.text(278, 132, "target", size=8.2, color=SECONDARY, align="right")
    d.text(278, 142, "deny", font="Bold", size=8.8, color=NEGATIVE, align="right")
    d.line(282, 149, 282, 198, color=GUIDE, width=.7, dash=(2, 2))

    for y, label, row, present, prediction, ok in (
            (160, "identity", "A", False, "deny", True),
            (195, "swap", "B", True, "allow", False)):
        d.text(24, y + 3.2, label, font="Bold", size=9.3, align="left")
        token(102, y, "a")
        d.arrow([(124, y), (151, y)], color=SECONDARY)
        obj(171, y, row, present=present)
        d.text(205, y + 3.2, prediction, size=9.0, align="left")
        d.status(310, y, ok, radius=5.5)
        d.text(321, y + 3.2, "retain" if ok else "exclude", size=8.8,
               align="left", color=POSITIVE if ok else NEGATIVE)

    d.text(18, 215, "shortest witness", size=8.4, color=SECONDARY, align="left")
    d.text(88, 215, "remove(A); lookup(a)", font="Math", size=8.8, align="left")
    path = d.finish()
    if svg is not None:
        export_svg(path, svg)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--svg", type=Path)
    parser.add_argument("--variant", default="final")
    args = parser.parse_args()
    draw(args.output, args.results, svg=args.svg, variant=args.variant)
