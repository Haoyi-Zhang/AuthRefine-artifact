"""Render the evaluation figures as pure vector PDFs from retained results."""

import argparse
from collections import Counter
import csv
import gzip
import json
import math
from pathlib import Path
from statistics import median

from reportlab.lib.colors import white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from figure_typography import (
    ACCENT as NAVY, GRID, GUIDE, INK, LIGHT, SECONDARY as MUTED, TEXT, WIDTH,
    label_size, register_fonts,
)

ARTIFACT = Path(__file__).resolve().parents[1]


def chart(output, name, height):
    c = Canvas(str(output / f"{name}.pdf"), pagesize=(WIDTH, height),
               invariant=True, initialFontName="Body")
    c.setTitle(name.replace("-", " ").capitalize())
    c.setCreator("")
    c.chart_height = height
    c.chart_labels = []
    return c


def text(c, x, y, value, align="center", size=TEXT, color=INK, font="Body"):
    value = str(value)
    size = label_size(font, size)
    w = pdfmetrics.stringWidth(value, font, size)
    x0 = x - {"center": w / 2, "left": 0, "right": w}[align]
    y0, y1 = y - .23 * size, y + .76 * size
    if x0 < 4 or x0 + w > WIDTH - 4 or y0 < 2 or y1 > c.chart_height - 3:
        raise ValueError(f"Label outside plot safe area: {value}")
    for a, b, d, e, other in c.chart_labels:
        if x0 < d + 1 and a < x0 + w + 1 and y0 < e + 1 and b < y1 + 1:
            raise ValueError(f"Chart labels collide: {value!r} and {other!r}")
    c.chart_labels.append((x0, y0, x0 + w, y1, value))
    c.setFont(font, size)
    c.setFillColor(color)
    {"center": c.drawCentredString, "left": c.drawString,
     "right": c.drawRightString}[align](x, y, value)


def line(c, x0, y0, x1, y1, color=GRID, width=.65):
    c.setStrokeColor(color)
    c.setLineWidth(width)
    c.line(x0, y0, x1, y1)


def dot(c, x, y, radius=2.5, open_marker=False, color=NAVY):
    c.setFillColor(white if open_marker else color)
    c.setStrokeColor(color)
    c.setLineWidth(.8)
    c.circle(x, y, radius, fill=1, stroke=int(open_marker))


def rect(c, x, y, w, h, color):
    c.setFillColor(color)
    c.rect(x, y, w, h, fill=1, stroke=0)


def square(c, x, y, r, color=NAVY):
    rect(c, x - r, y - r, 2*r, 2*r, color)


def diamond(c, x, y, r, color=INK):
    c.setFillColor(color)
    p = c.beginPath()
    p.moveTo(x - r, y)
    p.lineTo(x, y + r)
    p.lineTo(x + r, y)
    p.lineTo(x, y - r)
    p.close()
    c.drawPath(p, fill=1, stroke=0)


def axis(c, left, right, y, low, high, ticks):
    def loc(value):
        return left + (right - left) * (value - low) / (high - low)
    line(c, left, y, right, y, INK)
    for v, label in ticks:
        x = loc(v)
        line(c, x, y, x, y - 3, INK)
        text(c, x, y - 14, label, size=10.0)
    return loc


def finish(c):
    c.showPage()
    c.save()


def load_study(name):
    with gzip.open(ARTIFACT / "source_study/data" / name, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def coverage(output):
    rows = load_study("source-transfer.json.gz")["rows"]
    modes = ("baseline", "guarded")
    key = "routes_with_all_declared_direct_dependencies_linked"
    counts = [(sum(row[mode]["declared_routes"] for row in rows),
               sum(row[mode][key] for row in rows)) for mode in modes]
    changes = sorted(row["guarded"][key] - row["baseline"][key] for row in rows)
    if (len(rows) != 48 or len({r["repository_id"] for r in rows}) != len(rows)
            or counts != [(1591, 564), (1591, 757)]
            or any(row["guarded"]["declared_routes"] != row["baseline"]["declared_routes"]
                   for row in rows)
            or any(row["guarded"][key] - row["baseline"][key] !=
                   row["fully_linked_declared_route_delta"] for row in rows)
            or Counter((delta > 0) - (delta < 0) for delta in changes) != {1: 7, -1: 3, 0: 38}
            or sum(changes) != counts[1][1] - counts[0][1]):
        raise ValueError("The matched source cohort no longer matches the manuscript")

    c = chart(output, "source-interface-coverage", 348)
    left, right = 166, 374
    text(c, (left+right)/2, 331, "(a) Linked routes", font="Bold", size=11)
    text(c, 14, 305, "48 snapshots", "left", font="Bold", size=11)
    text(c, 14, 288, "38 unchanged", "left")
    x = axis(c, left, right, 260, 0, 1591, ((0, "0"), (800, "800"), (1591, "1,591")))
    for y, label, (_, complete) in zip((306, 282), ("Baseline", "Guarded"), counts):
        end = x(complete)
        rect(c, left, y-5, right-left, 10, LIGHT)
        rect(c, left, y-5, end-left, 10, NAVY)
        text(c, left-9, y-3.5, label, "right")
        text(c, end+7, y-3.5, f"{complete:,}", "left", font="Bold", size=11)
    text(c, (left+right)/2, 231, "Declared routes (1,591)")
    changed = sorted((r for r in rows if r["fully_linked_declared_route_delta"]),
                     key=lambda r: (-r["fully_linked_declared_route_delta"], r["repository"]))
    labels = [r["repository"].split("/", 1)[1] for r in changed]
    if len(set(labels)) != len(labels):
        raise ValueError("Repository labels must identify distinct changed snapshots")
    # Reserve a right gutter for the largest positive label; labels should not
    # be squeezed into the bar at journal width.
    left, right = 195, 360
    text(c, (left+right)/2, 207, "(b) Changed snapshots", font="Bold", size=11)
    u = axis(c, left, right, 34, -40, 130,
             tuple((n, str(n)) for n in (-40, 0, 40, 80, 120)))
    line(c, u(0), 34, u(0), 197, INK, .8)
    for y, row, label in zip(range(187, 37, -15), changed, labels):
        delta = row["fully_linked_declared_route_delta"]
        text(c, 176, y-3.5, label, "right")
        a,b=sorted((u(0),u(delta)))
        if delta > 0:
            rect(c,a,y-3.2,max(b-a,.8),6.4,NAVY)
            label = f"+{delta}"
            if b + 6 + pdfmetrics.stringWidth(label, "Body", 10) > WIDTH - 4:
                text(c,b-4,y-3.3,label,"right",size=10,color=white,font="Bold")
            else:
                text(c,b+6,y-3.3,label,"left",size=10)
        else:
            c.setFillColor(white);c.setStrokeColor(INK);c.setLineWidth(.7)
            c.rect(a,y-3.2,max(b-a,.8),6.4,fill=1,stroke=1)
            text(c,a-6,y-3.3,str(delta),"right",size=10)
    text(c, (left+right)/2, 7, "Guarded minus baseline (routes)")
    finish(c)
    (output / "source-interface-coverage.json").write_text(json.dumps({
        "snapshots": len(rows), "unchanged_snapshots": changes.count(0),
        "declared_routes": counts[0][0],
        "linked_routes": dict(zip(modes, [n for _, n in counts])),
        "changed_snapshots": [{"repository": r["repository"],
                               "repository_id": r["repository_id"],
                               "source_snapshot": r["source_snapshot"],
                               "delta": r["fully_linked_declared_route_delta"]}
                              for r in changed],
    }, indent=2)+"\n")


def transfer(output):
    """Compare retained outcomes for identical project context sets."""
    def load(name):
        path = ARTIFACT / "prospective_study" / f"{name}.json.gz"
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)

    frozen, adapted = load("primary"), load("secondary")
    before, after = frozen["rows"], adapted["rows"]
    if ([(r["id"], r["contexts"]) for r in before] !=
            [(r["id"], r["contexts"]) for r in after]
            or len({r["id"] for r in before}) != 9
            or not adapted["secondary_is_not_another_blind_transfer"]):
        raise ValueError("Expected identical boundary and context denominators")
    names = {"taigaio/taiga-back": "Taiga", "allegro/ralph": "Ralph",
             "open-webui/open-webui": "Open WebUI"}
    rows = []
    for repo, label in names.items():
        a, b = [[r for r in group if r["id"].startswith(repo + "/")]
                for group in (before, after)]
        n = sum(r["contexts"] for r in a)
        agree, unknown = [], []
        for group in (a, b):
            for r in group:
                if r["status"] not in {"contract_agreement", "inconclusive"}:
                    raise ValueError("Do not group differences with unknown contexts")
                if "differences" not in r:
                    if (r["status"] != "inconclusive" or r["unknown_contexts"] != r["contexts"]
                            or r.get("stage") != "source_admission" or r["observations"]):
                        raise ValueError("Absent differences field requires full non-admission")
                elif (r["differences"] != 0 or len(r["observations"]) != r["contexts"]
                      or sum(o["agrees"] is True for o in r["observations"]) !=
                      r["contexts"] - r["unknown_contexts"]):
                    raise ValueError("Do not group differences with unknown contexts")
            if any(not 0 <= r["unknown_contexts"] <= r["contexts"] for r in group):
                raise ValueError("Invalid unknown-context count")
            u = sum(r["unknown_contexts"] for r in group)
            unknown.append(u)
            agree.append(n-u)
        rows.append((label, n, *agree, *unknown))
    if rows != [("Taiga", 54, 23, 54, 31, 0), ("Ralph", 18, 0, 18, 18, 0),
                ("Open WebUI", 6, 0, 6, 6, 0)] or any(
                    sum(r["status"] == "contract_agreement" for r in d["rows"])
                    != d["complete_boundaries"] for d in (frozen, adapted)):
        raise ValueError("Context totals differ from the retained transfer study")

    c = chart(output, "evaluation-design", 174)
    ticks = tuple((n, str(n)) for n in (0, 18, 36, 54))
    positions = ((94, 221), (255, 382))
    scales = [axis(c, left, right, 33, 0, 54, ticks) for left, right in positions]
    adaptation_band(c, 145, 157, 12, 9, 2)
    text(c, 163, 156, "Agreement", "left")
    adaptation_band(c, 239, 157, 12, 9, 3)
    text(c, 257, 156, "Unknown", "left")
    for (left, right), stage in zip(positions, ("Frozen transfer", "After adaptation")):
        text(c, (left+right)/2, 136, stage, font="Bold", size=11)
    for y, (label, n, frozen_agree, adapted_agree, frozen_unknown, adapted_unknown) in zip(
            (112, 83, 54), rows):
        text(c, 83, y-3.5, label, "right")
        for scale, agreed, unknown in zip(
                scales, (frozen_agree, adapted_agree), (frozen_unknown, adapted_unknown)):
            if agreed + unknown != n:
                raise ValueError("Each stage must account for the same contexts")
            for start, count, kind in ((0, agreed, 2), (agreed, unknown, 3)):
                if not count:
                    continue
                a, b = scale(start), scale(start + count)
                mid = (a+b)/2
                adaptation_band(c, a, y-8, b-a, 16, kind)
                if kind == 3:
                    label_width = pdfmetrics.stringWidth(str(count), "Bold", 11)
                    rect(c, mid-label_width/2-5, y-8, label_width+10, 16, white)
                text(c, mid, y-3.5, count, font="Bold", size=11,
                     color=white if kind == 2 else INK)
    text(c, 238, 5, "Contexts")
    finish(c)


def adaptation_band(c, x, y, w, h, kind):
    if kind in (0, 1, 2):
        rect(c, x, y, w, h, (GRID, LIGHT, NAVY)[kind])
        if kind == 0:
            # A separate dash pattern preserves the source/input distinction in grayscale.
            for offset in range(3, int(h)-1, 5):
                line(c,x+1,y+offset,x+w-1,y+offset,MUTED,.6)
        if kind != 2:
            c.setStrokeColor(MUTED if kind == 0 else GUIDE)
            c.setLineWidth(.65)
            c.rect(x, y, w, h, fill=0, stroke=1)
        return
    c.saveState()
    p = c.beginPath()
    p.rect(x, y, w, h)
    c.clipPath(p, stroke=0, fill=0)
    for k in range(-math.ceil(h), math.ceil(w), 6):
        line(c, x+k, y, x+k+h, y+h, MUTED, .6)
    c.restoreState()
    c.setStrokeColor(MUTED)
    c.setLineWidth(.65)
    c.rect(x, y, w, h, fill=0, stroke=1)


def adaptation(output):
    records = json.loads((ARTIFACT / "adaptation_study/casebook.json").read_text(
        encoding="utf-8"
    ))["cases"]
    axes = ("identity origin", "post-authorization effects", "identity/state handoff",
            "runtime resolution", "environment and time")
    handling = (
        ("automatic supported source analysis", "Source"),
        ("explicit configuration/input", "Supplied input"),
        ("source-bound primitive adapter", "Primitive"),
        ("non-admission", "Unadmitted"),
    )
    counts = [Counter(r["axis_classification"][axis]["handling"] for r in records)
              for axis in axes]
    matrix = [tuple(row[key] for key, *_ in handling) for row in counts]
    if len(records) != 8 or matrix != [(0, 5, 3, 0), (0, 0, 5, 3), (1, 0, 7, 0),
                                       (2, 1, 4, 1), (0, 2, 3, 3)]:
        raise ValueError("Adaptation handling no longer matches the manuscript")
    if any(sum(row) != len(records) for row in matrix):
        raise ValueError("Adaptation choices must partition each axis")
    c = chart(output, "adaptation-handling", 190)
    left, right = 146, 373
    x = axis(c, left, right, 33, 0, 8, tuple((n, str(n)) for n in range(0, 9, 2)))
    for j, ((_, label), start) in enumerate(zip(handling, (52, 120, 219, 295))):
        adaptation_band(c, start, 173, 12, 9, j)
        text(c, start + 17, 172, label, "left")
    for y, name, row in zip((149, 125, 101, 77, 53), axes, matrix):
        text(c, left-9, y-3.5, name[0].upper() + name[1:], "right")
        cursor = 0
        for j, count in enumerate(row):
            if not count:
                continue
            a, b = x(cursor), x(cursor + count)
            adaptation_band(c, a, y-8, b-a, 16, j)
            if j in (0, 3):
                # Give labels an unhatched field.  The source and unadmitted
                # patterns remain visible around the value without crossing it.
                label_width = pdfmetrics.stringWidth(str(count), "Bold", 11)
                rect(c, (a+b)/2-label_width/2-5, y-8, label_width+10, 16,
                     GRID if j == 0 else white)
            text(c, (a+b)/2, y-3.5, count, color=white if j == 2 else INK,
                 font="Bold", size=11)
            cursor += count
    text(c, (left+right)/2, 5, "Cases (of 8)")
    finish(c)


def costs(output):
    data = load_study("credential-cost.json.gz")
    total = data["totals"]
    observed, native = data["measurements"], data["native_common_pipeline"]
    names = (("target_distance", "Target distance"), ("complete_product", "Complete product"),
             ("decision_diagram", "Decision diagram"), ("ordinary_BFS", "Ordinary BFS"))
    if (len(observed), len(native), total["fixed_binding_rows"], total["model_profiles"]) != (5, 3, 112, 8):
        raise ValueError("Unexpected cost denominators")
    if not all(r["complete_outputs_equal"] for r in observed) or not all(r["returncode"] == 0 for r in native):
        raise ValueError("Cost comparison is not equal-output and successful")
    values = {k: median(r["seconds"][k] for r in observed) for k, _ in names}
    if (values != total["algorithm_median_seconds"] or
            median(r["seconds"] for r in native) != total["common_native_pipeline_median_seconds"]):
        raise ValueError("Timing summary differs from raw measurements")
    ms = [v * 1000 for v in values.values()]
    if ([round(x, 2) for x in ms] != [10.84, 36.06, 14.67, 43.93]
            or round(total["common_native_pipeline_median_seconds"], 3) != 15.403
            or round(total["common_table_build_seconds"], 5) != 0.00877):
        raise ValueError("Cost data differs from the numbers in the manuscript")
    c = chart(output, "credential-algorithm-cost", 218)
    left, right = 115, 320
    x = axis(c, left, right, 31, 0, 50, tuple((v, str(v)) for v in range(0, 51, 10)))
    dot(c, 116, 201, 1.9, True)
    text(c, 124, 197.5, "Five runs", "left")
    line(c, 186, 201, 201, 201, MUTED, .9)
    for xx in (186, 201):line(c,xx,198.4,xx,203.6,MUTED,.9)
    text(c, 208, 197.5, "Range", "left")
    diamond(c, 283, 201, 2.8)
    text(c, 292, 197.5, "Median", "left")
    ordered = sorted(zip(names, ms), key=lambda item: item[1])
    for y, ((key, label), value) in zip((166, 130, 94, 58), ordered):
        run_ms = sorted(1000 * row["seconds"][key] for row in observed)
        lo,hi=x(run_ms[0]),x(run_ms[-1]);median_x=x(value)
        line(c,left,y,right,y,GRID,.6)
        line(c,lo,y,hi,y,MUTED,1.0)
        for xx in (lo,hi):line(c,xx,y-3,xx,y+3,MUTED,.9)
        # Exact time coordinates; only the categorical row coordinate is
        # displaced to expose coincident runs and the median marker.
        placed=[]
        choices=(0,4.6,-4.6,9.2,-9.2,13.8,-13.8,18.4,-18.4)
        for sample in run_ms:
            px=x(sample)
            offset=next(dy for dy in choices
                        if math.hypot(px-median_x,dy)>=5.7
                        and all(math.hypot(px-qx,dy-qy)>=4.4 for qx,qy in placed))
            placed.append((px,offset))
            dot(c,px,y+offset,radius=1.8,open_marker=True)
        diamond(c,median_x,y,3.0)
        text(c,left-10,y-3.5,label,"right")
        text(c,389,y-3.5,f"{value:.2f}","right",font="Bold",size=10.5)
    text(c,(left+right)/2,5,"Family-analysis time (ms)")
    finish(c)


def width(output):
    with (ARTIFACT / "results/width.csv").open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    aliases = [int(r["aliases"]) for r in rows]
    if aliases != list(range(1, 17)):
        raise ValueError("Width study must cover aliases 1 through 16")
    local, executed, derived = [], [], []
    for n, row in zip(aliases, rows):
        measured = row["global_oracle_executed"] == "True"
        bound = int(row["global_complete_work_bound"])
        count = int(row["local_binding_evaluations"])
        if (measured != (n <= 8) or bool(row["global_evaluations"]) != measured
                or bound != n * 2 ** (n + 1) or count != 4 * n
                or int(row["maximum_width"]) != 1):
            raise ValueError("Do not conflate executed and derived work")
        local.append((n, count))
        if measured:
            executed.append((n, int(row["global_evaluations"])))
            if executed[-1][1] != bound:
                raise ValueError("Executed complete work and bound disagree")
        if n >= 8:
            derived.append((n, bound))
    c = chart(output, "width", 206)
    left, right, bottom, top = 65, 367, 34, 158

    def loc(n, y):
        return left + 5 + (n - 1) / 15 * (right - left - 5), (
            bottom + (math.log10(y) - math.log10(2)) /
            (math.log10(4_000_000) - math.log10(2)) * (top - bottom)
        )

    for tick in (10, 100, 1000, 10_000, 100_000, 1_000_000):
        _, y = loc(1, tick)
        line(c, left, y, right, y, GRID, .6)
        digits = {1_000: "1k", 10_000: "10k", 100_000: "100k", 1_000_000: "1M"}
        text(c, left - 6, y - 3.2, digits.get(tick, str(tick)), "right", size=10)
    for tick in (1, 4, 8, 12, 16):
        x, _ = loc(tick, 2)
        line(c, x, bottom, x, bottom - 3, INK)
        text(c, x, 20, tick, size=10)
    line(c, left, bottom, right, bottom, INK)
    line(c, left, bottom, left, top, INK)
    text(c, (left + right)/2, 5, "Declared aliases")
    c.saveState(); c.translate(14, (bottom+top)/2); c.rotate(90)
    c.setFont("Body", 9.4); c.setFillColor(INK); c.drawCentredString(0, 0, "Evaluations (log)")
    c.restoreState()

    def series(points, color, marker):
        xy = [loc(*pt) for pt in points]
        if marker == "dash":
            c.setDash(4, 2)
        for a, b in zip(xy, xy[1:]):
            line(c, *a, *b, color, 1.2)
        c.setDash()
        for x, y in xy:
            if marker == "dot":
                dot(c, x, y, 2.4, True, color)
            elif marker == "square":
                square(c, x, y, 1.5, color)

    boundary,_ = loc(8,2)
    c.setDash(1.5,2.5)
    line(c,boundary,bottom,boundary,top,GUIDE,.65)
    c.setDash()
    label="Last global run";label_width=pdfmetrics.stringWidth(label,"Body",10)
    rect(c,boundary+5,top-14.8,label_width+4,12,white)
    text(c,boundary+7,top-12,label,"left",size=10)
    # Start the continuation at the final executed point. The first point is
    # shared by both series; the small square sits inside the local circle.
    series(derived, INK, "dash")
    series(local, NAVY, "dot")
    series(executed, INK, "square")
    # The line style encodes provenance, not a shaded range of alias counts.
    legend_y = 184
    for xx, label, kind in ((72, "Local run", "dot"),
                            (155, "Global run", "square"),
                            (242, "Global derived", "dash")):
        if kind == "dash":
            c.setDash(4, 2)
        line(c, xx, legend_y, xx+15, legend_y, NAVY if kind == "dot" else INK, 1)
        c.setDash()
        if kind == "dot":
            dot(c, xx+7.5, legend_y, 2.2, True)
        elif kind == "square":
            square(c, xx+7.5, legend_y, 1.5, INK)
        text(c, xx+20, legend_y-3.5, label, "left")
    finish(c)


def screening(output):
    with gzip.open(ARTIFACT / "adaptation_study/survey.json.gz", "rt", encoding="utf-8") as stream:
        survey = json.load(stream)
    keys = (("identity_input", "Identity input"),
            ("credential_processing", "Credential processing"),
            ("identity_handoff", "Identity handoff"),
            ("mutation_call", "Named mutation call"),
            ("dynamic_lookup", "Dynamic lookup"),
            ("asynchronous_flow", "Asynchronous flow"))
    total = survey["denominator"]
    counts = [survey["counts"][key] for key, _ in keys]
    if total != 48 or len(survey["rows"]) != total or counts != [17, 25, 10, 42, 24, 22]:
        raise ValueError("The screening snapshot counts differ from the manuscript")
    for (key, _), count in zip(keys, counts):
        if sum(row["features"][key] == "observed" for row in survey["rows"]) != count:
            raise ValueError(f"Screening summary does not match snapshot rows: {key}")
    c = chart(output, "source-screening", 188)
    left, right = 132, 358
    x = axis(c,left,right,31,0,48,tuple((v,str(v)) for v in range(0,49,12)))
    for tick in (12,24,36,48):line(c,x(tick),31,x(tick),179,GRID,.6)
    ordered = sorted(zip(keys,counts),key=lambda item:-item[1])
    for y, ((_,label),count) in zip((171,147,123,99,75,51),ordered):
        rect(c,left,y-4.6,x(count)-left,9.2,NAVY)
        text(c,left-9,y-3.5,label,"right")
        label_x=x(count)+9
        label_width=pdfmetrics.stringWidth(str(count),"Bold",11)
        rect(c,label_x-2,y-6.5,label_width+4,12,white)
        text(c,label_x,y-3.5,count,"left",font="Bold",size=11)
    text(c,(left+right)/2,5,f"Snapshots (of {total})")
    finish(c)


def frontend(output):
    data = load_study("frontend-cost.json.gz")
    rows = data["rows"]
    modes = ("baseline", "guarded")
    if (len(rows), data["measured_fresh_processes"]) != (144, 288) or not data[
            "all_original_source_outputs_unchanged"]:
        raise ValueError("Unexpected matched machine-cost study")
    if {r["repeat"] for r in rows} != {0, 1, 2}:
        raise ValueError("Expected three recorded batches")
    cohorts = [{r["repository_id"] for r in rows if r["repeat"] == i} for i in range(3)]
    if len(cohorts[0]) != 48 or any(c != cohorts[0] for c in cohorts):
        raise ValueError("Batch sources are not the same 48 snapshots")
    totals = {m: [sum(r["methods"][m]["outer_startup_through_exit_wall_ns"]
                      for r in rows if r["repeat"] == i) for i in range(3)] for m in modes}
    if any(totals[m] != data["summaries"][m]["whole48_batch_wall_ns"]
           or median(totals[m]) != data["summaries"][m]["median_whole48_batch_wall_ns"]
           for m in modes):
        raise ValueError("Recorded batch summary disagrees with the process rows")
    if any(sum(r["repeat"] == i for r in rows) != len(cohorts[i]) for i in range(3)):
        raise ValueError("Duplicate snapshot within a measured batch")
    pairs = [(a / 1e9, b / 1e9, (b-a) / 1e9)
             for a, b in zip(*(totals[m] for m in modes))]
    if [round(delta, 2) for _, _, delta in pairs] != [14.61, 14.85, 15.42]:
        raise ValueError("Paired differences differ from the manuscript")

    c = chart(output, "frontend-batch-cost", 170)
    left, right = 62, 223
    text(c, (left+right)/2, 154, "(a) Total wall time", font="Bold", size=11)
    x = axis(c, left, right, 32, 0, 45, tuple((v, str(v)) for v in (0, 15, 30, 45)))
    a0, a1 = 255, 349
    text(c, (a0+a1)/2, 154, "(b) Paired difference", font="Bold", size=11)
    u = axis(c, a0, a1, 32, 0, 16, tuple((v, str(v)) for v in (0, 8, 16)))
    dot(c, 66, 132, 2.5, True)
    text(c, 74, 128.5, "Baseline", "left")
    square(c, 155, 132, 2.5)
    text(c, 163, 128.5, "Guarded", "left")
    for y, i, (start, end, delta) in zip((108, 81, 54), range(1, 4), pairs):
        line(c, x(start), y, x(end), y, MUTED, 1.0)
        dot(c, x(start), y, 2.65, True)
        square(c, x(end), y, 2.5)
        text(c, left-7, y-3.5, f"Batch {i}", "right")
        line(c, a0, y, u(delta), y, GRID, .68)
        diamond(c, u(delta), y, 2.8)
        text(c, u(delta)+6, y-3.5, f"{delta:.2f}", "left", font="Bold", size=11)
    text(c, (left+right)/2, 5, "Wall time (s)")
    text(c, (a0+a1)/2, 5, "Guarded - baseline (s)")
    finish(c)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=True)
    register_fonts()
    for render in (coverage, transfer, adaptation, costs, width, screening, frontend):
        render(args.output_directory)


if __name__ == "__main__":
    main()
