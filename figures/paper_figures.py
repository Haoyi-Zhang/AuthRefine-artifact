#!/usr/bin/env python3
"""Regenerate every statistical figure of the AuthRefine paper and supplement.

All values are read from the retained artifact records. Each renderer checks
the denominators and headline values quoted in the manuscript before drawing,
so a stale or changed record stops the build instead of producing a silently
different plot. The same file is distributed as artifact/figures/paper_figures.py
and as the manuscript's figure-source/make_figures.py.

Usage (from any directory):
    python3 paper_figures.py --output-directory PATH [--artifact PATH]
            [--table-output PATH] [--receipt PATH]
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter, LogLocator

import figstyle as S

HERE = Path(__file__).resolve().parent
TABLE_OUTPUT = {}
# Main paper: validation-profiles, source-controls, session-certification, width,
# family-diagnosis-cost, session-correspondence, symbolic-comparison. The others
# belong to the technical supplement.
FIGURES = ("validation-profiles.pdf", "source-controls.pdf", "session-certification.pdf",
           "width.pdf", "family-diagnosis-cost.pdf", "session-correspondence.pdf",
           "symbolic-comparison.pdf", "source-interface-coverage.pdf", "evaluation-design.pdf",
           "source-screening.pdf", "adaptation-handling.pdf", "frontend-batch-cost.pdf",
           "credential-algorithm-cost.pdf")
METHODS = ("per-binding-product", "per-binding-target", "scan", "support-indexed",
           "finite-domain", "cudd")
COHORTS = (("family-cost", "State/support cohort", 38),
           ("session-correspondence", "Session correspondences", 40),
           ("native-policy-store", "Policy-file store", 80))


def log_fmt(v, _pos=None):
    if v <= 0:
        return ""
    if v >= 1:
        return f"{v:,.0f}"
    return f"{v:g}"


# ---------------------------------------------------------------- loaders
def load_comparison(art):
    """Load the six-method campaign and recompute every summary from raw samples."""
    res = art / "results/symbolic-comparison"
    report = json.loads((res / "summary.json").read_text())
    trials = json.loads((res / "trials.json").read_text())
    if (report["status"] != "PASS" or report["repeats"] != 7 or report["tasks"] != 158
            or report["timed_task_records"] != 5320 or report["processes"] != 42
            or report["methods"] != list(METHODS)):
        raise ValueError("Unexpected six-method campaign denominators")
    rows = {r["id"]: r for r in report["records"]}
    raw = {}
    for t in trials:
        if t["exit_code"] != 0 or t["complete_outputs_compared"] is not True:
            raise ValueError("Invalid worker record")
        for rec in t["records"]:
            raw[(t["repeat"], t["method"], rec["id"])] = rec
    for case, row in rows.items():
        if len({m["output_sha256"] for m in row["methods"].values()}) != 1:
            raise ValueError("Methods returned different complete profiles: " + case)
        for method, summ in row["methods"].items():
            samples = [raw[(r, method, case)]["diagnosis_wall_ns"] for r in range(7)]
            if (summ["diagnosis_wall_ns"]["samples"] != samples
                    or summ["diagnosis_wall_ns"]["median"] != median(samples)):
                raise ValueError("Summary differs from raw worker samples: " + case)
    if Counter(r["cohort"] for r in rows.values()) != {c: n for c, _, n in COHORTS}:
        raise ValueError("Cohort denominators changed")
    return rows


def wall(row, method):
    w = row["methods"][method]["diagnosis_wall_ns"]
    return w["median"] / 1e6, min(w["samples"]) / 1e6, max(w["samples"]) / 1e6


def load_study(art, name):
    with gzip.open(art / "source_study/data" / name, "rt", encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------------ main paper
def family_cost(art, rows, out):
    fam = {r["case"]: r for r in rows.values() if r["cohort"] == "family-cost"}
    if len(fam) != 38:
        raise ValueError("Expected 38 family-cost tasks")
    group_of = {"all-match": "match", "late-failure": "late", "early-failure": "early",
                "dense-support": "dense", "singleton": "dense"}
    pts = []
    for key, r in fam.items():
        p, g = r["methods"]["per-binding-product"], r["methods"]["support-indexed"]
        ps, gs = p["diagnosis_wall_ns"]["samples"], g["diagnosis_wall_ns"]["samples"]
        pts.append(dict(id=key, group=group_of.get(r["regime"], "source"),
                        calls=p["diagnostic_reference_calls"] / g["diagnostic_reference_calls"],
                        ratio=p["diagnosis_wall_ns"]["median"] / g["diagnosis_wall_ns"]["median"],
                        lo=min(ps) / max(gs), hi=max(ps) / min(gs)))
    # Values quoted in the text.
    big = fam["control-s32-f256-all-match"]["methods"]
    if (big["per-binding-product"]["diagnostic_reference_calls"], big["support-indexed"]["diagnostic_reference_calls"]) != (73728, 296):
        raise ValueError("Headline reference-call counts changed")
    if round(big["support-indexed"]["diagnosis_wall_ns"]["median"] / 1e6, 3) != 23.043:
        raise ValueError("Headline indexed median changed")

    style = {"match": ("o", "white", S.BLUE, "All match"),
             "late": ("D", S.ORANGE, S.ORANGE, "Late failure"),
             "early": ("s", S.VERMILLION, S.VERMILLION, "Early failure"),
             "dense": ("^", "white", S.GRAY, "Dense / singleton"),
             "source": ("X", S.GREEN, S.GREEN, "Source / control")}
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(S.TEXT_WIDTH, 2.85),
                                 gridspec_kw=dict(width_ratios=[1.12, 1.0], wspace=0.62))
    for p in pts:
        m, fc, ec, _ = style[p["group"]]
        ax.plot([p["calls"]] * 2, [p["lo"], p["hi"]], color=S.GRAY, lw=0.5, alpha=0.7, zorder=1)
        ax.plot(p["calls"], p["ratio"], marker=m, ms=4.2, mfc=fc, mec=ec, mew=0.9,
                ls="none", zorder=3)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlim(0.8, 400); ax.set_ylim(0.01, 1000)
    ax.axhline(1, color=S.INK, lw=0.6, ls=(0, (3, 2)), zorder=2)
    ax.axvline(1, color=S.INK, lw=0.6, ls=(0, (3, 2)), zorder=2)
    for a in (ax.xaxis, ax.yaxis):
        a.set_major_formatter(FuncFormatter(log_fmt))
        a.set_minor_formatter(NullFormatter())
    ax.set_xlabel("Reference-call ratio (product / indexed)")
    ax.set_ylabel("Diagnosis-time ratio (product / indexed)")
    S.panel_title(ax, "(a) All 38 tasks")
    handles = [Line2D([], [], marker=m, mfc=fc, mec=ec, mew=0.9, ls="none", ms=4.2, label=l)
               for m, fc, ec, l in style.values()]
    ax.legend(handles=handles, loc="upper left", ncol=1, handletextpad=0.3,
              borderaxespad=0.3, fontsize=7)

    detail = [("dense-s2-f2", "Dense, 2 $\\times$ 2"),
              ("dense-s2-f16", "Dense, 2 $\\times$ 16"),
              ("dense-s2-f256", "Dense, 2 $\\times$ 256"),
              ("dense-s8-f2", "Dense, 8 $\\times$ 2"),
              ("dense-s8-f16", "Dense, 8 $\\times$ 16"),
              ("dense-s8-f256", "Dense, 8 $\\times$ 256"),
              ("singleton-s32-f1", "Singleton, 32 $\\times$ 1"),
              ("healthchecks-resume-plain", "Healthchecks, plain key"),
              ("healthchecks-resume-stored_mac", "Healthchecks, MAC key"),
              ("piccolo-session-baseline", "Piccolo sessions"),
              ("piccolo-session-omit_delete", "Omitted-delete control")]
    look = {p["id"]: p for p in pts}
    for i, (key, label) in enumerate(detail):
        p = look[key]; y = len(detail) - 1 - i
        col = S.GRAY if i < 7 else S.GREEN
        bx.plot([p["lo"], p["hi"]], [y, y], color=col, lw=0.9)
        bx.plot([p["lo"]] * 2, [y - .18, y + .18], color=col, lw=0.8)
        bx.plot([p["hi"]] * 2, [y - .18, y + .18], color=col, lw=0.8)
        bx.plot(p["ratio"], y, marker="D", ms=3.8, color=S.INK, ls="none", zorder=3)
        bx.text(330, y, f"{p['ratio']:.2f}", va="center", ha="right", fontsize=7)
    bx.set_yticks(range(len(detail)))
    bx.set_yticklabels([l for _, l in detail][::-1], fontsize=7)
    bx.set_xscale("log"); bx.set_xlim(0.01, 350)
    bx.xaxis.set_major_locator(FixedLocator([0.01, 0.1, 1, 10, 100]))
    bx.xaxis.set_major_formatter(FuncFormatter(log_fmt)); bx.xaxis.set_minor_formatter(NullFormatter())
    bx.axvline(1, color=S.INK, lw=0.6, ls=(0, (3, 2)))
    bx.set_ylim(-0.7, len(detail) - 0.3)
    bx.grid(axis="y", visible=False)
    bx.tick_params(axis="y", length=0)
    bx.set_xlabel("Diagnosis-time ratio (product / indexed)")
    S.panel_title(bx, "(b) Dense, singleton and source tasks")
    S.save(fig, out / "family-diagnosis-cost.pdf"); plt.close(fig)

    # Table rows used by the manuscript.
    selected = [("family-cost/control-s32-f256-all-match", "All match (32, 256)"),
                ("family-cost/control-s32-f256-late-failure", "Late failure (32, 256)"),
                ("family-cost/dense-s8-f256", "Dense support (8, 256)"),
                ("family-cost/singleton-s32-f1", "Singleton (32, 1)"),
                ("session-correspondence/sessions-6-baseline/total", "Sessions (64, 720)"),
                ("native-policy-store/repaired-initial-0/total", "Policy file (16, 6)")]
    lines = ["% Generated from the raw seven-run records by the AuthRefine statistical-figure script."]
    for key, label in selected:
        vals = [rows[key]["methods"][m]["diagnosis_wall_ns"]["median"] / 1e6 for m in METHODS]
        best = min(vals)
        cells = [(r"\textbf{%s}" % f"{v:,.3f}") if v == best else f"{v:,.3f}" for v in vals]
        lines.append(label + " & " + " & ".join(cells) + r"\\")
    lines.append(r"\bottomrule")
    TABLE_OUTPUT.get("path", out.parent / "family-cost-rows.tex").write_text("\n".join(lines) + "\n")


def session_correspondence(art, rows, out):
    diag = json.loads((art / "results/session-correspondence/diagnosis.json").read_text())
    if diag["status"] != "PASS":
        raise ValueError("Session study did not pass")
    obs = {int(r["sessions"]): r for r in diag["cases"] if r["arm"] == "baseline"}
    ns = list(range(2, 7))
    for n in ns:
        o = obs[n]["caller_outcomes"]
        if (obs[n]["family_members"] != math.factorial(n) or o["lookup-only"]["matching"] != math.factorial(n)
                or o["one-removal"]["matching"] != 1 or o["unrestricted"]["matching"] != 1
                or set(obs[n]["selected_identity_matching"].values()) != {1}):
            raise ValueError("Session outcomes changed")

    def t(n, caller, method):
        return wall(rows[f"session-correspondence/sessions-{n}-baseline/{caller}"], method)

    if [round(x, 3) for x in t(6, "unrestricted", "scan")] != [306.782, 259.345, 699.265]:
        raise ValueError("Six-session scan timing changed")
    fig, axes = plt.subplots(1, 3, figsize=(S.TEXT_WIDTH, 2.25),
                             gridspec_kw=dict(width_ratios=[1, 1, 1.15], wspace=0.55))
    ax, bx, cx = axes
    # (a) surviving family under each caller/observation.
    series = [("Lookup only", [math.factorial(n) for n in ns], "o", "white", S.BLUE),
              ("One removal or unrestricted", [obs[n]["caller_outcomes"]["unrestricted"]["matching"] for n in ns], "D", S.ORANGE, S.ORANGE),
              ("Selected-row observation", [max(obs[n]["selected_identity_matching"].values()) for n in ns], "s", "white", S.VERMILLION)]
    off = {0: 0.0, 1: -0.12, 2: 0.12}
    for k, (lab, vals, m, fc, ec) in enumerate(series):
        ax.plot([n + off[k] for n in ns], vals, marker=m, mfc=fc, mec=ec, color=ec, mew=0.9,
                lw=0.8, ms=4, label=lab)
    for n in ns:
        ax.annotate(f"{math.factorial(n)}", (n, math.factorial(n)), textcoords="offset points",
                    xytext=(-4, 3) if n == 2 else (4, -7), ha="right" if n == 2 else "left",
                    fontsize=6.5)
    ax.set_yscale("log"); ax.set_ylim(0.6, 6e4)
    ax.yaxis.set_major_locator(FixedLocator([1, 10, 100, 1000, 10000]))
    ax.yaxis.set_major_formatter(FuncFormatter(log_fmt)); ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xticks(ns); ax.set_xlim(1.6, 6.5)
    ax.set_xlabel("Live sessions $n$"); ax.set_ylabel("Matching bijections")
    S.panel_title(ax, "(a) Surviving family")
    ax.legend(loc="upper left", fontsize=6.3, handlelength=1.4, borderaxespad=0.1)

    # (b) unrestricted caller, scan versus indexed, all sizes.
    meth = [("scan", "Scan", "o", "white", S.BLUE, -0.11),
            ("support-indexed", "Indexed", "D", S.ORANGE, S.ORANGE, 0.11)]
    for key, lab, m, fc, ec, dx in meth:
        med, lo, hi = zip(*[t(n, "unrestricted", key) for n in ns])
        xs = [n + dx for n in ns]
        bx.errorbar(xs, med, yerr=[[a - b for a, b in zip(med, lo)], [c - a for a, c in zip(med, hi)]],
                    fmt=m, mfc=fc, mec=ec, ecolor=ec, mew=0.9, ms=4, elinewidth=0.8, capsize=1.6,
                    capthick=0.7, label=lab, lw=0)
    bx.set_yscale("log"); bx.set_ylim(0.1, 2000)
    bx.yaxis.set_major_formatter(FuncFormatter(log_fmt)); bx.yaxis.set_minor_formatter(NullFormatter())
    bx.set_xticks(ns); bx.set_xlim(1.6, 6.5)
    bx.set_xlabel("Live sessions $n$"); bx.set_ylabel("Diagnosis time (ms)")
    S.panel_title(bx, "(b) Unrestricted caller")
    bx.legend(loc="upper left", fontsize=6.5, handlelength=1.0)

    # (c) six sessions: four applicable methods under three callers.
    callers = [("lookup-only", "Lookup\nonly"), ("one-removal", "One\nremoval"),
               ("unrestricted", "Unre-\nstricted")]
    meth4 = [("scan", "Scan", "o", "white", S.BLUE),
             ("support-indexed", "Indexed", "D", S.ORANGE, S.ORANGE),
             ("finite-domain", "Finite-domain DD", "s", "white", S.VERMILLION),
             ("cudd", "CUDD", "^", S.GREEN, S.GREEN)]
    for j, (key, lab, m, fc, ec) in enumerate(meth4):
        for i, (caller, _) in enumerate(callers):
            med, lo, hi = t(6, caller, key)
            y = (len(callers) - 1 - i) + (0.27 - 0.18 * j)
            cx.plot([lo, hi], [y, y], color=ec, lw=0.8)
            cx.plot(med, y, marker=m, mfc=fc, mec=ec, mew=0.9, ms=3.8, ls="none",
                    label=lab if i == 0 else None)
    cx.set_xscale("log"); cx.set_xlim(5, 3000)
    cx.xaxis.set_major_formatter(FuncFormatter(log_fmt)); cx.xaxis.set_minor_formatter(NullFormatter())
    cx.set_yticks(range(len(callers))); cx.set_yticklabels([l for _, l in callers][::-1], fontsize=7)
    cx.tick_params(axis="y", length=0); cx.grid(axis="y", visible=False)
    cx.set_ylim(-0.5, len(callers) - 0.35)
    cx.set_xlabel("Diagnosis time (ms)")
    S.panel_title(cx, "(c) Six sessions, by caller")
    h, l = cx.get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", bbox_to_anchor=(0.72, -0.17), ncol=4, fontsize=6.8,
               handlelength=1.0, columnspacing=1.0)
    S.save(fig, out / "session-correspondence.pdf"); plt.close(fig)


def symbolic_comparison(art, rows, out):
    series = [("scan", "Scan", S.BLUE, (0, (1.2, 1.2))),
              ("finite-domain", "Finite-domain DD", S.VERMILLION, "-"),
              ("cudd", "CUDD", S.GREEN, (0, (4, 1.6)))]
    fig, axes = plt.subplots(1, 3, figsize=(S.TEXT_WIDTH, 2.05), sharey=True,
                             gridspec_kw=dict(wspace=0.12))
    faster = {}
    for ax, (cohort, title, count) in zip(axes, COHORTS):
        sel = [r for r in rows.values() if r["cohort"] == cohort]
        assert len(sel) == count
        ax.axvspan(1e-3, 1, color="#F1F1F1", zorder=0, lw=0)
        for key, lab, col, ls in series:
            vals = sorted(r["methods"][key]["diagnosis_wall_ns"]["median"] /
                          r["methods"]["support-indexed"]["diagnosis_wall_ns"]["median"] for r in sel)
            faster[(cohort, key)] = sum(v < 1 for v in vals)
            xs = [1e-3] + vals + [1e4]
            ys = [0] + [100 * (i + 1) / count for i in range(count)] + [100]
            ax.step(xs, ys, where="post", color=col, ls=ls, lw=1.2, label=lab)
        ax.axvline(1, color=S.INK, lw=0.6, ls=(0, (3, 2)))
        ax.set_xscale("log"); ax.set_xlim(0.01, 1000)
        ax.xaxis.set_major_locator(FixedLocator([0.01, 1, 100]))
        ax.xaxis.set_minor_locator(FixedLocator([0.1, 10, 1000]))
        ax.xaxis.set_major_formatter(FuncFormatter(log_fmt)); ax.xaxis.set_minor_formatter(NullFormatter())
        ax.set_ylim(0, 102); ax.set_yticks([0, 25, 50, 75, 100])
        S.panel_title(ax, f"({'abc'[COHORTS.index((cohort, title, count))]}) {title} ({count})")
    expected = {("family-cost", "finite-domain"): 24, ("session-correspondence", "finite-domain"): 22,
                ("native-policy-store", "finite-domain"): 23, ("family-cost", "cudd"): 2,
                ("session-correspondence", "cudd"): 3, ("native-policy-store", "cudd"): 0}
    if any(faster[k] != v for k, v in expected.items()):
        raise ValueError("Faster-task counts changed: " + str(faster))
    axes[0].set_ylabel("Tasks at or below ratio (%)")
    axes[1].set_xlabel("Median diagnosis time relative to support indexing")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", bbox_to_anchor=(0.5, 0.99), ncol=3, fontsize=7,
               handlelength=2.4, columnspacing=1.6)
    S.save(fig, out / "symbolic-comparison.pdf"); plt.close(fig)


def source_controls(art, out):
    """RQ2: executable source changes, split by whether the status changes."""
    controls = json.loads((art / "results/source-observer/source-controls.json").read_text())
    labels = {"read_wrong_version": "Serializer version",
              "read_foreign_serializer": "Checked vs. serialized object",
              "resume_omit_save": "Omitted save",
              "resume_repeat_flip": "Duplicate event",
              "resume_stale_ping": "Uncleared timing field",
              "pretix_wrong_organizer": "Wrong organizer",
              "pretix_omit_grants": "Omitted grants",
              "wger_client_owner": "Client-supplied owner"}
    profile = {"read_": "Healthchecks read", "resume_": "Healthchecks resume",
               "pretix_": "Pretix event access", "wger_": "Wger owner insertion"}
    if [c["control"] for c in controls] != list(labels):
        raise ValueError("Source-control set changed")
    for c in controls:
        if c["field_only_differences"] + c["response_differences"] != c["changed_observations"] \
                or not c["changed_observations"]:
            raise ValueError("Source-control record inconsistent: " + c["control"])
    totals = (sum(c["tested_inputs"] for c in controls), sum(c["changed_observations"] for c in controls),
              sum(c["response_differences"] for c in controls))
    if totals != (2896, 318, 24):
        raise ValueError("Source-control totals changed: " + str(totals))

    fig, ax = plt.subplots(figsize=(S.TEXT_WIDTH, 2.05))
    n = len(controls)
    for i, c in enumerate(controls):
        y = n - 1 - i
        f, r = c["field_only_differences"], c["response_differences"]
        ax.barh(y, f, color=S.BLUE, height=0.62, edgecolor="white", lw=0.5)
        if r:
            ax.barh(y, r, left=f, color=S.ORANGE, height=0.62, edgecolor=S.INK, lw=0.5, hatch="////")
        ax.text(f + r + 1.5, y, f"{f + r} of {c['tested_inputs']}", va="center", fontsize=7)
    ax.set_yticks(range(n))
    ax.set_yticklabels([labels[c["control"]] for c in controls][::-1])
    ax.set_xlim(0, 125); ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_ylim(-0.6, n - 0.4)
    ax.grid(axis="y", visible=False); ax.tick_params(axis="y", length=0)
    ax.set_xlabel("Observations that differ from the unmodified source")
    # Profile brackets on the right-hand side.
    groups = []
    for i, c in enumerate(controls):
        name = next(v for k, v in profile.items() if c["control"].startswith(k))
        if groups and groups[-1][0] == name:
            groups[-1][2] = i
        else:
            groups.append([name, i, i])
    for name, a, b in groups:
        ya, yb = n - 1 - a + 0.3, n - 1 - b - 0.3
        ax.plot([123, 123], [yb, ya], color=S.GRAY, lw=0.7, clip_on=False)
        ax.text(124.5, (ya + yb) / 2, name, va="center", ha="left", fontsize=6.8, color=S.INK,
                clip_on=False)
    ax.legend(handles=[Patch(fc=S.BLUE, ec="white", label="Recorded field only (status/decision unchanged)"),
                       Patch(fc=S.ORANGE, ec=S.INK, hatch="////", label="Status or decision changed")],
              loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, fontsize=7)
    S.save(fig, out / "source-controls.pdf"); plt.close(fig)


def session_certification(art, out):
    """RQ3: certification requests from every initial store, theorem versus native words."""
    with gzip.open(art / "results/session-initial-state/validation.json.gz", "rt", encoding="utf-8") as fh:
        val = json.load(fh)
    if val["status"] != "PASS":
        raise ValueError("Initial-state study did not pass")
    opt = [c for c in val["cases"] if c["kind"] == "optimal"]
    o = val["optimal"]
    if (len(opt), o["initial_store_contexts"], o["requests"], o["restore_complete"],
            o["fixed_binding_histories"]) != (248, 124, 1434, 198, 100720):
        raise ValueError("Initial-state cohort changed")
    points = {}
    for c in opt:
        n = c["size"]; d = n - bin(c["initial"]).count("1")
        if c["surviving_bindings"] != [list(range(1, n + 1))]:
            raise ValueError("Optimal word did not isolate identity: " + c["id"])
        b = 1 if 0 < d < n else 0
        want = (2 * max(n - 1, 0) - b) if c["observation"] == "projected" else max(n - 1, 0)
        restore = 1 if d >= 2 else 0
        got = c["counts"]
        if (got["requests"], got["restore_complete"], got["reset_initial"]) != (want, restore, 0):
            raise ValueError("Native word differs from the optimal cost: " + c["id"])
        points.setdefault((c["observation"], n, d), []).append(got["requests"])
    ns = list(range(2, 7))
    colors = {2: S.SKY, 3: S.BLUE, 4: S.GREEN, 5: S.ORANGE, 6: S.VERMILLION}
    markers = {2: "o", 3: "s", 4: "D", 5: "^", 6: "v"}
    fig, axes = plt.subplots(1, 2, figsize=(S.TEXT_WIDTH, 2.2), sharey=True,
                             gridspec_kw=dict(wspace=0.08))
    for ax, (obs, title) in zip(axes, (("projected", "(a) Decision/presence observation"),
                                       ("selected-row", "(b) Selected-row observation"))):
        for n in ns:
            ds = list(range(0, n + 1))
            ys = [points[(obs, n, d)][0] for d in ds]
            if any(len(set(points[(obs, n, d)])) != 1 or len(points[(obs, n, d)]) != math.comb(n, d)
                   for d in ds):
                raise ValueError("Initial stores missing or inconsistent")
            ax.plot(ds, ys, color=colors[n], lw=0.9, zorder=2)
            for d, y in zip(ds, ys):
                filled = d >= 2
                ax.plot(d, y, marker=markers[n], ms=4.2, mec=colors[n], mew=0.9,
                        mfc=colors[n] if filled else "white", ls="none", zorder=3)
        ax.set_xticks(range(0, 7)); ax.set_xlim(-0.4, 6.4)
        ax.set_yticks(range(0, 11, 2)); ax.set_ylim(-0.3, 10.8)
        ax.set_xlabel("Initially absent rows $d$")
        S.panel_title(ax, title)
    axes[0].set_ylabel("Requests to certify identity")
    handles = [Line2D([], [], color=colors[n], marker=markers[n], mfc="white", mec=colors[n], mew=0.9,
                      ms=4.2, lw=0.9, label=f"$n={n}$") for n in ns]
    handles.append(Line2D([], [], marker="o", ls="none", mfc=S.GRAY, mec=S.GRAY, ms=4.2,
                          label="Needs one complete restoration"))
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.99), ncol=6, fontsize=7,
               handlelength=1.6, columnspacing=1.1)
    S.save(fig, out / "session-certification.pdf"); plt.close(fig)


def validation_profiles(art, out):
    """RQ1: outcome classes and per-binding shortest-failure lengths in the three validation domains."""
    res = art / "results"
    single = json.loads((res / "support-indexed/summary.json").read_text())
    overlap = json.loads((res / "support-overlap/summary.json").read_text())
    caller = json.loads((res / "protocol-grouping/summary.json").read_text())
    if single["status"] != "PASS" or overlap["status"] != "PASS" or caller["all_comparisons_passed"] is not True:
        raise ValueError("A validation domain did not pass")
    ov = caller["overlapping_supports"]
    domains = [
        ("Policy–target pairs",single["policy_machine_pairs"], single["family_classifications"],
         single["binding_shortest_lengths"], single["binding_profiles_checked"]),
        ("Correlated families", overlap["family_diagnoses"], overlap["family_classifications"],
         overlap["binding_shortest_lengths"], overlap["binding_profiles_checked"]),
        ("Caller/family cases", ov["family_cases"], ov["outcomes"],
         ov["shortest_lengths_across_families"], ov["classified_binding_rows_across_families"]),
    ]
    if [d[1] for d in domains] != [23040, 16575, 123930]:
        raise ValueError("Validation denominators changed")
    for name, n, outcomes, lengths, rows_ in domains:
        if sum(outcomes.values()) != n or sum(lengths.values()) != rows_:
            raise ValueError("Validation record inconsistent: " + name)
    if not all(c["detected"] for c in overlap["mutation_controls"] + caller["controls"]):
        raise ValueError("An executable control was not detected")

    classes = (("all", "Every member matches", S.GREEN, None),
               ("some", "Proper subfamily matches", S.ORANGE, None),
               ("none", "No member matches", S.VERMILLION, None),
               ("inactive", "Inconclusive: caller admits no event", "white", "////"),
               ("missing", "Inconclusive: missing enabled edge", "white", "...."))
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(S.TEXT_WIDTH, 2.05),
                                 gridspec_kw=dict(width_ratios=[1.0, 1.05], wspace=0.42))
    for i, (name, n, outcomes, _, _) in enumerate(domains):
        y = len(domains) - 1 - i; left = 0.0
        for key, _, col, hatch in classes:
            share = 100 * outcomes.get(key, 0) / n
            if share:
                ax.barh(y, share, left=left, color=col, hatch=hatch, height=0.58,
                        edgecolor=S.GRAY if hatch else "white", lw=0.5)
                left += share
        ax.text(101.5, y, f"{n:,}", va="center", ha="left", fontsize=7)
    ax.set_yticks(range(len(domains)))
    ax.set_yticklabels([d[0] for d in domains][::-1])
    ax.set_xlim(0, 100); ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_ylim(-0.6, len(domains) - 0.4)
    ax.grid(axis="y", visible=False); ax.tick_params(axis="y", length=0)
    ax.set_xlabel("Share of diagnoses (%)")
    S.panel_title(ax, "(a) Family outcome")
    fig.legend(handles=[Patch(fc=c, ec=S.GRAY if h else "none", hatch=h, label=l) for _, l, c, h in classes],
               loc="upper center", bbox_to_anchor=(0.5, -0.07), ncol=3, fontsize=6.8,
               handlelength=1.2, columnspacing=1.2)

    lengths = ["0", "1", "2", "3", "4", "5", "6", "7", "infinity"]
    pos = [j if j < 8 else 8.6 for j in range(len(lengths))]
    fills = ((S.SKY, None), (S.BLUE, None), ("white", "//////"))
    width_ = 0.27
    for k, (name, _, _, dist, rows_) in enumerate(domains):
        xs = [p + (k - 1) * width_ for p, key in zip(pos, lengths) if dist.get(key)]
        ys = [100 * dist[key] / rows_ for key in lengths if dist.get(key)]
        fc, hatch = fills[k]
        bx.bar(xs, ys, width=width_, bottom=0.05, color=fc, hatch=hatch, label=name,
               edgecolor=S.BLUE if hatch else "white", lw=0.5)
    bx.set_yscale("log"); bx.set_ylim(0.05, 150)
    bx.yaxis.set_major_locator(FixedLocator([0.1, 1, 10, 100]))
    bx.yaxis.set_major_formatter(FuncFormatter(log_fmt)); bx.yaxis.set_minor_formatter(NullFormatter())
    bx.set_xticks(pos)
    bx.set_xticklabels([str(j) for j in range(8)] + ["Match"])
    bx.set_xlim(-0.6, 9.1)
    bx.axvline(7.8, color=S.GRAY, lw=0.6, ls=(0, (1, 2)))
    bx.grid(axis="x", visible=False)
    bx.set_xlabel("Shortest distinguishing length per binding")
    bx.set_ylabel("Binding rows (%)")
    S.panel_title(bx, "(b) First-failure depth")
    bx.legend(loc="upper left", bbox_to_anchor=(0.47, 0.99), fontsize=6.6, handlelength=1.2, ncol=1)
    S.save(fig, out / "validation-profiles.pdf"); plt.close(fig)


# ------------------------------------------------------------- supplement
def source_coverage(art, out):
    rows = load_study(art, "source-transfer.json.gz")["rows"]
    key = "routes_with_all_declared_direct_dependencies_linked"
    counts = [(sum(r[m]["declared_routes"] for r in rows), sum(r[m][key] for r in rows))
              for m in ("baseline", "guarded")]
    changes = [r["fully_linked_declared_route_delta"] for r in rows]
    if len(rows) != 48 or counts != [(1591, 564), (1591, 757)] or \
            Counter((d > 0) - (d < 0) for d in changes) != {1: 7, -1: 3, 0: 38}:
        raise ValueError("Source-transfer cohort changed")
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(S.TEXT_WIDTH, 2.1),
                                 gridspec_kw=dict(width_ratios=[1, 1.2], wspace=0.75))
    labels = ["Baseline", "Guarded"]
    for i, (tot, done) in enumerate(counts):
        y = 1 - i
        ax.barh(y, tot, color=S.LIGHT, height=0.5, edgecolor="none")
        ax.barh(y, done, color=S.BLUE if i else S.SKY, height=0.5, edgecolor="none")
        ax.text(done + 25, y, f"{done:,}", va="center", fontsize=7.5)
    ax.set_yticks([1, 0]); ax.set_yticklabels(labels)
    ax.set_xlim(0, 1591); ax.set_xticks([0, 400, 800, 1200, 1591])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_ylim(-0.6, 1.6); ax.grid(axis="y", visible=False); ax.tick_params(axis="y", length=0)
    ax.set_xlabel("Routes with all direct dependencies linked (of 1,591)")
    S.panel_title(ax, "(a) 48 snapshots")
    changed = sorted((r for r in rows if r["fully_linked_declared_route_delta"]),
                     key=lambda r: (-r["fully_linked_declared_route_delta"], r["repository"]))
    for i, r in enumerate(changed):
        d = r["fully_linked_declared_route_delta"]; y = len(changed) - 1 - i
        bx.barh(y, d, color=S.BLUE if d > 0 else S.VERMILLION, height=0.6)
        bx.text(d + (3 if d > 0 else -3), y, f"{d:+d}", va="center",
                ha="left" if d > 0 else "right", fontsize=6.8)
    bx.set_yticks(range(len(changed)))
    bx.set_yticklabels([r["repository"].split("/", 1)[1] for r in changed][::-1], fontsize=6.8)
    bx.axvline(0, color=S.INK, lw=0.6)
    bx.set_xlim(-60, 150); bx.set_xticks([-50, 0, 50, 100, 150]); bx.grid(axis="y", visible=False); bx.tick_params(axis="y", length=0)
    bx.set_xlabel("Guarded minus baseline (routes)")
    S.panel_title(bx, "(b) Ten changed snapshots")
    S.save(fig, out / "source-interface-coverage.pdf"); plt.close(fig)


def transfer(art, out):
    def load(name):
        with gzip.open(art / "prospective_study" / f"{name}.json.gz", "rt", encoding="utf-8") as fh:
            return json.load(fh)
    before, after = load("primary")["rows"], load("secondary")["rows"]
    names = {"taigaio/taiga-back": "Taiga", "allegro/ralph": "Ralph",
             "open-webui/open-webui": "Open WebUI"}
    data = []
    for repo, label in names.items():
        a = [r for r in before if r["id"].startswith(repo + "/")]
        b = [r for r in after if r["id"].startswith(repo + "/")]
        n = sum(r["contexts"] for r in a)
        ua, ub = sum(r["unknown_contexts"] for r in a), sum(r["unknown_contexts"] for r in b)
        data.append((label, n, n - ua, ua, n - ub, ub))
    if [(d[0], d[1], d[2], d[4]) for d in data] != [("Taiga", 54, 23, 54), ("Ralph", 18, 0, 18),
                                                   ("Open WebUI", 6, 0, 6)]:
        raise ValueError("Prospective transfer counts changed")
    fig, axes = plt.subplots(1, 2, figsize=(S.TEXT_WIDTH, 1.45), sharey=True,
                             gridspec_kw=dict(wspace=0.08))
    for ax, (title, ai, ui) in zip(axes, (("(a) Frozen transfer", 2, 3),
                                          ("(b) After adaptation", 4, 5))):
        for k, d in enumerate(data):
            y = len(data) - 1 - k
            ax.barh(y, d[ai], color=S.BLUE, height=0.55, edgecolor="white", lw=0.6)
            ax.barh(y, d[ui], left=d[ai], color="white", height=0.55, edgecolor=S.GRAY,
                    hatch="////", lw=0.6)
            if d[ai]:
                ax.text(d[ai] / 2, y, str(d[ai]), ha="center", va="center", color="white", fontsize=7.5)
            if d[ui]:
                ax.text(d[ai] + d[ui] / 2, y, str(d[ui]), ha="center", va="center", fontsize=7.5,
                        bbox=dict(boxstyle="square,pad=0.15", fc="white", ec="none"))
        ax.set_xlim(0, 56); ax.set_xticks([0, 18, 36, 54])
        ax.grid(axis="y", visible=False); ax.tick_params(axis="y", length=0)
        ax.set_xlabel("Contexts"); S.panel_title(ax, title)
    axes[0].set_yticks(range(len(data))); axes[0].set_yticklabels([d[0] for d in data][::-1])
    axes[1].legend(handles=[Patch(fc=S.BLUE, label="Agreement"),
                            Patch(fc="white", ec=S.GRAY, hatch="////", label="Unknown")],
                   loc="lower right", fontsize=7)
    S.save(fig, out / "evaluation-design.pdf"); plt.close(fig)


def adaptation(art, out):
    records = json.loads((art / "adaptation_study/casebook.json").read_text())["cases"]
    axes_ = ("identity origin", "post-authorization effects", "identity/state handoff",
             "runtime resolution", "environment and time")
    handling = (("automatic supported source analysis", "Source analysis", S.BLUE, None),
                ("explicit configuration/input", "Supplied input", S.SKY, None),
                ("source-bound primitive adapter", "Primitive adapter", S.ORANGE, None),
                ("non-admission", "Not admitted", "white", "////"))
    matrix = [[Counter(r["axis_classification"][a]["handling"] for r in records)[h[0]]
               for h in handling] for a in axes_]
    if len(records) != 8 or matrix != [[0, 5, 3, 0], [0, 0, 5, 3], [1, 0, 7, 0], [2, 1, 4, 1], [0, 2, 3, 3]]:
        raise ValueError("Adaptation casebook changed")
    fig, ax = plt.subplots(figsize=(S.TEXT_WIDTH, 1.9))
    for i, (name, row) in enumerate(zip(axes_, matrix)):
        y = len(axes_) - 1 - i; left = 0
        for (key, lab, col, hatch), c in zip(handling, row):
            if c:
                ax.barh(y, c, left=left, color=col, hatch=hatch, height=0.6,
                        edgecolor=S.GRAY if hatch else "white", lw=0.6)
                ax.text(left + c / 2, y, str(c), ha="center", va="center", fontsize=7.5,
                        color="white" if col == S.BLUE else S.INK,
                        bbox=dict(boxstyle="square,pad=0.12", fc="white", ec="none") if hatch else None)
                left += c
    ax.set_yticks(range(len(axes_))); ax.set_yticklabels([a[0].upper() + a[1:] for a in axes_][::-1])
    ax.set_xlim(0, 8); ax.set_xlabel("Adaptation cases (of 8)")
    ax.grid(axis="y", visible=False); ax.tick_params(axis="y", length=0)
    ax.legend(handles=[Patch(fc=c, ec=S.GRAY if h else "none", hatch=h, label=l) for _, l, c, h in handling],
              loc="lower center", bbox_to_anchor=(0.45, 1.0), ncol=4, fontsize=7)
    S.save(fig, out / "adaptation-handling.pdf"); plt.close(fig)


def credential_costs(art, out):
    data = load_study(art, "credential-cost.json.gz")
    obs, tot = data["measurements"], data["totals"]
    names = (("target_distance", "Target distance"), ("complete_product", "Complete product"),
             ("decision_diagram", "Decision diagram"), ("ordinary_BFS", "Ordinary BFS"))
    if not all(r["complete_outputs_equal"] for r in obs) or len(obs) != 5:
        raise ValueError("Credential cost study changed")
    vals = {k: 1000 * median(r["seconds"][k] for r in obs) for k, _ in names}
    if [round(v, 2) for v in vals.values()] != [10.84, 36.06, 14.67, 43.93]:
        raise ValueError("Credential cost medians changed")
    order = sorted(names, key=lambda kv: vals[kv[0]])
    fig, ax = plt.subplots(figsize=(S.TEXT_WIDTH, 1.6))
    for i, (k, lab) in enumerate(order):
        y = len(order) - 1 - i
        runs = sorted(1000 * r["seconds"][k] for r in obs)
        ax.plot([runs[0], runs[-1]], [y, y], color=S.GRAY, lw=0.9)
        ax.plot(runs, [y + 0.18] * len(runs), "o", mfc="white", mec=S.BLUE, ms=3.2, mew=0.8)
        ax.plot(vals[k], y, "D", color=S.ORANGE, ms=4.2)
        ax.text(52.5, y, f"{vals[k]:.2f}", va="center", ha="right", fontsize=7.5)
    ax.set_yticks(range(len(order))); ax.set_yticklabels([l for _, l in order][::-1])
    ax.set_xlim(0, 53); ax.set_ylim(-0.5, len(order) - 0.3)
    ax.grid(axis="y", visible=False); ax.tick_params(axis="y", length=0)
    ax.set_xlabel("Family-analysis time (ms)")
    ax.legend(handles=[Line2D([], [], marker="o", mfc="white", mec=S.BLUE, ls="none", ms=3.2, label="Run"),
                       Line2D([], [], marker="D", color=S.ORANGE, ls="none", ms=4.2, label="Median"),
                       Line2D([], [], color=S.GRAY, lw=0.9, label="Range")],
              loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3, fontsize=7)
    S.save(fig, out / "credential-algorithm-cost.pdf"); plt.close(fig)


def width(art, out):
    with (art / "results/width.csv").open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    ns = [int(r["aliases"]) for r in rows]
    if ns != list(range(1, 17)):
        raise ValueError("Width study changed")
    local = [int(r["local_binding_evaluations"]) for r in rows]
    executed = [(n, int(r["global_evaluations"])) for n, r in zip(ns, rows)
                if r["global_oracle_executed"] == "True"]
    derived = [(n, int(r["global_complete_work_bound"])) for n, r in zip(ns, rows) if n >= 8]
    if any(l != 4 * n for n, l in zip(ns, local)) or [n for n, _ in executed] != list(range(1, 9)):
        raise ValueError("Width study values changed")
    fig, ax = plt.subplots(figsize=(S.TEXT_WIDTH * 0.62, 1.95))
    ax.plot(ns, local, marker="o", mfc="white", mec=S.BLUE, color=S.BLUE, ms=3.4, label="Local (executed)")
    ax.plot(*zip(*executed), marker="s", color=S.VERMILLION, ms=3.2, label="Global (executed)")
    ax.plot(*zip(*derived), color=S.VERMILLION, ls=(0, (4, 2)), lw=1.0, label="Global (derived bound)")
    ax.axvline(8, color=S.GRAY, lw=0.6, ls=(0, (1, 2)))
    ax.set_yscale("log"); ax.set_ylim(2, 5e6)
    ax.yaxis.set_major_locator(LogLocator(base=10, numticks=8))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: {1e3: "1k", 1e4: "10k", 1e5: "100k", 1e6: "1M"}.get(v, f"{v:g}")))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xticks([1, 4, 8, 12, 16]); ax.set_xlim(0.5, 16.5)
    ax.set_xlabel("Declared aliases"); ax.set_ylabel("Reference evaluations")
    ax.legend(loc="upper left", fontsize=7)
    S.save(fig, out / "width.pdf"); plt.close(fig)


def screening(art, out):
    with gzip.open(art / "adaptation_study/survey.json.gz", "rt", encoding="utf-8") as fh:
        survey = json.load(fh)
    keys = (("identity_input", "Identity input"), ("credential_processing", "Credential processing"),
            ("identity_handoff", "Identity handoff"), ("mutation_call", "Named mutation call"),
            ("dynamic_lookup", "Dynamic lookup"), ("asynchronous_flow", "Asynchronous flow"))
    counts = [survey["counts"][k] for k, _ in keys]
    if survey["denominator"] != 48 or counts != [17, 25, 10, 42, 24, 22]:
        raise ValueError("Screening counts changed")
    ordered = sorted(zip([l for _, l in keys], counts), key=lambda kv: -kv[1])
    fig, ax = plt.subplots(figsize=(S.TEXT_WIDTH * 0.62, 1.75))
    for i, (lab, c) in enumerate(ordered):
        y = len(ordered) - 1 - i
        ax.barh(y, c, color=S.BLUE, height=0.6)
        ax.text(c + 0.8, y, str(c), va="center", fontsize=7.5)
    ax.set_yticks(range(len(ordered))); ax.set_yticklabels([l for l, _ in ordered][::-1])
    ax.set_xlim(0, 48); ax.set_xticks([0, 12, 24, 36, 48])
    ax.grid(axis="y", visible=False); ax.tick_params(axis="y", length=0)
    ax.set_xlabel("Snapshots with the feature (of 48)")
    S.save(fig, out / "source-screening.pdf"); plt.close(fig)


def frontend(art, out):
    data = load_study(art, "frontend-cost.json.gz")
    rows = data["rows"]
    tot = {m: [sum(r["methods"][m]["outer_startup_through_exit_wall_ns"] for r in rows if r["repeat"] == i) / 1e9
               for i in range(3)] for m in ("baseline", "guarded")}
    diffs = [b - a for a, b in zip(tot["baseline"], tot["guarded"])]
    if len(rows) != 144 or [round(d, 2) for d in diffs] != [14.61, 14.85, 15.42]:
        raise ValueError("Front-end batch costs changed")
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(S.TEXT_WIDTH, 1.45), sharey=True,
                                 gridspec_kw=dict(width_ratios=[1.6, 1], wspace=0.1))
    for i in range(3):
        y = 2 - i
        ax.plot([tot["baseline"][i], tot["guarded"][i]], [y, y], color=S.GRAY, lw=0.9)
        ax.plot(tot["baseline"][i], y, "o", mfc="white", mec=S.BLUE, ms=4, mew=0.9,
                label="Baseline" if i == 0 else None)
        ax.plot(tot["guarded"][i], y, "s", color=S.VERMILLION, ms=3.8, label="Guarded" if i == 0 else None)
        bx.barh(y, diffs[i], color=S.ORANGE, height=0.45)
        bx.text(diffs[i] + 0.3, y, f"{diffs[i]:.2f}", va="center", fontsize=7.5)
    ax.set_yticks([2, 1, 0]); ax.set_yticklabels(["Batch 1", "Batch 2", "Batch 3"])
    ax.set_xlim(0, 45); ax.set_xticks([0, 15, 30, 45]); ax.set_xlabel("Whole-batch wall time (s)")
    ax.grid(axis="y", visible=False); ax.tick_params(axis="y", length=0); ax.set_ylim(-0.5, 2.5)
    ax.legend(loc="center left", fontsize=7, ncol=1)
    S.panel_title(ax, "(a) Total wall time")
    bx.set_xlim(0, 19); bx.set_xticks([0, 5, 10, 15]); bx.set_xlabel("Guarded minus baseline (s)")
    bx.grid(axis="y", visible=False); bx.tick_params(axis="y", length=0)
    S.panel_title(bx, "(b) Paired difference")
    S.save(fig, out / "frontend-batch-cost.pdf"); plt.close(fig)


def default_artifact():
    """The artifact root: this script runs from artifact/figures/ or paper/figure-source/."""
    if (HERE.parent / "results").is_dir():
        return HERE.parent
    return HERE.parent.parent / "artifact"


def default_output():
    """Only the manuscript copy has a default destination (paper/figures/)."""
    if (HERE.parent / "main.tex").is_file():
        return HERE.parent / "figures"
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifact", type=Path, default=default_artifact())
    ap.add_argument("--output", "--output-directory", dest="output", type=Path, default=default_output())
    ap.add_argument("--table-output", type=Path, default=None,
                    help="destination of family-cost-rows.tex (default: next to the output directory)")
    ap.add_argument("--receipt", type=Path, default=None,
                    help="optional JSON record of the figure set, digests and font provenance")
    args = ap.parse_args()
    if args.output is None:
        ap.error("--output-directory is required outside the manuscript tree")
    S.apply()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.table_output is not None:
        TABLE_OUTPUT["path"] = args.table_output
    rows = load_comparison(args.artifact)
    family_cost(args.artifact, rows, args.output)
    session_correspondence(args.artifact, rows, args.output)
    symbolic_comparison(args.artifact, rows, args.output)
    for f in (validation_profiles, source_controls, session_certification, width, source_coverage,
              transfer, adaptation, credential_costs, screening, frontend):
        f(args.artifact, args.output)
    written = sorted(p.name for p in args.output.glob("*.pdf"))
    if written != sorted(FIGURES):
        raise ValueError("Unexpected figure set: " + ", ".join(written))
    if args.receipt is not None:
        args.receipt.write_text(json.dumps({
            "figures": {name: hashlib.sha256((args.output / name).read_bytes()).hexdigest()
                        for name in written},
            "font": S.font_status(),
            "matplotlib": matplotlib.__version__,
        }, indent=2, sort_keys=True) + "\n")
    print(f"PASS: {len(written)} statistical figures written to {args.output} "
          f"(text face: {S.font_status()['status']})")


if __name__ == "__main__":
    main()
