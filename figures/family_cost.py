#!/usr/bin/env python3
"""Render complete-family cost evidence from retained seven-run trials."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from reportlab.lib.colors import white
from reportlab.pdfgen.canvas import Canvas

from figure_typography import register_fonts, WIDTH, INK, ACCENT, SECONDARY, GRID, GUIDE
from draw_evaluation import text, line, dot, square, diamond
from symbolic_comparison import load_checked

ART = Path(__file__).resolve().parents[1]


def triangle(c, x, y, r=3.0, *, filled=False, color=INK):
    c.setStrokeColor(color); c.setFillColor(color if filled else white); c.setLineWidth(.8)
    p=c.beginPath(); p.moveTo(x,y+r); p.lineTo(x+r*.9,y-r*.75); p.lineTo(x-r*.9,y-r*.75); p.close()
    c.drawPath(p,stroke=1,fill=1)


def cross(c, x, y, r=3.0, *, color=ACCENT):
    c.setStrokeColor(color); c.setLineWidth(1.0)
    c.line(x-r,y-r,x+r,y+r); c.line(x-r,y+r,x+r,y-r)


def draw(results: Path, output: Path, table_output=None):
    report, all_rows = load_checked(results)
    rows = {r["case"]: r for r in report["records"] if r["cohort"] == "family-cost"}
    plotted=[]
    for key,row in rows.items():
        product=row["methods"]["per-binding-product"]
        grouped=row["methods"]["support-indexed"]
        p_times=product["diagnosis_wall_ns"]["samples"]
        g_times=grouped["diagnosis_wall_ns"]["samples"]
        regime={"all-match":"match","late-failure":"late","early-failure":"early",
                "dense-support":"dense","singleton":"dense"}.get(row["regime"],"source")
        plotted.append({
            "id":key,
            "call_ratio":product["diagnostic_reference_calls"] / grouped["diagnostic_reference_calls"],
            "time_ratio_of_medians":product["diagnosis_wall_ns"]["median"] / grouped["diagnosis_wall_ns"]["median"],
            "group":regime,
            "observed_timing_envelope":{"low":min(p_times)/max(g_times),
                                        "high":max(p_times)/min(g_times)},
            "diagnosis_wall_ns":{"per-binding-product":p_times,"support-indexed":g_times},
        })
    if len(plotted)!=38:
        raise ValueError("Expected exactly 38 family-cost tasks")

    x_low=.8; x_high=320
    y_low=10**math.floor(math.log10(min(p["observed_timing_envelope"]["low"] for p in plotted)))
    y_high=10**math.ceil(math.log10(max(p["observed_timing_envelope"]["high"] for p in plotted)))
    output.mkdir(parents=True,exist_ok=True)
    c=Canvas(str(output/"family-diagnosis-cost.pdf"),pagesize=(WIDTH,480),
             invariant=True,initialFontName="Body")
    c.setTitle("Complete-family cost comparison"); c.setCreator("")
    c.chart_height=480;c.chart_labels=[]

    # (a) All tasks on one common coordinate system.  Shape encodes regime;
    # color is redundant and therefore safe in grayscale.
    left,right,bottom,top=55,382,280,438
    lx=lambda v:left+math.log(v/x_low)/math.log(x_high/x_low)*(right-left)
    ly=lambda v:bottom+math.log(v/y_low)/math.log(y_high/y_low)*(top-bottom)
    text(c,14,467,"(a) All 38 tasks",font="Bold",size=10.5,align="left")
    legend=(("match","all",64),("late","late",132),
            ("early","early",200),("dense","dense",276))
    def marker(group,x,y,r=2.9):
        if group=="match": dot(c,x,y,r,open_marker=True,color=INK)
        elif group=="late": diamond(c,x,y,r,color=ACCENT)
        elif group=="early": square(c,x,y,r*.72,INK)
        elif group=="dense": triangle(c,x,y,r,filled=False,color=SECONDARY)
        else: cross(c,x,y,r,color=ACCENT)
    for group,label,x in legend:
        marker(group,x,448,2.7); text(c,x+8,444.7,label,"left",size=8.4)
    cross(c,344,448,2.7,color=ACCENT); text(c,352,444.7,"source", "left", size=8.4)

    for tick in (1,10,100):
        xx=lx(tick); line(c,xx,bottom,xx,top,GRID,.6); text(c,xx,bottom-15,str(tick),size=9)
    for exp in range(int(math.log10(y_low)),int(math.log10(y_high))+1):
        val=10**exp; yy=ly(val); line(c,left,yy,right,yy,GRID,.6)
        text(c,left-7,yy-3.1,f"{val:g}","right",size=9)
    line(c,left,bottom,right,bottom,INK,.7); line(c,left,bottom,left,top,INK,.7)
    c.setDash(2,2); line(c,lx(1),bottom,lx(1),top,GUIDE,.8); line(c,left,ly(1),right,ly(1),GUIDE,.8); c.setDash()
    for p in plotted:
        xx=lx(p["call_ratio"]); lo=ly(p["observed_timing_envelope"]["low"]); hi=ly(p["observed_timing_envelope"]["high"])
        line(c,xx,lo,xx,hi,GUIDE,.55)
        marker(p["group"],xx,ly(p["time_ratio_of_medians"]),2.7)
    text(c,(left+right)/2,bottom-34,"Reference-call ratio (product / indexed, log)",size=9.3)
    c.saveState();c.translate(16,(bottom+top)/2);c.rotate(90);c.setFont("Body",9.3);c.setFillColor(INK);c.drawCentredString(0,0,"Diagnosis-time ratio (product / indexed, log)");c.restoreState()

    # (b) Edge cases and source controls, with exact labels and seven-run
    # envelopes.  This panel replaces three dense mini-panels.
    text(c,14,222,"(b) Dense, singleton, and source cases",font="Bold",size=10.5,align="left")
    detail=[
        ("dense-s2-f2","2 states, 2 bindings"),("dense-s2-f16","2 states, 16 bindings"),
        ("dense-s2-f256","2 states, 256 bindings"),("dense-s8-f2","8 states, 2 bindings"),
        ("dense-s8-f16","8 states, 16 bindings"),("dense-s8-f256","8 states, 256 bindings"),
        ("singleton-s32-f1","32 states, 1 binding"),
        ("healthchecks-resume-plain","Healthchecks, plain"),
        ("healthchecks-resume-stored_mac","Healthchecks, MAC"),
        ("piccolo-session-baseline","Piccolo sessions"),
        ("piccolo-session-omit_delete","Omitted-delete control"),
    ]
    lookup={p["id"]:p for p in plotted}
    if any(key not in lookup for key,_ in detail):
        missing=[key for key,_ in detail if key not in lookup]
        raise ValueError("Missing named family-cost cases: "+str(missing))
    fleft,fright=188,342
    flow=min(.01,min(lookup[k]["observed_timing_envelope"]["low"] for k,_ in detail))
    fhigh=max(100,max(lookup[k]["observed_timing_envelope"]["high"] for k,_ in detail))
    fx=lambda v:fleft+math.log(v/flow)/math.log(fhigh/flow)*(fright-fleft)
    ys=[190-i*15.5 for i in range(len(detail))]
    for exp in range(int(math.floor(math.log10(flow))),int(math.ceil(math.log10(fhigh)))+1):
        val=10**exp; xx=fx(val); line(c,xx,20,xx,196,GRID,.55)
        text(c,xx,6,f"{val:g}",size=8.6)
    c.setDash(2,2);line(c,fx(1),20,fx(1),196,SECONDARY,.8);c.setDash()
    line(c,fleft,20,fright,20,INK,.7)
    text(c,386,222,"median",font="Bold",size=9.3,align="right")
    for (key,label),yy in zip(detail,ys):
        p=lookup[key]; bounds=p["observed_timing_envelope"]; med=p["time_ratio_of_medians"]
        text(c,178,yy-3.1,label,"right",size=8.8)
        lo,hi=fx(bounds["low"]),fx(bounds["high"])
        line(c,lo,yy,hi,yy,SECONDARY,.9)
        line(c,lo,yy-2.3,lo,yy+2.3,SECONDARY,.7);line(c,hi,yy-2.3,hi,yy+2.3,SECONDARY,.7)
        diamond(c,fx(med),yy,2.5,INK)
        text(c,386,yy-3.1,f"{med:.2f}","right",font="Bold",size=9.0)
    text(c,(fleft+fright)/2,210,"Diagnosis-time ratio (log)",size=8.8)
    c.showPage();c.save()

    selected=[("family-cost/control-s32-f256-all-match","All match (32, 256)"),
              ("family-cost/control-s32-f256-late-failure","Late failure (32, 256)"),
              ("family-cost/dense-s8-f256","Dense support (8, 256)"),
              ("family-cost/singleton-s32-f1","Singleton (32, 1)"),
              ("session-correspondence/sessions-6-baseline/total","Sessions (64, 720)"),
              ("native-policy-store/repaired-initial-0/total","Policy file (16, 6)")]
    lines=["% Generated from raw matched trials by artifact/figures/family_cost.py."]
    order=("per-binding-product","per-binding-target","scan","support-indexed","finite-domain","cudd")
    for key,label in selected:
        values=[all_rows[key]["methods"][m]["diagnosis_wall_ns"]["median"]/1e6 for m in order]
        lines.append(label+" & "+" & ".join(f"{v:,.3f}" for v in values)+r"\\")
    lines.append(r"\bottomrule")
    table_output=Path(table_output) if table_output is not None else output/"family-cost-rows.tex"
    table_output.parent.mkdir(parents=True,exist_ok=True);table_output.write_text("\n".join(lines)+"\n")
    record={"input_summary_sha256":hashlib.sha256((results/"summary.json").read_bytes()).hexdigest(),
            "input_trials_sha256":hashlib.sha256((results/"trials.json").read_bytes()).hexdigest(),
            "timing_envelope_definition":"[min(product) / max(indexed), max(product) / min(indexed)] over seven observed runs; not a confidence interval",
            "raw_timing_samples_verified":True,"points":plotted,"selected_rows":[k for k,_ in selected],
            "layout":"all-task scatter plus named edge/source intervals"}
    (output/"family-diagnosis-cost.json").write_text(json.dumps(record,indent=2)+"\n")
    return record


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--table-output",type=Path)
    args=parser.parse_args();register_fonts();result=draw(args.results,args.output,args.table_output)
    print(json.dumps({"points":len(result["points"]),"status":"PASS"}))
