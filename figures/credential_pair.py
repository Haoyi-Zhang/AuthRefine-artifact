"""Draw checked credential handoffs and one shortest owner witness."""
from __future__ import annotations

from pathlib import Path
import gzip
import json

from figure_typography import (
    ACCENT, GUIDE, INK, NEGATIVE, PALE_BLUE, PALE_GREEN, PALE_ORANGE,
    POSITIVE, SECONDARY, WIDTH,
)
from journal_diagram import JournalCanvas

DATA = Path(__file__).resolve().parents[1] / "source_study" / "data"
IDS = ("plain-read-1r-header-GET-v1-1", "plain-read-1r-header-GET-v1-2")


def read(name):
    with gzip.open(DATA / (name + ".json.gz"), "rt", encoding="utf-8") as stream:
        return json.load(stream)


def observations():
    inputs = {r["id"]: r for r in read("credential-input")["owned_inputs"]}
    observed = {r["id"]: r for r in read("credential-observations")["rows"]}
    family = next(row for row in read("credential-family")["cases"] if row["id"] == "plain-read-GET")
    records = []
    fixed = ("profile", "mode", "keychoice", "carrier", "method", "version")
    assert all(inputs[IDS[0]][k] == inputs[IDS[1]][k] for k in fixed)
    for case_id in IDS:
        request = inputs[case_id]
        row = observed[case_id]
        value = row["observed"]
        obj = request["target"]
        owner = family["correct_binding"][f"owner-of-check-{obj}"]
        assert case_id in family["measured_cases"]
        assert row["agrees"] and row["exact_resolved_project_identity_transferred"]
        assert value["project"] == 1 and value["readonly"] and value["version"] == 1
        hits = row["serializer_transfers"]
        if hits:
            assert value["consumer"] == "serializer_boundary" and len(hits) == 1
            assert hits[0]["readonly"] is True and hits[0]["v"] == 1
        else:
            assert value["consumer"] is None
        records.append((obj, int(owner.removeprefix("project-")), value["status"], bool(hits)))
    assert records == [(1, 1, 200, True), (2, 2, 403, False)]
    result = family["diagnosis"]
    correct = family["correct_binding"]
    alternative = {**correct, "owner-of-check-2": "project-1"}
    assert result["matching_interpretations"] == [correct]
    assert result["strata"] == {"1": 26, "infinity": 1}
    witness = next(row for row in result["profiles"] if row["binding"] == alternative)
    assert witness["length"] == 1 and not witness["equivalent"]
    (step,) = witness["trace"]
    assert step["request"] == ["1r", "check-2", "header-first-v1"]
    assert step["target"] == ["deny", 0] and step["source"] == ["allow", 0]
    assert not step["decision_equal"] and step["state_equal"]
    contrast = [(2, step["target"][0], True), (1, step["source"][0], False)]
    return records, contrast, result["strata"]["infinity"], result["strata"]["1"]


def draw(output: Path, *, variant: str = "final") -> Path:
    rows, contrast, _, _ = observations()
    output.mkdir(parents=True, exist_ok=True)
    path = output / "credential-handoff.pdf"
    d = JournalCanvas(path, WIDTH, 310, "Credential handoff and owner witness")

    # Resolved project identity fans out to the two real objects.
    d.icon(198, 20, "person", 16)
    d.text(198, 42, "resolved p1", font="Math", size=9.8)

    for x, (obj, owner, status, reaches) in zip((92, 304), rows):
        d.arrow([(184 if x < 198 else 212, 27), (x, 27), (x, 56)], color=SECONDARY)
        d.text((198 + x) / 2, 19, "read", size=8.5, color=SECONDARY)
        d.icon(x, 65, "layers", 16)
        # Keep the object identity beside the path; never place prose on top of
        # the transition line.
        d.text(x + 16, 69, f"project p{owner}", font="Math", size=9.5, align="left")
        d.arrow([(x, 77), (x, 100)], color=SECONDARY)
        d.icon(x, 112, "object", 17)
        d.text(x + 15, 115, f"o{obj}", font="Math", size=10.0, align="left")
        d.arrow([(x, 124), (x, 142)], color=ACCENT)
        d.status(x - 24, 157, reaches, radius=5.6)
        d.text(x - 12, 160, f"{status} / {'allow' if reaches else 'deny'}",
               font="Bold", size=9.3, align="left",
               color=POSITIVE if reaches else NEGATIVE)
        if reaches:
            d.arrow([(x, 168), (x, 182)], color=SECONDARY)
            d.icon(x - 20, 194, "serializer", 14)
            d.text(x - 7, 197, "serializer", size=8.9, align="left")
        else:
            d.line(x - 8, 190, x + 8, 190, color=INK, width=1.5)
            d.text(x + 15, 193, "stop", size=8.8, color=SECONDARY, align="left")

    # The denial on o2 becomes the single observation used below.
    d.arrow([(304, 168), (304, 195), (210, 195)], color=SECONDARY, dash=(3, 2))
    d.icon(198, 195, "target", 14)
    d.text(198, 219, "observed o2: deny", font="Math", size=9.3)

    # Candidate correspondences are alternatives, not observed runtime facts.
    for x, (owner, predicted, agrees) in zip((110, 286), contrast):
        d.arrow([(198, 225), (x, 225), (x, 245)], color=SECONDARY)
        d.icon(x - 24, 255, "person", 13)
        d.text(x - 8, 258, f"z2=p{owner}", font="Math", size=9.6, align="left")
        d.status(x - 22, 285, agrees, radius=5.4)
        d.text(x - 10, 288, predicted, size=8.9, align="left",
               color=POSITIVE if agrees else NEGATIVE)
        d.text(x + 24, 288, "agrees" if agrees else "excluded", size=8.5,
               align="left", color=POSITIVE if agrees else NEGATIVE)
    d.text(286, 305, "witness: read o2", font="Math", size=8.5, color=NEGATIVE)
    return d.finish()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--variant", default="final")
    args = parser.parse_args()
    draw(args.output_directory, variant=args.variant)
